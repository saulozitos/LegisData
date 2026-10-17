"""
Funções puras da carga (sem acesso a banco): conversões, classificação, resolução de autores e de partidos.
Separadas do `db_loader` para poderem ser testadas sem Postgres e reutilizadas pelos scripts de saneamento.
"""

import math
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from etl.utils.names import (
    NON_PERSON_AUTHORS,
    build_unique_name_map,
    chave_sigla,
    first_signatory,
    normalize_name_tokens,
)

# Início da 57ª legislatura (1º/fev/2023): único limite inferior de observação que se conhece para quem está
# "em exercício" quando a fonte não informa a data de filiação/mandato.
LEGISLATURA_ATUAL = 57
LEGISLATURA_ATUAL_INICIO = date(2023, 2, 1)

SEM_PARTIDO = "S.PART."


def texto(valor: Any) -> Optional[str]:
    """Texto sem espaços nas pontas; vazio ou None viram None."""
    limpo = str(valor).strip() if valor is not None else ""
    return limpo or None


def inteiro(valor: Any) -> Optional[int]:
    """Inteiro ou None para vazio e para o que não converte."""
    try:
        return None if valor is None or valor == "" else int(valor)
    except (TypeError, ValueError, OverflowError):
        return None


def inteiro_em(valor: Any, minimo: int, maximo: int) -> Optional[int]:
    """Inteiro dentro do intervalo fechado [minimo, maximo]; fora dele ou inválido, None."""
    numero = inteiro(valor)
    return numero if numero is not None and minimo <= numero <= maximo else None


def normalizar_sigla_presenca(sigla: Any) -> Optional[str]:
    """Sigla de partido vinda das fontes de presença -> sigla canônica; None quando a fonte não registra partido.

    A Câmara publica "s/partido" para quem não tem partido (vira `S.PART.`) e "sem registro" quando não há informação
    (vira None, pois não é um partido).
    """
    texto = str(sigla).strip() if sigla is not None else ""
    if not texto or texto.lower() == "sem registro":
        return None
    if texto.lower() == "s/partido":
        return SEM_PARTIDO
    return texto


def _dec(value: Any) -> Optional[Decimal]:
    """Decimal a partir de número/str; None/NaN/vazio -> None. Zero legítimo continua sendo Decimal('0')."""
    if value is None:
        return None
    if isinstance(value, float) and value != value:  # NaN
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _texto_ou_none(value: Any) -> Optional[str]:
    """Texto aparado; None/NaN/vazio -> None (CSV do pandas devolve NaN para célula vazia)."""
    if value is None or (isinstance(value, float) and value != value):
        return None
    texto = str(value).strip()
    return texto or None


def _to_date(value: Any) -> Optional[date]:
    """Converte 'AAAA-MM-DD...' / date / datetime em date; vazio/NaN/'none' -> None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    texto = str(value).strip()
    if not texto or texto.lower() in ("none", "nan", "nat"):
        return None
    try:
        return datetime.strptime(texto[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _to_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    texto = str(value).strip()
    try:
        return datetime.fromisoformat(texto) if "T" in texto else datetime.strptime(texto[:10], "%Y-%m-%d")
    except ValueError:
        return None


def legislatura_datas(numero: int) -> Tuple[date, date]:
    """Início e fim (1º/fev a 31/jan) de uma legislatura. A 57ª vai de 2023-02-01 a 2027-01-31."""
    ano_inicio = LEGISLATURA_ATUAL_INICIO.year + 4 * (int(numero) - LEGISLATURA_ATUAL)
    return date(ano_inicio, 2, 1), date(ano_inicio + 4, 1, 31)


def classify_proposition_impact(tipo: str, numero: int, ano: int, titulo: str, ementa: str):
    """
    Classifica a proposição em eixos temáticos por palavras-chave. Sem correspondência devolve (None, None):
    antes, o eixo era `(numero + ano) % 5`, ou seja, um eixo ALEATÓRIO atribuído como se fosse análise.
    """
    t = f"{titulo} {ementa}".lower()
    tipo = (tipo or "").upper()

    # 1. Matérias estruturantes explícitas — por (tipo, número, ano), não só pelo número
    if (tipo == "PLP" and numero == 93 and ano == 2023) or "arcabouço fiscal" in t or "regime fiscal sustentável" in t:
        return "Responsabilidade Fiscal", "Responsabilidade Fiscal, Regulação Macroeconômica"
    if (
        (tipo == "PEC" and numero == 45 and ano == 2019)
        or "reforma tributária" in t
        or ("tributária" in t and "consumo" in t)
    ):
        return "Tributação & Renda", "Tributação & Renda, Desoneração Corporativa"
    if (tipo == "MPV" and numero == 1172 and ano == 2023) or "salário mínimo" in t:
        return "Transferência de Renda", "Transferência de Renda, Direitos Trabalhistas, Tributação & Renda"
    if (tipo == "MPV" and numero == 1184 and ano == 2023) or "fundos exclusivos" in t or "offshores" in t:
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

    return None, None


# Padrões dos contatos que versões anteriores do loader INVENTAVAM a partir do id do parlamentar.
_EMAIL_INVENTADO = re.compile(r"^(dep|sen)\.\d+@(camara|senado)\.leg\.br$")
_SALA_INVENTADA = re.compile(r"^(Anexo IV, Gabinete \d+|Ala Filinto Müller, Gabinete \d{2})$")
_TEL_INVENTADO = re.compile(r"^\(61\) (3215-5\d{3}|3303-\d{4})$")


def limpar_contatos_inventados(pol: Any) -> bool:
    """Remove contatos que carregam o padrão exato dos valores sintéticos antigos. Devolve True se limpou algo."""
    alterou = False
    if pol.email and _EMAIL_INVENTADO.match(pol.email):
        pol.email = None
        alterou = True
    if pol.cabinet_room and _SALA_INVENTADA.match(pol.cabinet_room):
        pol.cabinet_room = None
        if pol.cabinet_phone and _TEL_INVENTADO.match(pol.cabinet_phone):
            pol.cabinet_phone = None
        alterou = True
    return alterou


def resolve_party_id(party_map: Dict[str, Any], sigla: Optional[str]) -> Optional[Any]:
    """Resolve sigla -> id de partido (exata, depois maiúscula). Sigla vazia => 'Sem Partido'."""
    if not sigla or (isinstance(sigla, float) and sigla != sigla):
        return party_map.get(SEM_PARTIDO)
    sigla = str(sigla).strip()
    return party_map.get(sigla) or party_map.get(sigla.upper())


class AuthorResolver:
    """
    Resolve o nome de autor de uma proposição para um Politician.id.

    Ordem: (1) ids oficiais; (2) nome do PRIMEIRO signatário igual ao nome eleitoral/civil bruto;
    (3) igualdade do nome normalizado; (4) igualdade do CONJUNTO de tokens. Em (2)-(4) o nome precisa ser
    único na base: homônimos resolvem para None. A regra antiga "tokens do nome eleitoral ⊂ tokens do autor
    com até 1 token extra" ligava "Flávio Dino" a "Flávio Bolsonaro" e "Gil Diniz" a "Gil"; foi removida.
    """

    def __init__(self, politicians: Iterable[Any], deputy_map: Dict[int, Any], senator_map: Dict[int, Any]):
        self.deputy_map = deputy_map
        self.senator_map = senator_map
        pols = list(politicians)
        self.raw = build_unique_name_map(
            [(p.id, (p.electoral_name or "").strip()) for p in pols if p.electoral_name]
            + [(p.id, (p.civil_name or "").strip()) for p in pols if p.civil_name]
        )
        # chave bruta (sem normalização agressiva) -> id único
        self.raw_exact: Dict[str, Any] = {}
        contagem: Dict[str, set] = {}
        for p in pols:
            for nome in (p.electoral_name, p.civil_name):
                if nome:
                    contagem.setdefault(nome.strip(), set()).add(p.id)
        self.raw_exact = {k: next(iter(v)) for k, v in contagem.items() if len(v) == 1}

        tokens: Dict[frozenset, set] = {}
        for p in pols:
            for nome in (p.electoral_name, p.civil_name):
                toks = frozenset(normalize_name_tokens(nome).split()) if nome else frozenset()
                if len(toks) >= 2:
                    tokens.setdefault(toks, set()).add(p.id)
        self.token_sets = {k: next(iter(v)) for k, v in tokens.items() if len(v) == 1}

    def resolve(
        self,
        autor_nome_raw: Optional[str],
        camara_id: Optional[int] = None,
        senado_id: Optional[int] = None,
    ) -> Optional[Any]:
        if camara_id and camara_id in self.deputy_map:
            return self.deputy_map[camara_id]
        if senado_id and senado_id in self.senator_map:
            return self.senator_map[senado_id]
        if not autor_nome_raw:
            return None

        primeiro = first_signatory(autor_nome_raw)
        for candidato in (autor_nome_raw.strip(), primeiro):
            if candidato in self.raw_exact:
                return self.raw_exact[candidato]

        norm = normalize_name_tokens(primeiro)
        if not norm or norm in NON_PERSON_AUTHORS:
            return None
        if norm in self.raw:
            return self.raw[norm]

        toks = frozenset(norm.split())
        if len(toks) >= 2 and toks in self.token_sets:
            return self.token_sets[toks]
        return None


# ── composição do Congresso ──────────────────────────────────────────────────────────────────────────────────────
ALINHAMENTOS = {"BASE_GOVERNO", "INDEPENDENTE_CENTRO", "OPOSICAO", "NAO_CLASSIFICADO"}


def bancadas_da_casa(casa: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Une as bancadas exibidas (`cadeiras`) e as eleitas segundo o TSE (`cadeiras_tse`) por partido. A união usa a chave
    normalizada da sigla ('PCdoB' da curadoria e 'PC DO B' do TSE são o mesmo partido); a sigla gravada é a da curadoria.
    """
    por_partido: Dict[str, Dict[str, Any]] = {}
    for b in (x for x in casa.get("bancadas") or [] if isinstance(x, dict)):
        sigla = texto(b.get("partido"))
        if not sigla:
            continue
        alinhamento = texto(b.get("alinhamento")) or "NAO_CLASSIFICADO"
        por_partido[chave_sigla(sigla)] = {
            "sigla": sigla,
            "cadeiras": inteiro(b.get("cadeiras")),
            "cadeiras_tse": None,
            "alinhamento": alinhamento if alinhamento in ALINHAMENTOS else "NAO_CLASSIFICADO",
            "cor_hex": texto(b.get("cor_hex")),
        }
    for b in (x for x in casa.get("bancadas_eleitas_tse") or [] if isinstance(x, dict)):
        sigla = texto(b.get("partido"))
        if not sigla:
            continue
        linha = por_partido.setdefault(
            chave_sigla(sigla),
            {"sigla": sigla, "cadeiras": None, "cadeiras_tse": None, "alinhamento": None, "cor_hex": None},
        )
        linha["cadeiras_tse"] = inteiro(b.get("cadeiras"))
    linhas = [b for b in por_partido.values() if b["cadeiras"] is not None or b["cadeiras_tse"] is not None]
    # a ordem da curadoria (desempates entre partidos de mesmo tamanho) é preservada
    for ordem, linha in enumerate(linhas):
        linha["ordem"] = ordem
    return linhas


def validar_soma_das_bancadas(bancadas: List[Dict[str, Any]], total: int, rotulo: str) -> None:
    """A soma das cadeiras exibidas não pode passar do total da Casa (a menos seria só parte sem classificação)."""
    soma = sum(b["cadeiras"] or 0 for b in bancadas)
    if soma > total:
        raise ValueError(f"Composição de '{rotulo}': as bancadas somam {soma} cadeiras, mais que o total ({total})")


# ── PNAD ─────────────────────────────────────────────────────────────────────────────────────────────────────────
DISTRIBUICOES_PNAD = (
    "domicilios_renda_total",
    "pessoas_renda_domiciliar",
    "pessoas_renda_per_capita",
    "ocupados_renda_trabalho",
)
N_FAIXAS_PNAD = 8
SOMA_PERCENTUAL_TOLERANCIA = 1.0  # pontos percentuais de folga para o arredondamento


def percentual_valido(valor: Any) -> Optional[List[float]]:
    """Lista de 8 percentuais numéricos e finitos que somam cerca de 100; qualquer outra coisa é None."""
    if not isinstance(valor, list) or len(valor) != N_FAIXAS_PNAD:
        return None
    try:
        numeros = [float(v) for v in valor]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(n) for n in numeros):
        return None
    return numeros if abs(sum(numeros) - 100.0) <= SOMA_PERCENTUAL_TOLERANCIA else None


def ano_pnad_valido(ano: Any, entrada: Any) -> bool:
    """
    O ano só entra com chave entre 1995 e 2100, visita (1 a 5), salário mínimo positivo e as duas distribuições usadas
    nas classes (domicílios e pessoas). Nada é presumido: sem visita no arquivo, o ano é pulado.
    """
    if inteiro_em(ano, 1995, 2100) is None or not isinstance(entrada, dict):
        return False
    if inteiro_em(entrada.get("visita"), 1, 5) is None:
        return False
    try:
        salario = float(entrada.get("salario_minimo_brl"))
    except (TypeError, ValueError):
        return False
    if not (math.isfinite(salario) and salario > 0):
        return False
    nacional = entrada.get("nacional")
    if not isinstance(nacional, dict):
        return False
    return all(
        isinstance(nacional.get(c), dict) and percentual_valido(nacional[c].get("percentual")) is not None
        for c in ("domicilios_renda_total", "pessoas_renda_domiciliar")
    )


def linhas_pnad_do_ano(entrada: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Uma linha por escopo (BR ou UF) e distribuição com percentuais válidos."""
    escopos = {"BR": entrada.get("nacional") or {}}
    uf_do_ano = entrada.get("uf")
    for uf, dados in uf_do_ano.items() if isinstance(uf_do_ano, dict) else []:
        escopos[str(uf).upper()] = dados or {}
    linhas = []
    for escopo, dados in escopos.items():
        for distribuicao in DISTRIBUICOES_PNAD:
            info = dados.get(distribuicao) if isinstance(dados, dict) else None
            percentual = percentual_valido(info.get("percentual")) if isinstance(info, dict) else None
            if percentual is None:
                continue
            linhas.append(
                {
                    "escopo": escopo,
                    "distribuicao": distribuicao,
                    "total": info.get("total_estimado"),
                    "media": info.get("media_nominal_brl"),
                    "percentual": percentual,
                }
            )
    return linhas


# ── Finanças (schema `fin`) ──────────────────────────────────────────────────────────────────────────────────────────
UF_POR_NOME = {
    "ACRE": "AC",
    "ALAGOAS": "AL",
    "AMAPA": "AP",
    "AMAZONAS": "AM",
    "BAHIA": "BA",
    "CEARA": "CE",
    "DISTRITO FEDERAL": "DF",
    "ESPIRITO SANTO": "ES",
    "GOIAS": "GO",
    "MARANHAO": "MA",
    "MATO GROSSO": "MT",
    "MATO GROSSO DO SUL": "MS",
    "MINAS GERAIS": "MG",
    "PARA": "PA",
    "PARAIBA": "PB",
    "PARANA": "PR",
    "PERNAMBUCO": "PE",
    "PIAUI": "PI",
    "RIO DE JANEIRO": "RJ",
    "RIO GRANDE DO NORTE": "RN",
    "RIO GRANDE DO SUL": "RS",
    "RONDONIA": "RO",
    "RORAIMA": "RR",
    "SANTA CATARINA": "SC",
    "SAO PAULO": "SP",
    "SERGIPE": "SE",
    "TOCANTINS": "TO",
}
_UFS = frozenset(UF_POR_NOME.values())
_SEQUENCIA_CPF = re.compile(r"(?<!\d)\d{11}(?!\d)")
TIPOS_DE_AUTOR_INSTITUCIONAL = ("BANCADA_ESTADUAL", "COMISSAO_INSTITUCIONAL", "RELATOR_GERAL")


def so_digitos(valor: Any) -> str:
    return re.sub(r"\D", "", str(valor)) if valor is not None else ""


def cnpj_do_fornecedor(valor: Any) -> Optional[str]:
    """
    Os 14 dígitos de um CNPJ. CPF (11 dígitos), documento truncado e o CNPJ de enchimento que a Câmara usa para
    lançamentos sem fornecedor ("CELULAR FUNCIONAL", "RAMAL") viram None: CPF nunca é gravado (decisão D3).
    """
    digitos = so_digitos(valor)
    if len(digitos) != 14 or digitos[:12] == "0" * 12:
        return None
    return digitos


def nome_do_fornecedor(valor: Any) -> str:
    """Nome do fornecedor sem CPF embutido (MEI aparece como 'NOME 06507955124' na fonte); vazio vira o rótulo padrão."""
    limpo = " ".join(_SEQUENCIA_CPF.sub(" ", str(valor or "")).split())
    return limpo or "Fornecedor não identificado"


def documento_do_doador(valor: Any) -> Optional[str]:
    """
    Documento do doador como o TSE publica: CNPJ inteiro e CPF já mascarado ('***.060.603-**'). Um CPF completo
    (11 dígitos sem máscara) é mascarado aqui, para nunca ser gravado.
    """
    bruto = texto(valor)
    if bruto is None:
        return None
    if "*" in bruto:
        return bruto
    digitos = so_digitos(bruto)
    if len(digitos) == 11:
        return f"***.{digitos[3:6]}.{digitos[6:9]}-**"
    return bruto


def tipo_do_autor(autor: Any, tipo_emenda: Any) -> str:
    """Tipo de autor da emenda: bancada estadual, relator-geral, comissão ou parlamentar individual."""
    nome = normalize_name_tokens(texto(autor) or "")
    tipo = texto(tipo_emenda) or ""
    if "bancada" in nome or tipo == "Emenda de Bancada":
        return "BANCADA_ESTADUAL"
    if "relator" in nome or tipo == "Emenda de Relator":
        return "RELATOR_GERAL"
    if nome.startswith(("com ", "comissao")) or tipo == "Emenda de Comissão":
        return "COMISSAO_INSTITUCIONAL"
    return "INDIVIDUAL"


def uf_da_localidade(localidade: Any) -> Optional[str]:
    """
    UF do destino da emenda: 'SÃO PAULO (UF)' é o estado e 'CAMPINAS - SP' é um município. Região, 'Nacional',
    'MÚLTIPLO' e 'Exterior' não têm UF (None).
    """
    bruto = texto(localidade)
    if bruto is None:
        return None
    if bruto.upper().endswith("(UF)"):
        return UF_POR_NOME.get(normalize_name_tokens(bruto[:-4]).upper())
    sufixo = re.search(r"\s-\s([A-Z]{2})$", bruto)
    return sufixo.group(1) if sufixo and sufixo.group(1) in _UFS else None
