"""Fusão do staging (`stg`) em `core` e `leg`: roda após cada carga do ETL e é idempotente."""

import logging
from typing import Any, Dict

from app.services.derivados_service import reservar_derivados
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def merge_staging(
    db: Session, allow_synthetic: bool = False, allow_unverified: bool = False, preparar: bool = True
) -> Dict[str, Any]:
    """
    Prepara o staging (`etl.preparar_staging`: resolve, em tabelas temporárias de trabalho, a que pessoa, partido, mandato e
    proposição cada registro das tabelas planas se refere), executa as funções `etl.merge_*` sobre elas e devolve o resumo da
    execução. Tudo numa só transação: as tabelas de trabalho vivem até o `commit`. `preparar=False` é para quem já montou as
    tabelas de trabalho na sessão (os testes que semeiam linhas direto).
    """
    reservar_derivados(db)  # a fusão escreve em `core.pessoa` antes das dependências: pega a trava de controle primeiro
    preparo: Dict[str, Any] = {}
    if preparar:
        preparo = db.execute(
            text("SELECT etl.preparar_staging(:sintetico, :nao_verificado)"),
            {"sintetico": allow_synthetic, "nao_verificado": allow_unverified},
        ).scalar_one()
    core = db.execute(text("SELECT etl.merge_cadastro()")).scalar_one()
    leg = db.execute(text("SELECT etl.merge_legislativo()")).scalar_one()
    db.execute(text("SELECT etl.aplicar_linhagens()"))
    db.commit()
    summary = {
        **dict(core),
        "legislativo": dict(leg),
        "rejeitos": core["rejeitos"] + leg["rejeitos"],
        "preparo": dict(preparo),
    }
    logger.info("Fusão staging -> core/leg: %s", summary)
    return summary
