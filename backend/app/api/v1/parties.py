from datetime import date
from typing import Any, Dict, List, Optional

from app.core.database import get_db
from app.core.party_constants import OFFICIAL_PARTY_LOGOS, PARTY_COLORS
from app.models import CargoPoliticoEnum, Mandate, PartyAffiliation, PoliticalParty, StatusMandatoEnum
from app.models.analytics import LogExecucaoCron
from app.schemas.parties import (
    CronLogItem,
    IPPMRankingResponse,
    PartyMandateTimelineResponse,
)
from app.services.party_productivity_service import (
    calculate_party_ippm_ranking,
    get_party_mandate_timeline,
)
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("", response_model=List[Dict[str, Any]])
def list_parties(db: Session = Depends(get_db)):
    """
    Retorna o catálogo completo de partidos políticos registrados,
    com suas ideologias, lemas oficiais, espectro político e bancadas atuais.
    """
    parties = (
        db.query(PoliticalParty).filter(PoliticalParty.acronym != "S.PART.").order_by(PoliticalParty.acronym).all()
    )

    # Bancada ATUAL: somente mandatos em curso (sem data de fim ou com fim futuro) e em exercício,
    # contando cada parlamentar uma única vez por partido (nunca mandatos históricos).
    current_filter = (
        or_(Mandate.end_date.is_(None), Mandate.end_date >= date.today()),
        Mandate.status.in_([StatusMandatoEnum.TITULAR_ATIVO, StatusMandatoEnum.SUPLENTE_EM_EXERCICIO]),
    )

    def current_counts(office: CargoPoliticoEnum) -> dict:
        return dict(
            db.query(Mandate.party_id, func.count(func.distinct(Mandate.politician_id)))
            .filter(Mandate.office == office, *current_filter)
            .group_by(Mandate.party_id)
            .all()
        )

    deputados_counts = current_counts(CargoPoliticoEnum.DEPUTADO_FEDERAL)
    senadores_counts = current_counts(CargoPoliticoEnum.SENADOR)

    # Contagem de filiados ativos na base (TSE)
    filiados_counts = dict(
        db.query(PartyAffiliation.party_id, func.count(PartyAffiliation.id))
        .filter(PartyAffiliation.is_current.is_(True))
        .group_by(PartyAffiliation.party_id)
        .all()
    )

    result = []
    for p in parties:
        sigla_upper = p.acronym.upper()
        total_dep = deputados_counts.get(p.id, 0)
        total_sen = senadores_counts.get(p.id, 0)
        total_fil = filiados_counts.get(p.id, 0)
        total_parl = total_dep + total_sen

        cor = PARTY_COLORS.get(sigla_upper, "#64748b")
        espectro = p.political_spectrum.value if p.political_spectrum else None

        result.append(
            {
                "id": str(p.id),
                "sigla": p.acronym,
                "nome_completo": p.full_name,
                "numero_eleitoral": p.electoral_number,
                "espectro_politico": espectro,
                "ideologia": p.ideology,
                "lema": p.motto,
                "logo_url": p.logo_url or OFFICIAL_PARTY_LOGOS.get(sigla_upper),
                "total_deputados": total_dep,
                "total_senadores": total_sen,
                "total_parlamentares": total_parl,
                "total_filiados_ativos": total_fil,
                "cor_hex": cor,
            }
        )

    # Ordenar por bancada parlamentar (maiores primeiro) e depois por número eleitoral
    result.sort(
        key=lambda x: (x["total_parlamentares"], x["total_filiados_ativos"]),
        reverse=True,
    )
    return result


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
