import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from threading import Lock

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import ErroDeDominio
from app.core.migrations import upgrade_schema
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger("uvicorn")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Cross-Origin-Resource-Policy": "cross-origin",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}
HSTS_HEADER = "max-age=31536000; includeSubDomains"
# Rotas utilitárias que não sofrem rate limit (health checks)
RATE_LIMIT_EXEMPT_PATHS = {"/", "/health"}
# A documentação interativa precisa de scripts/estilos externos: CSP restrita não se aplica a ela
DOCS_PATHS = ("/docs", "/redoc")


def startup_db_migrations() -> None:
    """Aplica as migrações Alembic; falha de banco não impede o boot, mas é registrada como erro."""
    try:
        upgrade_schema()
    except Exception as e:
        logger.error("DB auto-migration failed: %s", e)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    startup_db_migrations()
    yield


app = FastAPI(
    title="LegisData API",
    version="1.0.0",
    description="LegisData API - Plataforma Open-Source de Transparência, Atuação Parlamentar e Inteligência Macroeconômica (1992 - Presente)",
    openapi_url=None if settings.is_production else f"{settings.API_V1_STR}/openapi.json",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    lifespan=lifespan,
)


@app.exception_handler(ErroDeDominio)
async def erro_de_dominio_handler(_request: Request, exc: ErroDeDominio) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


# CORS: origens explícitas + regex restrito ao projeto na Vercel; API somente leitura
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.all_cors_origins,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX or None,
    allow_credentials=False,
    allow_methods=["GET", "HEAD", "OPTIONS"],
    allow_headers=["Accept", "Accept-Language", "Content-Type"],
)


class _RateLimiter:
    """Janela deslizante de 60s por IP, em memória (por worker). Suficiente como proteção básica."""

    def __init__(self) -> None:
        self._hits: dict = defaultdict(deque)
        self._lock = Lock()
        self._last_cleanup = time.monotonic()

    def allow(self, key: str, limit: int) -> bool:
        now = time.monotonic()
        with self._lock:
            if now - self._last_cleanup > 300:
                for k in [k for k, q in self._hits.items() if not q or now - q[-1] > 60]:
                    del self._hits[k]
                self._last_cleanup = now
            q = self._hits[key]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True


_rate_limiter = _RateLimiter()


def _client_ip(request: Request) -> str:
    if settings.TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    limit = settings.RATE_LIMIT_PER_MINUTE
    if limit > 0 and request.method != "OPTIONS" and request.url.path not in RATE_LIMIT_EXEMPT_PATHS:
        if not _rate_limiter.allow(_client_ip(request), limit):
            return JSONResponse(
                status_code=429,
                content={"detail": "Muitas requisições. Tente novamente em instantes."},
                headers={"Retry-After": "60"},
            )
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        if name == "Content-Security-Policy" and request.url.path.startswith(DOCS_PATHS):
            continue
        response.headers.setdefault(name, value)
    if settings.is_production:
        response.headers.setdefault("Strict-Transport-Security", HSTS_HEADER)
    return response


app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/", tags=["Health Check"])
def root():
    return {
        "status": "online",
        "service": settings.PROJECT_NAME,
        "docs_url": None if settings.is_production else "/docs",
        "periodo_coberto": "Governo Fernando Henrique Cardoso (1995) ao Governo Atual",
    }


@app.get("/health", tags=["Health Check"])
def health():
    """Liveness probe leve (sem consulta ao banco), usada pelo HEALTHCHECK do Docker."""
    return {"status": "ok"}
