"""Leitura de arquivos processados pelo ETL com cache invalidado por data de modificação."""

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

_cache: Dict[str, Tuple[float, Any]] = {}

# Primeiro ano das séries anuais (IPCA/PIB/etc.): mandatos iniciados antes começam a contar nele
FIRST_SERIES_YEAR = 1993


def _cached(file_path: Path, loader) -> Optional[Any]:
    """Arquivo ausente ou ilegível devolve None e NUNCA é cacheado (não "envenena" o processo)."""
    try:
        mtime = file_path.stat().st_mtime
    except OSError:
        return None
    key = f"{loader.__name__}:{file_path}"
    hit = _cache.get(key)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        data = loader(file_path)
    except Exception:
        return None
    _cache[key] = (mtime, data)
    return data


def _read_json(file_path: Path) -> Any:
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_json_cached(file_path: Path) -> Optional[Any]:
    """JSON compartilhado entre requisições: trate o retorno como somente leitura."""
    return _cached(file_path, _read_json)


def _read_csv(file_path: Path):
    import pandas as pd

    return pd.read_csv(file_path)


def load_csv_cached(file_path: Path):
    """DataFrame compartilhado entre requisições: filtre/copie, nunca modifique no lugar."""
    return _cached(file_path, _read_csv)


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
