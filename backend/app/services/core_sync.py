"""Ponte transitória legado -> core: roda após cada carga do ETL atual (some quando o novo ETL assumir)."""

import logging
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def sync_legacy_to_core(db: Session) -> Dict[str, Any]:
    """Executa etl.sincronizar_legado() (idempotente) e devolve o resumo da execução."""
    core = db.execute(text("SELECT etl.sincronizar_legado()")).scalar_one()
    leg = db.execute(text("SELECT etl.sincronizar_legado_leg()")).scalar_one()
    db.execute(text("SELECT etl.aplicar_linhagens()"))
    db.commit()
    summary = {**dict(core), "legislativo": dict(leg), "rejeitos": core["rejeitos"] + leg["rejeitos"]}
    logger.info("Sincronização legado -> core/leg: %s", summary)
    return summary
