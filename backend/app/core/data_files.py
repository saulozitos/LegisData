"""Intervalos de anos dos mandatos para as séries anuais."""

from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional, Tuple

# Primeiro ano das séries anuais (IPCA/PIB/etc.): mandatos iniciados antes começam a contar nele
FIRST_SERIES_YEAR = 1995


def _parse_date(value: str) -> date:
    return datetime.strptime(value[:10], "%Y-%m-%d").date()


def mandate_year_range(mandate: Dict[str, Any], last_data_year: int, min_year: Optional[int] = None) -> Tuple[int, int]:
    """
    Intervalo inclusivo de anos de um mandato. A data de fim é exclusiva (o mandato termina no dia anterior),
    portanto um mandato que termina em 01/01/AAAA não inclui o ano AAAA. Sem data de fim: até o último ano da série.
    """
    start = _parse_date(mandate["data_inicio"])
    first = max(start.year, min_year) if min_year else start.year
    if mandate.get("data_fim"):
        last = (_parse_date(mandate["data_fim"]) - timedelta(days=1)).year
    else:
        last = max(last_data_year, start.year)
    return first, max(first, last)
