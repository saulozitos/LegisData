"""Fusão do staging (`stg`) em `core` e `leg`: roda após cada carga do ETL e é idempotente."""

import logging
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def merge_staging(db: Session) -> Dict[str, Any]:
    """Executa as funções `etl.merge_*` e a unificação de cadastros duplicados e devolve o resumo da execução."""
    core = db.execute(text("SELECT etl.merge_cadastro()")).scalar_one()
    leg = db.execute(text("SELECT etl.merge_legislativo()")).scalar_one()
    db.execute(text("SELECT etl.aplicar_linhagens()"))
    unidos = db.execute(text("SELECT core.unificar_duplicadas()")).scalar_one()
    db.commit()
    summary = {
        **dict(core),
        "legislativo": dict(leg),
        "rejeitos": core["rejeitos"] + leg["rejeitos"],
        "cadastros_unificados": unidos,
    }
    logger.info("Fusão staging -> core/leg: %s", summary)
    return summary
