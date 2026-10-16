from datetime import date
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class PresidentialMandateListItem(BaseModel):
    """Mandato presidencial da listagem; os indicadores mensais vêm de `/mandates/{id}/indicators`."""

    id: UUID
    nome: str
    inicio: date
    fim: Optional[date] = None
    partido: str
    foto_url: Optional[str] = None
