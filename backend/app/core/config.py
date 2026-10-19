import os
from typing import List
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings
from sqlalchemy.engine import make_url

# Sufixos de hospedagem de bancos gerenciados que exigem TLS
CLOUD_DB_HOST_SUFFIXES = (
    "supabase.co",
    "supabase.com",
    "neon.tech",
    "rds.amazonaws.com",
    "railway.app",
    "render.com",
)


class Settings(BaseSettings):
    PROJECT_NAME: str = "LegisData API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "politica_user")
    POSTGRES_SERVER: str = os.getenv("POSTGRES_SERVER", "localhost")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "politica_db")
    POSTGRES_PASSWORD: str = ""
    DATABASE_URL: str = ""

    # Modo SSL do Postgres: "", "disable", "prefer", "require", "verify-full"...
    # Vazio = automático (require para bancos gerenciados em nuvem, nada para os demais).
    DB_SSLMODE: str = os.getenv("DB_SSLMODE", "")
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "5"))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "5"))
    DB_POOL_TIMEOUT: int = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    # Buscas de emendas ao mesmo tempo, por worker: precisa ficar abaixo do pool (DB_POOL_SIZE + DB_MAX_OVERFLOW), ou as
    # buscas lentas seguram todas as conexões e o resto da API espera o DB_POOL_TIMEOUT.
    EMENDAS_MAX_BUSCAS_SIMULTANEAS: int = int(os.getenv("EMENDAS_MAX_BUSCAS_SIMULTANEAS", "3"))

    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    # Regex adicional para previews do projeto na Vercel (restrito ao projeto, não a qualquer *.vercel.app)
    CORS_ORIGIN_REGEX: str = os.getenv("CORS_ORIGIN_REGEX", r"^https://legisdata(-[a-z0-9-]+)?\.vercel\.app$")

    # Limite de requisições por IP/minuto (em memória, por worker). 0 desativa.
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))
    # Token que autoriza renovação forçada do cache de consultas públicas (vazio = desabilitado)
    ADMIN_REFRESH_TOKEN: str = os.getenv("ADMIN_REFRESH_TOKEN", "")
    # Confia em X-Forwarded-For (somente atrás de proxy reverso controlado)
    TRUST_PROXY_HEADERS: bool = os.getenv("TRUST_PROXY_HEADERS", "false").lower() == "true"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        db_url = self.DATABASE_URL or os.getenv("DATABASE_URL")
        pwd = self.POSTGRES_PASSWORD or os.getenv("POSTGRES_PASSWORD")

        # Falha estrita (crash) para mitigar vulnerabilidade de segurança: nenhuma senha padrão
        if not db_url and not pwd:
            raise RuntimeError(
                "Falha de segurança crítica: Nenhuma senha de banco (POSTGRES_PASSWORD) ou DATABASE_URL foi configurada no ambiente. "
                "Defina POSTGRES_PASSWORD no arquivo .env para iniciar a aplicação."
            )

        if not db_url:
            db_url = (
                f"postgresql://{quote_plus(self.POSTGRES_USER)}:{quote_plus(pwd or '')}"
                f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )

        self.POSTGRES_PASSWORD = pwd or ""
        self.DATABASE_URL = db_url

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

        # SSL: configurável via DB_SSLMODE; no modo automático só exige TLS para bancos gerenciados em nuvem
        # (detecção pelo hostname parseado, nunca por substring da URL, que inclui usuário e senha).
        if "sslmode" not in url:
            sslmode = self.DB_SSLMODE.strip()
            if not sslmode and self._is_cloud_host(url):
                sslmode = "require"
            if sslmode:
                sep = "&" if "?" in url else "?"
                url = f"{url}{sep}sslmode={sslmode}"

        return url

    @staticmethod
    def _is_cloud_host(url: str) -> bool:
        try:
            host = (make_url(url).host or "").lower()
        except Exception:
            return False
        return any(host == suffix or host.endswith("." + suffix) for suffix in CLOUD_DB_HOST_SUFFIXES)

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

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

    API_PORT: int = 8000

    model_config = {
        "env_file": (".env", "../.env"),
        "case_sensitive": True,
        "extra": "ignore",
    }


settings = Settings()
