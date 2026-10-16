"""Utilidades de consulta compartilhadas pelas rotas: filtros "todos", busca textual segura e fuso de exibição."""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

# Fuso fixo do Brasil (sem horário de verão desde 2019) para exibir datas e horas de sessões, sem depender de tzdata
BRT = timezone(timedelta(hours=-3))
ALL_KEYWORDS = ("todos", "todas", "all")


def escape_like(value: str) -> str:
    """Escapa curingas do LIKE para que '%' e '_' digitados pelo usuário sejam literais."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def contains(column: Any, value: str) -> Any:
    """Condição `coluna ILIKE %valor%` com os curingas do usuário escapados."""
    return column.ilike(f"%{escape_like(value.strip())}%", escape="\\")


def is_filter_all(value: Optional[str]) -> bool:
    return not value or value.strip().lower() in ALL_KEYWORDS


def to_brt(dt: datetime) -> datetime:
    return dt.astimezone(BRT) if dt.tzinfo else dt
