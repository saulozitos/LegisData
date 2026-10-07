from fastapi import APIRouter
from app.api.v1.politicians import router as politicians_router
from app.api.v1.economic import router as economic_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.legislative import router as legislative_router
from app.api.v1.parties import router as parties_router
from app.api.v1.cidadania import router as cidadania_router

api_router = APIRouter()
api_router.include_router(politicians_router, prefix="/politicians", tags=["Políticos & Mandatos"])
api_router.include_router(parties_router, prefix="/parties", tags=["Partidos Políticos"])
api_router.include_router(economic_router, prefix="/economic", tags=["Indicadores Macroeconômicos"])
api_router.include_router(analytics_router, prefix="/analytics", tags=["Cruzamentos Analíticos"])
api_router.include_router(legislative_router, prefix="/legislative", tags=["Atividade Legislativa"])
api_router.include_router(cidadania_router, prefix="/cidadania", tags=["Cidadania Ativa & Consultas"])

