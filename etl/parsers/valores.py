"""Normalização de valores monetários, inteiros e textos vindos de CSV/JSON oficiais."""

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

# Marcadores que as fontes usam para "sem dado". Tratados como ausência (None),
# nunca convertidos em zero.
VALORES_AUSENTES = {"", "-", "S/I", "SEM INFORMACAO", "SEM INFORMAÇÃO", "NAN", "NONE", "NULL"}


def texto_ou_none(valor: Any) -> Optional[str]:
    """Retorna o texto sem espaços nas pontas, ou None se vazio/marcador de ausência."""
    if valor is None:
        return None
    if isinstance(valor, float) and valor != valor:  # NaN do pandas
        return None
    s = str(valor).strip()
    if s.upper() in VALORES_AUSENTES:
        return None
    return s


def parse_valor_br(valor: Any) -> Optional[Decimal]:
    """Converte valor no formato brasileiro ("1.234.567,89", "149600,00") em Decimal.

    - vírgula é o separador decimal; pontos antes dela são separadores de milhar;
    - aceita sinal negativo e prefixo "R$";
    - retorna None para vazio/"Sem informação" (não inventa zero).
    """
    if valor is None:
        return None
    if isinstance(valor, (int, Decimal)):
        return Decimal(valor)
    if isinstance(valor, float):
        if valor != valor:
            return None
        return Decimal(str(valor))
    s = texto_ou_none(valor)
    if s is None:
        return None
    s = s.replace("R$", "").replace("\xa0", "").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s):
        # "1.234.567" sem vírgula: pontos são milhar
        s = s.replace(".", "")
    try:
        return Decimal(s)
    except InvalidOperation:
        raise ValueError(f"valor monetário inválido: {valor!r}")


def parse_valor_ponto(valor: Any) -> Optional[Decimal]:
    """Converte valor com ponto decimal ("1148.7", "-90") em Decimal (CSV da Câmara)."""
    if valor is None:
        return None
    if isinstance(valor, (int, Decimal)):
        return Decimal(valor)
    if isinstance(valor, float):
        if valor != valor:
            return None
        return Decimal(str(valor))
    s = texto_ou_none(valor)
    if s is None:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        raise ValueError(f"valor numérico inválido: {valor!r}")


def parse_int(valor: Any) -> Optional[int]:
    s = texto_ou_none(valor)
    if s is None:
        return None
    try:
        return int(float(s)) if "." in s else int(s)
    except ValueError:
        return None


def truncar(valor: Optional[str], tamanho: int) -> Optional[str]:
    """Trunca texto ao tamanho da coluna (o banco rejeitaria a linha inteira)."""
    if valor is None:
        return None
    return valor if len(valor) <= tamanho else valor[: tamanho - 1] + "…"
