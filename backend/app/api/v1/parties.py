import uuid
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, or_

from app.core.database import get_db
from app.models import (
    PoliticalParty, Mandate, PartyAffiliation,
    CargoPoliticoEnum, EspectroPoliticoEnum
)

router = APIRouter()

PARTY_COLORS = {
    "PT": "#ef4444",
    "PL": "#1d4ed8",
    "UNIÃO": "#0284c7",
    "PP": "#3b82f6",
    "MDB": "#15803d",
    "PSD": "#f59e0b",
    "REPUBLICANOS": "#0369a1",
    "PSDB": "#38bdf8",
    "PSB": "#ea580c",
    "PDT": "#dc2626",
    "PSOL": "#e11d48",
    "PODE": "#06b6d4",
    "PODEMOS": "#06b6d4",
    "NOVO": "#f97316",
    "PCdoB": "#b91c1c",
    "PV": "#16a34a",
    "CIDADANIA": "#fb923c",
    "REDE": "#0d9488",
    "AVANTE": "#6366f1",
    "SOLIDARIEDADE": "#eab308",
    "PRD": "#84cc16",
}


@router.get("", response_model=List[Dict[str, Any]])
def list_parties(db: Session = Depends(get_db)):
    """
    Retorna o catálogo completo de partidos políticos registrados,
    com suas ideologias, lemas oficiais, espectro político e bancadas atuais.
    """
    parties = db.query(PoliticalParty).filter(PoliticalParty.acronym != "S.PART.").all()

    # Contagem de parlamentares por partido nos mandatos
    deputados_counts = dict(
        db.query(Mandate.party_id, func.count(Mandate.id))
        .filter(Mandate.office == CargoPoliticoEnum.DEPUTADO_FEDERAL)
        .group_by(Mandate.party_id)
        .all()
    )

    senadores_counts = dict(
        db.query(Mandate.party_id, func.count(Mandate.id))
        .filter(Mandate.office == CargoPoliticoEnum.SENADOR)
        .group_by(Mandate.party_id)
        .all()
    )

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
        espectro = p.political_spectrum.value if p.political_spectrum else "CENTRO"

        result.append({
            "id": str(p.id),
            "sigla": p.acronym,
            "nome_completo": p.full_name,
            "numero_eleitoral": p.electoral_number,
            "espectro_politico": espectro,
            "ideologia": p.ideology or "Centrismo Democrático",
            "lema": p.motto or "Pelo desenvolvimento e equilíbrio nacional",
            "logo_url": p.logo_url,
            "total_deputados": total_dep,
            "total_senadores": total_sen,
            "total_parlamentares": total_parl,
            "total_filiados_ativos": total_fil,
            "cor_hex": cor,
        })

    # Ordenar por bancada parlamentar (maiores primeiro) e depois por número eleitoral
    result.sort(key=lambda x: (x["total_parlamentares"], x["total_filiados_ativos"]), reverse=True)
    return result
