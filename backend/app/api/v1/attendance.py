"""Rankings de ausências no Congresso e cobertura da base de presença (regra em `services.attendance_service`)."""

from typing import Any, Dict, List, Optional

from app.core.database import get_db
from app.services import attendance_service
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/ranking/politicians")
def ranking_parlamentares(
    casa: Optional[str] = Query("ALL", description="ALL, CAMARA ou SENADO"),
    ano_inicio: Optional[int] = Query(None, ge=1995, le=2100),
    ano_fim: Optional[int] = Query(None, ge=1995, le=2100),
    ordenar: str = Query("faltas", description="'faltas', 'taxa', 'nao_justificadas' ou 'baixa_producao'"),
    limit: int = Query(30, ge=1, le=200),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Parlamentares com mais ausências no período, com a taxa de ausência e os pontos IALP para comparar."""
    return attendance_service.ranking_parlamentares(db, casa, ano_inicio, ano_fim, ordenar, limit)


@router.get("/ranking/parties")
def ranking_partidos(
    casa: Optional[str] = Query("ALL", description="ALL, CAMARA ou SENADO"),
    ano_inicio: Optional[int] = Query(None, ge=1995, le=2100),
    ano_fim: Optional[int] = Query(None, ge=1995, le=2100),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Partidos por taxa de ausência. O partido é o do dia (sigla vigente da linhagem)."""
    return attendance_service.ranking_partidos(db, casa, ano_inicio, ano_fim)


@router.get("/coverage")
def cobertura_presenca(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """Cobertura anual da base de presença por Casa e origem, para auditar lacunas."""
    return attendance_service.cobertura_presenca(db)
