from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from uuid import UUID

from app.core.database import get_db
from app.models.executivo import PresidentialMandate, MandateIndicator
from app.schemas.executivo import PresidentialMandateResponse

router = APIRouter()

@router.get("/mandates", response_model=List[PresidentialMandateResponse])
async def list_presidential_mandates(db: Session = Depends(get_db)):
    """
    Lista todos os mandatos presidenciais com seus indicadores
    """
    mandates = db.query(PresidentialMandate).order_by(PresidentialMandate.inicio.asc()).all()
    return mandates

@router.get("/mandates/{mandate_id}/indicators")
async def get_mandate_indicators(mandate_id: UUID, db: Session = Depends(get_db)):
    """
    Retorna os indicadores de um mandato específico, agrupados por data
    """
    mandate = db.query(PresidentialMandate).filter(PresidentialMandate.id == mandate_id).first()
    if not mandate:
        raise HTTPException(status_code=404, detail="Mandate not found")

    indicators = db.query(MandateIndicator).filter(MandateIndicator.mandate_id == mandate_id).order_by(MandateIndicator.data_medicao.asc()).all()
    
    # Agrupar por data de medição para facilitar o plot no frontend
    grouped_data: Dict[str, Dict[str, Any]] = {}
    for ind in indicators:
        date_str = ind.data_medicao.isoformat()
        if date_str not in grouped_data:
            grouped_data[date_str] = {"data": date_str}
        grouped_data[date_str][ind.chave_indicador] = ind.valor

    return list(grouped_data.values())
