"""Conversões numéricas pequenas compartilhadas pelas rotas e serviços."""

from typing import Any, Optional


def pct(parte: float, total: float) -> float:
    """Percentual com uma casa decimal; total zero ou negativo dá 0.0 (percentual sobre base negativa não faz sentido)."""
    return round(parte / total * 100.0, 1) if total > 0 else 0.0


def taxa_ou_desconhecida(parte: float, total: float) -> Optional[float]:
    """
    Taxa em percentual (uma casa decimal) de `parte` sobre `total`; None quando a base é zero ou negativa, porque a taxa
    não existe (pago sem empenhado não é 0% de execução). Use `pct` para a participação de uma parte no total que a contém.
    """
    return round(parte / total * 100.0, 1) if total > 0 else None


def brl(valor: float) -> str:
    """Valor em reais no formato brasileiro: R$ 1.234,56."""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def opt_float(valor: Any) -> Optional[float]:
    """float(valor) preservando None (dado não informado pela fonte)."""
    return None if valor is None else float(valor)
