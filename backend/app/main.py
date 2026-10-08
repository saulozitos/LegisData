from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1.router import api_router

app = FastAPI(
    title="LegisData API",
    version="1.0.0",
    description="LegisData API - Plataforma Open-Source de Transparência, Atuação Parlamentar e Inteligência Macroeconômica (1992 - Presente)",
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# CORS Middleware: suporta origens locais, variáveis de ambiente e domínios dinâmicos da Vercel (*.vercel.app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.all_cors_origins,
    allow_origin_regex=r"^https:\/\/.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.on_event("startup")
def startup_db_migrations():
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text
        with SessionLocal() as db:
            db.execute(text('ALTER TABLE certidoes_judiciais ADD COLUMN IF NOT EXISTS "numeroProcesso" VARCHAR(100);'))
            db.execute(text('ALTER TABLE certidoes_judiciais ADD COLUMN IF NOT EXISTS "dataEmissao" VARCHAR(50);'))
            db.execute(text('ALTER TABLE certidoes_judiciais ADD COLUMN IF NOT EXISTS "linkComprovacao" VARCHAR(500);'))
            db.execute(text('ALTER TABLE certidoes_judiciais ADD COLUMN IF NOT EXISTS "codigoAutenticidade" VARCHAR(100);'))
            db.execute(text('''
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
            '''))
            db.commit()
    except Exception as e:
        import logging
        logging.getLogger("uvicorn").warning(f"DB auto-migration warning: {e}")


@app.get("/", tags=["Health Check"])
def root():
    return {
        "status": "online",
        "service": settings.PROJECT_NAME,
        "docs_url": "/docs",
        "periodo_coberto": "Governo Itamar Franco (1992) ao Governo Atual"
    }
