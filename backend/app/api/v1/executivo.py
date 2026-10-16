"""Painel do Executivo: mandatos e indicadores mensais (regra em `services.executivo_service`)."""

from typing import Any, Dict, List, Optional
from uuid import UUID

from app.core.database import get_db
from app.schemas.executivo import PresidentialMandateListItem
from app.services import executivo_service
from app.services.iple_service import get_all_mandates_iple, get_mandate_iple
from app.services.presidencia_service import presidente_por_referencia
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/mandates", response_model=List[PresidentialMandateListItem])
def list_presidential_mandates(db: Session = Depends(get_db)):
    """Lista os mandatos presidenciais desde 1995, do mais antigo ao mais recente."""
    return executivo_service.listar_mandatos(db)


@router.get("/mandates/{mandate_id}/summary")
def get_mandate_summary(mandate_id: UUID, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Resumo de KPIs do mandato para os cards, calculado dos indicadores mensais oficiais:
    - Inflação (IPCA acumulado em 12 meses), desemprego (PNAD Contínua, desde 2012), câmbio e Selic meta.
    Indicador sem fonte oficial no período não aparece (nunca vem zerado).
    """
    resumo = executivo_service.resumo_do_mandato(db, mandate_id)
    presidente = presidente_por_referencia(db, str(mandate_id))
    resumo["iple"] = get_mandate_iple(presidente["id_referencia"], db=db) if presidente else None
    return resumo


@router.get("/mandates/{mandate_id}/indicators")
def get_mandate_indicators(mandate_id: UUID, db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """Indicadores mensais de um mandato, agrupados por data (séries temporais para gráficos)."""
    return executivo_service.indicadores_do_mandato(db, mandate_id)


@router.get("/iple")
def get_executive_legislative_power_index(
    mandate_id: Optional[str] = Query(
        None,
        description="ID de referência do mandato presidencial (ex: lula-2023, bolsonaro-2019, fhc-1995)",
    ),
    db: Session = Depends(get_db),
):
    """
    Retorna o Índice de Poder Legislativo do Executivo (IPLE) e variáveis contextuais QCA:
    - Taxa de Sucesso Legislativo (TS) = |P_exec_aprov| / |P_exec|
    - Taxa de Manutenção de Vetos (TMV) = |V_mantidos| / |V_total_apreciados|
    - IPLE = (TS + TMV) / 2 (estritamente 0.0 a 1.0)
    - X1: Tamanho da Oposição (% cadeiras)
    - X2: Fragmentação Partidária (NEP de Laakso & Taagepera)
    - X3: Polarização Ideológica Ponderada (IPP)
    - Calibragem Crisp-set QCA completa (Tabela 4)
    """
    if mandate_id:
        data = get_mandate_iple(mandate_id, db=db)
        if not data:
            raise HTTPException(
                status_code=404,
                detail=f"Mandato '{mandate_id}' não encontrado para cálculo do IPLE.",
            )
        return data
    return get_all_mandates_iple(db=db)
