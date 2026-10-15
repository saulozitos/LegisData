from typing import Any, Dict, List, Optional

from app.core.database import get_db
from app.models.analytics import LogExecucaoCron
from app.schemas.parties import (
    CronLogItem,
    IPPMRankingResponse,
    PartyMandateTimelineResponse,
)
from app.services.party_catalog_service import list_party_catalog
from app.services.party_productivity_service import (
    calculate_party_ippm_ranking,
    get_party_mandate_timeline,
)
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("", response_model=List[Dict[str, Any]])
def list_parties(db: Session = Depends(get_db)):
    """
    Retorna o catálogo completo de partidos políticos registrados,
    com suas ideologias, lemas oficiais, espectro político e bancadas atuais.
    """
    return list_party_catalog(db)


@router.get("/ippm-ranking", response_model=IPPMRankingResponse)
def get_ippm_ranking(
    ano: Optional[int] = Query(2026, description="Ano legislativo de referência"),
    casa: Optional[str] = Query("ALL", description="Casa Legislativa: ALL, CAMARA, SENADO"),
    bloco: Optional[str] = Query("ALL", description="Bloco Político: ALL, GOVERNO, OPOSICAO, INDEPENDENTE"),
    espectro: Optional[str] = Query("ALL", description="Espectro Político: ALL, ESQUERDA, CENTRO, DIREITA"),
    db: Session = Depends(get_db),
):
    """
    Retorna o ranking oficial do Índice de Produtividade Partidária Média (IPPM)
    agregado pelo IALP ponderado normalizado pelo tamanho da bancada ativa
    (Cadeiras-Dia em Exercício), acompanhado dos três pilares e diagnóstico de quadrante.
    """
    return calculate_party_ippm_ranking(db=db, ano=ano, casa=casa, bloco=bloco, espectro=espectro)


@router.get("/{sigla}/historico-bancada", response_model=PartyMandateTimelineResponse)
def get_party_timeline(sigla: str, db: Session = Depends(get_db)):
    """
    Retorna a linha do tempo e situação de todos os parlamentares do partido,
    isolando licenças médicas, afastamentos para ministérios e suplências ativas.
    """
    return get_party_mandate_timeline(partido_sigla=sigla, db=db)


@router.get("/cron/logs", response_model=List[CronLogItem])
def get_cron_logs(db: Session = Depends(get_db)):
    """
    Retorna os logs mais recentes de execução da rotina CRON de sincronização.
    """
    logs = db.query(LogExecucaoCron).order_by(LogExecucaoCron.data_execucao.desc()).limit(20).all()
    return [
        CronLogItem(
            id=str(log.id),
            data_execucao=log.data_execucao.isoformat(),
            status_execucao=log.status_execucao,
            registros_atualizados=log.registros_atualizados,
            tempo_processamento_segundos=log.tempo_processamento_segundos,
            erro_mensagem=log.erro_mensagem,
            etapa=log.etapa,
        )
        for log in logs
    ]
