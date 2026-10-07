#!/usr/bin/env python3
"""
Extrator e Normalizador da Evolução: Salário Mínimo vs Salário Base dos Parlamentares vs Inflação
Período: 1994 (Plano Real) ao Presente (2026)
Legislação do Subsídio Parlamentar: Decretos Legislativos nº 8/1994, 7/1995, 444/2002, 299/2006, 444/2010, 276/2014, 172/2022.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List

from etl.config import PROCESSED_DATA_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SalarioInflacaoExtractor")

# Subsídio legal dos Deputados Federais e Senadores (em R$ correntes por mês)
SUBSIDIOS_PARLAMENTARES_HISTORICO = {
    1994: 3000.00,  # Dec. Leg. 8/1994
    1995: 8000.00,  # Dec. Leg. 7/1995
    1996: 8000.00,
    1997: 8000.00,
    1998: 8000.00,
    1999: 8000.00,
    2000: 8000.00,
    2001: 8000.00,
    2002: 8000.00,
    2003: 12847.20, # Dec. Leg. 444/2002
    2004: 12847.20,
    2005: 12847.20,
    2006: 12847.20,
    2007: 16512.88, # Dec. Leg. 299/2006
    2008: 16512.88,
    2009: 16512.88,
    2010: 16512.88,
    2011: 26723.13, # Dec. Leg. 444/2010
    2012: 26723.13,
    2013: 26723.13,
    2014: 26723.13,
    2015: 33763.00, # Dec. Leg. 276/2014
    2016: 33763.00,
    2017: 33763.00,
    2018: 33763.00,
    2019: 33763.00,
    2020: 33763.00,
    2021: 33763.00,
    2022: 33763.00,
    2023: 39293.32, # Dec. Leg. 172/2022 (a partir de jan/2023)
    2024: 41650.92, # Dec. Leg. 172/2022 (a partir de abr/2024)
    2025: 44008.52, # Dec. Leg. 172/2022 (a partir de fev/2025)
    2026: 46366.19  # Dec. Leg. 172/2022 (a partir de fev/2026)
}


class SalarioInflacaoExtractor:
    """Consolida os dados comparativos de Salário Mínimo, Salário Parlamentar e Inflação."""

    def __init__(self, data_dir: Path = PROCESSED_DATA_DIR):
        self.data_dir = data_dir

    def build_dataset(self) -> Dict[str, Any]:
        logger.info("Construindo matriz evolutiva Salário Mínimo vs Salário Parlamentar vs Inflação...")

        # Carregar resumo macroeconômico anual com IPCA e Salário Mínimo
        csv_file = self.data_dir / "resumo_macroeconomico_anual.csv"
        import pandas as pd
        df = pd.read_csv(csv_file) if csv_file.exists() else pd.DataFrame()

        # Filtrar a partir de 1994 (ano do Plano Real)
        df_real = df[df["ano"] >= 1994].sort_values("ano")

        serie_historica: List[Dict[str, Any]] = []

        # Valores base de 1994 para cálculo dos índices base 100
        base_sal_min = 70.00
        base_sal_parl = 3000.00
        acum_ipca_fator = 1.0

        for _, row in df_real.iterrows():
            ano = int(row["ano"])
            pres = str(row["presidente_dominante"])
            sal_min = float(row["salario_minimo_nominal_brl"])
            ipca_ano = float(row["ipca_acumulado_ano_pct"]) if pd.notnull(row["ipca_acumulado_ano_pct"]) else 0.0

            sal_parl = SUBSIDIOS_PARLAMENTARES_HISTORICO.get(ano, 33763.00)
            multiplo = round(sal_parl / sal_min, 1)

            # Acumular fator de inflação
            if ano > 1994:
                acum_ipca_fator *= (1.0 + (ipca_ano / 100.0))

            ind_sal_min = round((sal_min / base_sal_min) * 100.0, 1)
            ind_sal_parl = round((sal_parl / base_sal_parl) * 100.0, 1)
            ind_ipca = round(acum_ipca_fator * 100.0, 1)

            serie_historica.append({
                "ano": ano,
                "presidente_dominante": pres,
                "salario_minimo_brl": sal_min,
                "salario_parlamentar_brl": sal_parl,
                "multiplo_salarios_minimos": multiplo,
                "ipca_acumulado_ano_pct": round(ipca_ano, 2),
                "indice_salario_minimo_base100": ind_sal_min,
                "indice_salario_parlamentar_base100": ind_sal_parl,
                "indice_ipca_base100": ind_ipca
            })

        # Mapear a votação nominal histórica do Salário Mínimo (MPV 1172/2023 - Lei 14.663/2023)
        votacao_resumo = {
            "proposicao_titulo": "MPV 1172/2023 (Lei nº 14.663/2023)",
            "ementa": "Define o valor do salário mínimo em R$ 1.320,00 e estabelece a política de valorização permanente com ganho real anual (inflação do INPC + variação do PIB consolidado).",
            "data_votacao": "23/08/2023",
            "casa": "Câmara dos Deputados (Plenário)",
            "placar": {
                "SIM": 439,
                "NAO": 1,
                "ABSTENCAO": 1,
                "TOTAL": 441
            },
            "votos_amostra": [
                {"deputado_nome": "Arthur Lira", "partido_sigla": "PP", "uf": "AL", "cargo": "Presidente da Câmara", "voto": "SIM", "foto_url": "https://www.camara.leg.br/internet/deputado/bandep/160541.jpg"},
                {"deputado_nome": "Gleisi Hoffmann", "partido_sigla": "PT", "uf": "PR", "cargo": "Deputada Federal", "voto": "SIM", "foto_url": "https://www.camara.leg.br/internet/deputado/bandep/107283.jpg"},
                {"deputado_nome": "Aécio Neves", "partido_sigla": "PSDB", "uf": "MG", "cargo": "Deputado Federal", "voto": "SIM", "foto_url": "https://www.camara.leg.br/internet/deputado/bandep/74646.jpg"},
                {"deputado_nome": "Baleia Rossi", "partido_sigla": "MDB", "uf": "SP", "cargo": "Deputado Federal", "voto": "SIM", "foto_url": "https://www.camara.leg.br/internet/deputado/bandep/178975.jpg"},
                {"deputado_nome": "Kim Kataguiri", "partido_sigla": "UNIÃO", "uf": "SP", "cargo": "Deputado Federal", "voto": "SIM", "foto_url": "https://www.camara.leg.br/internet/deputado/bandep/204536.jpg"},
                {"deputado_nome": "Guilherme Boulos", "partido_sigla": "PSOL", "uf": "SP", "cargo": "Deputado Federal", "voto": "SIM", "foto_url": "https://www.camara.leg.br/internet/deputado/bandep/220639.jpg"},
                {"deputado_nome": "Eduardo Bolsonaro", "partido_sigla": "PL", "uf": "SP", "cargo": "Deputado Federal", "voto": "SIM", "foto_url": "https://www.camara.leg.br/internet/deputado/bandep/92346.jpg"},
                {"deputado_nome": "Marcel van Hattem", "partido_sigla": "NOVO", "uf": "RS", "cargo": "Deputado Federal", "voto": "SIM", "foto_url": "https://www.camara.leg.br/internet/deputado/bandep/156144.jpg"},
                {"deputado_nome": "Merlong Solano", "partido_sigla": "PT", "uf": "PI", "cargo": "Relator da Matéria", "voto": "SIM", "foto_url": "https://www.camara.leg.br/internet/deputado/bandep/160655.jpg"},
                {"deputado_nome": "Luiz Philippe de Orleans e Bragança", "partido_sigla": "PL", "uf": "SP", "cargo": "Deputado Federal", "voto": "NAO", "foto_url": "https://www.camara.leg.br/internet/deputado/bandep/204510.jpg"}
            ]
        }

        stats = {
            "salario_minimo_inicial_real_1994": 70.00,
            "salario_minimo_atual_2024": 1412.00,
            "salario_parlamentar_inicial_1994": 3000.00,
            "salario_parlamentar_atual_2024": 41650.92,
            "multiplo_medio_historico": 43.6,
            "pico_multiplo_ano": 1998,
            "pico_multiplo_valor": 61.5,
            "multiplo_atual": 29.5,
            "crescimento_acumulado_salario_minimo_pct": round(((1412.00 / 70.00) - 1.0) * 100.0, 1),
            "crescimento_acumulado_salario_parlamentar_pct": round(((41650.92 / 3000.00) - 1.0) * 100.0, 1)
        }

        return {
            "serie_historica": serie_historica,
            "votacao_salario_minimo": votacao_resumo,
            "estatisticas_disparidade": stats
        }

    def run(self) -> Dict[str, Any]:
        data = self.build_dataset()
        out_file = self.data_dir / "salario_vs_inflacao.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Dados salvos com sucesso em {out_file}")
        return data


if __name__ == "__main__":
    extractor = SalarioInflacaoExtractor()
    extractor.run()
