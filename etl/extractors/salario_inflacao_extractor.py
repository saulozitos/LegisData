#!/usr/bin/env python3
"""
Extrator e Normalizador da Evolução: Salário Mínimo vs Salário Base dos Parlamentares vs Inflação
Período: 1994 (Plano Real) ao Presente (2026)
Legislação do Subsídio Parlamentar: Decretos Legislativos nº 8/1994, 7/1995, 444/2002, 299/2006, 444/2010, 276/2014, 172/2022.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from etl.config import PROCESSED_DATA_DIR
from etl.utils.datafiles import load_json
from etl.utils.io_utils import atomic_write_json

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
    2003: 12847.20,  # Dec. Leg. 444/2002
    2004: 12847.20,
    2005: 12847.20,
    2006: 12847.20,
    2007: 16512.88,  # Dec. Leg. 299/2006
    2008: 16512.88,
    2009: 16512.88,
    2010: 16512.88,
    2011: 26723.13,  # Dec. Leg. 444/2010
    2012: 26723.13,
    2013: 26723.13,
    2014: 26723.13,
    2015: 33763.00,  # Dec. Leg. 276/2014
    2016: 33763.00,
    2017: 33763.00,
    2018: 33763.00,
    2019: 33763.00,
    2020: 33763.00,
    2021: 33763.00,
    2022: 33763.00,
    2023: 39293.32,  # Dec. Leg. 172/2022 (a partir de jan/2023)
    2024: 41650.92,  # Dec. Leg. 172/2022 (a partir de abr/2024)
    2025: 44008.52,  # Dec. Leg. 172/2022 (a partir de fev/2025)
    2026: 46366.19,  # valor NÃO confirmado em norma citada neste projeto (ver ANOS_SUBSIDIO_NAO_CONFIRMADOS)
}

# Anos cujo valor do subsídio não está respaldado pelos decretos legislativos citados acima.
ANOS_SUBSIDIO_NAO_CONFIRMADOS = {2026}


class SalarioInflacaoExtractor:
    """Consolida os dados comparativos de Salário Mínimo, Salário Parlamentar e Inflação."""

    def __init__(self, data_dir: Path = PROCESSED_DATA_DIR):
        self.data_dir = data_dir

    def _votacao_salario_minimo(self) -> Dict[str, Any]:
        """
        Resumo da votação da MPV 1172/2023 (salário mínimo) calculado a partir dos votos nominais coletados.
        O placar e a "amostra de votos" digitados à mão (439x1x1) foram removidos: sem votação coletada, os
        campos ficam None em vez de um resultado que ninguém pode auditar.
        """
        base = {
            "proposicao_titulo": "MPV 1172/2023 (Lei nº 14.663/2023)",
            "ementa": "Define o valor do salário mínimo em R$ 1.320,00 e estabelece a política de valorização "
            "permanente com ganho real anual.",
            "data_votacao": None,
            "casa": "Câmara dos Deputados (Plenário)",
            "placar": None,
            "votos_amostra": [],
            "dados_indisponiveis": True,
        }
        sessoes = load_json(self.data_dir / "sessoes_votacao_2023.json", []) or []
        votos = load_json(self.data_dir / "votos_nominais_2023.json", []) or []

        def eh_mpv_1172(sessao: Dict[str, Any]) -> bool:
            if sessao.get("proposicao_tipo"):
                return (
                    str(sessao["proposicao_tipo"]).upper() == "MPV"
                    and sessao.get("proposicao_numero") == 1172
                    and sessao.get("proposicao_ano") == 2023
                )
            return "1172" in str(sessao.get("proposicao_titulo", "")) or "Salário Mínimo" in str(
                sessao.get("proposicao_titulo", "")
            )

        sessao = next((x for x in sessoes if eh_mpv_1172(x)), None)
        if not sessao:
            return base

        do_plenario = [v for v in votos if str(v.get("sessao_externa_id")) == str(sessao.get("sessao_externa_id"))]
        placar = {"SIM": 0, "NAO": 0, "ABSTENCAO": 0}
        for v in do_plenario:
            if v.get("voto") in placar:
                placar[v["voto"]] += 1
        placar["TOTAL"] = len(do_plenario)

        data_hora = str(sessao.get("data_hora") or "")[:10]
        base.update(
            {
                "data_votacao": data_hora or None,
                "placar": placar,
                "dados_indisponiveis": False,
                "fonte": "API Dados Abertos da Câmara (votos nominais coletados)",
            }
        )
        return base

    def build_dataset(self) -> Dict[str, Any]:
        logger.info("Construindo matriz evolutiva Salário Mínimo vs Salário Parlamentar vs Inflação...")

        csv_file = self.data_dir / "resumo_macroeconomico_anual.csv"
        if not csv_file.exists():
            raise FileNotFoundError(
                f"{csv_file.name} não encontrado: execute antes a etapa econômica (--economic). "
                "Sem ele não há salário mínimo nem IPCA para comparar."
            )
        df = pd.read_csv(csv_file)

        df_real = df[df["ano"] >= 1994].sort_values("ano")
        serie_historica: List[Dict[str, Any]] = []

        base_sal_min = 70.00
        base_sal_parl = 3000.00
        acum_ipca_fator = 1.0

        for _, row in df_real.iterrows():
            ano = int(row["ano"])
            pres = str(row["presidente_dominante"])
            if pd.isna(row["salario_minimo_nominal_brl"]) or row["salario_minimo_nominal_brl"] <= 0:
                logger.warning("Ano %s sem salário mínimo no resumo anual — ignorado.", ano)
                continue
            sal_min = float(row["salario_minimo_nominal_brl"])
            ipca_ano = float(row["ipca_acumulado_ano_pct"]) if pd.notnull(row["ipca_acumulado_ano_pct"]) else 0.0

            sal_parl = SUBSIDIOS_PARLAMENTARES_HISTORICO.get(ano)
            if sal_parl is None:
                logger.warning("Ano %s sem subsídio parlamentar catalogado — ignorado.", ano)
                continue
            multiplo = round(sal_parl / sal_min, 1)

            if ano > 1994:
                acum_ipca_fator *= 1.0 + (ipca_ano / 100.0)

            serie_historica.append(
                {
                    "ano": ano,
                    "presidente_dominante": pres,
                    "salario_minimo_brl": sal_min,
                    "salario_parlamentar_brl": sal_parl,
                    "salario_parlamentar_confirmado": ano not in ANOS_SUBSIDIO_NAO_CONFIRMADOS,
                    "multiplo_salarios_minimos": multiplo,
                    "ipca_acumulado_ano_pct": round(ipca_ano, 2),
                    "indice_salario_minimo_base100": round((sal_min / base_sal_min) * 100.0, 1),
                    "indice_salario_parlamentar_base100": round((sal_parl / base_sal_parl) * 100.0, 1),
                    "indice_ipca_base100": round(acum_ipca_fator * 100.0, 1),
                }
            )

        if not serie_historica:
            raise RuntimeError("Série histórica vazia: nenhum ano com salário mínimo e subsídio disponíveis.")

        # Estatísticas CALCULADAS da série (antes eram constantes digitadas que divergiam dos dados).
        primeiro = serie_historica[0]
        confirmados = [r for r in serie_historica if r["salario_parlamentar_confirmado"]] or serie_historica
        atual = confirmados[-1]
        pico = max(serie_historica, key=lambda r: r["multiplo_salarios_minimos"])
        multiplos = [r["multiplo_salarios_minimos"] for r in serie_historica]

        def cresc(final: float, inicial: float) -> float:
            return round(((final / inicial) - 1.0) * 100.0, 1)

        stats = {
            "ano_referencia_atual": atual["ano"],
            "ano_referencia_inicial": primeiro["ano"],
            "salario_minimo_inicial_real_1994": primeiro["salario_minimo_brl"],
            "salario_minimo_atual": atual["salario_minimo_brl"],
            "salario_parlamentar_inicial_1994": primeiro["salario_parlamentar_brl"],
            "salario_parlamentar_atual": atual["salario_parlamentar_brl"],
            # Chaves antigas, mantidas por compatibilidade (agora com o valor do último ano confirmado):
            "salario_minimo_atual_2024": atual["salario_minimo_brl"],
            "salario_parlamentar_atual_2024": atual["salario_parlamentar_brl"],
            "multiplo_medio_historico": round(sum(multiplos) / len(multiplos), 1),
            "pico_multiplo_ano": pico["ano"],
            "pico_multiplo_valor": pico["multiplo_salarios_minimos"],
            "multiplo_atual": atual["multiplo_salarios_minimos"],
            "crescimento_acumulado_salario_minimo_pct": cresc(
                atual["salario_minimo_brl"], primeiro["salario_minimo_brl"]
            ),
            "crescimento_acumulado_salario_parlamentar_pct": cresc(
                atual["salario_parlamentar_brl"], primeiro["salario_parlamentar_brl"]
            ),
        }

        return {
            "serie_historica": serie_historica,
            "votacao_salario_minimo": self._votacao_salario_minimo(),
            "estatisticas_disparidade": stats,
        }

    def run(self) -> Dict[str, Any]:
        data = self.build_dataset()
        out_file = self.data_dir / "salario_vs_inflacao.json"
        atomic_write_json(out_file, data)
        logger.info(f"Dados salvos com sucesso em {out_file}")
        return data


if __name__ == "__main__":
    extractor = SalarioInflacaoExtractor()
    extractor.run()
