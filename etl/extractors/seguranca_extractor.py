"""
Extrator de Indicadores de Segurança Pública (IPEA / Fórum Brasileiro de Segurança Pública - FBSP)
Dados históricos oficiais: Atlas da Violência e Anuário Brasileiro de Segurança Pública.
Série histórica: 1995 a 2024 (Taxa de Homicídios e Taxa de Feminicídios por 100 mil habitantes).

ATENÇÃO: os valores foram digitados manualmente e precisam ser conferidos contra o
IpeaData / Atlas da Violência (série a série) — ver TODO abaixo. Anos que as fontes
ainda não publicaram (2025, 2026) foram removidos: eram projeções exibidas como dado.
Feminicídio só passou a ser tipificado em 2015 (Lei 13.104/2015); valores anteriores
são estimativas retrospectivas e são marcados como tal na saída.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd

from etl.config import PROCESSED_DATA_DIR, RAW_DATA_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SegurancaExtractor")


class SegurancaExtractor:
    """Extrai e consolida estatísticas oficiais de homicídios e feminicídios no Brasil."""

    def __init__(self, raw_cache_dir: Path = RAW_DATA_DIR, processed_dir: Path = PROCESSED_DATA_DIR):
        self.raw_dir = raw_cache_dir
        self.processed_dir = processed_dir
        self.output_json = self.processed_dir / "seguranca_publica_historico.json"
        self.output_csv = self.processed_dir / "seguranca_publica_historico.csv"

        # Série histórica oficial compilada pelo IPEA (Atlas da Violência) e FBSP
        # Taxa por 100 mil habitantes (Homicídios) e Taxa por 100 mil mulheres (Feminicídios)
        self.homicidios_brasil: Dict[int, float] = {
            1995: 23.9,
            1996: 24.8,
            1997: 25.4,
            1998: 25.9,
            1999: 26.2,
            2000: 26.7,
            2001: 27.8,
            2002: 28.5,
            2003: 28.9,
            2004: 27.0,
            2005: 26.1,
            2006: 26.6,
            2007: 25.2,
            2008: 26.4,
            2009: 27.2,
            2010: 27.8,
            2011: 27.4,
            2012: 29.4,
            2013: 28.6,
            2014: 29.8,
            2015: 28.9,
            2016: 30.3,
            2017: 31.6,  # Pico histórico da violência no Brasil (~65.6 mil mortes)
            2018: 27.8,
            2019: 21.7,
            2020: 23.6,
            2021: 22.3,
            2022: 21.7,
            2023: 20.9,
            2024: 19.4,
        }

        # Feminicídios tipificados a partir da Lei 13.104/2015 (com estimativas históricas retrospectivas de gênero IPEA/FBSP)
        self.feminicidios_brasil: Dict[int, float] = {
            1995: 0.70,
            1996: 0.72,
            1997: 0.75,
            1998: 0.78,
            1999: 0.80,
            2000: 0.82,
            2001: 0.85,
            2002: 0.88,
            2003: 0.89,
            2004: 0.86,
            2005: 0.84,
            2006: 0.85,
            2007: 0.83,
            2008: 0.86,
            2009: 0.88,
            2010: 0.90,
            2011: 0.89,
            2012: 0.92,
            2013: 0.91,
            2014: 0.94,
            2015: 0.85,  # Início formal da tipificação
            2016: 0.95,
            2017: 1.04,
            2018: 1.15,
            2019: 1.25,
            2020: 1.28,
            2021: 1.31,
            2022: 1.40,
            2023: 1.42,
            2024: 1.38,
        }

    def get_annual_homicide_rates(self) -> Dict[int, float]:
        """Retorna dicionário de taxa de homicídios por ano (por 100k hab.)."""
        return self.homicidios_brasil.copy()

    def get_annual_feminicide_rates(self) -> Dict[int, float]:
        """Retorna dicionário de taxa de feminicídios por ano (por 100k mulheres)."""
        return self.feminicidios_brasil.copy()

    def fetch_seguranca_history(self, use_cache: bool = True) -> pd.DataFrame:
        """Consolida e persiste a série histórica de segurança pública em JSON e CSV."""
        if use_cache and self.output_csv.exists():
            logger.info("Carregando série histórica de segurança pública do cache processado...")
            return pd.read_csv(self.output_csv)

        logger.info("Construindo e salvando série histórica de segurança pública (IPEA/FBSP)...")
        records = []
        all_years = sorted(list(set(list(self.homicidios_brasil.keys()) + list(self.feminicidios_brasil.keys()))))

        for ano in all_years:
            records.append({
                "ano": ano,
                "taxa_homicidios": self.homicidios_brasil.get(ano),
                "taxa_feminicidios": self.feminicidios_brasil.get(ano),
                "feminicidio_estimado": ano < 2015,
                "fonte": "IPEA / Atlas da Violência / FBSP (valores curados manualmente; pendente de conferência)"
            })

        df = pd.DataFrame(records)
        df.to_csv(self.output_csv, index=False, encoding="utf-8")

        with open(self.output_json, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

        logger.info(f"-> {len(records)} anos de segurança pública consolidados em {self.output_json}.")
        return df


if __name__ == "__main__":
    extractor = SegurancaExtractor()
    df = extractor.fetch_seguranca_history(use_cache=False)
    print(df.tail(10))
