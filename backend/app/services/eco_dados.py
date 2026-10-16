"""Leitura das séries anuais de `eco` no formato por ano que as telas de comparação usam."""

from typing import Any, Dict, List

from app.core.errors import ErroDeDominio
from app.services import economia_service
from sqlalchemy import text
from sqlalchemy.orm import Session

_ANUAIS_SQL = text(
    """
    SELECT extract(year FROM o.referencia)::int AS ano, s.codigo, o.valor
    FROM eco.observacao o JOIN eco.serie s ON s.id = o.serie_id
    WHERE o.uf IS NULL AND s.periodicidade = 'ANUAL' AND s.codigo = ANY(:codigos)
    """
)

# campo devolvido -> código da série
SOCIAIS = {
    "extrema_pobreza_pct": "EXTREMA_POBREZA_PCT",
    "pobreza_pct": "POBREZA_PCT",
    "analfabetismo": "ANALFABETISMO",
    "inseguranca_alimentar_pct": "INSEGURANCA_ALIMENTAR_PCT",
    "gini": "GINI",
}
SEGURANCA = {"taxa_homicidios": "HOMICIDIOS_TAXA", "homicidios_total": "HOMICIDIOS_TOTAL"}


def _por_ano(db: Session, campos: Dict[str, str]) -> Dict[int, Dict[str, Any]]:
    codigo_para_campo = {codigo: campo for campo, codigo in campos.items()}
    por_ano: Dict[int, Dict[str, Any]] = {}
    for ano, codigo, valor in db.execute(_ANUAIS_SQL, {"codigos": list(codigo_para_campo)}):
        por_ano.setdefault(ano, {})[codigo_para_campo[codigo]] = float(valor)
    return por_ano


def sociais_por_ano(db: Session) -> Dict[int, Dict[str, Any]]:
    """Indicadores sociais nacionais por ano; o que a fonte não publicou fica ausente (nunca zero)."""
    return _por_ano(db, SOCIAIS)


def seguranca_por_ano(db: Session) -> Dict[int, Dict[str, Any]]:
    """Homicídios por ano; feminicídio não tem fonte aberta automatizável e vem sempre ausente."""
    return _por_ano(db, SEGURANCA)


def macro_por_ano(db: Session) -> Dict[int, Dict[str, Any]]:
    """Resumo macroeconômico por ano, com as mesmas colunas de `GET /economic/annual-summary`."""
    try:
        linhas: List[Dict[str, Any]] = economia_service.resumo_anual(db, None)
    except ErroDeDominio:  # série ainda não carregada: a comparação segue sem trajetória macro
        return {}
    return {linha["ano"]: linha for linha in linhas}
