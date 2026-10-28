from typing import Generator, Optional

from app.core.config import settings
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

POOL_RECYCLE_SEGUNDOS = 1800


def criar_engine(
    url: str,
    pool_size: Optional[int] = None,
    max_overflow: Optional[int] = None,
    pool_timeout: Optional[float] = None,
) -> Engine:
    """
    Engine síncrono do app (o mesmo para operações de dados e migrações); os testes o criam contra o banco de teste.
    O pool segue a configuração, salvo o que o chamador fixar (o pool dedicado dos derivados usa uma conexão só).
    """
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=settings.DB_POOL_SIZE if pool_size is None else pool_size,
        max_overflow=settings.DB_MAX_OVERFLOW if max_overflow is None else max_overflow,
        pool_timeout=settings.DB_POOL_TIMEOUT if pool_timeout is None else pool_timeout,
        pool_recycle=POOL_RECYCLE_SEGUNDOS,
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
