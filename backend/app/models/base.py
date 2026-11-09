from sqlalchemy.orm import DeclarativeBase


class MigratedBase(DeclarativeBase):
    """Base das tabelas dos schemas ref/core/leg: criadas e alteradas só por migrações Alembic (nunca por create_all)."""

    pass
