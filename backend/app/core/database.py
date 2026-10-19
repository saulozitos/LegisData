from typing import Generator

from app.core.config import settings
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def criar_engine(url: str) -> Engine:
    """Engine síncrono do app (o mesmo para operações de dados e migrações); os testes o criam contra o banco de teste."""
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_recycle=1800,
        hide_parameters=True,  # um erro do banco não copia os valores do lote (nomes, textos) para o log
    )


engine = criar_engine(settings.sync_database_url)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency para injeção de sessão do banco em rotas do FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
