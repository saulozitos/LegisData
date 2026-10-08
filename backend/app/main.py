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
            db.commit()
    except Exception as e:
        import logging
        logging.getLogger("uvicorn").warning(f"DB certidoes columns auto-migration warning: {e}")


@app.get("/", tags=["Health Check"])
def root():
    return {
        "status": "online",
        "service": settings.PROJECT_NAME,
        "docs_url": "/docs",
        "periodo_coberto": "Governo Itamar Franco (1992) ao Governo Atual"
    }
