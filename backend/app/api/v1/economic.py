"""Séries econômicas anuais e mensais (regra em `services.economia_service`)."""

from typing import Any, Dict, List, Optional

from app.core.database import get_db
from app.services import economia_service
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/annual-summary", response_model=List[Dict[str, Any]])
def get_annual_macro_summary(
    mandate_id: Optional[str] = Query(
        None,
        description="Filtrar por ID do mandato presidencial (ex: lula-2003, bolsonaro-2019)",
    ),
    db: Session = Depends(get_db),
):
    """
    Retorna a série histórica macroeconômica consolidada ano a ano (1995 a presente):
    IPCA acumulado anual, PIB crescimento real, inflação acumulada do mandato, taxa de desemprego anual,
    taxa de desmatamento da Amazônia (INPE/PRODES), insegurança alimentar, câmbio médio, dívida líquida e salário
    mínimo. Valor sem fonte oficial no ano vem `null`.
    """
    return economia_service.resumo_anual(db, mandate_id)


@router.get("/ipca-monthly")
def get_monthly_ipca(
    ano_inicio: Optional[int] = Query(None, ge=1900, le=2200, description="Filtrar por ano inicial"),
    ano_fim: Optional[int] = Query(None, ge=1900, le=2200, description="Filtrar por ano final"),
    db: Session = Depends(get_db),
):
    """Retorna o histórico mensal do IPCA (desde 1995) com filtros opcionais de data."""
    return economia_service.ipca_mensal(db, ano_inicio, ano_fim)
