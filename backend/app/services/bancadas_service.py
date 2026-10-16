"""Leitura das bancadas, totais de cadeiras e governabilidade de cada Casa durante um mandato presidencial."""

import math
from typing import Any, Dict, List, Optional

from app.services.party_catalog_service import DEFAULT_PARTY_COLOR as COR_PADRAO
from sqlalchemy import text
from sqlalchemy.orm import Session

# Casa (chave usada pela API e pelo IPLE) -> código em `ref.casa_legislativa`
CASAS = {"camara": "CAMARA_DOS_DEPUTADOS", "senado": "SENADO_FEDERAL"}
NAO_CLASSIFICADO = "NAO_CLASSIFICADO"

_COMPOSICAO_SQL = text(
    """
    SELECT c.*, k.codigo AS casa_codigo
    FROM leg.composicao_mandato c JOIN ref.casa_legislativa k ON k.id = c.casa_id
    WHERE c.mandato_id = (SELECT mandato_id FROM core.mandato_presidencial WHERE slug = :slug)
    """
)

_BANCADAS_SQL = text(
    """
    SELECT b.partido_sigla, b.cadeiras, b.cadeiras_tse, b.alinhamento, b.cor_hex, k.codigo AS casa_codigo
    FROM leg.bancada_mandato b JOIN ref.casa_legislativa k ON k.id = b.casa_id
    WHERE b.mandato_id = (SELECT mandato_id FROM core.mandato_presidencial WHERE slug = :slug)
    ORDER BY b.ordem
    """
)


def pct(parte: float, total: float) -> float:
    return round(parte / total * 100, 1) if total else 0.0


def composicoes(db: Session, slug: str) -> Dict[str, Dict[str, Any]]:
    """Metadados da composição de cada Casa do mandato, indexados pelo código da Casa."""
    return {r["casa_codigo"]: dict(r) for r in db.execute(_COMPOSICAO_SQL, {"slug": slug}).mappings()}


def linhas_de_bancada(db: Session, slug: str) -> List[Dict[str, Any]]:
    """Todas as linhas de `leg.bancada_mandato` do mandato (as duas Casas), na ordem da curadoria."""
    return [dict(r) for r in db.execute(_BANCADAS_SQL, {"slug": slug}).mappings()]


def bancadas_exibidas(linhas: List[Dict[str, Any]], total: int) -> List[Dict[str, Any]]:
    """Bancadas com cadeiras (curadoria ou TSE) de uma Casa, com percentual e cor (padrão se faltar)."""
    return [
        {
            "partido": r["partido_sigla"],
            "cadeiras": r["cadeiras"],
            "percentual": pct(r["cadeiras"], total),
            "alinhamento": r["alinhamento"],
            "cor_hex": r["cor_hex"] or COR_PADRAO,
        }
        for r in linhas
        if r["cadeiras"] is not None
    ]


def _classificadas(bancadas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [b for b in bancadas if b.get("alinhamento") not in (None, NAO_CLASSIFICADO)]


def cadeiras_da_oposicao(bancadas: List[Dict[str, Any]], total: Optional[int] = None) -> Optional[int]:
    """
    Soma da oposição; None quando não há bancadas ou nenhuma foi classificada (base/centro/oposição). Com `total`,
    também é None se parte das cadeiras ficou sem classificação: a soma parcial seria só um piso, não a oposição.
    """
    classificadas = _classificadas(bancadas)
    if not classificadas:
        return None
    if total is not None and sum(b["cadeiras"] for b in classificadas) < total:
        return None
    return sum(b["cadeiras"] for b in classificadas if b["alinhamento"] == "OPOSICAO")


def governabilidade(total: int, bancadas: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Base aliada, centro e oposição calculados das bancadas. Sem classificação, tudo `None`. Com classificação parcial
    (parte das cadeiras sem alinhamento), as somas e percentuais são PISOS (só as cadeiras classificadas;
    `nao_classificadas_cadeiras` diz quantas faltam) e as maiorias saem `None`: a base real pode ter o que falta.
    """
    vazio: Dict[str, Any] = {
        "base_aliada_cadeiras": None,
        "base_aliada_pct": None,
        "centro_cadeiras": None,
        "centro_pct": None,
        "oposicao_cadeiras": None,
        "oposicao_pct": None,
        "nao_classificadas_cadeiras": None,
        "maioria_simples_atingida": None,
        "maioria_pec_atingida": None,
    }
    classificadas = _classificadas(bancadas)
    if not classificadas:
        return vazio
    soma = {"BASE_GOVERNO": 0, "INDEPENDENTE_CENTRO": 0, "OPOSICAO": 0}
    for b in classificadas:
        if b["alinhamento"] in soma:
            soma[b["alinhamento"]] += b["cadeiras"]
    base = soma["BASE_GOVERNO"]
    sem_classificar = max(0, total - sum(soma.values()))
    return {
        "base_aliada_cadeiras": base,
        "base_aliada_pct": pct(base, total),
        "centro_cadeiras": soma["INDEPENDENTE_CENTRO"],
        "centro_pct": pct(soma["INDEPENDENTE_CENTRO"], total),
        "oposicao_cadeiras": soma["OPOSICAO"],
        "oposicao_pct": pct(soma["OPOSICAO"], total),
        "nao_classificadas_cadeiras": sem_classificar,
        "maioria_simples_atingida": _atingiu(base, sem_classificar, total // 2 + 1),
        "maioria_pec_atingida": _atingiu(base, sem_classificar, math.ceil(total * 3 / 5)),
    }


def _atingiu(base: int, sem_classificar: int, minimo: int) -> Optional[bool]:
    """True se a base já alcança o mínimo; False se nem com todas as cadeiras sem classificação alcançaria; senão None."""
    if base >= minimo:
        return True
    return False if base + sem_classificar < minimo else None
