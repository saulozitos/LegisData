from typing import Any, Dict

from app.core.database import get_db
from app.schemas.feedback import RelatoDeErro
from app.services import feedback_service
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

router = APIRouter()


@router.post("/erros", status_code=201, response_model=Dict[str, Any])
def relatar_erro(relato: RelatoDeErro, db: Session = Depends(get_db)):
    """
    Recebe "Encontrou uma informação incorreta?" ligado ao parlamentar, à matéria ou ao painel consultado.

    Não aceita CPF no texto. O relato fica numa tabela interna para a equipe corrigir a base; nada aparece publicamente.
    """
    return feedback_service.registrar(db, relato)
