from pydantic import BaseModel
from typing import Optional
from datetime import date
from decimal import Decimal
import uuid


class EconomicDataPointSchema(BaseModel):
    date: date
    year: int
    month: Optional[int] = None
    value: float
    series_code: str
    series_name: str
    unit: str


class AnnualMacroSummarySchema(BaseModel):
    year: int
    dominant_president_name: Optional[str] = None
    ipca_accumulated_year: Optional[float] = None
    gdp_real_growth: Optional[float] = None
    usd_brl_average: Optional[float] = None
    net_debt_pct_gdp: Optional[float] = None
    minimum_wage_nominal_brl: Optional[float] = None

    class Config:
        from_attributes = True
