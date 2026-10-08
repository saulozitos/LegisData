"""
Funções puras da carga (sem acesso a banco): conversões, classificação, resolução de autores e de partidos.
Separadas do `db_loader` para poderem ser testadas sem Postgres e reutilizadas pelos scripts de saneamento.
"""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, Optional, Tuple

import pandas as pd

from etl.utils.names import (
    NON_PERSON_AUTHORS,
    build_unique_name_map,
    first_signatory,
    normalize_name_tokens,
)

# Início da 57ª legislatura (1º/fev/2023): único limite inferior de observação que se conhece para quem está
# "em exercício" quando a fonte não informa a data de filiação/mandato.
LEGISLATURA_ATUAL = 57
LEGISLATURA_ATUAL_INICIO = date(2023, 2, 1)

SEM_PARTIDO = "S.PART."


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
