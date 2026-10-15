"""Execução programática das revisões Alembic (usada pelo boot da API e pelo ETL)."""

from pathlib import Path

from alembic import command
from alembic.config import Config

BACKEND_DIR = Path(__file__).resolve().parents[2]


def upgrade_schema(revision: str = "head") -> None:
    """Aplica as revisões pendentes; o env.py serializa execuções concorrentes com advisory lock."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, revision)
