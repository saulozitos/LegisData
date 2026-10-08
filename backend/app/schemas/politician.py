import uuid
from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class PoliticianBase(BaseModel):
    civil_name: str
    electoral_name: str
    cpf: Optional[str] = None
    tse_id: Optional[str] = None
    camara_id: Optional[int] = None
    senado_id: Optional[int] = None
    birth_date: Optional[date] = None
    photo_url: Optional[str] = None
    biography: Optional[str] = None


class PoliticianResponse(PoliticianBase):
    id: uuid.UUID

    class Config:
        from_attributes = True


class MandateResponse(BaseModel):
    id: uuid.UUID
    office: str
    jurisdiction_state: str
    election_year: int
    start_date: date
    end_date: Optional[date] = None
    status: str
    party_acronym: Optional[str] = None

    class Config:
        from_attributes = True
