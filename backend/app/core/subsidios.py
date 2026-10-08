"""
Subsídios constitucionais de referência (art. 49, VII e VIII, da Constituição).

Valores LEGAIS fixados por decreto legislativo, iguais para todos os ocupantes do
cargo. Não são contracheques individuais: o valor efetivamente pago pode diferir
(descontos, faltas, abate-teto, 13º, ajuda de custo etc.). Use-os apenas como
"subsídio de referência", sempre com o ato normativo citado.

Somente biblioteca padrão: este módulo é importado pela API e pelo ETL.
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

URL_DL_172_2022 = (
    "https://www2.camara.leg.br/legin/fed/decleg/2022/"
    "decretolegislativo-172-21-dezembro-2022-793529-publicacaooriginal-166604-pl.html"
)
URL_DL_276_2014 = (
    "https://www2.camara.leg.br/legin/fed/decleg/2014/"
    "decretolegislativo-276-18-dezembro-2014-779806-publicacaooriginal-145682-pl.html"
)
URL_DL_277_2014 = (
    "https://www2.camara.leg.br/legin/fed/decleg/2014/"
    "decretolegislativo-277-18-dezembro-2014-779807-publicacaooriginal-145683-pl.html"
)

_DL172 = "Decreto Legislativo nº 172, de 21/12/2022 (DOU 22/12/2022), art. 1º"

# Grupos: "CONGRESSO" (deputados federais e senadores) e "EXECUTIVO"
# (Presidente, Vice-Presidente e Ministros de Estado). Ordenado por vigência.
SUBSIDIOS: Dict[str, List[dict]] = {
    "CONGRESSO": [
        {"vigente_desde": date(2015, 2, 1), "valor": 33763.00,
         "ato": "Decreto Legislativo nº 276, de 18/12/2014, art. 1º (efeitos a partir de 01/02/2015)",
         "fonte_url": URL_DL_276_2014},
        {"vigente_desde": date(2023, 1, 1), "valor": 39293.32, "ato": _DL172 + ", inciso I",
         "fonte_url": URL_DL_172_2022},
        {"vigente_desde": date(2023, 4, 1), "valor": 41650.92, "ato": _DL172 + ", inciso II",
         "fonte_url": URL_DL_172_2022},
        {"vigente_desde": date(2024, 2, 1), "valor": 44008.52, "ato": _DL172 + ", inciso III",
         "fonte_url": URL_DL_172_2022},
        {"vigente_desde": date(2025, 2, 1), "valor": 46366.19, "ato": _DL172 + ", inciso IV",
         "fonte_url": URL_DL_172_2022},
    ],
    "EXECUTIVO": [
        {"vigente_desde": date(2015, 1, 1), "valor": 30934.70,
         "ato": "Decreto Legislativo nº 277, de 18/12/2014, art. 1º (efeitos a partir de 01/01/2015)",
         "fonte_url": URL_DL_277_2014},
        {"vigente_desde": date(2023, 1, 1), "valor": 39293.32, "ato": _DL172 + ", inciso I",
         "fonte_url": URL_DL_172_2022},
        {"vigente_desde": date(2023, 4, 1), "valor": 41650.92, "ato": _DL172 + ", inciso II",
         "fonte_url": URL_DL_172_2022},
        {"vigente_desde": date(2024, 2, 1), "valor": 44008.52, "ato": _DL172 + ", inciso III",
         "fonte_url": URL_DL_172_2022},
        {"vigente_desde": date(2025, 2, 1), "valor": 46366.19, "ato": _DL172 + ", inciso IV",
         "fonte_url": URL_DL_172_2022},
    ],
}

# Valores de CargoPoliticoEnum -> grupo do subsídio
GRUPO_POR_CARGO = {
    "DEPUTADO_FEDERAL": "CONGRESSO",
    "SENADOR": "CONGRESSO",
    "PRESIDENTE": "EXECUTIVO",
    "VICE_PRESIDENTE": "EXECUTIVO",
    "MINISTRO_DE_ESTADO": "EXECUTIVO",
}

NATUREZA = (
    "Subsídio constitucional de referência fixado em decreto legislativo; "
    "valor legal do cargo, não é o contracheque individual."
)


def subsidio_vigente(cargo: str, em: Optional[date] = None) -> Optional[dict]:
    """Retorna o subsídio de referência vigente para o cargo na data (ou None)."""
    grupo = GRUPO_POR_CARGO.get(cargo)
    if grupo is None:
        return None
    em = em or date.today()
    vigente = None
    for faixa in SUBSIDIOS[grupo]:
        if faixa["vigente_desde"] <= em:
            vigente = faixa
    if vigente is None:
        return None
    return {
        "cargo": cargo,
        "valor_mensal": vigente["valor"],
        "vigente_desde": vigente["vigente_desde"].isoformat(),
        "ato_normativo": vigente["ato"],
        "fonte_url": vigente["fonte_url"],
        "natureza": NATUREZA,
    }


def historico_subsidios(cargo: str) -> List[dict]:
    grupo = GRUPO_POR_CARGO.get(cargo)
    if grupo is None:
        return []
    return [
        {"vigente_desde": f["vigente_desde"].isoformat(), "valor_mensal": f["valor"],
         "ato_normativo": f["ato"], "fonte_url": f["fonte_url"]}
        for f in SUBSIDIOS[grupo]
    ]
