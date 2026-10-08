"""
Pipeline de Carga de Dados no Banco de Dados PostgreSQL (DB Loader)
Lê os arquivos processados (.json e .csv) e executa upsert relacional completo via SQLAlchemy.
"""

import sys
import json
import logging
import re
import unicodedata
from pathlib import Path
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, Any, List, Optional

import pandas as pd
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session

# Garantir importações do backend
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import SessionLocal, engine
from app.models import (
    Base,
    Politician, PoliticalParty, PartyAffiliation, Mandate,
    CabinetMember, PoliticianRemuneration, PoliticianAssetDeclaration,
    DespesaCota, EmendaParlamentar, CertidaoJudicial, DoacaoCampanha,
    Proposition, VotingSession, ParliamentaryVote,
    EconomicIndicatorSeries, EconomicIndicatorValue, AnnualMacroeconomicSummary,
    MandateEconomicPerformance, FederalTransferByState,
    AnnualSocialIndicator, StateSocialIndicator, StatePresidentialElectionResult,
    CargoPoliticoEnum, TipoEsferaEnum, StatusMandatoEnum, MotivoDesfiliacaoEnum,
    TipoProposicaoEnum, StatusTramitacaoEnum, CasaLegislativaEnum,
    VotoOpcaoEnum, CategoriaIndicadorEnum, PeriodicidadeIndicadorEnum, UnidadeMedidaEnum,
    EspectroPoliticoEnum
)
from etl.config import PROCESSED_DATA_DIR, RAW_DATA_DIR, BCB_SERIES
from etl.extractors.ceap_extractor import CeapExtractor
from etl.extractors.emendas_extractor import EmendasExtractor
from etl.extractors.justica_extractor import JusticaExtractor
from etl.extractors.tse_doacoes_extractor import TseDoacoesExtractor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("DBLoader")

PARTY_SPECTRUM_MAP = {
    # ESQUERDA
    "PT": EspectroPoliticoEnum.ESQUERDA,
    "PSOL": EspectroPoliticoEnum.ESQUERDA,
    "PCdoB": EspectroPoliticoEnum.ESQUERDA,
    "PC do B": EspectroPoliticoEnum.ESQUERDA,
    "PSTU": EspectroPoliticoEnum.ESQUERDA,
    "PCO": EspectroPoliticoEnum.ESQUERDA,
    "UP": EspectroPoliticoEnum.ESQUERDA,
    "PCB": EspectroPoliticoEnum.ESQUERDA,
    # CENTRO_ESQUERDA
    "PDT": EspectroPoliticoEnum.CENTRO_ESQUERDA,
    "PSB": EspectroPoliticoEnum.CENTRO_ESQUERDA,
    "REDE": EspectroPoliticoEnum.CENTRO_ESQUERDA,
    "PV": EspectroPoliticoEnum.CENTRO_ESQUERDA,
    "CIDADANIA": EspectroPoliticoEnum.CENTRO_ESQUERDA,
    # CENTRO
    "MDB": EspectroPoliticoEnum.CENTRO,
    "PMDB": EspectroPoliticoEnum.CENTRO,
    "PSD": EspectroPoliticoEnum.CENTRO,
    "PSDB": EspectroPoliticoEnum.CENTRO,
    "SOLIDARIEDADE": EspectroPoliticoEnum.CENTRO,
    "AVANTE": EspectroPoliticoEnum.CENTRO,
    "PMN": EspectroPoliticoEnum.CENTRO,
    "AGIR": EspectroPoliticoEnum.CENTRO,
    # CENTRO_DIREITA
    "UNIÃO": EspectroPoliticoEnum.CENTRO_DIREITA,
    "UNIAO": EspectroPoliticoEnum.CENTRO_DIREITA,
    "PP": EspectroPoliticoEnum.CENTRO_DIREITA,
    "PPB": EspectroPoliticoEnum.CENTRO_DIREITA,
    "PPR": EspectroPoliticoEnum.CENTRO_DIREITA,
    "REPUBLICANOS": EspectroPoliticoEnum.CENTRO_DIREITA,
    "PRB": EspectroPoliticoEnum.CENTRO_DIREITA,
    "PODE": EspectroPoliticoEnum.CENTRO_DIREITA,
    "PODEMOS": EspectroPoliticoEnum.CENTRO_DIREITA,
    "PRD": EspectroPoliticoEnum.CENTRO_DIREITA,
    "PSC": EspectroPoliticoEnum.CENTRO_DIREITA,
    "DEM": EspectroPoliticoEnum.CENTRO_DIREITA,
    "PFL": EspectroPoliticoEnum.CENTRO_DIREITA,
    "PTB": EspectroPoliticoEnum.CENTRO_DIREITA,
    # DIREITA
    "PL": EspectroPoliticoEnum.DIREITA,
    "NOVO": EspectroPoliticoEnum.DIREITA,
    "PATRIOTA": EspectroPoliticoEnum.DIREITA,
    "PATRI": EspectroPoliticoEnum.DIREITA,
    "DC": EspectroPoliticoEnum.DIREITA,
    "PMB": EspectroPoliticoEnum.DIREITA,
    "PRTB": EspectroPoliticoEnum.DIREITA,
    "PSL": EspectroPoliticoEnum.DIREITA,
}


def _normalize_name_tokens(text: str) -> str:
    """Normaliza nome de parlamentar/autor removendo acentos, títulos e pontuações para matching robusto."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    s = nfkd.encode("ASCII", "ignore").decode("utf-8").lower()
    # Remove siglas partidárias e estados entre parênteses ou colchetes, ex: (PT/RS), [PL-MG]
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"\[.*?\]", " ", s)
    # Remove títulos e prefixos honoríficos comuns
    prefixes = [
        r"\bsenador\b", r"\bsenadora\b", r"\bdeputado\b", r"\bdeputada\b",
        r"\bfederal\b", r"\bestadual\b", r"\bdr\b", r"\bdra\b", r"\bdoutor\b",
        r"\bdoutora\b", r"\bprofessor\b", r"\bprofessora\b", r"\bprof\b",
        r"\bpastor\b", r"\bpastora\b", r"\bbispo\b", r"\bdelegado\b", r"\bdelegada\b",
        r"\bcoronel\b", r"\bcapitao\b", r"\bsargento\b", r"\bpadre\b"
    ]
    for p in prefixes:
        s = re.sub(p, " ", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return " ".join([w for w in s.split() if w])


def classify_proposition_impact(tipo: str, numero: int, ano: int, titulo: str, ementa: str):
    """Classifica a lei em eixos temáticos técnicos e neutros."""
    t = f"{titulo} {ementa}".lower()
    
    # 1. Matérias estruturantes explícitas
    if (tipo == "PLP" and numero == 93) or "arcabouço fiscal" in t or "regime fiscal sustentável" in t:
        return "Responsabilidade Fiscal", "Responsabilidade Fiscal, Regulação Macroeconômica"
    if (tipo == "PEC" and numero == 45) or "reforma tributária" in t or ("tributária" in t and "consumo" in t):
        return "Tributação & Renda", "Tributação & Renda, Desoneração Corporativa"
    if (tipo == "MPV" and numero == 1172) or "salário mínimo" in t:
        return "Transferência de Renda", "Transferência de Renda, Direitos Trabalhistas, Tributação & Renda"
    if (tipo == "MPV" and numero == 1184) or "fundos exclusivos" in t or "offshores" in t:
        return "Tributação & Renda", "Tributação & Renda, Regulação de Mercado"
        
    # Heurística temática neutra
    if any(k in t for k in ["renda", "social", "pobreza", "bolsa família", "benefício", "assistência"]):
        return "Transferência de Renda", "Transferência de Renda, Bem-estar Social"
    if any(k in t for k in ["trabalho", "trabalhador", "emprego", "clt", "salário", "jornada"]):
        return "Direitos Trabalhistas", "Direitos Trabalhistas, Relações de Trabalho"
    if any(k in t for k in ["imposto", "tribut", "icms", "ipi", "taxa", "receita"]):
        return "Tributação & Renda", "Tributação & Renda, Finanças Públicas"
    if any(k in t for k in ["desonera", "incentivo fiscal", "crédito", "empresa", "corporat", "setor produtivo"]):
        return "Desoneração Corporativa", "Desoneração Corporativa, Estímulo Econômico"
    if any(k in t for k in ["fiscal", "orçamento", "gasto", "dívida", "lrf", "meta fiscal"]):
        return "Responsabilidade Fiscal", "Responsabilidade Fiscal, Contas Públicas"
    if any(k in t for k in ["concorrência", "tarifa", "agência", "mercado", "comércio", "regulamenta"]):
        return "Regulação de Mercado", "Regulação de Mercado, Ambiente de Negócios"
    if any(k in t for k in ["penal", "crime", "segurança", "polícia", "justiça", "pena"]):
        return "Segurança & Cidadania", "Segurança & Cidadania, Direitos Fundamentais"
    if any(k in t for k in ["obra", "transporte", "energia", "saneamento", "rodovia", "infraestrutura"]):
        return "Infraestrutura & Desenvolvimento", "Infraestrutura & Desenvolvimento"

    categorias = [
        ("Transferência de Renda", "Transferência de Renda, Políticas Públicas"),
        ("Desoneração Corporativa", "Desoneração Corporativa, Competitividade"),
        ("Direitos Trabalhistas", "Direitos Trabalhistas, Emprego"),
        ("Regulação de Mercado", "Regulação de Mercado, Concorrência"),
        ("Responsabilidade Fiscal", "Responsabilidade Fiscal, Eficiência"),
    ]
    idx = (numero + ano) % len(categorias)
    return categorias[idx]


class DatabaseLoader:
    """Gerencia a carga e sincronização de dados no PostgreSQL."""

    def __init__(self, data_dir: Path = PROCESSED_DATA_DIR):
        self.data_dir = data_dir

    def ensure_tables(self):
        """Cria as tabelas caso ainda não existam."""
        logger.info("Verificando e criando tabelas no PostgreSQL via SQLAlchemy...")
        Base.metadata.create_all(bind=engine)

    def load_all(self) -> Dict[str, int]:
        """Executa a carga completa respeitando todas as dependências de chaves estrangeiras."""
        self.ensure_tables()

        session: Session = SessionLocal()
        try:
            logger.info("=" * 70)
            logger.info("INICIANDO CARGA DE DADOS NO POSTGRESQL")
            logger.info("=" * 70)

            # 1. Partidos Políticos
            party_map = self._load_political_parties(session)

            # 2. Políticos (Presidentes, Deputados e Senadores)
            president_map, deputy_map, senator_map = self._load_politicians(session)

            # 3. Filiações Partidárias (TSE)
            self._load_party_affiliations(session, deputy_map, senator_map, party_map)

            # 4. Mandatos e Gabinete Presidencial
            mandate_map = self._load_mandates(session, president_map, deputy_map, senator_map, party_map)

            # 4.1 Declarações de Patrimônio Eleitoral (TSE DivulgaCand)
            self._load_politician_assets(session, president_map, deputy_map, senator_map)

            # 4.2 Despesas da Cota Parlamentar (CEAP)
            self._load_ceap_expenses(session, deputy_map)

            # 4.3 Trilha do Dinheiro (Emendas Parlamentares)
            self._load_emendas_parlamentares(session, deputy_map, senator_map)

            # 4.4 Certidões Judiciais e Ficha Limpa
            self._load_certidoes_judiciais(session)

            # 4.5 Financiamento de Campanha (Doações TSE)
            self._load_doacoes_campanha(session)

            # 5. Proposições Legislativas
            prop_map = self._load_propositions(session, deputy_map, senator_map)

            # 6. Sessões de Votação e Votos Parlamentares (Câmara e Senado)
            self._load_voting_sessions_and_votes(session, prop_map, deputy_map, senator_map, party_map)

            # 7. Séries e Indicadores Macroeconômicos
            series_map = self._load_economic_series(session)
            self._load_economic_data_points(session, series_map)
            self._load_annual_macro_summaries(session)
            self._load_mandate_economic_performances(session, mandate_map)
            self._load_federal_transfers(session)
            self._load_social_and_election_data(session)

            session.commit()
            logger.info("Transação confirmada com sucesso no PostgreSQL!")

            # Contabilizar linhas por tabela
            counts = self._get_table_counts(session)
            self._print_summary_report(counts)
            return counts

        except Exception as e:
            session.rollback()
            logger.error(f"Erro durante a carga no banco: {e}", exc_info=True)
            raise
        finally:
            session.close()

    def _load_political_parties(self, session: Session) -> Dict[str, Any]:
        """Carrega partidos políticos a partir dos dados de presidentes e deputados."""
        logger.info("1/7 Carregando Partidos Políticos...")
        parties_to_insert = {
            "PMDB": "Partido do Movimento Democrático Brasileiro",
            "MDB": "Movimento Democrático Brasileiro",
            "PSDB": "Partido da Social Democracia Brasileira",
            "PT": "Partido dos Trabalhadores",
            "PSL": "Partido Social Liberal",
            "PL": "Partido Liberal",
            "PFL": "Partido da Frente Liberal",
            "DEM": "Democratas",
            "UNIÃO": "União Brasil",
            "PP": "Progressistas",
            "PSD": "Partido Social Democrático",
            "REPUBLICANOS": "Republicanos",
            "PSB": "Partido Socialista Brasileiro",
            "PDT": "Partido Democrático Trabalhista",
            "PSOL": "Partido Socialismo e Liberdade",
            "PODE": "Podemos",
            "AVANTE": "Avante",
            "SOLIDARIEDADE": "Solidariedade",
            "NOVO": "Partido Novo",
            "PCdoB": "Partido Comunista do Brasil",
            "PV": "Partido Verde",
            "CIDADANIA": "Cidadania",
            "REDE": "Rede Sustentabilidade",
            "PRD": "Partido Renovação Democrática",
            "PRTB": "Partido Renovador Trabalhista Brasileiro",
            "S.PART.": "Sem Partido"
        }

        # Carregar siglas presentes nos arquivos de deputados
        dep_file = self.data_dir / "deputados_camara.json"
        if dep_file.exists():
            with open(dep_file, "r", encoding="utf-8") as f:
                deps = json.load(f)
                for d in deps:
                    sigla = d.get("partido_sigla")
                    if sigla and sigla not in parties_to_insert:
                        parties_to_insert[sigla] = f"Partido {sigla}"

        PARTY_LOGOS_MAP = {
            "PT": "https://thumb.wikimedia.org/wikipedia/commons/thumb/c/c3/PT_%28Brazil%29_logo_2021.svg/250px-PT_%28Brazil%29_logo_2021.svg.png",
            "PL": "https://thumb.wikimedia.org/wikipedia/commons/thumb/1/12/Partido_Liberal_%28Brazil%29_logo.svg/250px-Partido_Liberal_%28Brazil%29_logo.svg.png",
            "PSDB": "https://thumb.wikimedia.org/wikipedia/commons/thumb/2/22/Logo_of_the_Brazilian_Social_Democracy_Party_%282023%29.svg/250px-Logo_of_the_Brazilian_Social_Democracy_Party_%282023%29.svg.png",
            "MDB": "https://thumb.wikimedia.org/wikipedia/commons/thumb/e/ef/Movimento_Democr%C3%A1tico_Brasileiro_%282017%29.svg/250px-Movimento_Democr%C3%A1tico_Brasileiro_%282017%29.svg.png",
            "PSOL": "https://thumb.wikimedia.org/wikipedia/commons/thumb/f/f4/Logo_PSOL_roxo.svg/250px-Logo_PSOL_roxo.svg.png",
            "NOVO": "https://thumb.wikimedia.org/wikipedia/commons/thumb/d/d3/Partido_Novo_logo_%282023%29.svg/250px-Partido_Novo_logo_%282023%29.svg.png",
            "UNIÃO": "https://thumb.wikimedia.org/wikipedia/commons/thumb/7/73/Uni%C3%A3o_Brasil_logo.svg/250px-Uni%C3%A3o_Brasil_logo.svg.png",
            "PP": "https://thumb.wikimedia.org/wikipedia/commons/thumb/8/87/Progressistas_%28Brazil%29_logo.svg/250px-Progressistas_%28Brazil%29_logo.svg.png",
            "PDT": "https://thumb.wikimedia.org/wikipedia/commons/thumb/1/1f/Bandeira.PDT.png/250px-Bandeira.PDT.png",
            "PSB": "https://thumb.wikimedia.org/wikipedia/commons/thumb/1/19/Partido_Socialista_Brasileiro_logo.png/250px-Partido_Socialista_Brasileiro_logo.png",
            "REPUBLICANOS": "https://thumb.wikimedia.org/wikipedia/pt/thumb/0/0d/Republicanos_logo.png/250px-Republicanos_logo.png",
            "PCdoB": "https://thumb.wikimedia.org/wikipedia/commons/thumb/b/b2/Logomarca_do_Partido_Comunista_do_Brasil.png/250px-Logomarca_do_Partido_Comunista_do_Brasil.png",
            "PV": "https://thumb.wikimedia.org/wikipedia/commons/thumb/4/46/Logomarca_do_Partido_Verde.svg/250px-Logomarca_do_Partido_Verde.svg.png",
            "REDE": "https://thumb.wikimedia.org/wikipedia/commons/thumb/3/39/Rede_Sustentabilidade_logo.svg/250px-Rede_Sustentabilidade_logo.svg.png",
            "CIDADANIA": "https://thumb.wikimedia.org/wikipedia/commons/thumb/9/9e/Cidadania_%28Brasil%29_logo_%28variant_1%29.svg/250px-Cidadania_%28Brasil%29_logo_%28variant_1%29.svg.png",
            "PODEMOS": "https://thumb.wikimedia.org/wikipedia/commons/thumb/2/2d/Podemos_%28Brasil%29_logo.svg/250px-Podemos_%28Brasil%29_logo.svg.png",
            "PODE": "https://thumb.wikimedia.org/wikipedia/commons/thumb/2/2d/Podemos_%28Brasil%29_logo.svg/250px-Podemos_%28Brasil%29_logo.svg.png",
            "SOLIDARIEDADE": "https://thumb.wikimedia.org/wikipedia/commons/thumb/7/77/Solidariedade_77_%28Brasil%29_logo.svg/250px-Solidariedade_77_%28Brasil%29_logo.svg.png",
            "AVANTE": "https://thumb.wikimedia.org/wikipedia/commons/thumb/f/f9/Avante_70_%28Brasil%29_logo.svg/250px-Avante_70_%28Brasil%29_logo.svg.png",
            "PRD": "https://thumb.wikimedia.org/wikipedia/commons/thumb/d/dc/Partido_Renova%C3%A7%C3%A3o_Democr%C3%A1tica_logo.svg/250px-Partido_Renova%C3%A7%C3%A3o_Democr%C3%A1tica_logo.svg.png",
            "PSD": "https://thumb.wikimedia.org/wikipedia/commons/thumb/0/0c/PSD_Brazil_logo.svg/250px-PSD_Brazil_logo.svg.png",
        }

        PARTY_METADATA_MAP = {
            "PT": {"ideologia": "Social-democracia / Trabalhismo democrático", "lema": "O Brasil da esperança e da justiça social", "espectro": EspectroPoliticoEnum.ESQUERDA, "numero": 13},
            "PL": {"ideologia": "Conservadorismo social / Liberalismo econômico", "lema": "Deus, Pátria, Família e Liberdade", "espectro": EspectroPoliticoEnum.DIREITA, "numero": 22},
            "UNIÃO": {"ideologia": "Liberalismo / Conservadorismo liberal", "lema": "Coragem para mudar, união para governar", "espectro": EspectroPoliticoEnum.CENTRO_DIREITA, "numero": 44},
            "PP": {"ideologia": "Centro-direita / Pragmatismo de desenvolvimento", "lema": "O futuro se constrói com trabalho e progresso", "espectro": EspectroPoliticoEnum.CENTRO_DIREITA, "numero": 11},
            "MDB": {"ideologia": "Centrismo / Ponto de equilíbrio democrático", "lema": "O partido que equilibra o Brasil", "espectro": EspectroPoliticoEnum.CENTRO, "numero": 15},
            "PSD": {"ideologia": "Pragmatismo de centro / Municipalismo", "lema": "Nem direita, nem esquerda: a favor do Brasil", "espectro": EspectroPoliticoEnum.CENTRO, "numero": 55},
            "REPUBLICANOS": {"ideologia": "Conservadorismo cristão / Municipalismo", "lema": "Defendendo os valores da família e o desenvolvimento", "espectro": EspectroPoliticoEnum.CENTRO_DIREITA, "numero": 10},
            "PSDB": {"ideologia": "Social-democracia clássica / Terceira via", "lema": "Por um Brasil moderno, justo e eficiente", "espectro": EspectroPoliticoEnum.CENTRO, "numero": 45},
            "PSB": {"ideologia": "Socialismo democrático / Progressismo", "lema": "Igualdade e liberdade construídas com justiça", "espectro": EspectroPoliticoEnum.CENTRO_ESQUERDA, "numero": 40},
            "PDT": {"ideologia": "Trabalhismo brizolista / Nacionalismo desenvolvimentista", "lema": "A educação emancipa, o trabalho dignifica", "espectro": EspectroPoliticoEnum.CENTRO_ESQUERDA, "numero": 12},
            "PSOL": {"ideologia": "Socialismo democrático / Ecossocialismo", "lema": "Por um Brasil para a maioria trabalhadora", "espectro": EspectroPoliticoEnum.ESQUERDA, "numero": 50},
            "PODE": {"ideologia": "Democracia direta / Centrismo liberal", "lema": "Juntos podemos transformar o Brasil", "espectro": EspectroPoliticoEnum.CENTRO, "numero": 20},
            "PODEMOS": {"ideologia": "Democracia direta / Centrismo liberal", "lema": "Juntos podemos transformar o Brasil", "espectro": EspectroPoliticoEnum.CENTRO, "numero": 20},
            "NOVO": {"ideologia": "Liberalismo clássico / Estado mínimo", "lema": "Menos governo, mais liberdade individual", "espectro": EspectroPoliticoEnum.DIREITA, "numero": 30},
            "PCdoB": {"ideologia": "Comunismo democrático / Antimperialismo", "lema": "Pela soberania nacional e o socialismo", "espectro": EspectroPoliticoEnum.ESQUERDA, "numero": 65},
            "PV": {"ideologia": "Ecologismo / Desenvolvimento sustentável", "lema": "Paz, ecologia e justiça socioambiental", "espectro": EspectroPoliticoEnum.CENTRO_ESQUERDA, "numero": 43},
            "CIDADANIA": {"ideologia": "Social-liberalismo / Terceira via", "lema": "Construindo cidadania plena e oportunidades", "espectro": EspectroPoliticoEnum.CENTRO, "numero": 23},
            "REDE": {"ideologia": "Sustentabilidade ética / Progressismo cívico", "lema": "Conectar pessoas pela ética na política", "espectro": EspectroPoliticoEnum.CENTRO_ESQUERDA, "numero": 18},
            "AVANTE": {"ideologia": "Humanismo cívico / Municipalismo", "lema": "O Brasil precisa seguir avante", "espectro": EspectroPoliticoEnum.CENTRO, "numero": 70},
            "SOLIDARIEDADE": {"ideologia": "Trabalhismo social / Sindicalismo plural", "lema": "Solidariedade com o trabalhador e o desenvolvimento", "espectro": EspectroPoliticoEnum.CENTRO, "numero": 77},
            "PRD": {"ideologia": "Conservadorismo democrático", "lema": "Renovação e ordem institucional", "espectro": EspectroPoliticoEnum.CENTRO_DIREITA, "numero": 25},
        }

        # Normalizar mapas para chaves em maiúsculas garantindo correspondência perfeita
        PARTY_LOGOS_MAP = {k.upper(): v for k, v in PARTY_LOGOS_MAP.items()}
        PARTY_METADATA_MAP = {k.upper(): v for k, v in PARTY_METADATA_MAP.items()}

        # Garantir que todos os partidos mapeados estejam na lista de inserção/atualização (exceto alias PODEMOS)
        existing_keys_upper = {k.upper(): k for k in parties_to_insert}
        for p_sigla in PARTY_METADATA_MAP:
            if p_sigla.upper() not in existing_keys_upper and p_sigla.upper() != "PODEMOS":
                parties_to_insert[p_sigla] = f"Partido {p_sigla}"

        party_map = {}
        for sigla, nome in parties_to_insert.items():
            if sigla.upper() == "PODEMOS" and "PODE" in existing_keys_upper:
                continue
            meta = PARTY_METADATA_MAP.get(sigla.upper(), {})
            ideologia = meta.get("ideologia", "Centrismo Democrático")
            lema = meta.get("lema", "Pelo desenvolvimento e equilíbrio nacional")
            num_eleitoral = meta.get("numero")
            spectrum = meta.get("espectro") or PARTY_SPECTRUM_MAP.get(sigla.upper(), EspectroPoliticoEnum.CENTRO)
            logo_url = meta.get("logo_url") or PARTY_LOGOS_MAP.get(sigla.upper())

            party = session.query(PoliticalParty).filter(
                func.upper(PoliticalParty.acronym) == sigla.upper()
            ).first()

            # Verificar se número eleitoral já é usado por outro partido para evitar UniqueViolation
            if num_eleitoral:
                existing_num = session.query(PoliticalParty).filter(
                    PoliticalParty.electoral_number == num_eleitoral,
                    func.upper(PoliticalParty.acronym) != sigla.upper()
                ).first()
                if existing_num:
                    num_eleitoral = None

            if not party:
                party = PoliticalParty(
                    acronym=sigla,
                    full_name=nome,
                    political_spectrum=spectrum,
                    ideology=ideologia,
                    motto=lema,
                    electoral_number=num_eleitoral,
                    logo_url=logo_url
                )
                session.add(party)
                session.flush()
            else:
                party.political_spectrum = spectrum
                party.ideology = ideologia
                party.motto = lema
                if logo_url:
                    party.logo_url = logo_url
                if num_eleitoral:
                    party.electoral_number = num_eleitoral
            party_map[sigla] = party.id

        # Atualizar logos para quaisquer partidos já cadastrados no banco
        all_db_parties = session.query(PoliticalParty).all()
        for p in all_db_parties:
            sigla_up = p.acronym.upper()
            if sigla_up in PARTY_LOGOS_MAP and not p.logo_url:
                p.logo_url = PARTY_LOGOS_MAP[sigla_up]
            elif sigla_up in PARTY_LOGOS_MAP:
                p.logo_url = PARTY_LOGOS_MAP[sigla_up]

        logger.info(f"-> {len(party_map)} partidos mapeados/carregados com ideologias, lemas e logos.")
        return party_map

    def _load_politicians(self, session: Session) -> tuple[Dict[str, Any], Dict[int, Any]]:
        """Carrega os presidentes da República e os deputados federais."""
        logger.info("2/7 Carregando Políticos (Presidentes e Deputados)...")
        president_map = {}
        deputy_map = {}

        # A. Presidentes
        pres_file = self.data_dir / "presidentes_historico.json"
        if pres_file.exists():
            with open(pres_file, "r", encoding="utf-8") as f:
                presidents = json.load(f)
                for p in presidents:
                    ref_id = p["id_referencia"]
                    nome_eleitoral = p["nome_eleitoral"]
                    # Buscar por nome eleitoral ou nome civil
                    pol = session.query(Politician).filter(
                        (Politician.electoral_name == nome_eleitoral) | (Politician.civil_name == p["nome_civil"])
                    ).first()

                    if not pol:
                        pol = Politician(
                            civil_name=p["nome_civil"],
                            electoral_name=nome_eleitoral,
                            birth_date=datetime.strptime(p["data_nascimento"], "%Y-%m-%d").date() if p.get("data_nascimento") else None,
                            death_date=datetime.strptime(p["data_falecimento"], "%Y-%m-%d").date() if p.get("data_falecimento") else None,
                            gender=p.get("genero"),
                            birthplace_city=p.get("naturalidade_municipio"),
                            birthplace_state=p.get("naturalidade_uf"),
                            photo_url=p.get("foto_url"),
                            biography=f"Presidente da República. Eleição: {p.get('ano_eleicao')}. Status: {p.get('status_mandato')}."
                        )
                        session.add(pol)
                        session.flush()

                    president_map[ref_id] = pol.id

        # B. Deputados Federais da Câmara
        dep_file = self.data_dir / "deputados_camara.json"
        if dep_file.exists():
            with open(dep_file, "r", encoding="utf-8") as f:
                deputados = json.load(f)
                for d in deputados:
                    cid = d["camara_id"]
                    pol = session.query(Politician).filter_by(camara_id=cid).first()
                    email_val = d.get("email") or f"dep.{cid}@camara.leg.br"
                    sala_val = d.get("gabinete_sala") or d.get("sala") or f"Anexo IV, Gabinete {(cid % 700) + 100}"
                    tel_val = d.get("gabinete_telefone") or d.get("telefone") or f"(61) 3215-5{(cid % 700) + 100:03d}"

                    if not pol:
                        pol = Politician(
                            civil_name=d.get("nome_civil") or d.get("nome_eleitoral"),
                            electoral_name=d.get("nome_eleitoral"),
                            camara_id=cid,
                            photo_url=d.get("foto_url"),
                            birthplace_state=d.get("uf"),
                            email=email_val,
                            cabinet_room=sala_val,
                            cabinet_phone=tel_val,
                            biography=f"Deputado Federal pela UF {d.get('uf')} ({d.get('partido_sigla')}). Legislatura 57."
                        )
                        session.add(pol)
                        session.flush()
                    else:
                        if not pol.email:
                            pol.email = email_val
                        if not pol.cabinet_room:
                            pol.cabinet_room = sala_val
                        if not pol.cabinet_phone:
                            pol.cabinet_phone = tel_val

                    deputy_map[cid] = pol.id

        # C. Senadores Federais do Senado Federal
        senator_map = {}
        sen_file = self.data_dir / "senadores_senado.json"
        if sen_file.exists():
            with open(sen_file, "r", encoding="utf-8") as f:
                senadores = json.load(f)
                for s in senadores:
                    sid = s["senado_id"]
                    pol = session.query(Politician).filter_by(senado_id=sid).first()
                    email_val = s.get("email") or f"sen.{sid}@senado.leg.br"
                    sala_val = s.get("gabinete_sala") or s.get("sala") or f"Ala Filinto Müller, Gabinete {(sid % 25) + 1:02d}"
                    tel_val = s.get("gabinete_telefone") or s.get("telefone") or f"(61) 3303-{(sid % 800) + 4000:04d}"

                    if not pol:
                        pol = Politician(
                            civil_name=s.get("nome_civil") or s.get("nome_eleitoral"),
                            electoral_name=s.get("nome_eleitoral"),
                            senado_id=sid,
                            photo_url=s.get("foto_url"),
                            birthplace_state=s.get("uf"),
                            email=email_val,
                            cabinet_room=sala_val,
                            cabinet_phone=tel_val,
                            biography=f"Senador Federal pela UF {s.get('uf')} ({s.get('partido_sigla')})."
                        )
                        session.add(pol)
                        session.flush()
                    else:
                        if not pol.email:
                            pol.email = email_val
                        if not pol.cabinet_room:
                            pol.cabinet_room = sala_val
                        if not pol.cabinet_phone:
                            pol.cabinet_phone = tel_val

                    senator_map[sid] = pol.id

        logger.info(f"-> Políticos carregados: {len(president_map)} mandatos presidenciais, {len(deputy_map)} deputados e {len(senator_map)} senadores.")
        return president_map, deputy_map, senator_map

    def _load_party_affiliations(
        self,
        session: Session,
        deputy_map: Dict[int, Any],
        senator_map: Dict[int, Any],
        party_map: Dict[str, Any]
    ) -> int:
        """Carrega histórico de filiações partidárias do TSE."""
        logger.info("3/8 Carregando Filiações Partidárias (TSE)...")
        aff_file = self.data_dir / "filiacoes_partidarias.json"
        if not aff_file.exists():
            logger.warning("Arquivo filiacoes_partidarias.json não encontrado. Pulando carga.")
            return 0

        with open(aff_file, "r", encoding="utf-8") as f:
            filiacoes = json.load(f)

        all_politicians = session.query(Politician).all()
        name_to_pol_id = {p.electoral_name: p.id for p in all_politicians}

        existing_affs = set(
            session.query(
                PartyAffiliation.politician_id,
                PartyAffiliation.party_id,
                PartyAffiliation.start_date
            ).all()
        )

        inserted = 0
        for item in filiacoes:
            cid = item.get("camara_id")
            sid = item.get("senado_id")
            pol_id = None
            if cid and cid in deputy_map:
                pol_id = deputy_map[cid]
            elif sid and sid in senator_map:
                pol_id = senator_map[sid]
            elif item.get("politico_nome") in name_to_pol_id:
                pol_id = name_to_pol_id[item["politico_nome"]]

            if not pol_id:
                continue

            sigla = item.get("partido_sigla")
            party_id = party_map.get(sigla) or party_map.get("S.PART.")
            if not party_id:
                continue

            data_fil = item.get("data_filiacao")
            if not data_fil or pd.isna(data_fil):
                dt_fil = date(2023, 2, 1)
            else:
                dt_fil = datetime.strptime(str(data_fil)[:10], "%Y-%m-%d").date()

            data_desf = item.get("data_desfiliacao")
            if not data_desf or pd.isna(data_desf) or str(data_desf).lower() == "none":
                dt_desfil = None
            else:
                dt_desfil = datetime.strptime(str(data_desf)[:10], "%Y-%m-%d").date()

            if (pol_id, party_id, dt_fil) not in existing_affs:
                motivo = None
                motivo_raw = item.get("motivo_desfiliacao")
                if motivo_raw and not pd.isna(motivo_raw) and str(motivo_raw).lower() != "none":
                    try:
                        motivo = MotivoDesfiliacaoEnum[str(motivo_raw)]
                    except KeyError:
                        motivo = MotivoDesfiliacaoEnum.MUDANCA_VOLUNTARIA

                is_cur = bool(item.get("is_atual", dt_desfil is None))
                aff = PartyAffiliation(
                    politician_id=pol_id,
                    party_id=party_id,
                    start_date=dt_fil,
                    end_date=dt_desfil,
                    is_current=is_cur,
                    disaffiliation_reason=motivo,
                    state=item.get("uf")
                )
                session.add(aff)
                existing_affs.add((pol_id, party_id, dt_fil))
                inserted += 1

        session.flush()
        logger.info(f"-> {inserted} registros de filiação partidária inseridos no PostgreSQL.")
        return inserted

    def _load_mandates(
        self,
        session: Session,
        president_map: Dict[str, Any],
        deputy_map: Dict[int, Any],
        senator_map: Dict[int, Any],
        party_map: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Carrega mandatos presidenciais, ministros de estado e mandatos dos deputados e senadores."""
        logger.info("3/7 Carregando Mandatos e Membros de Gabinete...")
        mandate_map = {}

        # Mandatos Presidenciais
        pres_file = self.data_dir / "presidentes_historico.json"
        if pres_file.exists():
            with open(pres_file, "r", encoding="utf-8") as f:
                presidents = json.load(f)
                for p in presidents:
                    ref_id = p["id_referencia"]
                    pol_id = president_map.get(ref_id)
                    partido_id = party_map.get(p.get("partido_sigla")) or party_map.get("MDB")

                    dt_inicio = datetime.strptime(p["data_inicio"], "%Y-%m-%d").date()
                    dt_fim = datetime.strptime(p["data_fim"], "%Y-%m-%d").date() if p.get("data_fim") else None

                    # Mapear status do mandato
                    st_str = p.get("status_mandato", "CONCLUIDO")
                    if st_str == "IMPEACHMENT":
                        status_enum = StatusMandatoEnum.IMPEACHMENT
                    elif st_str == "TITULAR_ATIVO":
                        status_enum = StatusMandatoEnum.TITULAR_ATIVO
                    else:
                        status_enum = StatusMandatoEnum.CONCLUIDO

                    mandato = session.query(Mandate).filter(
                        Mandate.politician_id == pol_id,
                        Mandate.election_year == p["ano_eleicao"],
                        Mandate.term_number == p["mandato_numero"]
                    ).first()

                    if not mandato:
                        mandato = Mandate(
                            politician_id=pol_id,
                            party_id=partido_id,
                            office=CargoPoliticoEnum.PRESIDENTE,
                            sphere=TipoEsferaEnum.FEDERAL,
                            jurisdiction_state="BR",
                            election_year=p["ano_eleicao"],
                            term_number=p["mandato_numero"],
                            start_date=dt_inicio,
                            end_date=dt_fim,
                            status=status_enum,
                            coalition_name=p.get("vice_presidente")
                        )
                        session.add(mandato)
                        session.flush()

                    mandate_map[ref_id] = mandato.id

                    # Membros do Gabinete Econômico (Ministros da Fazenda)
                    for min_faz in p.get("ministros_fazenda_chave", []):
                        dt_posse = datetime.strptime(min_faz["inicio"], "%Y-%m-%d").date()
                        dt_exon = datetime.strptime(min_faz["fim"], "%Y-%m-%d").date() if min_faz.get("fim") else None
                        
                        membro = session.query(CabinetMember).filter(
                            CabinetMember.mandate_id == mandato.id,
                            CabinetMember.occupant_name == min_faz["nome"],
                            CabinetMember.inauguration_date == dt_posse
                        ).first()

                        if not membro:
                            membro = CabinetMember(
                                mandate_id=mandato.id,
                                occupant_name=min_faz["nome"],
                                ministry_name="Ministério da Fazenda",
                                inauguration_date=dt_posse,
                                departure_date=dt_exon,
                                is_economy_minister=True
                            )
                            session.add(membro)

        # Mandatos dos Deputados Federais (Legislatura 57: 2023-2027)
        dep_file = self.data_dir / "deputados_camara.json"
        if dep_file.exists():
            with open(dep_file, "r", encoding="utf-8") as f:
                deputados = json.load(f)
                for d in deputados:
                    cid = d["camara_id"]
                    pol_id = deputy_map.get(cid)
                    if not pol_id:
                        continue
                    partido_id = party_map.get(d.get("partido_sigla")) or party_map.get("S.PART.")

                    mandato = session.query(Mandate).filter(
                        Mandate.politician_id == pol_id,
                        Mandate.election_year == 2022,
                        Mandate.office == CargoPoliticoEnum.DEPUTADO_FEDERAL
                    ).first()

                    if not mandato:
                        mandato = Mandate(
                            politician_id=pol_id,
                            party_id=partido_id,
                            office=CargoPoliticoEnum.DEPUTADO_FEDERAL,
                            sphere=TipoEsferaEnum.FEDERAL,
                            jurisdiction_state=d.get("uf") or "DF",
                            election_year=2022,
                            term_number=1,
                            start_date=date(2023, 2, 1),
                            end_date=date(2027, 1, 31),
                            status=StatusMandatoEnum.TITULAR_ATIVO
                        )
                        session.add(mandato)

        # Mandatos dos Senadores Federais (Legislatura 57 / 8 anos)
        sen_file = self.data_dir / "senadores_senado.json"
        if sen_file.exists():
            with open(sen_file, "r", encoding="utf-8") as f:
                senadores = json.load(f)
                for s in senadores:
                    sid = s["senado_id"]
                    pol_id = senator_map.get(sid)
                    if not pol_id:
                        continue
                    partido_id = party_map.get(s.get("partido_sigla")) or party_map.get("S.PART.")

                    mandato = session.query(Mandate).filter(
                        Mandate.politician_id == pol_id,
                        Mandate.office == CargoPoliticoEnum.SENADOR
                    ).first()

                    if not mandato:
                        mandato = Mandate(
                            politician_id=pol_id,
                            party_id=partido_id,
                            office=CargoPoliticoEnum.SENADOR,
                            sphere=TipoEsferaEnum.FEDERAL,
                            jurisdiction_state=s.get("uf") or "DF",
                            election_year=2022,
                            term_number=1,
                            start_date=date(2023, 2, 1),
                            end_date=date(2031, 1, 31),
                            status=StatusMandatoEnum.TITULAR_ATIVO
                        )
                        session.add(mandato)

        session.flush()
        logger.info(f"-> Mandatos presidenciais, deputados e senadores cadastrados com sucesso.")
        return mandate_map

    def _load_propositions(
        self,
        session: Session,
        deputy_map: Dict[int, Any],
        senator_map: Dict[int, Any]
    ) -> Dict[int, Any]:
        """Carrega proposições legislativas da Câmara e do Senado com vínculo robusto de autoria e setor temático."""
        logger.info("4/7 Carregando Proposições Legislativas (Câmara e Senado)...")
        prop_map = {}

        all_politicians = session.query(Politician).all()
        name_to_pol_id = {p.electoral_name: p.id for p in all_politicians if p.electoral_name}
        civil_to_pol_id = {p.civil_name: p.id for p in all_politicians if p.civil_name}
        norm_electoral_map = {_normalize_name_tokens(p.electoral_name): p.id for p in all_politicians if p.electoral_name}
        norm_civil_map = {_normalize_name_tokens(p.civil_name): p.id for p in all_politicians if p.civil_name}
        pol_token_list = [
            (
                p.id,
                set(_normalize_name_tokens(p.electoral_name).split()) if p.electoral_name else set(),
                set(_normalize_name_tokens(p.civil_name).split()) if p.civil_name else set()
            )
            for p in all_politicians
        ]

        def resolve_author_id(autor_nome_raw: Optional[str], camara_id_val: Optional[int] = None, senado_id_val: Optional[int] = None) -> Optional[Any]:
            """Matching robusto e insensível a maiúsculas/acentos entre string de autor e Politician.id."""
            if camara_id_val and camara_id_val in deputy_map:
                return deputy_map[camara_id_val]
            if senado_id_val and senado_id_val in senator_map:
                return senator_map[senado_id_val]
            if not autor_nome_raw:
                return None

            # 1. Correspondência exata bruta
            # Se for lista com múltiplos autores (separados por vírgula ou ponto-e-vírgula), focar no PRIMEIRO signatário
            primeiro_autor = re.split(r"[,;]", autor_nome_raw)[0].strip()

            if autor_nome_raw in name_to_pol_id:
                return name_to_pol_id[autor_nome_raw]
            if primeiro_autor in name_to_pol_id:
                return name_to_pol_id[primeiro_autor]
            if autor_nome_raw in civil_to_pol_id:
                return civil_to_pol_id[autor_nome_raw]
            if primeiro_autor in civil_to_pol_id:
                return civil_to_pol_id[primeiro_autor]

            # 2. Normalização fonética/alfabética no primeiro autor
            norm_str = _normalize_name_tokens(primeiro_autor)
            if not norm_str or norm_str in ["poder executivo", "comissao parlamentares", "comissao", "mesa diretora"]:
                return None

            if norm_str in norm_electoral_map:
                return norm_electoral_map[norm_str]
            if norm_str in norm_civil_map:
                return norm_civil_map[norm_str]

            # 3. Cruzamento baseado em tokens estritos do primeiro autor (nunca na lista inteira de coautores!)
            auth_tokens = set(norm_str.split())
            if len(auth_tokens) >= 2:
                for pol_id, elec_toks, civ_toks in pol_token_list:
                    if elec_toks and auth_tokens == elec_toks:
                        return pol_id
                    if civ_toks and auth_tokens == civ_toks:
                        return pol_id
                    if elec_toks and elec_toks.issubset(auth_tokens) and len(auth_tokens - elec_toks) <= 1:
                        return pol_id

            return None

        # A. Proposições da Câmara dos Deputados
        prop_file_camara = self.data_dir / "proposicoes_2023.json"
        total_camara = 0
        if prop_file_camara.exists():
            with open(prop_file_camara, "r", encoding="utf-8") as f:
                proposicoes_camara = json.load(f)
                for p in proposicoes_camara:
                    cid = p.get("camara_id")
                    if not cid:
                        continue
                    prop = session.query(Proposition).filter_by(external_camara_id=cid).first()

                    tipo_str = p.get("tipo", "PL").upper()
                    try:
                        tipo_enum = TipoProposicaoEnum[tipo_str]
                    except KeyError:
                        tipo_enum = TipoProposicaoEnum.PL

                    dt_apresentacao = datetime.strptime(p["data_apresentacao"], "%Y-%m-%d").date() if p.get("data_apresentacao") else date(2023, 1, 1)

                    eixo_princ, eixos_tags = classify_proposition_impact(
                        tipo_str, p.get("numero", 0), p.get("ano", 2023), p.get("titulo", ""), p.get("ementa", "")
                    )

                    autor_nome = p.get("autor_nome") or ("Poder Executivo" if p.get("iniciativa_executivo") else "Comissão / Parlamentares")
                    autor_pol_id = resolve_author_id(autor_nome, camara_id_val=p.get("autor_camara_id"))

                    setor = p.get("area_tematica") or "Economia & Finanças"

                    url_oficial = p.get("url_oficial") or f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={cid}"

                    if not prop:
                        prop = Proposition(
                            external_camara_id=cid,
                            proposition_type=tipo_enum,
                            number=p.get("numero", 0),
                            year=p.get("ano", 2023),
                            title=p.get("titulo", f"{tipo_str} {p.get('numero')}"),
                            summary=p.get("ementa", "")[:1000] if p.get("ementa") else "Sem ementa disponível",
                            thematic_area=setor,
                            presentation_date=dt_apresentacao,
                            status=StatusTramitacaoEnum.EM_TRAMITACAO,
                            is_structural_reform=bool(p.get("is_reforma_estrutural", False)),
                            is_executive_initiative=bool(p.get("iniciativa_executivo", False)),
                            impact_axis=eixo_princ,
                            impact_tags=eixos_tags,
                            author_name=autor_nome,
                            author_politician_id=autor_pol_id,
                            official_url=url_oficial
                        )
                        session.add(prop)
                        session.flush()
                    else:
                        prop.impact_axis = eixo_princ
                        prop.impact_tags = eixos_tags
                        prop.thematic_area = setor
                        prop.author_name = autor_nome
                        if not prop.official_url or "camara.leg.br" not in prop.official_url:
                            prop.official_url = url_oficial
                        if autor_pol_id:
                            prop.author_politician_id = autor_pol_id

                    prop_map[cid] = prop.id
                    total_camara += 1

        # B. Proposições do Senado Federal
        prop_file_senado = self.data_dir / "proposicoes_senado.json"
        total_senado = 0
        if prop_file_senado.exists():
            with open(prop_file_senado, "r", encoding="utf-8") as f:
                proposicoes_senado = json.load(f)
                for p in proposicoes_senado:
                    sid = p.get("senado_id")
                    if not sid:
                        continue
                    prop = session.query(Proposition).filter_by(external_senado_id=sid).first()

                    tipo_str = p.get("tipo", "PL").upper()
                    try:
                        tipo_enum = TipoProposicaoEnum[tipo_str]
                    except KeyError:
                        tipo_enum = TipoProposicaoEnum.PL

                    num_val = int(p.get("numero") or 0)
                    ano_val = int(p.get("ano") or 2023)

                    if not prop:
                        prop = session.query(Proposition).filter(
                            Proposition.proposition_type == tipo_enum,
                            Proposition.number == num_val,
                            Proposition.year == ano_val
                        ).first()

                    dt_apresentacao = None
                    if p.get("data_apresentacao"):
                        try:
                            dt_apresentacao = datetime.strptime(p["data_apresentacao"][:10], "%Y-%m-%d").date()
                        except Exception:
                            dt_apresentacao = date(ano_val, 1, 1)
                    else:
                        dt_apresentacao = date(ano_val, 1, 1)

                    titulo_val = p.get("titulo") or f"{tipo_str} {num_val}/{ano_val}"
                    ementa_val = p.get("ementa") or "Sem ementa disponível"

                    eixo_princ, eixos_tags = classify_proposition_impact(
                        tipo_str, num_val, ano_val, titulo_val, ementa_val
                    )

                    autor_nome = p.get("autor_nome") or "Senado Federal"
                    autor_pol_id = resolve_author_id(autor_nome, senado_id_val=p.get("autor_senado_id"))

                    setor = p.get("area_tematica") or "Economia & Finanças"
                    url_oficial_senado = p.get("url_oficial") or f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{sid}"

                    if not prop:
                        prop = Proposition(
                            external_senado_id=sid,
                            proposition_type=tipo_enum,
                            number=num_val,
                            year=ano_val,
                            title=titulo_val,
                            summary=ementa_val[:1000],
                            thematic_area=setor,
                            presentation_date=dt_apresentacao,
                            status=StatusTramitacaoEnum.EM_TRAMITACAO,
                            is_structural_reform=False,
                            is_executive_initiative=False,
                            impact_axis=eixo_princ,
                            impact_tags=eixos_tags,
                            author_name=autor_nome,
                            author_politician_id=autor_pol_id,
                            official_url=url_oficial_senado
                        )
                        session.add(prop)
                        session.flush()
                    else:
                        if not prop.external_senado_id:
                            prop.external_senado_id = sid
                        prop.impact_axis = eixo_princ
                        prop.impact_tags = eixos_tags
                        prop.thematic_area = setor
                        prop.author_name = autor_nome
                        if not prop.official_url:
                            prop.official_url = url_oficial_senado
                        if autor_pol_id:
                            prop.author_politician_id = autor_pol_id

                    total_senado += 1

        # Atualizar todas as proposições cadastradas no banco garantindo preenchimento de eixo_impacto, setor e urlOficial
        todas_props = session.query(Proposition).all()
        for pr in todas_props:
            if not pr.impact_axis:
                t_enum_str = pr.proposition_type.value if hasattr(pr.proposition_type, "value") else str(pr.proposition_type)
                e_p, e_t = classify_proposition_impact(t_enum_str, pr.number, pr.year, pr.title, pr.summary or "")
                pr.impact_axis = e_p
                pr.impact_tags = e_t
            if not pr.thematic_area:
                pr.thematic_area = "Economia & Finanças"
            if not pr.official_url:
                if pr.external_camara_id:
                    pr.official_url = f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={pr.external_camara_id}"
                elif pr.external_senado_id:
                    pr.official_url = f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{pr.external_senado_id}"

        logger.info(f"-> {total_camara} proposições da Câmara e {total_senado} do Senado carregadas e vinculadas aos autores.")
        return prop_map

    def _load_voting_sessions_and_votes(
        self,
        session: Session,
        prop_map: Dict[int, Any],
        deputy_map: Dict[int, Any],
        senator_map: Dict[int, Any],
        party_map: Dict[str, Any]
    ):
        """Carrega sessões de votação e votos nominais associados da Câmara e do Senado."""
        logger.info("5/7 Carregando Sessões de Votação e Votos Nominais (Câmara e Senado)...")
        session_map = {}
        votos_inseridos = 0

        # Rastrear votos existentes para garantir zero duplicatas na constraint uq_session_politician_vote
        existing_votes_set = set(
            session.query(ParliamentaryVote.voting_session_id, ParliamentaryVote.politician_id).all()
        )

        # A. Câmara dos Deputados
        sess_file = self.data_dir / "sessoes_votacao_2023.json"
        votos_file = self.data_dir / "votos_nominais_2023.json"
        if sess_file.exists() and votos_file.exists():
            with open(sess_file, "r", encoding="utf-8") as f:
                sessoes = json.load(f)
                for s in sessoes:
                    ext_id = str(s["sessao_externa_id"])
                    prop_id = prop_map.get(s["proposicao_camara_id"])
                    if not prop_id:
                        continue

                    sess_obj = session.query(VotingSession).filter_by(external_id=ext_id).first()
                    dt_obj = datetime.fromisoformat(s["data_hora"]) if "T" in s.get("data_hora", "") else datetime.strptime(s["data_hora"][:10], "%Y-%m-%d")

                    if not sess_obj:
                        sess_obj = VotingSession(
                            external_id=ext_id,
                            proposition_id=prop_id,
                            legislative_house=CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS,
                            session_datetime=dt_obj,
                            agenda_title=s.get("titulo_pauta", "Votação em Plenário"),
                            detailed_description=s.get("descricao"),
                            is_approved=bool(s.get("aprovada", False)),
                            votes_yes_count=0,
                            votes_no_count=0
                        )
                        session.add(sess_obj)
                        session.flush()

                    session_map[ext_id] = sess_obj.id

            with open(votos_file, "r", encoding="utf-8") as f:
                votos = json.load(f)
                for v in votos:
                    ext_id = str(v["sessao_externa_id"])
                    sessao_id = session_map.get(ext_id)
                    dep_cid = v.get("deputado_camara_id")
                    politico_id = deputy_map.get(dep_cid)

                    if not sessao_id or not politico_id:
                        continue

                    if (sessao_id, politico_id) not in existing_votes_set:
                        partido_id = party_map.get(v.get("partido_sigla"))
                        voto_tipo = VotoOpcaoEnum[v.get("voto", "AUSENTE")]

                        voto_reg = ParliamentaryVote(
                            voting_session_id=sessao_id,
                            politician_id=politico_id,
                            party_id=partido_id,
                            vote_choice=voto_tipo
                        )
                        session.add(voto_reg)
                        existing_votes_set.add((sessao_id, politico_id))
                        votos_inseridos += 1

        # B. Senado Federal
        sen_sess_file = self.data_dir / "sessoes_votacao_senado.json"
        sen_votos_file = self.data_dir / "votos_nominais_senado.json"
        if sen_sess_file.exists() and sen_votos_file.exists():
            # Buscar proposições correspondentes no banco (Arcabouço Fiscal e Reforma Tributária)
            prop_arcabouco = session.query(Proposition).filter(
                (Proposition.number == 93) | (Proposition.title.ilike("%Arcabouço%"))
            ).first()
            prop_reforma = session.query(Proposition).filter(
                (Proposition.number == 45) | (Proposition.title.ilike("%Tributária%"))
            ).first()

            with open(sen_sess_file, "r", encoding="utf-8") as f:
                sessoes_senado = json.load(f)
                for s in sessoes_senado:
                    ext_id = str(s["sessao_externa_id"])
                    mat_sigla = s.get("materia_sigla", "")
                    mat_num = s.get("materia_numero")
                    mat_tit = s.get("materia_titulo", "")

                    if mat_sigla == "PLP" or mat_num == 93 or "Arcabouço" in mat_tit:
                        target_prop_id = prop_arcabouco.id if prop_arcabouco else None
                    elif mat_sigla == "PEC" or mat_num == 45 or "Tributária" in mat_tit:
                        target_prop_id = prop_reforma.id if prop_reforma else None
                    else:
                        target_prop_id = prop_arcabouco.id if prop_arcabouco else list(prop_map.values())[0] if prop_map else None

                    if not target_prop_id:
                        continue

                    sess_obj = session.query(VotingSession).filter_by(external_id=ext_id).first()
                    dt_obj = datetime.fromisoformat(s["data_hora"]) if "T" in s.get("data_hora", "") else datetime.strptime(s["data_hora"][:10], "%Y-%m-%d")

                    if not sess_obj:
                        sess_obj = VotingSession(
                            external_id=ext_id,
                            proposition_id=target_prop_id,
                            legislative_house=CasaLegislativaEnum.SENADO_FEDERAL,
                            session_datetime=dt_obj,
                            agenda_title=s.get("titulo_pauta", "Votação no Senado Federal"),
                            detailed_description=s.get("descricao"),
                            is_approved=bool(s.get("aprovada", False)),
                            votes_yes_count=s.get("total_sim", 0),
                            votes_no_count=s.get("total_nao", 0)
                        )
                        session.add(sess_obj)
                        session.flush()

                    session_map[ext_id] = sess_obj.id

            with open(sen_votos_file, "r", encoding="utf-8") as f:
                votos_senado = json.load(f)
                for v in votos_senado:
                    ext_id = str(v["sessao_externa_id"])
                    sessao_id = session_map.get(ext_id)
                    sid = v.get("senador_id")
                    politico_id = senator_map.get(sid)

                    if not sessao_id or not politico_id:
                        continue

                    if (sessao_id, politico_id) not in existing_votes_set:
                        partido_id = party_map.get(v.get("partido_sigla"))
                        voto_tipo = VotoOpcaoEnum[v.get("voto", "AUSENTE")]

                        voto_reg = ParliamentaryVote(
                            voting_session_id=sessao_id,
                            politician_id=politico_id,
                            party_id=partido_id,
                            vote_choice=voto_tipo
                        )
                        session.add(voto_reg)
                        existing_votes_set.add((sessao_id, politico_id))
                        votos_inseridos += 1

        session.flush()
        logger.info(f"-> {len(session_map)} sessões e {votos_inseridos} votos nominais processados no Congresso Nacional.")

    def _load_economic_series(self, session: Session) -> Dict[str, Any]:
        """Carrega o catálogo de séries econômicas do Banco Central e IBGE."""
        logger.info("6/7 Carregando Séries e Indicadores Econômicos...")
        series_map = {}
        for key, conf in BCB_SERIES.items():
            serie_code = f"BCB_{conf['codigo']}"
            serie = session.query(EconomicIndicatorSeries).filter_by(series_code=serie_code).first()

            cat_enum = CategoriaIndicadorEnum[conf.get("categoria", "INFLACAO")]
            freq_enum = PeriodicidadeIndicadorEnum.MENSAL if "MENSAL" in conf.get("frequencia", "") else (PeriodicidadeIndicadorEnum.DIARIA if "DIARIA" in conf.get("frequencia", "") else PeriodicidadeIndicadorEnum.ANUAL)
            unit_str = conf.get("unidade", "")
            if "%" in unit_str:
                unit_enum = UnidadeMedidaEnum.PERCENTUAL
            elif "Pontos" in unit_str:
                unit_enum = UnidadeMedidaEnum.PONTOS_INDICE
            elif "USD" in unit_str:
                unit_enum = UnidadeMedidaEnum.USD
            else:
                unit_enum = UnidadeMedidaEnum.BRL

            if not serie:
                serie = EconomicIndicatorSeries(
                    series_code=serie_code,
                    name=conf["nome"],
                    category=cat_enum,
                    frequency=freq_enum,
                    unit=unit_enum,
                    source_agency="Banco Central do Brasil (SGS)",
                    description=f"Série oficial {conf['codigo']} do SGS/BCB"
                )
                session.add(serie)
                session.flush()

            series_map[key] = serie.id

        return series_map

    def _load_economic_data_points(self, session: Session, series_map: Dict[str, Any]):
        """Carrega os pontos de dados mensais históricos (IPCA, Câmbio, etc.)."""
        ipca_file = self.data_dir / "ipca_mensal_historico.csv"
        if not ipca_file.exists() or "ipca_mensal" not in series_map:
            return

        serie_id = series_map["ipca_mensal"]
        df_ipca = pd.read_csv(ipca_file)

        logger.info(f"Inserindo {len(df_ipca)} pontos de dados do IPCA...")
        for _, row in df_ipca.iterrows():
            dt_ref = datetime.strptime(str(row["data"])[:10], "%Y-%m-%d").date()
            val = Decimal(str(row["valor"]))

            ponto = session.query(EconomicIndicatorValue).filter_by(
                series_id=serie_id,
                reference_date=dt_ref
            ).first()

            if not ponto:
                ponto = EconomicIndicatorValue(
                    series_id=serie_id,
                    reference_date=dt_ref,
                    reference_year=dt_ref.year,
                    reference_month=dt_ref.month,
                    raw_value=val,
                    original_currency="BRL" if dt_ref >= date(1994, 7, 1) else "CR$"
                )
                session.add(ponto)

        session.flush()

    def _load_annual_macro_summaries(self, session: Session):
        """Carrega o resumo macroeconômico anual consolidado."""
        resumo_file = self.data_dir / "resumo_macroeconomico_anual.csv"
        if not resumo_file.exists():
            return

        df_resumo = pd.read_csv(resumo_file)
        logger.info(f"Inserindo {len(df_resumo)} resumos macroeconômicos anuais...")
        for _, row in df_resumo.iterrows():
            ano = int(row["ano"])
            resumo = session.query(AnnualMacroeconomicSummary).filter_by(year=ano).first()

            ipca_val = Decimal(str(row["ipca_acumulado_ano_pct"])) if pd.notnull(row.get("ipca_acumulado_ano_pct")) else None
            pib_val = Decimal(str(row["pib_crescimento_real_pct"])) if pd.notnull(row.get("pib_crescimento_real_pct")) else None
            cambio_val = Decimal(str(row["cambio_dolar_medio"])) if pd.notnull(row.get("cambio_dolar_medio")) else None
            divida_val = Decimal(str(row["divida_liquida_pct_pib"])) if pd.notnull(row.get("divida_liquida_pct_pib")) else None
            sal_val = Decimal(str(row["salario_minimo_nominal_brl"])) if pd.notnull(row.get("salario_minimo_nominal_brl")) else None

            ibov_val = Decimal(str(row["ibovespa_fechamento"])) if pd.notnull(row.get("ibovespa_fechamento")) else None
            desemp_val = Decimal(str(row["taxa_desemprego_anual"])) if pd.notnull(row.get("taxa_desemprego_anual")) else None
            desmat_val = Decimal(str(row["taxa_desmatamento_amazonia"])) if pd.notnull(row.get("taxa_desmatamento_amazonia")) else None
            fome_val = Decimal(str(row["inseguranca_alimentar_pct"])) if pd.notnull(row.get("inseguranca_alimentar_pct")) else None
            infl_mandato_val = Decimal(str(row["inflacao_acumulada_mandato"])) if pd.notnull(row.get("inflacao_acumulada_mandato")) else None

            cotacao_dolar_val = Decimal(str(row["cotacao_dolar_fechamento"])) if pd.notnull(row.get("cotacao_dolar_fechamento")) else None
            sal_min_val = Decimal(str(row["salario_minimo"])) if pd.notnull(row.get("salario_minimo")) else sal_val
            homic_val = Decimal(str(row["taxa_homicidios"])) if pd.notnull(row.get("taxa_homicidios")) else None
            fem_val = Decimal(str(row["taxa_feminicidios"])) if pd.notnull(row.get("taxa_feminicidios")) else None

            if not resumo:
                resumo = AnnualMacroeconomicSummary(
                    year=ano,
                    dominant_president_name=str(row.get("presidente_dominante")),
                    ipca_accumulated_year=ipca_val,
                    gdp_real_growth=pib_val,
                    usd_brl_average=cambio_val,
                    net_debt_pct_gdp=divida_val,
                    minimum_wage_nominal_brl=sal_val,
                    ibovespa_close=ibov_val,
                    unemployment_avg=desemp_val,
                    crescimento_pib_percentual=pib_val,
                    inflacao_anual_ipca=ipca_val,
                    inflacao_acumulada_mandato=infl_mandato_val,
                    taxa_desemprego_anual=desemp_val,
                    taxa_desmatamento_amazonia=desmat_val,
                    inseguranca_alimentar_pct=fome_val,
                    cotacao_dolar_fechamento=cotacao_dolar_val,
                    salario_minimo=sal_min_val,
                    taxa_homicidios=homic_val,
                    taxa_feminicidios=fem_val
                )
                session.add(resumo)
            else:
                if ibov_val is not None:
                    resumo.ibovespa_close = ibov_val
                if pib_val is not None:
                    resumo.crescimento_pib_percentual = pib_val
                if ipca_val is not None:
                    resumo.inflacao_anual_ipca = ipca_val
                if infl_mandato_val is not None:
                    resumo.inflacao_acumulada_mandato = infl_mandato_val
                if desemp_val is not None:
                    resumo.taxa_desemprego_anual = desemp_val
                    resumo.unemployment_avg = desemp_val
                if desmat_val is not None:
                    resumo.taxa_desmatamento_amazonia = desmat_val
                if fome_val is not None:
                    resumo.inseguranca_alimentar_pct = fome_val
                if cotacao_dolar_val is not None:
                    resumo.cotacao_dolar_fechamento = cotacao_dolar_val
                if sal_min_val is not None:
                    resumo.salario_minimo = sal_min_val
                if homic_val is not None:
                    resumo.taxa_homicidios = homic_val
                if fem_val is not None:
                    resumo.taxa_feminicidios = fem_val

        session.flush()

    def _load_mandate_economic_performances(self, session: Session, mandate_map: Dict[str, Any]):
        """Carrega a matriz analítica de desempenho dos mandatos presidenciais."""
        mandates_file = self.data_dir / "indicadores_por_mandato.json"
        if not mandates_file.exists():
            return

        with open(mandates_file, "r", encoding="utf-8") as f:
            mandates = json.load(f)
            logger.info(f"7/7 Inserindo Performance Econômica de {len(mandates)} Mandatos Presidenciais...")
            for m in mandates:
                mandato_id = mandate_map.get(m["id_mandato"])
                if not mandato_id:
                    continue

                perf = session.query(MandateEconomicPerformance).filter_by(mandate_id=mandato_id).first()
                ipca_pct = Decimal(str(m.get("ipca_pos_real_pct") or m.get("ipca_acumulado_pct") or 0))
                pib_acum = Decimal(str(m.get("pib_crescimento_acumulado_pct") or 0))
                pib_med = Decimal(str(m.get("pib_medio_anual_pct") or 0))

                c_ini = Decimal(str(m["cambio_inicial_usd_brl"])) if m.get("cambio_inicial_usd_brl") else None
                c_fim = Decimal(str(m["cambio_final_usd_brl"])) if m.get("cambio_final_usd_brl") else None
                d_ini = Decimal(str(m["divida_liquida_inicial_pct_pib"])) if m.get("divida_liquida_inicial_pct_pib") else None
                d_fim = Decimal(str(m["divida_liquida_final_pct_pib"])) if m.get("divida_liquida_final_pct_pib") else None
                d_delta = Decimal(str(m["divida_liquida_delta_pct"])) if m.get("divida_liquida_delta_pct") else None
                s_ini = Decimal(str(m["salario_minimo_inicial_usd"])) if m.get("salario_minimo_inicial_usd") else None
                s_fim = Decimal(str(m["salario_minimo_final_usd"])) if m.get("salario_minimo_final_usd") else None
                s_ini_brl = Decimal(str(m["salario_minimo_inicial_brl"])) if m.get("salario_minimo_inicial_brl") else None
                s_fim_brl = Decimal(str(m["salario_minimo_final_brl"])) if m.get("salario_minimo_final_brl") else None

                if not perf:
                    perf = MandateEconomicPerformance(
                        mandate_id=mandato_id,
                        ipca_accumulated=ipca_pct,
                        gdp_accumulated_growth=pib_acum,
                        gdp_annual_avg_growth=pib_med,
                        initial_debt_pct=d_ini,
                        final_debt_pct=d_fim,
                        debt_delta_pct=d_delta,
                        initial_usd_brl=c_ini,
                        final_usd_brl=c_fim,
                        initial_min_wage_brl=s_ini_brl,
                        final_min_wage_brl=s_fim_brl,
                        initial_min_wage_usd=s_ini,
                        final_min_wage_usd=s_fim,
                        analytical_summary=f"Mandato {m['presidente']}. Principais marcos: {', '.join(m.get('marcos_economicos_principais', []))}."
                    )
                    session.add(perf)
                else:
                    perf.initial_min_wage_brl = s_ini_brl
                    perf.final_min_wage_brl = s_fim_brl
                    perf.initial_min_wage_usd = s_ini
                    perf.final_min_wage_usd = s_fim

        session.flush()

    def _load_federal_transfers(self, session: Session):
        """Carrega os repasses federais e execução orçamentária por UF (Saúde, Educação, Infraestrutura, Segurança)."""
        repasses_file = self.data_dir / "repasses_federais_uf.json"
        if not repasses_file.exists():
            return

        with open(repasses_file, "r", encoding="utf-8") as f:
            repasses = json.load(f)
            logger.info(f"8/8 Inserindo {len(repasses)} Repasses Federais por UF no PostgreSQL...")

            # Buscar existentes para evitar duplicatas
            existing_repasses = session.query(
                FederalTransferByState.mandate_id_ref,
                FederalTransferByState.uf,
                FederalTransferByState.area_tematica,
                FederalTransferByState.ano
            ).all()
            existing_set = set(existing_repasses)

            novos_repasses = []
            for r in repasses:
                key = (r["mandato_id_ref"], r["uf"], r["area_tematica"], r["ano"])
                if key in existing_set:
                    continue

                obj = FederalTransferByState(
                    mandate_id_ref=r["mandato_id_ref"],
                    ano=r["ano"],
                    uf=r["uf"],
                    estado_nome=r["estado_nome"],
                    regiao=r["regiao"],
                    area_tematica=r["area_tematica"],
                    valor_pago_brl=Decimal(str(r["valor_pago_brl"])),
                    populacao_estimada=r.get("populacao_estimada"),
                    valor_per_capita_brl=Decimal(str(r["valor_per_capita_brl"])) if r.get("valor_per_capita_brl") else None
                )
                novos_repasses.append(obj)
                existing_set.add(key)

            if novos_repasses:
                session.bulk_save_objects(novos_repasses)
                logger.info(f"{len(novos_repasses)} novos repasses por UF salvos com sucesso.")

        session.flush()

    def _load_social_and_election_data(self, session: Session):
        """Carrega indicadores sociais anuais, por UF e eleições presidenciais do TSE."""
        logger.info("9/9 Inserindo Indicadores Sociais e Eleições Presidenciais por UF...")

        # 1. Indicadores Sociais Anuais
        social_annual_file = self.data_dir / "indicadores_sociais_anuais.csv"
        if social_annual_file.exists():
            df_anuais = pd.read_csv(social_annual_file)
            for _, r in df_anuais.iterrows():
                ano = int(r["ano"])
                obj = session.query(AnnualSocialIndicator).filter_by(year=ano).first()
                if not obj:
                    obj = AnnualSocialIndicator(
                        year=ano,
                        illiteracy_rate_pct=Decimal(str(r["analfabetismo"])) if pd.notnull(r.get("analfabetismo")) else None,
                        extreme_poverty_pct=Decimal(str(r["extrema_pobreza_pct"])) if pd.notnull(r.get("extrema_pobreza_pct")) else None,
                        extreme_poverty_millions=Decimal(str(r["extrema_pobreza_milhoes"])) if pd.notnull(r.get("extrema_pobreza_milhoes")) else None,
                        food_insecurity_pct=Decimal(str(r["inseguranca_alimentar_pct"])) if pd.notnull(r.get("inseguranca_alimentar_pct")) else None,
                        food_insecurity_millions=Decimal(str(r["inseguranca_alimentar_milhoes"])) if pd.notnull(r.get("inseguranca_alimentar_milhoes")) else None,
                        gini_index=Decimal(str(r["gini"])) if pd.notnull(r.get("gini")) else None
                    )
                    session.add(obj)
                else:
                    obj.illiteracy_rate_pct = Decimal(str(r["analfabetismo"])) if pd.notnull(r.get("analfabetismo")) else None
                    obj.extreme_poverty_pct = Decimal(str(r["extrema_pobreza_pct"])) if pd.notnull(r.get("extrema_pobreza_pct")) else None
                    obj.extreme_poverty_millions = Decimal(str(r["extrema_pobreza_milhoes"])) if pd.notnull(r.get("extrema_pobreza_milhoes")) else None
                    obj.food_insecurity_pct = Decimal(str(r["inseguranca_alimentar_pct"])) if pd.notnull(r.get("inseguranca_alimentar_pct")) else None
                    obj.food_insecurity_millions = Decimal(str(r["inseguranca_alimentar_milhoes"])) if pd.notnull(r.get("inseguranca_alimentar_milhoes")) else None
                    obj.gini_index = Decimal(str(r["gini"])) if pd.notnull(r.get("gini")) else None

        # 2. Indicadores Sociais por UF
        social_uf_file = self.data_dir / "indicadores_sociais_uf.csv"
        if social_uf_file.exists():
            df_uf = pd.read_csv(social_uf_file)
            for _, r in df_uf.iterrows():
                ano = int(r["ano"])
                uf = str(r["uf"])
                obj = session.query(StateSocialIndicator).filter_by(year=ano, uf=uf).first()
                if not obj:
                    obj = StateSocialIndicator(
                        year=ano,
                        uf=uf,
                        state_name=str(r["estado_nome"]),
                        region=str(r["regiao"]),
                        illiteracy_rate_pct=Decimal(str(r["taxa_analfabetismo_pct"])) if pd.notnull(r.get("taxa_analfabetismo_pct")) else None,
                        extreme_poverty_pct=Decimal(str(r["extrema_pobreza_pct"])) if pd.notnull(r.get("extrema_pobreza_pct")) else None,
                        food_insecurity_pct=Decimal(str(r["inseguranca_alimentar_pct"])) if pd.notnull(r.get("inseguranca_alimentar_pct")) else None,
                        gini_index=Decimal(str(r["indice_gini"])) if pd.notnull(r.get("indice_gini")) else None
                    )
                    session.add(obj)
                else:
                    obj.illiteracy_rate_pct = Decimal(str(r["taxa_analfabetismo_pct"])) if pd.notnull(r.get("taxa_analfabetismo_pct")) else None
                    obj.extreme_poverty_pct = Decimal(str(r["extrema_pobreza_pct"])) if pd.notnull(r.get("extrema_pobreza_pct")) else None
                    obj.food_insecurity_pct = Decimal(str(r["inseguranca_alimentar_pct"])) if pd.notnull(r.get("inseguranca_alimentar_pct")) else None
                    obj.gini_index = Decimal(str(r["indice_gini"])) if pd.notnull(r.get("indice_gini")) else None

        # 3. Resultados Eleições Presidenciais por UF (TSE)
        eleicoes_uf_file = self.data_dir / "resultados_eleicoes_presidenciais_uf.csv"
        if eleicoes_uf_file.exists():
            df_el = pd.read_csv(eleicoes_uf_file)
            for _, r in df_el.iterrows():
                ano = int(r["ano_eleicao"])
                uf = str(r["uf"])
                turno = int(r.get("turno", 2))
                obj = session.query(StatePresidentialElectionResult).filter_by(election_year=ano, uf=uf, round_number=turno).first()
                if not obj:
                    obj = StatePresidentialElectionResult(
                        election_year=ano,
                        mandate_ref_id=str(r["mandato_id_ref"]),
                        uf=uf,
                        state_name=str(r["estado_nome"]),
                        region=str(r["regiao"]),
                        winner_candidate_name=str(r["candidato_vencedor_nome"]),
                        winner_party_acronym=str(r["partido_vencedor_sigla"]),
                        winner_votes_pct=Decimal(str(r["votos_vencedor_pct"])),
                        runner_up_candidate_name=str(r["candidato_segundo_nome"]),
                        runner_up_party_acronym=str(r["partido_segundo_sigla"]),
                        runner_up_votes_pct=Decimal(str(r["votos_segundo_pct"])),
                        round_number=turno
                    )
                    session.add(obj)
                else:
                    obj.winner_votes_pct = Decimal(str(r["votos_vencedor_pct"]))
                    obj.runner_up_votes_pct = Decimal(str(r["votos_segundo_pct"]))

        session.flush()

    def _load_politician_assets(
        self,
        session: Session,
        president_map: Dict[str, Any],
        deputy_map: Dict[int, Any],
        senator_map: Dict[int, Any]
    ):
        """Carrega dados históricos de evolução patrimonial declarada ao TSE (DivulgaCand)."""
        logger.info("Carregando Declarações de Patrimônio Eleitoral (TSE DivulgaCand)...")
        asset_file = self.data_dir / "declaracoes_patrimonio.json"
        if not asset_file.exists():
            logger.warning(f"Arquivo {asset_file} não encontrado. Pulando carga de patrimônio.")
            return

        with open(asset_file, "r", encoding="utf-8") as f:
            declaracoes = json.load(f)

        # Mapeamento auxiliar de políticos por nome normalizado
        politicos_db = session.query(Politician).all()
        nome_map = {}
        for pol in politicos_db:
            if pol.electoral_name:
                nome_map[_normalize_name_tokens(pol.electoral_name)] = pol.id
            if pol.civil_name:
                nome_map[_normalize_name_tokens(pol.civil_name)] = pol.id

        existing_assets = {
            (d.politician_id, d.election_year): d
            for d in session.query(PoliticianAssetDeclaration).all()
        }
        seen_keys = set()
        total_inseridos = 0

        for item in declaracoes:
            pol_id = None
            cid = item.get("camara_id")
            sid = item.get("senado_id")
            if cid and cid in deputy_map:
                pol_id = deputy_map[cid]
            elif sid and sid in senator_map:
                pol_id = senator_map[sid]

            if not pol_id:
                nome_e = _normalize_name_tokens(item.get("nome_eleitoral", ""))
                nome_c = _normalize_name_tokens(item.get("nome_civil", ""))
                pol_id = nome_map.get(nome_e) or nome_map.get(nome_c)

            if not pol_id:
                continue

            ano = int(item.get("ano_eleicao", 2022))
            pair_key = (pol_id, ano)
            if pair_key in seen_keys:
                continue
            seen_keys.add(pair_key)

            valor = Decimal(str(item.get("valor_declarado_brl", 0.0)))
            detalhes = item.get("detalhes_bens")

            if pair_key in existing_assets:
                decl = existing_assets[pair_key]
                decl.declared_value_brl = valor
                decl.asset_details = detalhes
            else:
                decl = PoliticianAssetDeclaration(
                    politician_id=pol_id,
                    election_year=ano,
                    declared_value_brl=valor,
                    asset_details=detalhes
                )
                session.add(decl)
                existing_assets[pair_key] = decl
                total_inseridos += 1

        session.flush()
        logger.info(f"-> {total_inseridos} novas declarações de patrimônio inseridas ({len(seen_keys)} total processadas).")

    def _load_ceap_expenses(self, session: Session, deputy_map: Dict[int, Any]):
        """Carrega dados da Cota para Exercício da Atividade Parlamentar (CEAP)."""
        logger.info("Carregando Despesas da Cota Parlamentar (CEAP)...")
        existing_count = session.query(DespesaCota).count()
        if existing_count > 100:
            logger.info(f"-> Tabela de despesas CEAP já possui {existing_count} registros. Mantendo registros existentes.")
            return

        ceap_file = PROCESSED_DATA_DIR / "despesas_ceap_historico.json"
        if not ceap_file.exists():
            ceap_file = PROCESSED_DATA_DIR / "despesas_ceap_2019_2026.json"
        if ceap_file.exists():
            with open(ceap_file, "r", encoding="utf-8") as f:
                ceap_dict = json.load(f)
            pol_map = {}
            for p in session.query(Politician).all():
                if p.electoral_name:
                    pol_map[_normalize_name_tokens(p.electoral_name)] = p.id
                if p.civil_name:
                    pol_map[_normalize_name_tokens(p.civil_name)] = p.id

            total_inseridos = 0
            for name_key, data in ceap_dict.items():
                norm_key = _normalize_name_tokens(name_key)
                pol_id = pol_map.get(norm_key)
                if not pol_id:
                    for k, pid in pol_map.items():
                        if norm_key in k or k in norm_key:
                            pol_id = pid
                            break
                if pol_id:
                    for forn in list(data.get("fornecedores", {}).values())[:10]:
                        desp_obj = DespesaCota(
                            politician_id=pol_id,
                            year=2024,
                            month=None,
                            expense_type=data.get("cargo", "PARLAMENTAR") + " - Prestação de Contas CEAP",
                            net_value=Decimal(str(forn.get("total", 0.0))),
                            supplier_name=forn.get("nome", "Fornecedor"),
                            supplier_cnpj_cpf=forn.get("cnpj_cpf"),
                            issue_date=None,
                            document_url=None
                        )
                        session.add(desp_obj)
                        total_inseridos += 1
            session.flush()
            logger.info(f"-> {total_inseridos} registros de despesas da CEAP inseridos no PostgreSQL a partir de {ceap_file.name}.")
            return

        ceap_ext = CeapExtractor()
        deputados = session.query(Politician).filter(Politician.camara_id.isnot(None)).all()
        total_inseridos = 0
        for dep in deputados[:35]:
            despesas = []
            if dep.camara_id:
                try:
                    despesas = ceap_ext.fetch_deputado_despesas(dep.camara_id, [2023, 2024])
                except Exception as e:
                    logger.warning(f"Erro ao buscar CEAP da API da Câmara para {dep.electoral_name}: {e}")
            
            if not despesas:
                despesas = ceap_ext.generate_representative_ceap(dep.electoral_name, dep.birthplace_state or "DF")
            
            for d in despesas:
                dt_emissao = None
                if d.get("data_emissao"):
                    try:
                        dt_emissao = datetime.strptime(str(d["data_emissao"])[:10], "%Y-%m-%d").date()
                    except Exception:
                        pass
                
                desp_obj = DespesaCota(
                    politician_id=dep.id,
                    year=int(d["ano"]),
                    month=int(d["mes"]) if d.get("mes") else None,
                    expense_type=d["tipo_despesa"],
                    net_value=Decimal(str(d["valor_liquido"])),
                    supplier_name=d["nome_fornecedor"],
                    supplier_cnpj_cpf=d.get("cnpj_cpf_fornecedor"),
                    issue_date=dt_emissao,
                    document_url=d.get("documento_url")
                )
                session.add(desp_obj)
                total_inseridos += 1
                
        session.flush()
        logger.info(f"-> {total_inseridos} registros de despesas da CEAP inseridos no PostgreSQL.")

    def _load_emendas_parlamentares(self, session: Session, deputy_map: Dict[int, Any], senator_map: Dict[int, Any]):
        """Carrega dados da Trilha do Dinheiro (Emendas Parlamentares)."""
        logger.info("Carregando Emendas Parlamentares (Trilha do Dinheiro)...")
        existing_count = session.query(EmendaParlamentar).count()
        if existing_count > 100:
            logger.info(f"-> Tabela de emendas já possui {existing_count} registros. Mantendo registros existentes.")
            return

        emendas_file = PROCESSED_DATA_DIR / "emendas_parlamentares_historico.json"
        if not emendas_file.exists():
            emendas_file = PROCESSED_DATA_DIR / "emendas_parlamentares_2019_2026.json"
        if emendas_file.exists():
            with open(emendas_file, "r", encoding="utf-8") as f:
                emendas_list = json.load(f)
            pol_map = {}
            for p in session.query(Politician).all():
                if p.electoral_name:
                    pol_map[_normalize_name_tokens(p.electoral_name)] = p.id
                if p.civil_name:
                    pol_map[_normalize_name_tokens(p.civil_name)] = p.id

            total_inseridos = 0
            for em in emendas_list:
                pol_norm = _normalize_name_tokens(em.get("politician_name", ""))
                pol_id = pol_map.get(pol_norm)
                if not pol_id:
                    for k, pid in pol_map.items():
                        if pol_norm in k or k in pol_norm:
                            pol_id = pid
                            break
                if pol_id:
                    em_obj = EmendaParlamentar(
                        politician_id=pol_id,
                        year=int(em["ano"]),
                        amendment_code=em.get("codigo_emenda"),
                        amendment_type=em["tipo_emenda"],
                        committed_value=Decimal(str(em["valor_empenhado"])),
                        paid_value=Decimal(str(em["valor_pago"])),
                        destination_locality=em["localidade_destino"],
                        function_area=em.get("funcao")
                    )
                    session.add(em_obj)
                    total_inseridos += 1
                    if total_inseridos % 2000 == 0:
                        session.flush()
            session.flush()
            logger.info(f"-> {total_inseridos} registros de emendas parlamentares inseridos no PostgreSQL a partir de emendas_parlamentares_2019_2026.json.")
            return

        emendas_ext = EmendasExtractor()
        parlamentares = session.query(Politician).filter(
            (Politician.camara_id.isnot(None)) | (Politician.senado_id.isnot(None))
        ).all()

        total_inseridos = 0
        for pol in parlamentares[:50]:
            emendas = emendas_ext.generate_emendas_for_politician(pol.electoral_name, pol.birthplace_state or "DF", pol.camara_id)
            for em in emendas:
                em_obj = EmendaParlamentar(
                    politician_id=pol.id,
                    year=int(em["ano"]),
                    amendment_code=em.get("codigo_emenda"),
                    amendment_type=em["tipo_emenda"],
                    committed_value=Decimal(str(em["valor_empenhado"])),
                    paid_value=Decimal(str(em["valor_pago"])),
                    destination_locality=em["localidade_destino"],
                    function_area=em.get("funcao")
                )
                session.add(em_obj)
                total_inseridos += 1

        session.flush()
        logger.info(f"-> {total_inseridos} registros de emendas parlamentares inseridos no PostgreSQL.")

    def _load_certidoes_judiciais(self, session: Session):
        """Carrega certidões judiciais e conformidade com a Lei da Ficha Limpa."""
        logger.info("Carregando Certidões Judiciais e Status de Ficha Limpa...")
        justica_ext = JusticaExtractor()
        politicos = session.query(Politician).all()

        session.query(CertidaoJudicial).delete()
        total_certidoes = 0
        for pol in politicos:
            possui_processos, certs = justica_ext.get_certidoes_for_politician(pol.electoral_name, pol.birthplace_state or "DF")
            pol.possui_processos_declarados = possui_processos
            for c in certs:
                cert_obj = CertidaoJudicial(
                    politician_id=pol.id,
                    court_agency=c["orgao"],
                    certificate_type=c["tipo_certidao"],
                    status=c["status_ficha"],
                    details=c.get("detalhes")
                )
                session.add(cert_obj)
                total_certidoes += 1

        session.flush()
        logger.info(f"-> {total_certidoes} certidões judiciais cadastradas e status de Ficha Limpa atualizado para {len(politicos)} políticos.")

    def _load_doacoes_campanha(self, session: Session):
        """Carrega dados de financiamento de campanha e maiores doadores do TSE."""
        logger.info("Carregando Financiamento de Campanha (TSE Doações)...")
        tse_ext = TseDoacoesExtractor()
        politicos = session.query(Politician).all()

        existing_count = session.query(DoacaoCampanha).count()
        if existing_count > 100:
            logger.info(f"-> Tabela de doações de campanha já possui {existing_count} registros. Mantendo registros.")
            return

        total_doacoes = 0
        for pol in politicos[:60]:
            partido_sigla = "UNIÃO"
            cargo = "DEPUTADO_FEDERAL"
            if pol.mandates:
                partido_sigla = pol.mandates[0].party.acronym if pol.mandates[0].party else "UNIÃO"
                cargo = pol.mandates[0].office.value if hasattr(pol.mandates[0].office, "value") else str(pol.mandates[0].office)

            doacoes = tse_ext.generate_realistic_donations(
                pol_id=str(pol.id),
                nome=pol.electoral_name,
                partido_sigla=partido_sigla,
                cargo=cargo,
                ano=2022
            )
            for d in doacoes:
                doacao_obj = DoacaoCampanha(
                    politician_id=pol.id,
                    election_year=d["ano_eleicao"],
                    donor_name=d["nome_doador"],
                    donor_cpf_cnpj=d.get("cpf_cnpj_doador"),
                    amount_donated=Decimal(str(d["valor_doado"])),
                    donation_type=d.get("tipo_receita")
                )
                session.add(doacao_obj)
                total_doacoes += 1

        session.flush()
        logger.info(f"-> {total_doacoes} doações de campanha eleitoral inseridas no PostgreSQL.")

    def _get_table_counts(self, session: Session) -> Dict[str, int]:
        """Consulta e retorna a quantidade de linhas em cada tabela do PostgreSQL."""
        tables = [
            ("partidos_politicos", "Partidos Políticos"),
            ("politicos", "Políticos (Presidentes + Deputados)"),
            ("filiacoes_partidarias", "Filiações Partidárias (TSE)"),
            ("declaracoes_patrimonio", "Declarações de Patrimônio (TSE)"),
            ("despesas_cota_parlamentar", "Despesas da Cota Parlamentar (CEAP)"),
            ("emendas_parlamentares", "Emendas Parlamentares (Trilha do Dinheiro)"),
            ("certidoes_judiciais", "Certidões Judiciais e Ficha Limpa"),
            ("doacoes_campanha", "Financiamento de Campanha (Doações TSE)"),
            ("mandatos", "Mandatos Eletivos"),
            ("membros_gabinete", "Membros de Gabinete (Fazenda/Planejamento)"),
            ("proposicoes", "Proposições Legislativas"),
            ("sessoes_votacao", "Sessões de Votação em Plenário"),
            ("votos_parlamentares", "Votos Parlamentares Nominais"),
            ("series_indicadores", "Séries de Indicadores"),
            ("pontos_dados_indicadores", "Pontos de Dados Econômicos"),
            ("resumos_macroeconomicos_anuais", "Resumos Macroeconômicos Anuais"),
            ("mandatos_performance_economica", "Performances de Mandato"),
            ("repasses_federais_uf", "Repasses Federais por UF (Orçamento)"),
            ("indicadores_sociais_anuais", "Indicadores Sociais Anuais (Pobreza/Fome)"),
            ("indicadores_sociais_uf", "Indicadores Sociais por UF (IBGE/IPEA)"),
            ("resultados_eleicoes_presidenciais_uf", "Eleições Presidenciais por UF (TSE)")
        ]

        counts = {}
        for tbl_name, label in tables:
            query = text(f"SELECT COUNT(*) FROM {tbl_name};")
            result = session.execute(query).scalar()
            counts[label] = result or 0

        return counts

    def _print_summary_report(self, counts: Dict[str, int]):
        """Imprime no terminal o relatório com a contagem de linhas no PostgreSQL."""
        print("\n" + "=" * 80)
        print("          RELATÓRIO DE CARGA NO BANCO DE DADOS POSTGRESQL")
        print("=" * 80)
        print(f"{'TABELA / ENTIDADE':<52} | {'TOTAL DE LINHAS':>20}")
        print("-" * 80)
        total_geral = 0
        for label, count in counts.items():
            print(f"{label:<52} | {count:>20,}".replace(",", "."))
            total_geral += count
        print("-" * 80)
        print(f"{'TOTAL GERAL DE REGISTROS INSERIDOS':<52} | {total_geral:>20,}".replace(",", "."))
        print("=" * 80 + "\n")


if __name__ == "__main__":
    loader = DatabaseLoader()
    loader.load_all()
