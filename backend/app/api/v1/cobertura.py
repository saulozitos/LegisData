from typing import Any, Dict, List

from app.core.database import get_db
from app.services import cobertura_service
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("", response_model=List[Dict[str, Any]])
def cobertura_dos_paineis(db: Session = Depends(get_db)):
    """
    Para cada painel: fonte, período que a base cobre, última carga e se a base está completa ou parcial.

    Serve para a tela não parecer uma conclusão sobre toda a atividade do Congresso quando mostra só o que a base tem.
    """
    return cobertura_service.cobertura_dos_paineis(db)
