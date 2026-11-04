"""Ambiente do Alembic: usa a mesma URL do aplicativo e serializa migrações com advisory lock."""

import os

from alembic import context
from app.core.config import settings
from app.models import StagingBase
from sqlalchemy import create_engine, pool, text

config = context.config
target_metadata = StagingBase.metadata

# Mesmo identificador usado pela migração legada, para que workers concorrentes esperem uns pelos outros
ALEMBIC_ADVISORY_LOCK_ID = 7_450_001


def _url() -> str:
    return os.environ.get("ALEMBIC_DATABASE_URL") or settings.sync_database_url


def include_object(obj, name, type_, reflected, compare_to):
    """
    O alvo (`target_metadata`) só conhece o schema `stg`; ref/core/leg/eco/fin/param/etl nascem em migrações escritas à mão.
    Sem este filtro, `alembic revision --autogenerate` proporia apagar todas as tabelas dos outros schemas.
    """
    if type_ == "table":
        return getattr(obj, "schema", None) == "stg"
    return True  # colunas e índices seguem a tabela que já passou pelo filtro


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
                include_object=include_object,
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
