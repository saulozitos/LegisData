"""
Módulo de Normalização, Cálculos Macroeconômicos e Alinhamento por Mandato
Contém as fórmulas científicas oficiais (capitalização composta de IPCA, PIB real, câmbio e dívida).
"""

import math
from typing import List, Dict, Any, Optional
from datetime import datetime
import pandas as pd
import numpy as np


class EconomicNormalizer:
    """Normaliza séries econômicas e computa métricas acumuladas por mandato."""

    @staticmethod
    def calculate_compound_inflation(monthly_rates: List[float]) -> float:
        """
        Calcula a inflação acumulada composta oficial (fórmula do IBGE/Banco Central):
        Taxa Acumulada (%) = [ Produto(1 + taxa_i / 100) - 1 ] * 100
        """
        if not monthly_rates:
            return 0.0

        factor = 1.0
        for rate in monthly_rates:
            if rate is not None and not math.isnan(rate):
                factor *= (1.0 + (rate / 100.0))

        return round((factor - 1.0) * 100.0, 4)

    @staticmethod
    def calculate_compound_growth(growth_rates: List[float]) -> float:
        """
        Calcula a taxa real de crescimento acumulada do PIB:
        Crescimento Acumulado (%) = [ Produto(1 + taxa_ano / 100) - 1 ] * 100
        """
        if not growth_rates:
            return 0.0

        factor = 1.0
        for rate in growth_rates:
            if rate is not None and not math.isnan(rate):
                factor *= (1.0 + (rate / 100.0))

        return round((factor - 1.0) * 100.0, 2)

    @classmethod
    def align_indicators_to_mandates(
        cls,
        presidents: List[Dict[str, Any]],
        ipca_df: pd.DataFrame,
        cambio_df: pd.DataFrame,
        pib_anual_df: pd.DataFrame,
        divida_df: pd.DataFrame,
        salario_min_df: pd.DataFrame,
        unemployment_dict: Optional[Dict[int, float]] = None,
        deforestation_dict: Optional[Dict[int, float]] = None,
        food_insecurity_dict: Optional[Dict[int, float]] = None,
        homicide_dict: Optional[Dict[int, float]] = None,
        feminicide_dict: Optional[Dict[int, float]] = None
    ) -> List[Dict[str, Any]]:
        """
        Cruza todas as séries macroeconômicas oficiais com as datas exatas
        de cada mandato presidencial de Itamar Franco até o presente.
        """
        mandate_summaries = []

        # Garantir conversão de datas para datetime
        for df in [ipca_df, cambio_df, pib_anual_df, divida_df, salario_min_df]:
            if not df.empty and not pd.api.types.is_datetime64_any_dtype(df["data"]):
                df["data"] = pd.to_datetime(df["data"])

        for pres in presidents:
            dt_inicio = pd.to_datetime(pres["data_inicio"])
            dt_fim = pd.to_datetime(pres["data_fim"]) if pres.get("data_fim") else pd.to_datetime(datetime.now())

            # 1. IPCA no período do mandato
            ipca_subset = ipca_df[(ipca_df["data"] >= dt_inicio) & (ipca_df["data"] <= dt_fim)] if not ipca_df.empty else pd.DataFrame()
            if not ipca_subset.empty:
                # Caso especial de Itamar Franco:
                # O período pré-Real (1992-1994) teve hiperinflação de milhares de %.
                # Calculamos tanto o total quanto o pós-Real (jul/1994 em diante) para análise comparativa.
                monthly_ipca_rates = ipca_subset["valor"].tolist()
                ipca_acumulado = cls.calculate_compound_inflation(monthly_ipca_rates)

                # Se for mandato de Itamar Franco, destacar pós-Plano Real
                if "itamar" in pres["id_referencia"]:
                    pos_real_rates = ipca_subset[ipca_subset["data"] >= "1994-07-01"]["valor"].tolist()
                    ipca_pos_real = cls.calculate_compound_inflation(pos_real_rates)
                else:
                    ipca_pos_real = ipca_acumulado
            else:
                ipca_acumulado = 0.0
                ipca_pos_real = 0.0

            # 2. PIB no período (Variação real anual)
            # Associar anos de mandato
            ano_ini = dt_inicio.year
            ano_fim = min(dt_fim.year, datetime.now().year)
            # Se assumiu após julho, o primeiro ano pleno é o seguinte para impacto
            pib_subset = pib_anual_df[(pib_anual_df["ano"] >= ano_ini) & (pib_anual_df["ano"] <= ano_fim)] if not pib_anual_df.empty else pd.DataFrame()
            if not pib_subset.empty:
                pib_growth_rates = pib_subset["valor"].tolist()
                pib_acumulado = cls.calculate_compound_growth(pib_growth_rates)
                pib_medio_ano = round(float(np.mean(pib_growth_rates)), 2)
            else:
                pib_acumulado = 0.0
                pib_medio_ano = 0.0

            # 3. Taxa de Câmbio (USD/BRL)
            cambio_subset = cambio_df[(cambio_df["data"] >= dt_inicio) & (cambio_df["data"] <= dt_fim)] if not cambio_df.empty else pd.DataFrame()
            if not cambio_subset.empty:
                # Pegar valor pós-Real para evitar distorção de milhões de Cruzeiros
                cambio_real_subset = cambio_subset[cambio_subset["data"] >= "1994-07-01"]
                if not cambio_real_subset.empty:
                    cambio_ini = float(cambio_real_subset.iloc[0]["valor"])
                    cambio_fim = float(cambio_real_subset.iloc[-1]["valor"])
                    cambio_var_pct = round(((cambio_fim / cambio_ini) - 1.0) * 100.0, 2)
                else:
                    cambio_ini = float(cambio_subset.iloc[0]["valor"])
                    cambio_fim = float(cambio_subset.iloc[-1]["valor"])
                    cambio_var_pct = round(((cambio_fim / cambio_ini) - 1.0) * 100.0, 2)
            else:
                cambio_ini = None
                cambio_fim = None
                cambio_var_pct = None

            # 4. Dívida Líquida (% PIB)
            divida_subset = divida_df[(divida_df["data"] >= dt_inicio) & (divida_df["data"] <= dt_fim)] if not divida_df.empty else pd.DataFrame()
            if not divida_subset.empty:
                divida_ini = float(divida_subset.iloc[0]["valor"])
                divida_fim = float(divida_subset.iloc[-1]["valor"])
                divida_delta = round(divida_fim - divida_ini, 2)
            else:
                divida_ini = None
                divida_fim = None
                divida_delta = None

            # 5. Salário Mínimo (em R$ e equivalente em USD)
            sal_min_subset = salario_min_df[(salario_min_df["data"] >= dt_inicio) & (salario_min_df["data"] <= dt_fim)] if not salario_min_df.empty else pd.DataFrame()
            if not sal_min_subset.empty:
                sal_pos_real = sal_min_subset[sal_min_subset["data"] >= "1994-07-01"]
                if not sal_pos_real.empty:
                    sal_ini = float(sal_pos_real.iloc[0]["valor"])
                    sal_fim = float(sal_pos_real.iloc[-1]["valor"])
                else:
                    sal_ini = float(sal_min_subset.iloc[0]["valor"])
                    sal_fim = float(sal_min_subset.iloc[-1]["valor"])
            else:
                sal_ini = None
                sal_fim = None

            sal_ini_usd = round(sal_ini / cambio_ini, 2) if (sal_ini and cambio_ini and cambio_ini > 0) else None
            sal_fim_usd = round(sal_fim / cambio_fim, 2) if (sal_fim and cambio_fim and cambio_fim > 0) else None

            # Anos do mandato
            mandate_years = [y for y in range(ano_ini, ano_fim + 1)] if ano_fim >= ano_ini else [ano_ini]

            # 6. Desemprego no mandato (Início, Fim, Média)
            desemp_ini = None
            desemp_fim = None
            desemp_med = None
            if unemployment_dict:
                valid_u = [unemployment_dict[y] for y in mandate_years if y in unemployment_dict]
                if valid_u:
                    desemp_ini = valid_u[0]
                    desemp_fim = valid_u[-1]
                    desemp_med = round(float(np.mean(valid_u)), 2)

            # 7. Desmatamento Amazônia (PRODES / INPE)
            desmat_acum = None
            desmat_med = None
            if deforestation_dict:
                valid_d = [deforestation_dict[y] for y in mandate_years if y in deforestation_dict]
                if valid_d:
                    desmat_acum = round(float(sum(valid_d)), 1)
                    desmat_med = round(float(np.mean(valid_d)), 1)

            # 8. Insegurança Alimentar / Fome
            fome_ini = None
            fome_fim = None
            fome_med = None
            if food_insecurity_dict:
                valid_f = [food_insecurity_dict[y] for y in mandate_years if y in food_insecurity_dict]
                if valid_f:
                    fome_ini = valid_f[0]
                    fome_fim = valid_f[-1]
                    fome_med = round(float(np.mean(valid_f)), 2)

            # 9. Segurança Pública: Homicídios e Feminicídios (IPEA / FBSP)
            homic_ini, homic_fim, homic_med = None, None, None
            if homicide_dict:
                valid_h = [homicide_dict[y] for y in mandate_years if y in homicide_dict]
                if valid_h:
                    homic_ini = valid_h[0]
                    homic_fim = valid_h[-1]
                    homic_med = round(float(np.mean(valid_h)), 2)

            fem_ini, fem_fim, fem_med = None, None, None
            if feminicide_dict:
                valid_fem = [feminicide_dict[y] for y in mandate_years if y in feminicide_dict]
                if valid_fem:
                    fem_ini = valid_fem[0]
                    fem_fim = valid_fem[-1]
                    fem_med = round(float(np.mean(valid_fem)), 2)

            # 10. Trajetória anual detalhada para Drill-down de gráficos
            valores_anuais = []
            for y in mandate_years:
                pib_row = pib_anual_df[pib_anual_df["ano"] == y]
                y_pib = float(pib_row.iloc[0]["valor"]) if not pib_row.empty else None

                y_ipca_rows = ipca_df[ipca_df["ano"] == y]["valor"].tolist()
                y_ipca = cls.calculate_compound_inflation(y_ipca_rows) if y_ipca_rows else None

                y_cambio_rows = cambio_df[cambio_df["ano"] == y]
                y_dolar = round(float(y_cambio_rows.iloc[-1]["valor"]), 4) if not y_cambio_rows.empty else None

                y_sal_rows = salario_min_df[salario_min_df["ano"] == y]
                y_sal = float(y_sal_rows.iloc[-1]["valor"]) if not y_sal_rows.empty else None

                valores_anuais.append({
                    "ano": y,
                    "pib_crescimento_real_pct": y_pib,
                    "crescimento_pib_percentual": y_pib,
                    "ipca_acumulado_ano_pct": y_ipca,
                    "inflacao_anual_ipca": y_ipca,
                    "cotacao_dolar_fechamento": y_dolar,
                    "cambio_dolar_medio": round(float(y_cambio_rows["valor"].mean()), 4) if not y_cambio_rows.empty else None,
                    "salario_minimo": y_sal,
                    "salario_minimo_nominal_brl": y_sal,
                    "taxa_desemprego_anual": unemployment_dict.get(y) if unemployment_dict else None,
                    "taxa_homicidios": homicide_dict.get(y) if homicide_dict else None,
                    "taxa_feminicidios": feminicide_dict.get(y) if feminicide_dict else None,
                    "taxa_desmatamento_amazonia": deforestation_dict.get(y) if deforestation_dict else None,
                    "inseguranca_alimentar_pct": food_insecurity_dict.get(y) if food_insecurity_dict else None,
                })

            summary = {
                "id_mandato": pres["id_referencia"],
                "presidente": pres["nome_eleitoral"],
                "partido": pres["partido_sigla"],
                "data_inicio": pres["data_inicio"],
                "data_fim": pres["data_fim"] or datetime.now().strftime("%Y-%m-%d"),
                "status_mandato": pres["status_mandato"],
                "anos_cobertos": f"{ano_ini} - {ano_fim}",
                "ipca_acumulado_pct": ipca_acumulado,
                "ipca_pos_real_pct": ipca_pos_real if "itamar" in pres["id_referencia"] else ipca_acumulado,
                "pib_crescimento_acumulado_pct": pib_acumulado,
                "pib_medio_anual_pct": pib_medio_ano,
                "cambio_inicial_usd_brl": cambio_ini,
                "cambio_final_usd_brl": cambio_fim,
                "cambio_variacao_pct": cambio_var_pct,
                "divida_liquida_inicial_pct_pib": divida_ini,
                "divida_liquida_final_pct_pib": divida_fim,
                "divida_liquida_delta_pct": divida_delta,
                "salario_minimo_inicial_brl": sal_ini,
                "salario_minimo_final_brl": sal_fim,
                "salario_minimo_inicial_usd": sal_ini_usd,
                "salario_minimo_final_usd": sal_fim_usd,
                "desemprego_inicial_pct": desemp_ini,
                "desemprego_final_pct": desemp_fim,
                "desemprego_medio_pct": desemp_med,
                "desmatamento_acumulado_km2": desmat_acum,
                "desmatamento_medio_anual_km2": desmat_med,
                "fome_inicial_pct": fome_ini,
                "fome_final_pct": fome_fim,
                "fome_media_pct": fome_med,
                "homicidios_inicial": homic_ini,
                "homicidios_final": homic_fim,
                "homicidios_medio": homic_med,
                "feminicidios_inicial": fem_ini,
                "feminicidios_final": fem_fim,
                "feminicidios_medio": fem_med,
                "valores_anuais": valores_anuais,
                "ministros_fazenda_principais": [m["nome"] for m in pres.get("ministros_fazenda_chave", [])],
                "marcos_economicos_principais": pres.get("marcos_economicos", [])[:2]
            }
            mandate_summaries.append(summary)

        return mandate_summaries

    @classmethod
    def build_annual_summaries(
        cls,
        ipca_df: pd.DataFrame,
        pib_anual_df: pd.DataFrame,
        cambio_df: pd.DataFrame,
        salario_min_df: pd.DataFrame,
        divida_df: pd.DataFrame,
        presidents: List[Dict[str, Any]],
        ibovespa_df: Optional[pd.DataFrame] = None,
        unemployment_dict: Optional[Dict[int, float]] = None,
        deforestation_dict: Optional[Dict[int, float]] = None,
        food_insecurity_dict: Optional[Dict[int, float]] = None,
        homicide_dict: Optional[Dict[int, float]] = None,
        feminicide_dict: Optional[Dict[int, float]] = None,
        dolar_fechamento_df: Optional[pd.DataFrame] = None
    ) -> pd.DataFrame:
        """
        Cria a tabela macroeconômica consolidada ano a ano (1993 a presente)
        associando cada ano ao presidente dominante daquele exercício e calculando
        indicadores socioambientais expandidos (PIB, IPCA anual, IPCA acumulado do mandato,
        desemprego, desmatamento da Amazônia, insegurança alimentar, dólar fechamento,
        salário mínimo, homicídios e feminicídios).
        """
        all_years = sorted(list(set(ipca_df["ano"].unique())))
        all_years = [y for y in all_years if y >= 1993]

        records = []
        for ano in all_years:
            # IPCA do ano
            ipca_ano = ipca_df[ipca_df["ano"] == ano]["valor"].tolist()
            ipca_acum = cls.calculate_compound_inflation(ipca_ano)

            # PIB do ano
            pib_row = pib_anual_df[pib_anual_df["ano"] == ano]
            pib_cresc = float(pib_row.iloc[0]["valor"]) if not pib_row.empty else None

            # Câmbio médio do ano e fechamento (PTAX no final do ano)
            cambio_rows = cambio_df[cambio_df["ano"] == ano]
            # Considerar câmbio pós-Real (1995 em diante ou média do segundo semestre de 1994)
            if ano == 1994:
                cambio_rows = cambio_rows[cambio_rows["mes"] >= 7]
            cambio_medio = round(float(cambio_rows["valor"].mean()), 4) if not cambio_rows.empty else None

            # Cotação do Dólar no final do ano
            cotacao_dolar_fechamento = None
            if dolar_fechamento_df is not None and not dolar_fechamento_df.empty:
                dolar_rows = dolar_fechamento_df[dolar_fechamento_df["ano"] == ano]
                if not dolar_rows.empty:
                    cotacao_dolar_fechamento = round(float(dolar_rows.iloc[-1]["valor"]), 4)
            if cotacao_dolar_fechamento is None and not cambio_rows.empty:
                cotacao_dolar_fechamento = round(float(cambio_rows.iloc[-1]["valor"]), 4)

            # Dívida no final do ano
            divida_rows = divida_df[divida_df["ano"] == ano]
            divida_fim = float(divida_rows.iloc[-1]["valor"]) if not divida_rows.empty else None

            # Salário mínimo em dezembro
            sal_rows = salario_min_df[salario_min_df["ano"] == ano]
            sal_fim = float(sal_rows.iloc[-1]["valor"]) if not sal_rows.empty else None

            # Ibovespa no fechamento do ano
            ibov_fim = None
            if ibovespa_df is not None and not ibovespa_df.empty:
                ibov_rows = ibovespa_df[ibovespa_df["ano"] == ano]
                if not ibov_rows.empty:
                    ibov_fim = float(ibov_rows.iloc[0]["ibovespa_fechamento"])

            # Presidente dominante naquele ano (baseado no meio do ano, 01 de julho)
            dt_ref = f"{ano}-07-01"
            pres_dominante = "N/D"
            pres_dominante_obj = None
            for p in presidents:
                dt_i = p["data_inicio"]
                dt_f = p["data_fim"] or "2099-12-31"
                if dt_i <= dt_ref <= dt_f:
                    pres_dominante = p["nome_eleitoral"]
                    pres_dominante_obj = p
                    break

            # Inflação acumulada no mandato até o fim deste ano
            infl_acum_mandato = None
            if pres_dominante_obj:
                dt_mandato_ini = pd.to_datetime(pres_dominante_obj["data_inicio"])
                dt_fim_ano = pd.to_datetime(f"{ano}-12-31")
                if pres_dominante_obj.get("data_fim"):
                    dt_max = min(dt_fim_ano, pd.to_datetime(pres_dominante_obj["data_fim"]))
                else:
                    dt_max = dt_fim_ano

                # Se for mandato de Itamar Franco, considerar pós-Real para consistência
                if "itamar" in pres_dominante_obj["id_referencia"]:
                    dt_mandato_ini = max(dt_mandato_ini, pd.to_datetime("1994-07-01"))

                monthly_rates = ipca_df[(ipca_df["data"] >= dt_mandato_ini) & (ipca_df["data"] <= dt_max)]["valor"].tolist()
                if monthly_rates:
                    infl_acum_mandato = cls.calculate_compound_inflation(monthly_rates)

            desemprego_ano = unemployment_dict.get(ano) if unemployment_dict else None
            desmatamento_ano = deforestation_dict.get(ano) if deforestation_dict else None
            fome_ano = food_insecurity_dict.get(ano) if food_insecurity_dict else None
            homicidio_ano = homicide_dict.get(ano) if homicide_dict else None
            feminicidio_ano = feminicide_dict.get(ano) if feminicide_dict else None

            records.append({
                "ano": ano,
                "presidente_dominante": pres_dominante,
                "ipca_acumulado_ano_pct": ipca_acum,
                "pib_crescimento_real_pct": pib_cresc,
                "crescimento_pib_percentual": pib_cresc,
                "inflacao_anual_ipca": ipca_acum,
                "inflacao_acumulada_mandato": infl_acum_mandato,
                "taxa_desemprego_anual": desemprego_ano,
                "taxa_desmatamento_amazonia": desmatamento_ano,
                "inseguranca_alimentar_pct": fome_ano,
                "cambio_dolar_medio": cambio_medio,
                "cotacao_dolar_fechamento": cotacao_dolar_fechamento,
                "salario_minimo": sal_fim,
                "salario_minimo_nominal_brl": sal_fim,
                "taxa_homicidios": homicidio_ano,
                "taxa_feminicidios": feminicidio_ano,
                "divida_liquida_pct_pib": divida_fim,
                "ibovespa_fechamento": ibov_fim
            })

        return pd.DataFrame(records)
