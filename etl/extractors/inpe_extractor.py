"""
Extrator de Dados de Desmatamento da Amazônia Legal (PRODES / INPE)
Fonte Oficial: Instituto Nacional de Pesquisas Espaciais (INPE) - Projeto PRODES / TerraBrasilis
Série Histórica Anual Oficial: 1995 a 2024
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import pandas as pd

from etl.config import RAW_DATA_DIR, PROCESSED_DATA_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("INPEExtractor")

# Série Histórica Consolidada Oficial do PRODES / INPE (Taxa Anual de Desmatamento em km²)
# Medição de 1º de agosto do ano anterior a 31 de julho do ano de referência
PRODES_AMAZONIA_HISTORICO: Dict[int, float] = {
    1995: 29059.0,  # Pico histórico
    1996: 18161.0,
    1997: 13227.0,
    1998: 17383.0,
    1999: 17259.0,
    2000: 15850.0,
    2001: 18165.0,
    2002: 21650.0,
    2003: 25396.0,
    2004: 27772.0,  # Criação do PPCDAm (Plano de Ação para Prevenção e Controle do Desmatamento)
    2005: 19014.0,
    2006: 14286.0,
    2007: 11651.0,
    2008: 12911.0,
    2009: 7464.0,
    2010: 7000.0,
    2011: 6418.0,
    2012: 4571.0,   # Menor taxa histórica da série PRODES
    2013: 5891.0,
    2014: 5012.0,
    2015: 6207.0,
    2016: 7893.0,
    2017: 6947.0,
    2018: 7536.0,
    2019: 10129.0,
    2020: 10851.0,
    2021: 13038.0,
    2022: 11594.0,
    2023: 9001.0,
    2024: 6288.0,   # Redução consolidada PRODES 2024
}


class INPEExtractor:
    """Consome e gerencia os dados oficiais de desmatamento da Amazônia Legal do PRODES/INPE."""

    def __init__(self, raw_cache_dir: Path = RAW_DATA_DIR, processed_dir: Path = PROCESSED_DATA_DIR):
        self.cache_dir = raw_cache_dir
        self.processed_dir = processed_dir
        self.cache_file = self.cache_dir / "inpe_prodes_desmatamento_amazonia.json"

    def fetch_deforestation_history(self, use_cache: bool = True) -> pd.DataFrame:
        """
        Retorna um DataFrame com a taxa de desmatamento anual em km² (1995 a 2024).
        """
        if use_cache and self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return pd.DataFrame(data)
            except Exception as e:
                logger.warning(f"Erro ao ler cache do INPE: {e}. Recriando a partir da série oficial.")

        records = [
            {
                "ano": ano,
                "desmatamento_km2": km2,
                "fonte": "INPE / PRODES (Amazônia Legal)",
                "unidade": "km²"
            }
            for ano, km2 in sorted(PRODES_AMAZONIA_HISTORICO.items())
        ]

        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
            logger.info(f"Série de desmatamento PRODES/INPE salva em cache: {len(records)} anos.")
        except Exception as ex:
            logger.error(f"Erro ao salvar cache do INPE: {ex}")

        return pd.DataFrame(records)

    def get_deforestation_for_years(self, years: List[int]) -> Dict[str, Any]:
        """
        Calcula o total acumulado e a média anual de desmatamento para uma lista de anos (mandato).
        """
        matched_values = [PRODES_AMAZONIA_HISTORICO[y] for y in years if y in PRODES_AMAZONIA_HISTORICO]
        if not matched_values:
            return {
                "desmatamento_acumulado_km2": None,
                "desmatamento_medio_anual_km2": None,
                "anos_com_dados": 0
            }

        total_acumulado = round(float(sum(matched_values)), 1)
        media_anual = round(float(total_acumulado / len(matched_values)), 1)

        return {
            "desmatamento_acumulado_km2": total_acumulado,
            "desmatamento_medio_anual_km2": media_anual,
            "anos_com_dados": len(matched_values)
        }
