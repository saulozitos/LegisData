from datetime import date
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class MandateIndicatorBase(BaseModel):
    chave_indicador: str
    valor: float
    data_medicao: date


class MandateIndicatorResponse(MandateIndicatorBase):
    id: UUID
    mandate_id: UUID

    model_config = ConfigDict(from_attributes=True)


class PresidentialMandateBase(BaseModel):
    nome: str
    inicio: date
    fim: Optional[date] = None
    partido: str
    foto_url: Optional[str] = None


class PresidentialMandateResponse(PresidentialMandateBase):
    id: UUID
    indicadores: List[MandateIndicatorResponse] = []

    model_config = ConfigDict(from_attributes=True)
