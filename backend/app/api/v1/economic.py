import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from app.core.config import PROCESSED_DATA_DIR

router = APIRouter()
DATA_DIR = PROCESSED_DATA_DIR


@router.get("/annual-summary", response_model=List[Dict[str, Any]])
def get_annual_macro_summary(
    mandate_id: Optional[str] = Query(None, description="Filtrar por ID do mandato presidencial (ex: lula-2003, bolsonaro-2019)")
):
    """
    Retorna a série histórica macroeconômica consolidada ano a ano (1993 a presente):
    IPCA acumulado anual, PIB crescimento real, PIB percentual, inflação anual, inflação acumulada do mandato,
    taxa de desemprego anual (PNAD/IBGE), taxa de desmatamento da Amazônia (INPE/PRODES),
    insegurança alimentar / fome, câmbio médio, dívida líquida e salário mínimo.
    """
    file_path = DATA_DIR / "resumo_macroeconomico_anual.csv"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Resumo macroeconômico não encontrado. Execute o ETL.")
    
    df = pd.read_csv(file_path)

    if mandate_id:
        mandates_file = DATA_DIR / "indicadores_por_mandato.json"
        if mandates_file.exists():
            with open(mandates_file, "r", encoding="utf-8") as f:
                mandates = json.load(f)
            m = next((item for item in mandates if item.get("id_mandato") == mandate_id), None)
            if m:
                ini_yr = int(m["data_inicio"][:4])
                fim_yr = int(m["data_fim"][:4]) if m.get("data_fim") else ini_yr + 4
                if mandate_id == "itamar-franco-1992":
                    target_years = [1993, 1994]
                elif mandate_id == "dilma-2015":
                    target_years = [2015, 2016]
                elif mandate_id == "temer-2016":
                    target_years = [2016, 2017, 2018]
                elif mandate_id == "lula-2023":
                    target_years = [2023, 2024, 2025, 2026]
                else:
                    target_years = list(range(ini_yr, fim_yr + 1))
                df = df[df["ano"].isin(target_years)]

    # Substituir NaN por None para JSON válido
    return df.where(pd.notnull(df), None).to_dict(orient="records")


@router.get("/ipca-monthly")
def get_monthly_ipca(
    ano_inicio: Optional[int] = Query(None, description="Filtrar por ano inicial"),
    ano_fim: Optional[int] = Query(None, description="Filtrar por ano final")
):
    """Retorna o histórico mensal do IPCA com filtros opcionais de data."""
    file_path = DATA_DIR / "ipca_mensal_historico.csv"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Série histórica do IPCA não encontrada.")
    
    df = pd.read_csv(file_path)
    if ano_inicio:
        df = df[df["ano"] >= ano_inicio]
    if ano_fim:
        df = df[df["ano"] <= ano_fim]
        
    return df.to_dict(orient="records")
