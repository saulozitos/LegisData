"""População residente estimada do IBGE (SIDRA t6579) para o Brasil e por UF, usada em valores per capita."""

import logging
from typing import Dict, Optional

from etl.utils.sidra import NIVEL_BRASIL, NIVEL_UF, SidraClient, serie_por_ano, serie_por_uf_ano

logger = logging.getLogger("IBGEDemografia")

TABELA_POPULACAO = 6579  # População residente estimada (Estimativas e Censos)
VARIAVEL_POPULACAO = "9324"
FONTE_POPULACAO = "IBGE/SIDRA t6579 (estimativas) e t9514 (Censo 2022)"
# O t6579 não publica 2007, 2010, 2022 e 2023 (anos de Censo/Contagem e transição). O Censo 2022 (t9514) cobre 2022.
TABELA_CENSO_2022 = 9514
CLASSIF_CENSO_TOTAL = {2: "6794", 287: "100362", 286: "113635"}  # sexo, idade e forma de declaração: total


def populacao_brasil(sidra: SidraClient) -> Dict[int, int]:
    linhas = sidra.try_values(TABELA_POPULACAO, NIVEL_BRASIL, "all", VARIAVEL_POPULACAO, "all")
    serie = {ano: int(v) for ano, v in serie_por_ano(linhas).items() if v is not None}
    censo = sidra.try_values(TABELA_CENSO_2022, NIVEL_BRASIL, "all", "93", "2022", CLASSIF_CENSO_TOTAL)
    for ano, v in serie_por_ano(censo).items():
        if v is not None:
            serie.setdefault(ano, int(v))
    return serie


def populacao_uf(sidra: SidraClient) -> Dict[str, Dict[int, int]]:
    linhas = sidra.try_values(TABELA_POPULACAO, NIVEL_UF, "all", VARIAVEL_POPULACAO, "all")
    por_uf = serie_por_uf_ano(linhas, "D1C", "D3C")
    saida = {uf: {a: int(v) for a, v in anos.items() if v is not None} for uf, anos in por_uf.items()}
    censo = sidra.try_values(TABELA_CENSO_2022, NIVEL_UF, "all", "93", "2022", CLASSIF_CENSO_TOTAL)
    for uf, anos in serie_por_uf_ano(censo, "D1C", "D3C").items():
        for ano, v in anos.items():
            if v is not None:
                saida.setdefault(uf, {}).setdefault(ano, int(v))
    return saida


def populacao_no_ano(serie: Dict[int, int], ano: int) -> Optional[int]:
    """População do ano; se ainda não publicada, usa o último ano disponível anterior (nunca extrapola)."""
    if ano in serie:
        return serie[ano]
    anteriores = [a for a in serie if a < ano]
    return serie[max(anteriores)] if anteriores else None
