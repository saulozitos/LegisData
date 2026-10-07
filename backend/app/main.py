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


@app.get("/", tags=["Health Check"])
def root():
    return {
        "status": "online",
        "service": settings.PROJECT_NAME,
        "docs_url": "/docs",
        "periodo_coberto": "Governo Itamar Franco (1992) ao Governo Atual"
    }
