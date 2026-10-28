import uuid
from datetime import datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class StagingBase(DeclarativeBase):
    """Tabelas de entrada do ETL (schema `stg`): o que o ETL grava e as funções `etl.merge_*` projetam em `core`/`leg`."""

    metadata = MetaData(schema="stg")


class MigratedBase(DeclarativeBase):
    """Base das tabelas dos schemas ref/core/leg: criadas e alteradas só por migrações Alembic (nunca por create_all)."""

    pass


class TimeStampedModel(StagingBase):
    """Abstract model adding created_at and updated_at timestamps."""

    __abstract__ = True

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
