"""Ambiente do Alembic: usa a mesma URL do aplicativo e serializa migrações com advisory lock."""

import os

from alembic import context
from app.core.config import settings
from sqlalchemy import create_engine, pool, text

config = context.config
# Sem metadados-alvo: todas as migrações são escritas à mão (nenhum `--autogenerate`), e o schema `stg` é conferido contra
# o que o ETL espera pelo teste `test_staging_orm_models_match_the_migrated_database`.
target_metadata = None

# Mesmo identificador usado pela migração legada, para que workers concorrentes esperem uns pelos outros
ALEMBIC_ADVISORY_LOCK_ID = 7_450_001


def _url() -> str:
    return os.environ.get("ALEMBIC_DATABASE_URL") or settings.sync_database_url


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        connection.execute(text("SELECT pg_advisory_lock(:id)"), {"id": ALEMBIC_ADVISORY_LOCK_ID})
        connection.commit()
        try:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                include_schemas=True,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": ALEMBIC_ADVISORY_LOCK_ID})
            connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
