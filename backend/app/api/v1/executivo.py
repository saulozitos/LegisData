from typing import Any, Dict, List, Optional
from uuid import UUID

from app.core.database import get_db
from app.models.executivo import MandateIndicator, PresidentialMandate
from app.schemas.executivo import PresidentialMandateListItem
from app.services.iple_service import get_all_mandates_iple, get_mandate_iple
from app.services.presidential_service import get_president_by_reference
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/mandates", response_model=List[PresidentialMandateListItem])
def list_presidential_mandates(db: Session = Depends(get_db)):
    """
    Lista todos os mandatos presidenciais
    """
    mandates = db.query(PresidentialMandate).order_by(PresidentialMandate.inicio.asc()).all()
    return mandates


@router.get("/mandates/{mandate_id}/summary")
def get_mandate_summary(mandate_id: UUID, db: Session = Depends(get_db)):
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
        raise HTTPException(status_code=404, detail="Mandato não encontrado.")

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
    if by_key.get("emendas_bilhoes") and kpis.get("emendas_bilhoes"):
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

    pres = get_president_by_reference(str(mandate_id), db)
    ref_id = pres.get("id_referencia") if pres else None
    iple_data = get_mandate_iple(ref_id, db=db) if ref_id else None

    return {
        "mandate_id": str(mandate_id),
        "nome": mandate.nome,
        "partido": mandate.partido,
        "inicio": mandate.inicio.isoformat(),
        "fim": mandate.fim.isoformat() if mandate.fim else None,
        "foto_url": mandate.foto_url,
        "kpis": kpis,
        "total_meses": len(by_key.get("inflacao_ipca", [])),
        "iple": iple_data,
    }


@router.get("/mandates/{mandate_id}/indicators")
def get_mandate_indicators(mandate_id: UUID, db: Session = Depends(get_db)):
    """
    Retorna os indicadores de um mandato específico, agrupados por data (para gráficos de séries temporais)
    """
    mandate = db.query(PresidentialMandate).filter(PresidentialMandate.id == mandate_id).first()
    if not mandate:
        raise HTTPException(status_code=404, detail="Mandato não encontrado.")

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
