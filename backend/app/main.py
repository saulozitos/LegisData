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

# Chave arbitrária do advisory lock que serializa a migração entre os workers do Gunicorn
MIGRATION_ADVISORY_LOCK_ID = 727_420_001

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


def run_db_migrations() -> None:
    """Aplica DDL idempotente sob advisory lock (evita corrida entre workers)."""
    from app.core.database import SessionLocal
    from sqlalchemy import text

    with SessionLocal() as db:
        if db.bind is not None and db.bind.dialect.name != "postgresql":
            return
        # Lock transacional: os demais workers aguardam e depois executam no-ops (IF NOT EXISTS)
        db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": MIGRATION_ADVISORY_LOCK_ID})
        for enum_val in ("PR", "PRC", "PDS", "REQ", "INC"):
            db.execute(text(f"ALTER TYPE tipoproposicaoenum ADD VALUE IF NOT EXISTS '{enum_val}';"))
        for enum_val in ("APROVADO_PLENARIO", "APROVADO_COMISSAO"):
            db.execute(text(f"ALTER TYPE statustramitacaoenum ADD VALUE IF NOT EXISTS '{enum_val}';"))
        db.execute(text('ALTER TABLE certidoes_judiciais ADD COLUMN IF NOT EXISTS "numeroProcesso" VARCHAR(100);'))
        db.execute(text('ALTER TABLE certidoes_judiciais ADD COLUMN IF NOT EXISTS "dataEmissao" VARCHAR(50);'))
        db.execute(text('ALTER TABLE certidoes_judiciais ADD COLUMN IF NOT EXISTS "linkComprovacao" VARCHAR(500);'))
        db.execute(text('ALTER TABLE certidoes_judiciais ADD COLUMN IF NOT EXISTS "codigoAutenticidade" VARCHAR(100);'))
        db.execute(text('ALTER TABLE emendas_parlamentares ALTER COLUMN "tipoEmenda" TYPE VARCHAR(150);'))
        db.execute(text('ALTER TABLE remuneracoes_politicos ALTER COLUMN "salarioLiquido" DROP NOT NULL;'))
        db.execute(text('ALTER TABLE remuneracoes_politicos ALTER COLUMN "cotaParlamentarCeap" DROP NOT NULL;'))
        db.execute(text('ALTER TABLE remuneracoes_politicos ALTER COLUMN "auxilioMoradia" DROP NOT NULL;'))
        db.execute(text('ALTER TABLE remuneracoes_politicos ALTER COLUMN "outrosBeneficios" DROP NOT NULL;'))
        db.execute(text('ALTER TABLE sessoes_votacao ADD COLUMN IF NOT EXISTS "orientacaoGoverno" VARCHAR(20);'))
        # Indicadores sociais oficiais (IBGE/SIDRA) e repasses do Portal da Transparência: colunas novas
        for coluna, tipo in (
            ('"populacaoPobrezaPct"', "NUMERIC(5,2)"),
            ('"populacaoInsegurancaAlimentarTotalPct"', "NUMERIC(5,2)"),
            ('"taxaDesempregoPct"', "NUMERIC(5,2)"),
            ('"serieGini"', "VARCHAR(100)"),
        ):
            db.execute(
                text(f"ALTER TABLE IF EXISTS indicadores_sociais_anuais ADD COLUMN IF NOT EXISTS {coluna} {tipo};")
            )
        db.execute(
            text('ALTER TABLE IF EXISTS indicadores_sociais_uf ADD COLUMN IF NOT EXISTS "pobrezaPct" NUMERIC(5,2);')
        )
        for coluna, tipo in (
            ('"periodoInicio"', "VARCHAR(7)"),
            ('"periodoFim"', "VARCHAR(7)"),
            ('"mesesCobertos"', "INTEGER"),
            ('"coberturaParcial"', "BOOLEAN"),
        ):
            db.execute(text(f"ALTER TABLE IF EXISTS repasses_federais_uf ADD COLUMN IF NOT EXISTS {coluna} {tipo};"))
        db.execute(text('ALTER TABLE sessoes_votacao ADD COLUMN IF NOT EXISTS "orientacoesBancadas" TEXT;'))
        db.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS processos_judiciais (
                id UUID PRIMARY KEY,
                "politicoId" UUID NOT NULL REFERENCES politicos(id) ON DELETE CASCADE,
                "numeroProcesso" VARCHAR(100) NOT NULL,
                "tribunal" VARCHAR(100) NOT NULL,
                "dataProcesso" VARCHAR(50) NOT NULL,
                "classeAssunto" VARCHAR(255) NOT NULL,
                "descricao" TEXT NOT NULL,
                "situacaoJuridica" TEXT NOT NULL,
                "linkComprovacao" VARCHAR(500) NOT NULL,
                "statusResumo" VARCHAR(50) NOT NULL,
                "declaradoTse" BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_processo_politico ON processos_judiciais ("politicoId");
            CREATE INDEX IF NOT EXISTS idx_processo_numero ON processos_judiciais ("numeroProcesso");

            CREATE TABLE IF NOT EXISTS historico_mandatos (
                id UUID PRIMARY KEY,
                "politicoId" UUID NOT NULL REFERENCES politicos(id) ON DELETE CASCADE,
                "partidoId" UUID REFERENCES partidos_politicos(id),
                "partidoSigla" VARCHAR(20) NOT NULL,
                "casa" VARCHAR(20) NOT NULL,
                "situacao" VARCHAR(50) NOT NULL DEFAULT 'EXERCICIO',
                "dataInicio" DATE NOT NULL,
                "dataFim" DATE,
                "observacao" TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_hist_mandato_politico ON historico_mandatos ("politicoId");
            CREATE INDEX IF NOT EXISTS idx_hist_mandato_partido ON historico_mandatos ("partidoSigla");
            CREATE INDEX IF NOT EXISTS idx_hist_mandato_periodo ON historico_mandatos ("dataInicio", "dataFim");
            CREATE INDEX IF NOT EXISTS idx_hist_mandato_situacao ON historico_mandatos ("situacao");

            CREATE TABLE IF NOT EXISTS log_execucao_cron (
                id UUID PRIMARY KEY,
                "dataExecucao" TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                "statusExecucao" VARCHAR(20) NOT NULL,
                "registrosAtualizados" INTEGER NOT NULL DEFAULT 0,
                "tempoProcessamentoSegundos" INTEGER NOT NULL DEFAULT 0,
                "erroMensagem" TEXT,
                "etapa" VARCHAR(50)
            );
            CREATE INDEX IF NOT EXISTS idx_cron_data ON log_execucao_cron ("dataExecucao");
            CREATE INDEX IF NOT EXISTS idx_cron_status ON log_execucao_cron ("statusExecucao");
        """
            )
        )
        # Atualização idempotente de logotipos e metadados oficiais dos partidos
        from app.core.party_constants import OFFICIAL_PARTY_LOGOS, OFFICIAL_PARTY_METADATA

        for sigla, logo in OFFICIAL_PARTY_LOGOS.items():
            db.execute(
                text(
                    """
                    UPDATE partidos_politicos
                    SET "logoUrl" = :logo
                    WHERE UPPER(sigla) = :sigla
                      AND COALESCE("logoUrl", '') = '';
                    """
                ),
                {"sigla": sigla.upper(), "logo": logo},
            )

        for sigla, meta in OFFICIAL_PARTY_METADATA.items():
            db.execute(
                text(
                    """
                    UPDATE partidos_politicos SET
                        "numeroEleitoral" = CASE
                            WHEN :numero IS NOT NULL
                             AND NOT EXISTS (
                                 SELECT 1 FROM partidos_politicos p2
                                 WHERE p2."numeroEleitoral" = :numero AND UPPER(p2.sigla) != :sigla
                             )
                            THEN COALESCE("numeroEleitoral", :numero)
                            ELSE "numeroEleitoral"
                        END,
                        "ideologia" = COALESCE("ideologia", :ideologia),
                        "lema" = COALESCE("lema", :lema),
                        "espectroPolitico" = COALESCE("espectroPolitico", :espectro)
                    WHERE UPPER(sigla) = :sigla;
                    """
                ),
                {
                    "sigla": sigla.upper(),
                    "numero": meta.get("numero"),
                    "ideologia": meta.get("ideologia"),
                    "lema": meta.get("lema"),
                    "espectro": meta.get("espectro"),
                },
            )
        # Saneamento de mandatos espúrios de legendas sem registro oficial no TSE (ex: MISSÃO)
        db.execute(
            text(
                """
                DELETE FROM historico_mandatos WHERE UPPER("partidoSigla") = 'MISSÃO';
                DELETE FROM mandatos WHERE "partidoId" IN (SELECT id FROM partidos_politicos WHERE UPPER(sigla) = 'MISSÃO');
                """
            )
        )
        db.commit()


def startup_db_migrations() -> None:
    """Executa a migração leve; falha de banco não impede o boot, mas é registrada como erro."""
    try:
        run_db_migrations()
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
