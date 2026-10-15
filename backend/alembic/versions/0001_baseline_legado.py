"""Baseline do schema legado (public).

Bancos existentes já têm estas tabelas (criadas pelo ORM e por run_db_migrations): a revisão não faz nada.
Bancos novos recebem o snapshot do schema legado para que as revisões seguintes tenham onde se apoiar.

Revision ID: 0001
Revises:
"""

from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

BASELINE_SQL = Path(__file__).resolve().parent.parent / "baseline_legacy.sql"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.exec_driver_sql("SELECT to_regclass('public.politicos')").scalar():
        return
    bind.exec_driver_sql(BASELINE_SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    raise NotImplementedError("O baseline legado não é reversível.")
