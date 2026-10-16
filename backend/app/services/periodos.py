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
    ultimo = ultimo_ano_do_mandato(fim)
    ultimo = max(ultimo_ano_da_serie, inicio.year) if ultimo is None else ultimo
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


def mandato_em_curso(fim: Optional[date], hoje: Optional[date] = None) -> bool:
    """Mandato sem data de fim ou cujo fim previsto (a posse do sucessor) ainda não chegou."""
    return fim is None or fim > (hoje or date.today())


def ultimo_ano_do_mandato(fim: Optional[date]) -> Optional[int]:
    """
    Último ano em que o mandato vigora. O fim é exclusivo quando coincide com a posse do sucessor nos primeiros dias de
    janeiro (1º de janeiro; 5 de janeiro a partir da EC 111/2021): o mandato que termina em 01/01/AAAA não vai até AAAA. Um
    mandato que termina depois disso (impeachment, renúncia) vigora até o próprio ano do fim. `None` sem data de fim.
    """
    if fim is None:
        return None
    return fim.year - 1 if fim.month == 1 and fim.day <= 7 else fim.year


def rotulo_do_periodo(inicio: date, fim: Optional[date], hoje: Optional[date] = None) -> str:
    """'2023 - Presente' (em curso), '1995 - 1998' (fim em 1º/jan do sucessor) ou '2015 - 2016' (fim em 31/08/2016)."""
    if mandato_em_curso(fim, hoje):
        return f"{inicio.year} - Presente"
    return f"{inicio.year} - {ultimo_ano_do_mandato(fim)}"
