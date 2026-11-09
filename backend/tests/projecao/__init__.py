"""
Projeção de teste: as linhas semeadas com os modelos de `tests/stg_models.py` viram `core`/`leg`.

Só existe no banco de teste. `instalar(engine)` cria as tabelas de entrada (`w_*` em `public` e as cinco do legado em
`stg`) e as duas funções de projeção; `merge_staging(db)` as roda e devolve o resumo.
"""

from pathlib import Path
from typing import Any, Dict

from app.services.derivados_service import reservar_derivados
from sqlalchemy import text
from sqlalchemy.orm import Session

PASTA = Path(__file__).parent


def instalar(engine: Any) -> None:
    from tests.stg_models import StagingBase

    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS stg"))
        for arquivo in ("cadastro.sql", "legislativo.sql"):
            conn.exec_driver_sql((PASTA / arquivo).read_text(encoding="utf-8").replace("%", "%%"))
    StagingBase.metadata.create_all(engine)
    with engine.begin() as conn:
        # tabelas de entrada sem chave única nem estrangeira: o teste semeia linhas em qualquer ordem e repetidas, como as
        # tabelas de trabalho que a projeção sempre leu
        restricoes = conn.execute(
            text(
                "SELECT conrelid::regclass::text, conname FROM pg_constraint WHERE contype IN ('u', 'f') "
                "AND conrelid::regclass::text LIKE 'w\\_%'"
            )
        ).all()
        for tabela, nome in restricoes:
            conn.execute(text(f'ALTER TABLE {tabela} DROP CONSTRAINT "{nome}"'))


def merge_staging(db: Session, preparar: bool = False, **_: Any) -> Dict[str, Any]:
    """Projeta o que os testes semearam; `preparar` só existe para manter a assinatura dos testes."""
    reservar_derivados(db)
    core = db.execute(text("SELECT public.projetar_cadastro()")).scalar_one()
    leg = db.execute(text("SELECT public.projetar_legislativo()")).scalar_one()
    db.execute(text("SELECT etl.aplicar_linhagens()"))
    db.commit()
    return {**dict(core), "legislativo": dict(leg), "rejeitos": core["rejeitos"] + leg["rejeitos"]}
