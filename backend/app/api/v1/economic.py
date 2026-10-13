from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from app.core.config import PROCESSED_DATA_DIR
from app.core.data_files import FIRST_SERIES_YEAR, load_csv_cached, load_json_cached, mandate_year_range
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()
DATA_DIR = PROCESSED_DATA_DIR


def _read_csv(file_path) -> pd.DataFrame:
    df = load_csv_cached(file_path)
    if df is None:
        raise HTTPException(status_code=500, detail=f"Arquivo de dados ilegível: {file_path.name}")
    if "ano" not in df.columns:
        raise HTTPException(status_code=500, detail=f"Arquivo de dados inválido (sem coluna 'ano'): {file_path.name}")
    return df


def _records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Converte para registros JSON válidos: NaN/NaT/inf viram None (JSON não aceita NaN)."""
    safe = df.replace([np.inf, -np.inf], np.nan)
    return safe.astype(object).replace({np.nan: None}).to_dict(orient="records")


@router.get("/annual-summary", response_model=List[Dict[str, Any]])
def get_annual_macro_summary(
    mandate_id: Optional[str] = Query(
        None,
        description="Filtrar por ID do mandato presidencial (ex: lula-2003, bolsonaro-2019)",
    )
):
    """
    Retorna a série histórica macroeconômica consolidada ano a ano (1993 a presente):
    IPCA acumulado anual, PIB crescimento real, PIB percentual, inflação anual, inflação acumulada do mandato,
    taxa de desemprego anual (PNAD/IBGE), taxa de desmatamento da Amazônia (INPE/PRODES),
    insegurança alimentar / fome, câmbio médio, dívida líquida e salário mínimo.
    """
    file_path = DATA_DIR / "resumo_macroeconomico_anual.csv"
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Resumo macroeconômico não encontrado. Execute o ETL.",
        )

    df = _read_csv(file_path)

    if mandate_id:
        mandates_file = DATA_DIR / "indicadores_por_mandato.json"
        if not mandates_file.exists():
            raise HTTPException(status_code=404, detail="Catálogo de mandatos não encontrado. Execute o ETL.")
        mandates = load_json_cached(mandates_file) or []
        m = next((item for item in mandates if item.get("id_mandato") == mandate_id), None)
        if not m:
            raise HTTPException(status_code=404, detail=f"Mandato '{mandate_id}' não encontrado.")
        ini_yr, fim_yr = mandate_year_range(m, int(df["ano"].max()), FIRST_SERIES_YEAR)
        df = df[(df["ano"] >= ini_yr) & (df["ano"] <= fim_yr)]

    return _records(df)


@router.get("/ipca-monthly")
def get_monthly_ipca(
    ano_inicio: Optional[int] = Query(None, ge=1900, le=2200, description="Filtrar por ano inicial"),
    ano_fim: Optional[int] = Query(None, ge=1900, le=2200, description="Filtrar por ano final"),
):
    """Retorna o histórico mensal do IPCA com filtros opcionais de data."""
    if ano_inicio is not None and ano_fim is not None and ano_inicio > ano_fim:
        raise HTTPException(status_code=422, detail="ano_inicio não pode ser maior que ano_fim.")
    file_path = DATA_DIR / "ipca_mensal_historico.csv"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Série histórica do IPCA não encontrada.")

    df = _read_csv(file_path)
    if ano_inicio is not None:
        df = df[df["ano"] >= ano_inicio]
    if ano_fim is not None:
        df = df[df["ano"] <= ano_fim]

    return _records(df)
