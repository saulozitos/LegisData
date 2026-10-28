"""Pontos IALP de um parlamentar somados sobre `leg.mv_autoria_pontuada_unica` (uma linha por pessoa e proposição)."""

from app.services.derivados_service import garantir_atualizados
from sqlalchemy import text
from sqlalchemy.orm import Session

_PONTOS_PESSOA = text("SELECT coalesce(sum(pontos_ialp), 0) FROM leg.mv_autoria_pontuada_unica WHERE pessoa_id = :pid")


def pontos_ialp_pessoa(db: Session, pessoa_id: int) -> float:
    """
    Total de pontos IALP da carreira, o mesmo valor do ranking de autores e do ranking de ausências (os três leem o
    derivado). Os rankings de partido ainda calculam a partir de `leg.vw_autoria_pontuada`: enquanto um refresh estiver
    pendente, a soma por partido pode divergir da soma por autor.
    """
    garantir_atualizados(db)
    return float(db.execute(_PONTOS_PESSOA, {"pid": pessoa_id}).scalar() or 0)
