"""
Pipeline de Carga de Dados no Banco de Dados PostgreSQL (DB Loader)
Lê os arquivos processados (.json e .csv) e executa upsert relacional completo via SQLAlchemy.

Princípios (ver revisão do ETL):
  * identificação de pessoas por ID oficial (camara_id/senado_id) e, na falta dele, por nome COMPLETO normalizado
    e INEQUÍVOCO — nunca por substring/primeiro match;
  * nenhum dado é inventado: contatos, datas, números de processo, certidões, doações, emendas e patrimônio só
    entram no banco quando a fonte traz proveniência (`fonte`, `is_synthetic=False`);
  * dados sintéticos só entram com `allow_synthetic=True` (CLI: --allow-synthetic) e carregam marcação textual;
  * cargas idempotentes por chave natural (rodar duas vezes não duplica nem deixa dados antigos errados).
"""

import argparse
import logging
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from etl.utils.bootstrap import ensure_backend_on_path

ensure_backend_on_path()

from app.core.database import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    CabinetMember,
    CargoPoliticoEnum,
    CasaLegislativaEnum,
    EspectroPoliticoEnum,
    Mandate,
    MotivoDesfiliacaoEnum,
    ParliamentaryVote,
    PartyAffiliation,
    PoliticalParty,
    Politician,
    Proposition,
    StatusMandatoEnum,
    StatusTramitacaoEnum,
    TipoEsferaEnum,
    TipoProposicaoEnum,
    VotingSession,
    VotoOpcaoEnum,
)

from etl.config import PROCESSED_DATA_DIR  # noqa: E402
from etl.pipelines.loader_helpers import (  # noqa: E402,F401
    LEGISLATURA_ATUAL,
    LEGISLATURA_ATUAL_INICIO,
    SEM_PARTIDO,
    AuthorResolver,
    _dec,
    _texto_ou_none,
    _to_date,
    _to_datetime,
    classify_proposition_impact,
    legislatura_datas,
    limpar_contatos_inventados,
    resolve_party_id,
)
from etl.pipelines.votacoes_loader import carregar_parlamentares_historicos, carregar_votacoes  # noqa: E402
from etl.utils.datafiles import load_deputados, load_json, load_senadores  # noqa: E402
from etl.utils.names import build_unique_name_map, normalize_name_tokens  # noqa: E402
from etl.utils.provenance import is_synthetic, is_trusted  # noqa: E402

logger = logging.getLogger("DBLoader")

# Compatibilidade com o nome privado anterior
_normalize_name_tokens = normalize_name_tokens

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

# Nomes completos de partidos extintos/renomeados que aparecem em filiações históricas e votos. Sem isto,
# cada um deles virava "Sem Partido" e a trajetória partidária de quem passou por eles era apagada.
PARTY_FULL_NAMES = {
    "PTB": "Partido Trabalhista Brasileiro",
    "PATRIOTA": "Patriota",
    "PATRI": "Patriota",
    "PROS": "Partido Republicano da Ordem Social",
    "PSC": "Partido Social Cristão",
    "PRP": "Partido Republicano Progressista",
    "PHS": "Partido Humanista da Solidariedade",
    "PPS": "Partido Popular Socialista",
    "PRB": "Partido Republicano Brasileiro",
    "PMN": "Partido da Mobilização Nacional",
    "PEN": "Partido Ecológico Nacional",
    "PR": "Partido da República",
    "PDS": "Partido Democrático Social",
    "PPB": "Partido Progressista Brasileiro",
    "PPR": "Partido Progressista Reformador",
    "PC DO B": "Partido Comunista do Brasil",
}


PARTY_LOGOS_MAP = {
    "PT": "https://thumb.wikimedia.org/wikipedia/commons/thumb/c/c3/PT_%28Brazil%29_logo_2021.svg/250px-PT_%28Brazil%29_logo_2021.svg.png",
    "PL": "https://thumb.wikimedia.org/wikipedia/commons/thumb/1/12/Partido_Liberal_%28Brazil%29_logo.svg/250px-Partido_Liberal_%28Brazil%29_logo.svg.png",
    "PSDB": "https://thumb.wikimedia.org/wikipedia/commons/thumb/2/22/Logo_of_the_Brazilian_Social_Democracy_Party_%282023%29.svg/250px-Logo_of_the_Brazilian_Social_Democracy_Party_%282023%29.svg.png",
    "MDB": "https://thumb.wikimedia.org/wikipedia/commons/thumb/e/ef/Movimento_Democr%C3%A1tico_Brasileiro_%282017%29.svg/250px-Movimento_Democr%C3%A1tico_Brasileiro_%282017%29.svg.png",
    "PMDB": "https://thumb.wikimedia.org/wikipedia/commons/thumb/c/cc/PMDB_2000_a_2017.svg/250px-PMDB_2000_a_2017.svg.png",
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
    "DC": "https://thumb.wikimedia.org/wikipedia/commons/thumb/e/ed/Logomarca_Democracia_Crist%C3%A3.svg/250px-Logomarca_Democracia_Crist%C3%A3.svg.png",
    "DEM": "https://thumb.wikimedia.org/wikipedia/commons/thumb/3/39/Democratas_%28Brazil%29_logo_%282018-2022%29_%28horizontal%29.svg/250px-Democratas_%28Brazil%29_logo_%282018-2022%29_%28horizontal%29.svg.png",
    "PATRIOTA": "https://thumb.wikimedia.org/wikipedia/commons/thumb/f/f9/Logomarca_do_Partido_Patriota.png/250px-Logomarca_do_Partido_Patriota.png",
    "PFL": "https://thumb.wikimedia.org/wikipedia/commons/thumb/e/e7/Partido_da_Frente_Liberal_logo_%281985-2005%29.svg/250px-Partido_da_Frente_Liberal_logo_%281985-2005%29.svg.png",
    "PRTB": "https://thumb.wikimedia.org/wikipedia/commons/thumb/d/d5/Logomarca_do_Partido_Renovador_Trabalhista_Brasileiro_2.png/250px-Logomarca_do_Partido_Renovador_Trabalhista_Brasileiro_2.png",
    "PTB": "https://thumb.wikimedia.org/wikipedia/commons/thumb/6/6a/Logomarca_Partido_Trabalhista_Brasileiro.png/250px-Logomarca_Partido_Trabalhista_Brasileiro.png",
    "MISSÃO": "https://thumb.wikimedia.org/wikipedia/commons/thumb/6/67/Partido_Miss%C3%A3o_logo_%28light%29.svg/250px-Partido_Miss%C3%A3o_logo_%28light%29.svg.png",
    "PROS": "https://thumb.wikimedia.org/wikipedia/commons/thumb/e/ee/Logomarca_do_Partido_Republicano_da_Ordem_Social_%28PROS%29%2C_do_Brasil.png/250px-Logomarca_do_Partido_Republicano_da_Ordem_Social_%28PROS%29%2C_do_Brasil.png",
    "PSC": "https://thumb.wikimedia.org/wikipedia/commons/thumb/a/a9/PSC_logo%28cortado%29.png/250px-PSC_logo%28cortado%29.png",
    "PSL": "https://thumb.wikimedia.org/wikipedia/commons/thumb/c/c2/Partido_Social_Liberal_logo.svg/250px-Partido_Social_Liberal_logo.svg.png",
    "PR": "https://thumb.wikimedia.org/wikipedia/commons/thumb/f/fe/Logomarca_do_Partido_da_Rep%C3%BAblica.png/250px-Logomarca_do_Partido_da_Rep%C3%BAblica.png",
    "PPS": "https://thumb.wikimedia.org/wikipedia/commons/thumb/d/d3/Logomarca_do_Partido_Popular_Socialista.png/250px-Logomarca_do_Partido_Popular_Socialista.png",
    "PRB": "https://thumb.wikimedia.org/wikipedia/commons/thumb/a/a2/Logomarca_do_Partido_Republicano_Brasileiro_%282012%E2%80%932019%29.png/250px-Logomarca_do_Partido_Republicano_Brasileiro_%282012%E2%80%932019%29.png",
    "PHS": "https://thumb.wikimedia.org/wikipedia/commons/thumb/7/75/Logo_-_Partido_Humanista_da_Solidariedade.png/250px-Logo_-_Partido_Humanista_da_Solidariedade.png",
    "PMN": "https://thumb.wikimedia.org/wikipedia/commons/thumb/d/dd/PMN_logo.svg/250px-PMN_logo.svg.png",
    "PSDC": "https://thumb.wikimedia.org/wikipedia/commons/thumb/a/aa/Bandeira_do_Partido_Social_Democrata_Crist%C3%A3o.svg/250px-Bandeira_do_Partido_Social_Democrata_Crist%C3%A3o.svg.png",
    "PDC": "https://thumb.wikimedia.org/wikipedia/commons/thumb/6/65/Bandeirapdc85melhorada.png/250px-Bandeirapdc85melhorada.png",
    "PDS": "https://thumb.wikimedia.org/wikipedia/commons/thumb/a/a9/Partido_Democr%C3%A1tico_Social_logo.svg/250px-Partido_Democr%C3%A1tico_Social_logo.svg.png",
    "PRONA": "https://thumb.wikimedia.org/wikipedia/commons/thumb/c/ca/Partido_de_Reedifica%C3%A7%C3%A3o_da_Ordem_Nacional_logo_%282004%E2%80%932006%29.png/250px-Partido_de_Reedifica%C3%A7%C3%A3o_da_Ordem_Nacional_logo_%282004%E2%80%932006%29.png",
}

PARTY_METADATA_MAP = {
    "PT": {
        "ideologia": "Social-democracia / Trabalhismo democrático",
        "lema": "O Brasil da esperança e da justiça social",
        "espectro": EspectroPoliticoEnum.ESQUERDA,
        "numero": 13,
    },
    "PL": {
        "ideologia": "Conservadorismo social / Liberalismo econômico",
        "lema": "Deus, Pátria, Família e Liberdade",
        "espectro": EspectroPoliticoEnum.DIREITA,
        "numero": 22,
    },
    "UNIÃO": {
        "ideologia": "Liberalismo / Conservadorismo liberal",
        "lema": "Coragem para mudar, união para governar",
        "espectro": EspectroPoliticoEnum.CENTRO_DIREITA,
        "numero": 44,
    },
    "PP": {
        "ideologia": "Centro-direita / Pragmatismo de desenvolvimento",
        "lema": "O futuro se constrói com trabalho e progresso",
        "espectro": EspectroPoliticoEnum.CENTRO_DIREITA,
        "numero": 11,
    },
    "MDB": {
        "ideologia": "Centrismo / Ponto de equilíbrio democrático",
        "lema": "O partido que equilibra o Brasil",
        "espectro": EspectroPoliticoEnum.CENTRO,
        "numero": 15,
    },
    "PSD": {
        "ideologia": "Pragmatismo de centro / Municipalismo",
        "lema": "Nem direita, nem esquerda: a favor do Brasil",
        "espectro": EspectroPoliticoEnum.CENTRO,
        "numero": 55,
    },
    "REPUBLICANOS": {
        "ideologia": "Conservadorismo cristão / Municipalismo",
        "lema": "Defendendo os valores da família e o desenvolvimento",
        "espectro": EspectroPoliticoEnum.CENTRO_DIREITA,
        "numero": 10,
    },
    "PSDB": {
        "ideologia": "Social-democracia clássica / Terceira via",
        "lema": "Por um Brasil moderno, justo e eficiente",
        "espectro": EspectroPoliticoEnum.CENTRO,
        "numero": 45,
    },
    "PSB": {
        "ideologia": "Socialismo democrático / Progressismo",
        "lema": "Igualdade e liberdade construídas com justiça",
        "espectro": EspectroPoliticoEnum.CENTRO_ESQUERDA,
        "numero": 40,
    },
    "PDT": {
        "ideologia": "Trabalhismo brizolista / Nacionalismo desenvolvimentista",
        "lema": "A educação emancipa, o trabalho dignifica",
        "espectro": EspectroPoliticoEnum.CENTRO_ESQUERDA,
        "numero": 12,
    },
    "PSOL": {
        "ideologia": "Socialismo democrático / Ecossocialismo",
        "lema": "Por um Brasil para a maioria trabalhadora",
        "espectro": EspectroPoliticoEnum.ESQUERDA,
        "numero": 50,
    },
    "PODE": {
        "ideologia": "Democracia direta / Centrismo liberal",
        "lema": "Juntos podemos transformar o Brasil",
        "espectro": EspectroPoliticoEnum.CENTRO,
        "numero": 20,
    },
    "PODEMOS": {
        "ideologia": "Democracia direta / Centrismo liberal",
        "lema": "Juntos podemos transformar o Brasil",
        "espectro": EspectroPoliticoEnum.CENTRO,
        "numero": 20,
    },
    "NOVO": {
        "ideologia": "Liberalismo clássico / Estado mínimo",
        "lema": "Menos governo, mais liberdade individual",
        "espectro": EspectroPoliticoEnum.DIREITA,
        "numero": 30,
    },
    "PCdoB": {
        "ideologia": "Comunismo democrático / Antimperialismo",
        "lema": "Pela soberania nacional e o socialismo",
        "espectro": EspectroPoliticoEnum.ESQUERDA,
        "numero": 65,
    },
    "PV": {
        "ideologia": "Ecologismo / Desenvolvimento sustentável",
        "lema": "Paz, ecologia e justiça socioambiental",
        "espectro": EspectroPoliticoEnum.CENTRO_ESQUERDA,
        "numero": 43,
    },
    "CIDADANIA": {
        "ideologia": "Social-liberalismo / Terceira via",
        "lema": "Construindo cidadania plena e oportunidades",
        "espectro": EspectroPoliticoEnum.CENTRO,
        "numero": 23,
    },
    "REDE": {
        "ideologia": "Sustentabilidade ética / Progressismo cívico",
        "lema": "Conectar pessoas pela ética na política",
        "espectro": EspectroPoliticoEnum.CENTRO_ESQUERDA,
        "numero": 18,
    },
    "AVANTE": {
        "ideologia": "Humanismo cívico / Municipalismo",
        "lema": "O Brasil precisa seguir avante",
        "espectro": EspectroPoliticoEnum.CENTRO,
        "numero": 70,
    },
    "SOLIDARIEDADE": {
        "ideologia": "Trabalhismo social / Sindicalismo plural",
        "lema": "Solidariedade com o trabalhador e o desenvolvimento",
        "espectro": EspectroPoliticoEnum.CENTRO,
        "numero": 77,
    },
    "PRD": {
        "ideologia": "Conservadorismo democrático",
        "lema": "Renovação e ordem institucional",
        "espectro": EspectroPoliticoEnum.CENTRO_DIREITA,
        "numero": 25,
    },
    "DC": {
        "ideologia": "Democracia cristã / Conservadorismo social",
        "lema": "Deus, pátria e família",
        "espectro": EspectroPoliticoEnum.DIREITA,
        "numero": 27,
    },
    "DEM": {
        "ideologia": "Liberalismo / Conservadorismo liberal",
        "lema": "A favor do Brasil",
        "espectro": EspectroPoliticoEnum.CENTRO_DIREITA,
        "numero": 25,
    },
    "PATRIOTA": {
        "ideologia": "Conservadorismo / Nacionalismo",
        "lema": "Brasil acima de tudo",
        "espectro": EspectroPoliticoEnum.DIREITA,
        "numero": 51,
    },
    "PFL": {
        "ideologia": "Liberalismo conservador",
        "lema": "Construindo o futuro",
        "espectro": EspectroPoliticoEnum.CENTRO_DIREITA,
        "numero": 25,
    },
    "PMDB": {
        "ideologia": "Centrismo / Democracia partidária",
        "lema": "O partido do Brasil",
        "espectro": EspectroPoliticoEnum.CENTRO,
        "numero": 15,
    },
    "PRTB": {
        "ideologia": "Trabalhismo participativo / Conservadorismo",
        "lema": "Coragem para transformar",
        "espectro": EspectroPoliticoEnum.DIREITA,
        "numero": 28,
    },
    "PTB": {
        "ideologia": "Trabalhismo / Conservadorismo",
        "lema": "A força do trabalhador",
        "espectro": EspectroPoliticoEnum.DIREITA,
        "numero": 14,
    },
    "MISSÃO": {
        "ideologia": "Liberalismo econômico / Renovação política",
        "lema": "Missão pelo futuro do Brasil",
        "espectro": EspectroPoliticoEnum.CENTRO_DIREITA,
        "numero": 99,
    },
    "PROS": {
        "ideologia": "Centrismo / Reformismo social",
        "lema": "Por um Brasil justo e fraterno",
        "espectro": EspectroPoliticoEnum.CENTRO,
        "numero": 90,
    },
    "PSC": {
        "ideologia": "Democracia cristã / Conservadorismo cristão",
        "lema": "O ser humano em primeiro lugar",
        "espectro": EspectroPoliticoEnum.CENTRO_DIREITA,
        "numero": 20,
    },
    "PSL": {
        "ideologia": "Conservadorismo / Liberalismo",
        "lema": "Mais Brasil, menos Brasília",
        "espectro": EspectroPoliticoEnum.DIREITA,
        "numero": 17,
    },
}

# Chaves em maiúsculas para correspondência uniforme
PARTY_LOGOS_MAP = {k.upper(): v for k, v in PARTY_LOGOS_MAP.items()}
PARTY_METADATA_MAP = {k.upper(): v for k, v in PARTY_METADATA_MAP.items()}

# Arquivos legados de votação do Senado não traziam o ano da matéria; as duas matérias coletadas são conhecidas.
from etl.extractors.senado_extractor import MATERIAS_BUSCA  # noqa: E402

MATERIA_ANO_CONHECIDA = {(m["sigla"], m["numero"]): m["ano"] for m in MATERIAS_BUSCA}

SUPPLIER_CONSOLIDADO = "Consolidado por tipo de despesa"


class DatabaseLoader:
    """Gerencia a carga e sincronização de dados no PostgreSQL."""

    def __init__(
        self,
        data_dir: Path = PROCESSED_DATA_DIR,
        allow_synthetic: bool = False,
        allow_unverified: bool = False,
    ):
        self.data_dir = Path(data_dir)
        self.allow_synthetic = allow_synthetic
        self.allow_unverified = allow_unverified

    def ensure_tables(self):
        """Aplica as migrações Alembic, únicas donas do schema (as tabelas de `stg` nascem delas)."""
        logger.info("Aplicando as migrações do schema no PostgreSQL...")
        from app.core.migrations import upgrade_schema

        upgrade_schema()

    # ------------------------------------------------------------------ orquestração
    def load_all(self) -> Dict[str, int]:
        """Executa a carga completa respeitando as dependências de chaves estrangeiras (uma transação)."""
        self.ensure_tables()

        session: Session = SessionLocal()
        # A sessão do backend usa autoflush=False: sem isto, consultas feitas logo após um `add` não enxergavam
        # o objeto pendente (checagens de unicidade passavam e estouravam UniqueViolation no commit).
        session.autoflush = True
        try:
            logger.info("=" * 70)
            logger.info("INICIANDO CARGA DE DADOS NO POSTGRESQL")
            logger.info("=" * 70)

            etapas = 6
            n = 0

            def etapa(descricao: str) -> None:
                nonlocal n
                n += 1
                logger.info(f"[{n}/{etapas}] {descricao}")

            etapa("Partidos Políticos")
            party_map = self._load_political_parties(session)

            etapa("Políticos (Presidentes, Deputados e Senadores)")
            president_map, deputy_map, senator_map = self._load_politicians(session)

            etapa("Filiações Partidárias")
            self._load_party_affiliations(session, deputy_map, senator_map, party_map)

            etapa("Mandatos e Gabinete Presidencial")
            self._load_mandates(session, president_map, deputy_map, senator_map, party_map)
            # Ex-parlamentares (legislaturas anteriores) entram antes de CEAP/emendas: sem eles esses registros ficavam sem vínculo.
            carregar_parlamentares_historicos(
                session, self.data_dir, deputy_map, senator_map, party_map, self._ensure_party
            )

            etapa("Proposições Legislativas")
            prop_map = self._load_propositions(session, deputy_map, senator_map)

            etapa("Sessões de Votação e Votos Parlamentares")
            self._load_voting_sessions_and_votes(session, prop_map, deputy_map, senator_map, party_map)
            carregar_votacoes(session, self.data_dir, deputy_map, senator_map, party_map, self._ensure_party)

            session.commit()
            logger.info("Transação confirmada com sucesso no PostgreSQL!")

            # Ponte transitória: projeta o schema legado no schema core (pessoa, partido, filiação, mandato)
            self._sincronizar_core(session)

            counts = self._get_table_counts(session)
            self._print_summary_report(counts)
            return counts

        except Exception as e:
            session.rollback()
            logger.error(f"Erro durante a carga no banco: {e}", exc_info=True)
            raise
        finally:
            session.close()

    @staticmethod
    def _sincronizar_core(session: Session) -> None:
        """Projeta o legado no schema core. Falha aqui não desfaz a carga (já confirmada), mas é registrada."""
        from app.services.staging_merge import merge_staging

        try:
            merge_staging(session)
        except Exception as exc:  # noqa: BLE001 - a carga principal já foi confirmada
            session.rollback()
            logger.error("Sincronização legado -> core falhou: %s", exc, exc_info=True)

    # ------------------------------------------------------------------ utilidades de proveniência
    def _usable(self, record: Dict[str, Any]) -> bool:
        """Registro com proveniência e não sintético; sintético só com `allow_synthetic` (e marcado no texto)."""
        if is_trusted(record):
            return True
        return self.allow_synthetic and is_synthetic(record)

    # ------------------------------------------------------------------ partidos
    def _load_political_parties(self, session: Session) -> Dict[str, Any]:
        """Carrega partidos a partir de presidentes, deputados, senadores e filiações (inclui extintos)."""
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
            SEM_PARTIDO: "Sem Partido",
        }

        # Siglas presentes nas fontes — inclusive partidos extintos citados só em filiações históricas
        siglas_fontes: List[str] = []
        siglas_fontes += [d.get("partido_sigla") for d in load_deputados(self.data_dir)]
        siglas_fontes += [s.get("partido_sigla") for s in load_senadores(self.data_dir)]
        siglas_fontes += [
            f.get("partido_sigla") for f in (load_json(self.data_dir / "filiacoes_partidarias.json", []) or [])
        ]
        siglas_fontes += [
            p.get("partido_sigla") for p in (load_json(self.data_dir / "presidentes_historico.json", []) or [])
        ]
        conhecidas_upper = {k.upper() for k in parties_to_insert}
        for sigla in siglas_fontes:
            if sigla and isinstance(sigla, str) and sigla.upper() not in conhecidas_upper:
                parties_to_insert[sigla] = PARTY_FULL_NAMES.get(sigla.upper(), f"Partido {sigla}")
                conhecidas_upper.add(sigla.upper())

        existing_keys_upper = {k.upper(): k for k in parties_to_insert}
        for p_sigla in PARTY_METADATA_MAP:  # chaves já em maiúsculas
            if p_sigla not in existing_keys_upper and p_sigla != "PODEMOS":
                parties_to_insert[p_sigla] = f"Partido {p_sigla}"
                existing_keys_upper[p_sigla] = p_sigla

        party_map: Dict[str, Any] = {}
        for sigla, nome in parties_to_insert.items():
            if sigla.upper() == "PODEMOS" and "PODE" in existing_keys_upper:
                continue
            meta = PARTY_METADATA_MAP.get(sigla.upper(), {})
            # Partidos sem metadados curados ficam SEM ideologia/lema/espectro (antes recebiam
            # "Centrismo Democrático" e um lema genérico, ou seja, texto inventado).
            ideologia = meta.get("ideologia")
            lema = meta.get("lema")
            num_eleitoral = meta.get("numero")
            spectrum = meta.get("espectro") or PARTY_SPECTRUM_MAP.get(sigla.upper())
            logo_url = meta.get("logo_url") or PARTY_LOGOS_MAP.get(sigla.upper())

            party = session.query(PoliticalParty).filter(func.upper(PoliticalParty.acronym) == sigla.upper()).first()

            # Número eleitoral já usado por outro partido => não repetir (evita UniqueViolation)
            if num_eleitoral:
                existing_num = (
                    session.query(PoliticalParty)
                    .filter(
                        PoliticalParty.electoral_number == num_eleitoral,
                        func.upper(PoliticalParty.acronym) != sigla.upper(),
                    )
                    .first()
                )
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
                    logo_url=logo_url,
                )
                session.add(party)
                session.flush()
            else:
                if spectrum:
                    party.political_spectrum = spectrum
                if ideologia:
                    party.ideology = ideologia
                if lema:
                    party.motto = lema
                if logo_url:
                    party.logo_url = logo_url
                if num_eleitoral:
                    party.electoral_number = num_eleitoral
            party_map[sigla] = party.id
            party_map.setdefault(sigla.upper(), party.id)

        logger.info(f"-> {len({v for v in party_map.values()})} partidos mapeados/carregados.")
        return party_map

    def _ensure_party(self, session: Session, party_map: Dict[str, Any], sigla: str) -> Any:
        """Garante um partido para a sigla (partidos extintos citados em filiações viravam 'Sem Partido')."""
        existente = resolve_party_id(party_map, sigla)
        if existente:
            return existente
        party = session.query(PoliticalParty).filter(func.upper(PoliticalParty.acronym) == sigla.upper()).first()
        if not party:
            party = PoliticalParty(
                acronym=sigla,
                full_name=PARTY_FULL_NAMES.get(sigla.upper(), f"Partido {sigla}"),
                political_spectrum=PARTY_SPECTRUM_MAP.get(sigla.upper()),
            )
            session.add(party)
            session.flush()
        party_map[sigla] = party.id
        party_map.setdefault(sigla.upper(), party.id)
        return party.id

    # ------------------------------------------------------------------ políticos
    def _load_politicians(self, session: Session) -> Tuple[Dict[str, Any], Dict[int, Any], Dict[int, Any]]:
        """Carrega presidentes, deputados e senadores. Só grava contatos que a fonte informa."""
        president_map: Dict[str, Any] = {}
        deputy_map: Dict[int, Any] = {}
        senator_map: Dict[int, Any] = {}
        contatos_limpos = 0

        for p in load_json(self.data_dir / "presidentes_historico.json", []) or []:
            ref_id = p["id_referencia"]
            nome_eleitoral = p["nome_eleitoral"]
            pol = (
                session.query(Politician)
                .filter((Politician.civil_name == p["nome_civil"]) | (Politician.electoral_name == nome_eleitoral))
                .first()
            )

            if not pol:
                pol = Politician(
                    civil_name=p["nome_civil"],
                    electoral_name=nome_eleitoral,
                    birth_date=_to_date(p.get("data_nascimento")),
                    death_date=_to_date(p.get("data_falecimento")),
                    gender=p.get("genero"),
                    birthplace_city=p.get("naturalidade_municipio"),
                    birthplace_state=p.get("naturalidade_uf"),
                    photo_url=p.get("foto_url"),
                    biography=f"Presidente da República. Eleição: {p.get('ano_eleicao')}. Status: {p.get('status_mandato')}.",
                )
                session.add(pol)
                session.flush()
            president_map[ref_id] = pol.id

        for d in load_deputados(self.data_dir):  # deduplicado por camara_id
            cid = d["camara_id"]
            pol = session.query(Politician).filter_by(camara_id=cid).first()
            legislatura = d.get("id_legislatura")
            bio = f"Deputado Federal pela UF {d.get('uf')} ({d.get('partido_sigla')})."
            if legislatura:
                bio = f"Deputado Federal pela UF {d.get('uf')} ({d.get('partido_sigla')}). Legislatura {legislatura}."

            if not pol:
                pol = Politician(
                    civil_name=d.get("nome_civil") or d.get("nome_eleitoral"),
                    electoral_name=d.get("nome_eleitoral"),
                    camara_id=cid,
                    photo_url=d.get("foto_url"),
                    birth_date=_to_date(d.get("data_nascimento")),
                    gender=d.get("sexo"),
                    # A UF do deputado é a ELEITORAL; naturalidade só vem do endpoint de detalhe.
                    birthplace_state=d.get("uf_nascimento"),
                    birthplace_city=d.get("municipio_nascimento"),
                    email=d.get("email"),
                    cabinet_room=d.get("gabinete_sala"),
                    cabinet_phone=d.get("gabinete_telefone"),
                    biography=bio,
                )
                session.add(pol)
                session.flush()
            else:
                contatos_limpos += int(limpar_contatos_inventados(pol))
                # Preenche apenas com dado real da fonte; nunca com valor derivado do id.
                for attr, chave in (
                    ("email", "email"),
                    ("cabinet_room", "gabinete_sala"),
                    ("cabinet_phone", "gabinete_telefone"),
                    ("birthplace_state", "uf_nascimento"),
                    ("birthplace_city", "municipio_nascimento"),
                    ("gender", "sexo"),
                ):
                    if not getattr(pol, attr) and d.get(chave):
                        setattr(pol, attr, d[chave])
                if not pol.birth_date and d.get("data_nascimento"):
                    pol.birth_date = _to_date(d["data_nascimento"])
            deputy_map[cid] = pol.id

        for s in load_senadores(self.data_dir):  # deduplicado por senado_id
            sid = s["senado_id"]
            pol = session.query(Politician).filter_by(senado_id=sid).first()
            if not pol:
                pol = Politician(
                    civil_name=s.get("nome_civil") or s.get("nome_eleitoral"),
                    electoral_name=s.get("nome_eleitoral"),
                    senado_id=sid,
                    photo_url=s.get("foto_url"),
                    email=s.get("email"),
                    cabinet_room=s.get("gabinete_sala"),
                    cabinet_phone=s.get("gabinete_telefone"),
                    biography=f"Senador Federal pela UF {s.get('uf')} ({s.get('partido_sigla')}).",
                )
                session.add(pol)
                session.flush()
            else:
                contatos_limpos += int(limpar_contatos_inventados(pol))
                if not pol.email and s.get("email"):
                    pol.email = s["email"]
            senator_map[sid] = pol.id

        if contatos_limpos:
            logger.info(f"-> {contatos_limpos} políticos tiveram contatos sintéticos legados removidos.")
        logger.info(
            f"-> Políticos carregados: {len(president_map)} mandatos presidenciais, {len(deputy_map)} deputados e {len(senator_map)} senadores."
        )
        return president_map, deputy_map, senator_map

    # ------------------------------------------------------------------ filiações
    def _load_party_affiliations(
        self,
        session: Session,
        deputy_map: Dict[int, Any],
        senator_map: Dict[int, Any],
        party_map: Dict[str, Any],
    ) -> int:
        """Carrega histórico de filiações. Identifica o político por id oficial; nome só se for único."""
        filiacoes = load_json(self.data_dir / "filiacoes_partidarias.json", None)
        if filiacoes is None:
            logger.warning("Arquivo filiacoes_partidarias.json não encontrado. Pulando carga.")
            return 0

        name_to_pol_id = build_unique_name_map(
            [(p.id, p.electoral_name) for p in session.query(Politician).all() if p.electoral_name]
        )

        existing_affs = set(
            session.query(PartyAffiliation.politician_id, PartyAffiliation.party_id, PartyAffiliation.start_date).all()
        )

        inserted = 0
        sem_politico = 0
        data_estimada = 0
        sem_proveniencia = 0
        for item in filiacoes:
            if is_synthetic(item) and not self.allow_synthetic:
                continue
            if not item.get("fonte") and not self.allow_unverified:
                sem_proveniencia += 1  # legado: origens/datas de filiação eram sorteadas por `idx % N`
                continue
            cid = item.get("camara_id")
            sid = item.get("senado_id")
            pol_id = None
            if cid and cid in deputy_map:
                pol_id = deputy_map[cid]
            elif sid and sid in senator_map:
                pol_id = senator_map[sid]
            else:
                pol_id = name_to_pol_id.get(normalize_name_tokens(item.get("politico_nome")))

            if not pol_id:
                sem_politico += 1
                continue

            sigla = item.get("partido_sigla")
            party_id = self._ensure_party(session, party_map, sigla) if sigla else party_map.get(SEM_PARTIDO)
            if not party_id:
                continue

            dt_fil = _to_date(item.get("data_filiacao"))
            if dt_fil is None:
                # A data de filiação é desconhecida. A filiação ATUAL é um fato (vem das APIs); só a data não.
                # Usa o início da legislatura como LIMITE INFERIOR de observação (campo é obrigatório).
                dt_fil = LEGISLATURA_ATUAL_INICIO
                data_estimada += 1
            dt_desfil = _to_date(item.get("data_desfiliacao"))

            if (pol_id, party_id, dt_fil) in existing_affs:
                continue

            motivo = None
            motivo_raw = item.get("motivo_desfiliacao")
            if motivo_raw and not pd.isna(motivo_raw) and str(motivo_raw).lower() != "none":
                try:
                    motivo = MotivoDesfiliacaoEnum[str(motivo_raw)]
                except KeyError:
                    motivo = MotivoDesfiliacaoEnum.MUDANCA_VOLUNTARIA

            session.add(
                PartyAffiliation(
                    politician_id=pol_id,
                    party_id=party_id,
                    start_date=dt_fil,
                    end_date=dt_desfil,
                    is_current=bool(item.get("is_atual", dt_desfil is None)),
                    disaffiliation_reason=motivo,
                    state=item.get("uf"),
                )
            )
            existing_affs.add((pol_id, party_id, dt_fil))
            inserted += 1

        session.flush()
        if sem_proveniencia:
            logger.warning(
                f"-> {sem_proveniencia} filiações ignoradas por falta de proveniência (arquivo legado com origens "
                "sorteadas). Reexecute `--tse` ou use --allow-unverified."
            )
        logger.info(
            f"-> {inserted} filiações inseridas ({data_estimada} com data desconhecida usando o início da "
            f"legislatura como limite inferior; {sem_politico} sem político identificável)."
        )
        return inserted

    # ------------------------------------------------------------------ mandatos
    def _load_mandates(
        self,
        session: Session,
        president_map: Dict[str, Any],
        deputy_map: Dict[int, Any],
        senator_map: Dict[int, Any],
        party_map: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Carrega mandatos presidenciais, ministros da Fazenda e mandatos de deputados e senadores."""
        mandate_map: Dict[str, Any] = {}

        for p in load_json(self.data_dir / "presidentes_historico.json", []) or []:
            ref_id = p["id_referencia"]
            pol_id = president_map.get(ref_id)
            partido_id = resolve_party_id(party_map, p.get("partido_sigla")) or resolve_party_id(party_map, "MDB")

            dt_inicio = _to_date(p["data_inicio"])
            dt_fim = _to_date(p.get("data_fim"))

            st_str = p.get("status_mandato", "CONCLUIDO")
            if st_str == "IMPEACHMENT":
                status_enum = StatusMandatoEnum.IMPEACHMENT
            elif st_str == "TITULAR_ATIVO":
                status_enum = StatusMandatoEnum.TITULAR_ATIVO
            else:
                status_enum = StatusMandatoEnum.CONCLUIDO

            mandato = (
                session.query(Mandate)
                .filter(
                    Mandate.politician_id == pol_id,
                    Mandate.election_year == p["ano_eleicao"],
                    Mandate.term_number == p["mandato_numero"],
                )
                .first()
            )

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
                    # `coalition_name` não é o vice-presidente (campo usado errado antes); fica vazio.
                    coalition_name=None,
                )
                session.add(mandato)
                session.flush()
            mandate_map[ref_id] = mandato.id

            for min_faz in p.get("ministros_fazenda_chave", []):
                dt_posse = _to_date(min_faz["inicio"])
                dt_exon = _to_date(min_faz.get("fim"))
                membro = (
                    session.query(CabinetMember)
                    .filter(
                        CabinetMember.mandate_id == mandato.id,
                        CabinetMember.occupant_name == min_faz["nome"],
                        CabinetMember.inauguration_date == dt_posse,
                    )
                    .first()
                )
                if not membro:
                    session.add(
                        CabinetMember(
                            mandate_id=mandato.id,
                            occupant_name=min_faz["nome"],
                            ministry_name="Ministério da Fazenda",
                            inauguration_date=dt_posse,
                            departure_date=dt_exon,
                            is_economy_minister=True,
                        )
                    )

        # Deputados: o mandato segue a legislatura informada pela API (57ª => eleição 2022, 2023-02-01 a 2027-01-31).
        criados_dep = 0
        for d in load_deputados(self.data_dir):
            pol_id = deputy_map.get(d["camara_id"])
            if not pol_id:
                continue
            legislatura = int(d.get("id_legislatura") or LEGISLATURA_ATUAL)
            inicio, fim = legislatura_datas(legislatura)
            ano_eleicao = inicio.year - 1
            partido_id = resolve_party_id(party_map, d.get("partido_sigla")) or party_map.get(SEM_PARTIDO)

            mandato = (
                session.query(Mandate)
                .filter(
                    Mandate.politician_id == pol_id,
                    Mandate.election_year == ano_eleicao,
                    Mandate.office == CargoPoliticoEnum.DEPUTADO_FEDERAL,
                )
                .first()
            )
            if not mandato:
                session.add(
                    Mandate(
                        politician_id=pol_id,
                        party_id=partido_id,
                        office=CargoPoliticoEnum.DEPUTADO_FEDERAL,
                        sphere=TipoEsferaEnum.FEDERAL,
                        jurisdiction_state=d.get("uf") or "DF",
                        election_year=ano_eleicao,
                        term_number=1,
                        start_date=inicio,
                        end_date=fim,
                        status=StatusMandatoEnum.TITULAR_ATIVO,
                    )
                )
                criados_dep += 1

        # Senadores: datas do mandato vêm da API (legislaturas do mandato); o mandato dura 8 anos (2 legislaturas).
        criados_sen = 0
        sem_dados_sen = 0
        for s in load_senadores(self.data_dir):
            pol_id = senator_map.get(s["senado_id"])
            if not pol_id:
                continue
            partido_id = resolve_party_id(party_map, s.get("partido_sigla")) or party_map.get(SEM_PARTIDO)
            inicio, fim, ano_eleicao = self._datas_mandato_senador(s)
            if inicio is None:
                # Fonte sem datas (arquivo gerado antes da extração de `Mandato`): usa o início da legislatura
                # atual, SEM data de término — e SEM afirmar que foi eleito em 2022 (metade do Senado foi em 2018).
                sem_dados_sen += 1
                inicio, fim, ano_eleicao = LEGISLATURA_ATUAL_INICIO, None, LEGISLATURA_ATUAL_INICIO.year - 1

            mandato = (
                session.query(Mandate)
                .filter(
                    Mandate.politician_id == pol_id,
                    Mandate.office == CargoPoliticoEnum.SENADOR,
                )
                .order_by(Mandate.start_date.desc())
                .first()
            )
            if not mandato:
                session.add(
                    Mandate(
                        politician_id=pol_id,
                        party_id=partido_id,
                        office=CargoPoliticoEnum.SENADOR,
                        sphere=TipoEsferaEnum.FEDERAL,
                        jurisdiction_state=s.get("uf") or "DF",
                        election_year=ano_eleicao,
                        term_number=1,
                        start_date=inicio,
                        end_date=fim,
                        status=StatusMandatoEnum.TITULAR_ATIVO,
                    )
                )
                criados_sen += 1
            elif s.get("mandato_inicio") or s.get("legislatura_inicio"):
                # Só corrige datas quando a fonte as informa de fato
                mandato.start_date, mandato.end_date, mandato.election_year = inicio, fim, ano_eleicao

        session.flush()
        if sem_dados_sen:
            logger.warning(
                f"-> {sem_dados_sen} senadores sem datas de mandato na fonte: usado o início da legislatura atual "
                "sem data de término. Reexecute a extração do Senado para obter as datas reais."
            )
        logger.info(
            f"-> Mandatos: {criados_dep} de deputados e {criados_sen} de senadores criados; presidenciais sincronizados."
        )
        return mandate_map

    @staticmethod
    def _datas_mandato_senador(s: Dict[str, Any]) -> Tuple[Optional[date], Optional[date], Optional[int]]:
        inicio = _to_date(s.get("mandato_inicio"))
        fim = _to_date(s.get("mandato_fim"))
        if inicio is None and s.get("legislatura_inicio"):
            inicio, _ = legislatura_datas(int(s["legislatura_inicio"]))
        if fim is None and s.get("legislatura_fim"):
            _, fim = legislatura_datas(int(s["legislatura_fim"]))
        if inicio is None:
            return None, None, None
        return inicio, fim, inicio.year - 1

    # ------------------------------------------------------------------ patrimônio
    # ------------------------------------------------------------------ CEAP
    # ------------------------------------------------------------------ emendas
    # ------------------------------------------------------------------ certidões / doações
    # ------------------------------------------------------------------ proposições
    @staticmethod
    def _tipo_proposicao(tipo_str: Optional[str]) -> TipoProposicaoEnum:
        try:
            return TipoProposicaoEnum[(tipo_str or "PL").upper()]
        except KeyError:
            return TipoProposicaoEnum.PL

    def _load_propositions(
        self,
        session: Session,
        deputy_map: Dict[int, Any],
        senator_map: Dict[int, Any],
    ) -> Dict[int, Any]:
        """
        Proposições da Câmara e do Senado. Cada casa é identificada pelo seu id externo: Câmara e Senado numeram
        por conta própria, então casar o PL do Senado com "o PL de mesmo número/ano" sobrescrevia autor, eixo e
        área de uma proposição da Câmara diferente.
        """
        prop_map: Dict[int, Any] = {}
        resolver = AuthorResolver(session.query(Politician).all(), deputy_map, senator_map)
        data_aproximada = 0
        autores_ignorados = 0

        def data_apresentacao(valor: Any, ano: int) -> date:
            nonlocal data_aproximada
            dt = _to_date(valor)
            if dt is None:
                # Coluna obrigatória; a fonte não informou. 1º de janeiro do ano da proposição é só um
                # limite inferior — contabilizado e logado, nunca apresentado como data real.
                data_aproximada += 1
                return date(ano, 1, 1)
            return dt

        # A. Câmara dos Deputados
        total_camara = 0
        for p in load_json(self.data_dir / "proposicoes_2023.json", []) or []:
            cid = p.get("camara_id")
            if not cid:
                continue
            prop = session.query(Proposition).filter_by(external_camara_id=cid).first()

            tipo_str = (p.get("tipo") or "PL").upper()
            numero, ano = int(p.get("numero") or 0), int(p.get("ano") or 2023)
            titulo = p.get("titulo") or f"{tipo_str} {numero}/{ano}"
            ementa = p.get("ementa") or ""
            eixo_princ, eixos_tags = classify_proposition_impact(tipo_str, numero, ano, titulo, ementa)

            # Autoria só é usada quando a fonte a atesta (`autor_fonte`). Arquivos legados atribuíam autor por
            # round-robin quando a API falhava: sem proveniência não dá para separar o real do fabricado.
            if p.get("autor_fonte") or self.allow_unverified:
                autor_nome = p.get("autor_nome") or ("Poder Executivo" if p.get("iniciativa_executivo") else None)
                autor_camara_id = p.get("autor_camara_id")
            else:
                autor_nome = "Poder Executivo" if p.get("iniciativa_executivo") else None
                autor_camara_id = None
                autores_ignorados += 1
            autor_conhecido = bool(autor_nome)
            autor_pol_id = resolver.resolve(autor_nome, camara_id=autor_camara_id)
            setor = p.get("area_tematica")
            url_oficial = (
                p.get("url_oficial") or f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={cid}"
            )

            if not prop:
                prop = Proposition(
                    external_camara_id=cid,
                    proposition_type=self._tipo_proposicao(tipo_str),
                    number=numero,
                    year=ano,
                    title=titulo,
                    summary=ementa[:1000] if ementa else "Sem ementa disponível",
                    thematic_area=setor,
                    presentation_date=data_apresentacao(p.get("data_apresentacao"), ano),
                    status=StatusTramitacaoEnum.EM_TRAMITACAO,
                    is_structural_reform=bool(p.get("is_reforma_estrutural", False)),
                    is_executive_initiative=bool(p.get("iniciativa_executivo", False)),
                    impact_axis=eixo_princ,
                    impact_tags=eixos_tags,
                    author_name=autor_nome,
                    author_politician_id=autor_pol_id,
                    official_url=url_oficial,
                )
                session.add(prop)
                session.flush()
            else:
                prop.impact_axis, prop.impact_tags = eixo_princ, eixos_tags
                if setor:
                    prop.thematic_area = setor
                if not prop.official_url or "camara.leg.br" not in prop.official_url:
                    prop.official_url = url_oficial
                if autor_conhecido or autor_nome:
                    # Autoria conhecida na fonte: o vínculo é recalculado (inclusive para None), o que desfaz
                    # vínculos errados gravados por regras antigas. Fonte sem autor não apaga vínculo existente.
                    prop.author_name = autor_nome
                    prop.author_politician_id = autor_pol_id

            prop_map[cid] = prop.id
            total_camara += 1

        # B. Senado Federal — identificado só por `external_senado_id`
        total_senado = 0
        for p in load_json(self.data_dir / "proposicoes_senado.json", []) or []:
            if not isinstance(p, dict):  # arquivo legado em formato {id: {...}} ou lista de ids
                continue
            sid = p.get("senado_id")
            if not sid:
                continue
            prop = session.query(Proposition).filter_by(external_senado_id=sid).first()

            tipo_str = (p.get("tipo") or "PL").upper()
            num_val, ano_val = int(p.get("numero") or 0), int(p.get("ano") or 2023)
            titulo = p.get("titulo") or f"{tipo_str} {num_val}/{ano_val}"
            ementa = p.get("ementa") or "Sem ementa disponível"
            eixo_princ, eixos_tags = classify_proposition_impact(tipo_str, num_val, ano_val, titulo, ementa)

            if p.get("autor_fonte") or self.allow_unverified:
                autor_nome = p.get("autor_nome")
            else:
                autor_nome = None
                autores_ignorados += 1
            autor_pol_id = resolver.resolve(autor_nome, senado_id=p.get("autor_senado_id") if autor_nome else None)
            setor = p.get("area_tematica")
            url_oficial = p.get("url_oficial") or f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{sid}"

            if not prop:
                prop = Proposition(
                    external_senado_id=sid,
                    proposition_type=self._tipo_proposicao(tipo_str),
                    number=num_val,
                    year=ano_val,
                    title=titulo,
                    summary=ementa[:1000],
                    thematic_area=setor,
                    presentation_date=data_apresentacao(p.get("data_apresentacao"), ano_val),
                    status=StatusTramitacaoEnum.EM_TRAMITACAO,
                    is_structural_reform=False,
                    is_executive_initiative=False,
                    impact_axis=eixo_princ,
                    impact_tags=eixos_tags,
                    author_name=autor_nome,
                    author_politician_id=autor_pol_id,
                    official_url=url_oficial,
                )
                session.add(prop)
                session.flush()
            else:
                prop.impact_axis, prop.impact_tags = eixo_princ, eixos_tags
                if setor:
                    prop.thematic_area = setor
                if not prop.official_url:
                    prop.official_url = url_oficial
                if autor_nome:
                    prop.author_name = autor_nome
                    prop.author_politician_id = autor_pol_id
            total_senado += 1

        # Completa urlOficial e eixo ausentes (sem inventar área temática)
        for pr in (
            session.query(Proposition)
            .filter((Proposition.impact_axis.is_(None)) | (Proposition.official_url.is_(None)))
            .all()
        ):
            if not pr.impact_axis:
                tipo_val = (
                    pr.proposition_type.value if hasattr(pr.proposition_type, "value") else str(pr.proposition_type)
                )
                pr.impact_axis, pr.impact_tags = classify_proposition_impact(
                    tipo_val, pr.number, pr.year, pr.title, pr.summary or ""
                )
            if not pr.official_url:
                if pr.external_camara_id:
                    pr.official_url = f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={pr.external_camara_id}"
                elif pr.external_senado_id:
                    pr.official_url = (
                        f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{pr.external_senado_id}"
                    )

        session.flush()
        if autores_ignorados:
            logger.warning(
                f"-> Autoria de {autores_ignorados} proposições ignorada por falta de proveniência (arquivo legado). "
                "Reexecute a extração (--camara/--senado) ou use --allow-unverified para carregá-las mesmo assim."
            )
        if data_aproximada:
            logger.warning(
                f"-> {data_aproximada} proposições sem data de apresentação na fonte (usado 1º de janeiro do ano)."
            )
        logger.info(f"-> {total_camara} proposições da Câmara e {total_senado} do Senado carregadas.")
        return prop_map

    # ------------------------------------------------------------------ votações
    @staticmethod
    def _opcao_voto(valor: Any) -> Optional[VotoOpcaoEnum]:
        return VotoOpcaoEnum.__members__.get(str(valor or "AUSENTE").strip().upper())

    def _proposicao_por_chave(self, session: Session, sigla: Optional[str], numero: Any, ano: Any) -> Optional[Any]:
        """Proposição por (tipo, número, ano) exatos. Ambiguidade/ausência => None (a sessão é descartada)."""
        if not sigla or numero in (None, "") or ano in (None, ""):
            return None
        try:
            tipo = TipoProposicaoEnum[str(sigla).upper()]
        except KeyError:
            return None
        candidatos = (
            session.query(Proposition)
            .filter(
                Proposition.proposition_type == tipo, Proposition.number == int(numero), Proposition.year == int(ano)
            )
            .all()
        )
        if len(candidatos) == 1:
            return candidatos[0].id
        com_camara = [c for c in candidatos if c.external_camara_id]
        if len(com_camara) == 1:
            return com_camara[0].id
        return None

    def _load_voting_sessions_and_votes(
        self,
        session: Session,
        prop_map: Dict[int, Any],
        deputy_map: Dict[int, Any],
        senator_map: Dict[int, Any],
        party_map: Dict[str, Any],
    ):
        """Sessões e votos nominais (Câmara e Senado), idempotentes e sem associar sessão a proposição arbitrária."""
        session_map: Dict[str, Any] = {}
        votos_inseridos = 0
        descartadas = 0
        votos_invalidos = 0

        # Só os votos das sessões deste arquivo são carregados na memória (a tabela passa de 1 milhão de linhas
        # depois da carga histórica; consultar todos custava centenas de MB a cada execução).
        existing_votes_set: set = set()
        sessoes_com_votos_lidos: set = set()

        def totais_por_sessao(votos: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
            tot: Dict[str, Dict[str, int]] = {}
            for v in votos:
                t = tot.setdefault(str(v.get("sessao_externa_id")), {})
                op = str(v.get("voto") or "")
                t[op] = t.get(op, 0) + 1
            return tot

        def upsert_sessao(
            s: Dict[str, Any], house: CasaLegislativaEnum, prop_id: Any, titulo_padrao: str, totais: Dict[str, int]
        ):
            ext_id = str(s["sessao_externa_id"])
            dt_obj = _to_datetime(s.get("data_hora"))
            if dt_obj is None:
                logger.warning("Sessão %s sem data/hora — ignorada (data não é presumida).", ext_id)
                return None

            # Totais recalculados dos votos nominais quando existem (fonte única de verdade); senão, os do arquivo.
            sim = totais.get("SIM", 0) if totais else s.get("total_sim", 0)
            nao = totais.get("NAO", 0) if totais else s.get("total_nao", 0)
            abst = totais.get("ABSTENCAO", 0) if totais else s.get("total_abstencao", 0)
            obst = totais.get("OBSTRUCAO", 0) if totais else s.get("total_obstrucao", 0)

            obj = session.query(VotingSession).filter_by(external_id=ext_id).first()
            if obj is not None and obj.legislative_house != house:
                logger.warning("external_id %s já pertence a outra casa — sessão ignorada.", ext_id)
                return None
            if obj is None:
                obj = VotingSession(
                    external_id=ext_id,
                    proposition_id=prop_id,
                    legislative_house=house,
                    session_datetime=dt_obj,
                    agenda_title=s.get("titulo_pauta") or titulo_padrao,
                    detailed_description=s.get("descricao"),
                    is_approved=bool(s.get("aprovada")),  # indeterminada (None) => False; campo é obrigatório
                )
                session.add(obj)
            obj.votes_yes_count, obj.votes_no_count = sim or 0, nao or 0
            obj.votes_abstain_count, obj.votes_obstruction_count = abst or 0, obst or 0
            session.flush()
            return obj

        def inserir_votos(votos: List[Dict[str, Any]], chave_politico: str, politician_map: Dict[int, Any]) -> None:
            nonlocal votos_inseridos, votos_invalidos
            novas = {session_map[k] for k in {str(v["sessao_externa_id"]) for v in votos} if k in session_map}
            novas -= sessoes_com_votos_lidos
            if novas:
                existing_votes_set.update(
                    session.query(ParliamentaryVote.voting_session_id, ParliamentaryVote.politician_id)
                    .filter(ParliamentaryVote.voting_session_id.in_(novas))
                    .all()
                )
                sessoes_com_votos_lidos.update(novas)
            for v in votos:
                sessao_id = session_map.get(str(v["sessao_externa_id"]))
                politico_id = politician_map.get(v.get(chave_politico))
                if not sessao_id or not politico_id:
                    continue
                opcao = self._opcao_voto(v.get("voto"))
                if opcao is None:
                    votos_invalidos += 1  # antes: KeyError derrubava a carga inteira
                    continue
                if (sessao_id, politico_id) in existing_votes_set:
                    continue
                session.add(
                    ParliamentaryVote(
                        voting_session_id=sessao_id,
                        politician_id=politico_id,
                        party_id=(
                            resolve_party_id(party_map, v.get("partido_sigla")) if v.get("partido_sigla") else None
                        ),
                        vote_choice=opcao,
                    )
                )
                existing_votes_set.add((sessao_id, politico_id))
                votos_inseridos += 1

        # A. Câmara dos Deputados
        sessoes_cam = load_json(self.data_dir / "sessoes_votacao_2023.json", None)
        votos_cam = load_json(self.data_dir / "votos_nominais_2023.json", None)
        if sessoes_cam is not None and votos_cam is not None:
            totais = totais_por_sessao(votos_cam)
            for s in sessoes_cam:
                prop_id = prop_map.get(s.get("proposicao_camara_id"))
                if not prop_id:
                    descartadas += 1
                    continue
                obj = upsert_sessao(
                    s,
                    CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS,
                    prop_id,
                    "Votação em Plenário",
                    totais.get(str(s["sessao_externa_id"]), {}),
                )
                if obj is not None:
                    session_map[str(s["sessao_externa_id"])] = obj.id
            inserir_votos(votos_cam, "deputado_camara_id", deputy_map)

        # B. Senado Federal — proposição por (tipo, número, ano) exatos; sem correspondência única => descarta
        sessoes_sen = load_json(self.data_dir / "sessoes_votacao_senado.json", None)
        votos_sen = load_json(self.data_dir / "votos_nominais_senado.json", None)
        if sessoes_sen is not None and votos_sen is not None:
            totais = totais_por_sessao(votos_sen)
            for s in sessoes_sen:
                ano_materia = s.get("materia_ano") or MATERIA_ANO_CONHECIDA.get(
                    (s.get("materia_sigla"), s.get("materia_numero"))
                )
                prop_id = self._proposicao_por_chave(
                    session, s.get("materia_sigla"), s.get("materia_numero"), ano_materia
                )
                if not prop_id:
                    descartadas += 1
                    logger.warning(
                        "Sessão do Senado %s (%s %s/%s) sem proposição única correspondente — descartada.",
                        s.get("sessao_externa_id"),
                        s.get("materia_sigla"),
                        s.get("materia_numero"),
                        s.get("materia_ano"),
                    )
                    continue
                obj = upsert_sessao(
                    s,
                    CasaLegislativaEnum.SENADO_FEDERAL,
                    prop_id,
                    "Votação no Senado Federal",
                    totais.get(str(s["sessao_externa_id"]), {}),
                )
                if obj is not None:
                    session_map[str(s["sessao_externa_id"])] = obj.id
            inserir_votos(votos_sen, "senador_id", senator_map)

        session.flush()
        logger.info(
            f"-> {len(session_map)} sessões e {votos_inseridos} votos nominais novos "
            f"({descartadas} sessões descartadas, {votos_invalidos} votos com opção desconhecida)."
        )

    # ------------------------------------------------------------------ relatórios
    def _get_table_counts(self, session: Session) -> Dict[str, int]:
        """Consulta e retorna a quantidade de linhas em cada tabela do PostgreSQL."""
        tables = [
            ("partidos_politicos", "Partidos Políticos"),
            ("politicos", "Políticos (Presidentes + Deputados)"),
            ("filiacoes_partidarias", "Filiações Partidárias (TSE)"),
            ("mandatos", "Mandatos Eletivos"),
            ("membros_gabinete", "Membros de Gabinete (Fazenda/Planejamento)"),
            ("proposicoes", "Proposições Legislativas"),
            ("sessoes_votacao", "Sessões de Votação em Plenário"),
            ("votos_parlamentares", "Votos Parlamentares Nominais"),
        ]

        counts = {}
        for tbl_name, label in tables:
            # Nomes de tabela são constantes desta lista (não vêm de entrada externa).
            result = session.execute(text(f"SELECT COUNT(*) FROM stg.{tbl_name};")).scalar()  # nosec B608
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
        print(f"{'TOTAL GERAL DE REGISTROS NAS TABELAS':<52} | {total_geral:>20,}".replace(",", "."))
        print("=" * 80 + "\n")


def main(argv: Optional[List[str]] = None) -> Dict[str, int]:
    parser = argparse.ArgumentParser(description="Carga dos dados processados no PostgreSQL.")
    parser.add_argument(
        "--allow-synthetic", action="store_true", help="Carrega dados sintéticos de demonstração (marcados no texto)."
    )
    parser.add_argument(
        "--allow-unverified",
        action="store_true",
        help="Carrega dados digitados e não verificados (ex.: eleições por UF).",
    )
    args = parser.parse_args(argv)
    return DatabaseLoader(
        allow_synthetic=args.allow_synthetic,
        allow_unverified=args.allow_unverified,
    ).load_all()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    main()
