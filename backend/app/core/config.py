import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import List


def get_processed_data_dir() -> Path:
    """
    Localiza o diretório de dados processados do ETL com suporte a múltiplos ambientes:
    - Docker container mount em /etl_data/processed
    - Docker container mount em /etl/data/processed
    - Desenvolvimento local a partir da raiz do repositório
    """
    candidates = [
        Path("/etl_data/processed"),
        Path("/etl/data/processed"),
        Path(__file__).resolve().parents[3] / "etl" / "data" / "processed",
        Path(__file__).resolve().parents[2] / "etl" / "data" / "processed",
    ]
    for c in candidates:
        if c.exists():
            return c
    return Path("/etl_data/processed")


PROCESSED_DATA_DIR = get_processed_data_dir()


class Settings(BaseSettings):
    PROJECT_NAME: str = "LegisData API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "politica_user")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "politica_secret_123")
    POSTGRES_SERVER: str = os.getenv("POSTGRES_SERVER", "localhost")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "politica_db")

    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_SERVER}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )

    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")

    @property
    def sync_database_url(self) -> str:
        """
        Retorna a URL do PostgreSQL sanitizada para SQLAlchemy 2.0 e bancos gerenciados em nuvem (Supabase, Neon, AWS RDS, Railway).
        Garante protocolo postgresql:// e sslmode=require em ambiente de produção.
        """
        url = self.DATABASE_URL.strip()

        # Correção do dialeto para garantir driver psycopg2 explícito no SQLAlchemy 2.0
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif url.startswith("postgresql://") and not url.startswith("postgresql+"):
            url = url.replace("postgresql://", "postgresql+psycopg2://", 1)

        # Em produção (Supabase, Neon, Render), exigir conexões seguras com sslmode=require
        is_cloud_db = any(host in url for host in ["supabase.co", "neon.tech", "aws", "rds", "railway.app", "render.com"])
        if (self.ENVIRONMENT == "production" or is_cloud_db) and "sslmode" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}sslmode=require"

        return url

    @property
    def all_cors_origins(self) -> List[str]:
        """Consolida origens locais e variáveis de ambiente permitidas no CORS."""
        origins = [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
        ]
        if self.CORS_ORIGINS:
            for item in self.CORS_ORIGINS.split(","):
                clean = item.strip()
                if clean and clean not in origins:
                    origins.append(clean)
        return origins

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

