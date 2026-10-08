"""
Funções puras (somente stdlib) para vincular registros oficiais a políticos e mandatos.

Usadas pelos extratores de presença/remuneração e pelo db_loader; isoladas aqui
para poderem ser testadas sem banco nem pandas.
"""

from __future__ import annotations

import calendar
import unicodedata
from datetime import date
from typing import Dict, Hashable, Iterable, List, Optional, Sequence, Tuple


def normalizar(texto: Optional[str]) -> str:
    """Maiúsculas, sem acentos, espaços simples."""
    if not texto:
        return ""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    return " ".join(sem_acento.upper().split())


# (mandato_id, data_inicio, data_fim_ou_None)
MandatoIntervalo = Tuple[Hashable, date, Optional[date]]


def mandato_na_data(mandatos: Sequence[MandatoIntervalo], dia: date) -> Optional[Hashable]:
    """Mandato vigente no dia. Se houver mais de um, o de início mais recente."""
    candidatos = [m for m in mandatos if m[1] <= dia and (m[2] is None or dia <= m[2])]
    if not candidatos:
        return None
    return max(candidatos, key=lambda m: m[1])[0]


def mandato_no_mes(mandatos: Sequence[MandatoIntervalo], ano: int, mes: int) -> Optional[Hashable]:
    """Mandato que se sobrepõe ao mês de referência (folha mensal)."""
    inicio_mes = date(ano, mes, 1)
    fim_mes = date(ano, mes, calendar.monthrange(ano, mes)[1])
    candidatos = [m for m in mandatos if m[1] <= fim_mes and (m[2] is None or m[2] >= inicio_mes)]
    if not candidatos:
        return None
    return max(candidatos, key=lambda m: m[1])[0]


def indice_unico(pares: Iterable[Tuple[Hashable, Hashable]]) -> Dict[Hashable, Hashable]:
    """Monta chave -> valor descartando chaves ambíguas (mais de um valor distinto)."""
    vistos: Dict[Hashable, set] = {}
    for chave, valor in pares:
        vistos.setdefault(chave, set()).add(valor)
    return {k: next(iter(v)) for k, v in vistos.items() if len(v) == 1}


def chaves_ambiguas(pares: Iterable[Tuple[Hashable, Hashable]]) -> List[Hashable]:
    vistos: Dict[Hashable, set] = {}
    for chave, valor in pares:
        vistos.setdefault(chave, set()).add(valor)
    return sorted((k for k, v in vistos.items() if len(v) > 1), key=str)
