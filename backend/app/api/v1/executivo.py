from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any, Optional
from uuid import UUID

from app.core.database import get_db
from app.models.executivo import PresidentialMandate, MandateIndicator
from app.schemas.executivo import PresidentialMandateResponse

router = APIRouter()


@router.get("/mandates", response_model=List[PresidentialMandateResponse])
async def list_presidential_mandates(db: Session = Depends(get_db)):
    """
    Lista todos os mandatos presidenciais
    """
    mandates = db.query(PresidentialMandate).order_by(PresidentialMandate.inicio.asc()).all()
    return mandates


@router.get("/mandates/{mandate_id}/summary")
async def get_mandate_summary(mandate_id: UUID, db: Session = Depends(get_db)):
    """
    Retorna um resumo de KPIs do mandato para exibição em cards:
    - Inflação IPCA: média, min, max e valor inicial/final
    - Desemprego: média, min, max
    - Aprovação: média, pico e vale
    - Câmbio: valor inicial e final
    - Selic: valor médio e atual
    - Emendas: total acumulado
    """
    mandate = db.query(PresidentialMandate).filter(PresidentialMandate.id == mandate_id).first()
    if not mandate:
        raise HTTPException(status_code=404, detail="Mandate not found")

    indicators = (
        db.query(MandateIndicator)
        .filter(MandateIndicator.mandate_id == mandate_id)
        .order_by(MandateIndicator.data_medicao.asc())
        .all()
    )

    # Agrupar por indicador
    by_key: Dict[str, List[Dict[str, Any]]] = {}
    for ind in indicators:
        key = ind.chave_indicador
        if key not in by_key:
            by_key[key] = []
        by_key[key].append({"data": ind.data_medicao.isoformat(), "valor": ind.valor})

    def stats(values: List[Dict]) -> Optional[Dict]:
        if not values:
            return None
        vals = [v["valor"] for v in values]
        return {
            "primeiro": round(vals[0], 2),
            "ultimo": round(vals[-1], 2),
            "minimo": round(min(vals), 2),
            "maximo": round(max(vals), 2),
            "media": round(sum(vals) / len(vals), 2),
        }

    kpis: Dict[str, Any] = {}
    for key, series in by_key.items():
        kpis[key] = stats(series)

    # Emendas: acumulado total (valor do último mês reportado, que é cumulativo no ano)
    # Calcula melhor como a soma dos valores "finais de cada ano"
    emendas_total = None
    if "emendas_bilhoes" in by_key:
        vals = by_key["emendas_bilhoes"]
        # Agrupa por ano e pega o max de cada ano (valor de dezembro de cada ano)
        por_ano: Dict[int, float] = {}
        for v in vals:
            ano = int(v["data"][:4])
            if ano not in por_ano or v["valor"] > por_ano[ano]:
                por_ano[ano] = v["valor"]
        emendas_total = round(sum(por_ano.values()), 1)
        kpis["emendas_bilhoes"]["total_acumulado"] = emendas_total

    # Calcula variação da inflação: (ultimo - primeiro) em pp
    if "inflacao_ipca" in kpis and kpis["inflacao_ipca"]:
        ipca = kpis["inflacao_ipca"]
        ipca["variacao_pp"] = round(ipca["ultimo"] - ipca["primeiro"], 2)

    return {
        "mandate_id": str(mandate_id),
        "nome": mandate.nome,
        "partido": mandate.partido,
        "inicio": mandate.inicio.isoformat(),
        "fim": mandate.fim.isoformat() if mandate.fim else None,
        "foto_url": mandate.foto_url,
        "kpis": kpis,
        "total_meses": len(by_key.get("inflacao_ipca", [])),
    }


@router.get("/mandates/{mandate_id}/indicators")
async def get_mandate_indicators(mandate_id: UUID, db: Session = Depends(get_db)):
    """
    Retorna os indicadores de um mandato específico, agrupados por data (para gráficos de séries temporais)
    """
    mandate = db.query(PresidentialMandate).filter(PresidentialMandate.id == mandate_id).first()
    if not mandate:
        raise HTTPException(status_code=404, detail="Mandate not found")

    indicators = (
        db.query(MandateIndicator)
        .filter(MandateIndicator.mandate_id == mandate_id)
        .order_by(MandateIndicator.data_medicao.asc())
        .all()
    )

    # Agrupar por data de medição para facilitar o plot no frontend
    grouped_data: Dict[str, Dict[str, Any]] = {}
    for ind in indicators:
        date_str = ind.data_medicao.isoformat()
        if date_str not in grouped_data:
            grouped_data[date_str] = {"data": date_str}
        grouped_data[date_str][ind.chave_indicador] = ind.valor

    return list(grouped_data.values())
