"""Configuração dos testes do ETL: raiz do projeto no sys.path e ambiente mínimo para importar o backend."""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
for candidate in (str(PROJECT_ROOT), str(PROJECT_ROOT / "backend")):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

# O engine do backend é criado no import (sem conectar). Uma URL qualquer basta para os testes de import.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("ENVIRONMENT", "test")


# ── Postgres de teste do ETL (porta 5433, `make test-db-up`) ─────────────────────────────────────────────────────────
import pytest  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

SERVIDOR_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg2://test:test_pass@localhost:5433/legis_test")
# Banco próprio no mesmo servidor: a suíte do backend recria os schemas do `legis_test` e não pode colidir com esta.
BANCO_ETL = "legis_test_etl"
TEST_DATABASE_URL = SERVIDOR_URL.rsplit("/", 1)[0] + f"/{BANCO_ETL}"


def _schema_atualizado(engine) -> bool:
    """O banco próprio já está na última revisão (evita refazer ~90 s de migrações a cada execução)."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from app.core.migrations import BACKEND_DIR

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cabeca = ScriptDirectory.from_config(config).get_current_head()
    try:
        with engine.connect() as conn:
            return conn.execute(text("SELECT version_num FROM public.alembic_version")).scalar() == cabeca
    except Exception:  # noqa: BLE001 - sem tabela de versão: schema por criar
        return False


@pytest.fixture(scope="module")
def pg_engine():
    try:
        admin = create_engine(SERVIDOR_URL, isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            if not conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": BANCO_ETL}).scalar():
                conn.execute(text(f"CREATE DATABASE {BANCO_ETL}"))
        admin.dispose()
        engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
        reutilizar = _schema_atualizado(engine)
    except OperationalError as exc:
        pytest.skip(f"Postgres de teste indisponível em {SERVIDOR_URL} ({exc.__class__.__name__}); `make test-db-up`")
    if not reutilizar:
        with engine.begin() as conn:
            for schema in ("api", "stg", "leg", "param", "etl", "eco", "core", "ref", "public"):
                conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
        from app.core.migrations import upgrade_schema

        anterior = os.environ.get("ALEMBIC_DATABASE_URL")
        os.environ["ALEMBIC_DATABASE_URL"] = TEST_DATABASE_URL
        try:
            upgrade_schema()
        finally:
            if anterior is None:
                os.environ.pop("ALEMBIC_DATABASE_URL", None)
            else:
                os.environ["ALEMBIC_DATABASE_URL"] = anterior
    yield engine
    engine.dispose()
