"""Janela de dados e regras de calendário dos mandatos, sem dependência de outros serviços."""

import re
from datetime import date, timedelta
from typing import Any, List, Optional, Tuple

from app.core.data_files import FIRST_SERIES_YEAR

# Decisão D8: toda a janela de dados começa em 1995-01-01 (a restrição de `eco.observacao` e o loader usam o mesmo ano).
PRIMEIRO_ANO = FIRST_SERIES_YEAR

SLUG_MANDATO = re.compile(r"^[a-z0-9-]{1,60}$")

Serie = List[Tuple[date, float]]


def nome_do_mandato(nome: str, rotulo: Optional[str]) -> str:
    """Nome de exibição com o rótulo do mandato: "Lula (Lula 2)"; sem rótulo, só o nome."""
    return f"{nome} ({rotulo})" if rotulo else nome


def intervalo_de_anos(inicio: date, fim: Optional[date], ultimo_ano_da_serie: int) -> Tuple[int, int]:
    """Anos inclusivos de um mandato. O fim é exclusivo: o mandato que termina em 01/01/AAAA não inclui AAAA."""
    primeiro = max(inicio.year, PRIMEIRO_ANO)
    ultimo = (fim - timedelta(days=1)).year if fim is not None else max(ultimo_ano_da_serie, inicio.year)
    return primeiro, max(primeiro, ultimo)


def do_mandato(serie: Serie, inicio: date, fim_exclusivo: date) -> Serie:
    """Meses do mandato: cada mês vale para quem estava no cargo no meio dele (dia 15)."""
    return [(d, v) for d, v in serie if inicio <= d + timedelta(days=14) < fim_exclusivo]


def composto(taxas_pct: List[float]) -> Optional[float]:
    """Taxa acumulada por capitalização composta; lista vazia é ausência (None), nunca 0."""
    if not taxas_pct:
        return None
    fator = 1.0
    for taxa in taxas_pct:
        fator *= 1.0 + taxa / 100.0
    return round((fator - 1.0) * 100.0, 4)


def valor_opcional(valor: Any) -> Optional[float]:
    return None if valor is None else float(valor)
