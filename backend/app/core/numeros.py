"""Conversões numéricas pequenas compartilhadas pelas rotas e serviços."""

from typing import Any, Optional


def pct(parte: float, total: float) -> float:
    """Percentual com uma casa decimal; total zero ou negativo dá 0.0 (percentual sobre base negativa não faz sentido)."""
    return round(parte / total * 100.0, 1) if total > 0 else 0.0


def brl(valor: float) -> str:
    """Valor em reais no formato brasileiro: R$ 1.234,56."""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def opt_float(valor: Any) -> Optional[float]:
    """float(valor) preservando None (dado não informado pela fonte)."""
    return None if valor is None else float(valor)
