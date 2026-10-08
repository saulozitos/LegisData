import os
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings

# Tamanho do pool por processo. Atenção: cada worker do Gunicorn tem o próprio pool,
# então o total de conexões possíveis é workers * (DB_POOL_SIZE + DB_MAX_OVERFLOW),
# que deve ficar abaixo do max_connections do Postgres (padrão 100), com folga para
# ETL e manutenção. Ex.: 4 workers * (5 + 10) = 60 conexões.
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "10"))

# Engine síncrono para operações de dados e migrações
engine = create_engine(
    settings.sync_database_url,
    pool_pre_ping=True,
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    pool_timeout=30,
    pool_recycle=1800
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency para injeção de sessão do banco em rotas do FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
