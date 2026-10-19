"""
Pipeline Principal de ETL: Sincronização de Presidentes e Indicadores Econômicos Básicos (BCB / IBGE)
"""

import logging
from typing import Any, Dict, List

import pandas as pd

from etl.config import PROCESSED_DATA_DIR
from etl.extractors.bcb_extractor import BCBExtractor
from etl.extractors.ibge_extractor import IBGEExtractor
from etl.extractors.inpe_extractor import INPEExtractor
from etl.extractors.presidents_extractor import PresidentsExtractor
from etl.extractors.seguranca_extractor import SegurancaExtractor
from etl.extractors.social_indicators_extractor import SocialIndicatorsExtractor
from etl.transformers.economic_normalizer import EconomicNormalizer
from etl.utils.io_utils import atomic_write_json, atomic_write_text

logger = logging.getLogger("ETLPipeline")


class EssentialSeriesMissing(RuntimeError):
    """Série indispensável veio vazia: abortar é melhor do que gravar mandatos inteiros com zeros."""


def _fmt(valor, formato: str, sufixo: str = "") -> str:
    """Formata números do painel; None/NaN viram 'N/D' (valor 0 legítimo continua sendo 0)."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return "N/D"
    return format(valor, formato) + sufixo


def series_mensais(series: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Séries do BCB em formato longo (`serie`, `data`, `valor`), uma linha por mês, a partir de 1995-01-01.

    Série diária ou com vários pontos no mês fica com o último valor do mês. Série vazia não gera linha: o carregador
    não apaga o que já está no banco quando a fonte não respondeu.
    """
    partes = []
    for codigo, df in series.items():
        if df is None or df.empty:
            continue
        mensal = df[df["data"] >= "1995-01-01"].sort_values("data").copy()
        mensal["data"] = mensal["data"].dt.to_period("M").dt.to_timestamp()
        mensal = mensal.groupby("data", as_index=False).last()
        mensal["serie"] = codigo
        mensal["data"] = mensal["data"].dt.strftime("%Y-%m-%d")
        partes.append(mensal[["serie", "data", "valor"]])
    if not partes:
        return pd.DataFrame(columns=["serie", "data", "valor"])
    return pd.concat(partes, ignore_index=True)


class PresidentsEconomicSyncPipeline:
    """Executa a extração, alinhamento e cruzamento dos dados de presidentes e macroeconomia."""

    def __init__(self):
        self.presidents_extractor = PresidentsExtractor()
        self.bcb_extractor = BCBExtractor()
        self.ibge_extractor = IBGEExtractor()
        self.inpe_extractor = INPEExtractor()
        self.social_extractor = SocialIndicatorsExtractor()
        self.seguranca_extractor = SegurancaExtractor()
        self.normalizer = EconomicNormalizer()

    def run(self, use_cache: bool = True) -> Dict[str, Any]:
        logger.info("=" * 70)
        logger.info("INICIANDO PIPELINE: PRESIDENTES E INDICADORES MACROECONÔMICOS (1995 - PRESENTE)")
        logger.info("=" * 70)

        # 1. Obter catálogo histórico de presidentes
        logger.info("Passo 1/5: Extraindo lista histórica de presidentes (Fernando Henrique Cardoso -> Presente)...")
        presidents = self.presidents_extractor.get_presidents()
        logger.info(f"-> {len(presidents)} mandatos presidenciais mapeados com sucesso.")

        # 2. Extrair dados das APIs públicas do Banco Central e IBGE
        logger.info("Passo 2/5: Extraindo indicadores econômicos das APIs do Banco Central (SGS) e IBGE...")

        # IPCA Mensal (Série 433 BCB)
        ipca_df = self.bcb_extractor.fetch_serie_dataframe("ipca_mensal", use_cache=use_cache)
        if ipca_df.empty:
            raise EssentialSeriesMissing("IPCA mensal (SGS 433) vazio: nada foi gravado.")
        logger.info(
            f"-> IPCA Mensal: {len(ipca_df)} registros obtidos ({ipca_df['data'].min()} a {ipca_df['data'].max()})"
        )

        # Câmbio USD/BRL (Série 3698 BCB)
        cambio_df = self.bcb_extractor.fetch_serie_dataframe("cambio_usd_brl_venda", use_cache=use_cache)
        if cambio_df.empty:
            raise EssentialSeriesMissing("Câmbio USD/BRL (SGS 3698) vazio: nada foi gravado.")
        logger.info(f"-> Câmbio USD/BRL: {len(cambio_df)} registros obtidos.")

        # Dólar de fim de período (PTAX, série 10813): é o "fechamento"; a média mensal (3698) NÃO serve para isso
        dolar_fechamento_df = self.bcb_extractor.fetch_serie_dataframe("dolar_ptax_fechamento", use_cache=use_cache)
        logger.info(f"-> Dólar (fim de período): {len(dolar_fechamento_df)} registros obtidos.")

        # PIB Variação Anual Real (Série 7326 BCB)
        pib_anual_df = self.bcb_extractor.fetch_serie_dataframe("pib_variacao_anual", use_cache=use_cache)
        logger.info(f"-> PIB Variação Anual: {len(pib_anual_df)} anos registrados.")

        # Dívida Líquida (% PIB - Série 4513 BCB)
        divida_df = self.bcb_extractor.fetch_serie_dataframe("divida_liquida_pib", use_cache=use_cache)
        logger.info(f"-> Dívida Líquida / PIB: {len(divida_df)} registros obtidos.")

        # Salário Mínimo Nominal (Série 1619 BCB)
        salario_min_df = self.bcb_extractor.fetch_serie_dataframe("salario_minimo_nominal", use_cache=use_cache)
        logger.info(f"-> Salário Mínimo: {len(salario_min_df)} registros obtidos.")

        # Meta Selic (432) e desocupação PNAD Contínua (24369): só entram nas séries mensais do banco
        selic_df = self.bcb_extractor.fetch_serie_dataframe("selic_meta_ano", use_cache=use_cache)
        desocupacao_df = self.bcb_extractor.fetch_serie_dataframe("desemprego_pnad", use_cache=use_cache)
        logger.info(f"-> Selic meta: {len(selic_df)} registros; desocupação PNADC: {len(desocupacao_df)} registros.")

        # 2.1 Extrair indicadores socioambientais expandidos
        logger.info("-> Extraindo dados de desemprego (IBGE), desmatamento (INPE/PRODES) e fome...")
        unemployment_dict = self.social_extractor.get_annual_unemployment_history()

        deforest_df = self.inpe_extractor.fetch_deforestation_history(use_cache=use_cache)
        deforestation_dict = (
            dict(zip(deforest_df["ano"], deforest_df["desmatamento_km2"])) if not deforest_df.empty else {}
        )

        social_indicators = self.social_extractor.get_annual_social_indicators()
        food_insecurity_dict = {
            item["ano"]: item.get("inseguranca_alimentar_pct")
            for item in social_indicators
            if item.get("inseguranca_alimentar_pct") is not None
        }

        # 2.2 Extrair indicadores de segurança pública (IPEA / FBSP)
        logger.info("-> Extraindo dados de homicídios e feminicídios (IPEA/FBSP)...")
        self.seguranca_extractor.fetch_seguranca_history(use_cache=use_cache)
        homicide_dict = self.seguranca_extractor.get_annual_homicide_rates()
        feminicide_dict = self.seguranca_extractor.get_annual_feminicide_rates()

        # 3. Transformação e Cruzamento Analítico
        logger.info("Passo 3/5: Processando cálculos matemáticos e alinhando por mandato presidencial...")
        mandates_summary = self.normalizer.align_indicators_to_mandates(
            presidents=presidents,
            ipca_df=ipca_df,
            cambio_df=cambio_df,
            pib_anual_df=pib_anual_df,
            divida_df=divida_df,
            salario_min_df=salario_min_df,
            unemployment_dict=unemployment_dict,
            deforestation_dict=deforestation_dict,
            food_insecurity_dict=food_insecurity_dict,
            homicide_dict=homicide_dict,
            feminicide_dict=feminicide_dict,
        )

        logger.info("Passo 4/5: Construindo série histórica macroeconômica anual consolidada (1995 a presente)...")
        annual_summary_df = self.normalizer.build_annual_summaries(
            ipca_df=ipca_df,
            pib_anual_df=pib_anual_df,
            cambio_df=cambio_df,
            salario_min_df=salario_min_df,
            divida_df=divida_df,
            presidents=presidents,
            unemployment_dict=unemployment_dict,
            deforestation_dict=deforestation_dict,
            food_insecurity_dict=food_insecurity_dict,
            homicide_dict=homicide_dict,
            feminicide_dict=feminicide_dict,
            dolar_fechamento_df=dolar_fechamento_df,
        )

        # 4. Exportação dos Dados Estruturados
        logger.info("Passo 5/5: Salvando arquivos processados em etl/data/processed/...")

        # Todas as gravações são atômicas (temp + os.replace): uma falha no meio não deixa arquivo truncado.
        atomic_write_json(PROCESSED_DATA_DIR / "presidentes_historico.json", presidents)
        atomic_write_json(PROCESSED_DATA_DIR / "indicadores_por_mandato.json", mandates_summary)

        mandates_df_export = pd.DataFrame(mandates_summary).copy()
        mandates_df_export["ministros_fazenda_principais"] = mandates_df_export["ministros_fazenda_principais"].apply(
            lambda x: ", ".join(x) if isinstance(x, list) else x
        )
        mandates_df_export["marcos_economicos_principais"] = mandates_df_export["marcos_economicos_principais"].apply(
            lambda x: " | ".join(x) if isinstance(x, list) else x
        )
        atomic_write_text(PROCESSED_DATA_DIR / "indicadores_por_mandato.csv", mandates_df_export.to_csv(index=False))

        atomic_write_text(PROCESSED_DATA_DIR / "resumo_macroeconomico_anual.csv", annual_summary_df.to_csv(index=False))
        atomic_write_text(PROCESSED_DATA_DIR / "ipca_mensal_historico.csv", ipca_df.to_csv(index=False))
        atomic_write_text(
            PROCESSED_DATA_DIR / "bcb_series_mensais.csv",
            series_mensais(
                {
                    "CAMBIO_MENSAL": cambio_df,
                    "DIVIDA_LIQUIDA_PIB_MENSAL": divida_df,
                    "SALARIO_MINIMO_MENSAL": salario_min_df,
                    "SELIC_META": selic_df,
                    "DESEMPREGO_PNADC_MENSAL": desocupacao_df,
                }
            ).to_csv(index=False),
        )

        logger.info(f"Arquivos gerados com sucesso em {PROCESSED_DATA_DIR}")

        # 5. Exibir Relatório Sintético no Console
        self._print_terminal_dashboard(mandates_summary)

        return {
            "total_presidents": len(presidents),
            "mandates_summary": mandates_summary,
            "annual_records": len(annual_summary_df),
            "output_directory": str(PROCESSED_DATA_DIR),
        }

    def _print_terminal_dashboard(self, mandates_summary: List[Dict[str, Any]]) -> None:
        """Gera um painel comparativo elegante no terminal."""
        print("\n" + "=" * 115)
        print("          PAINEL ANALÍTICO COMPARATIVO: GOVERNOS E INDICADORES ECONÔMICOS (1995 - PRESENTE)")
        print("=" * 115)
        header = f"{'PRESIDENTE':<26} | {'PARTIDO':<6} | {'PERÍODO':<11} | {'INFLAÇÃO IPCA':<15} | {'PIB MÉD/ANO':<12} | {'CÂMBIO (FIM)':<12} | {'SAL. MÍN (USD)'}"
        print(header)
        print("-" * 115)

        for m in mandates_summary:
            pres = m["presidente"]
            partido = m["partido"]
            periodo = m["anos_cobertos"]

            # Formatação de inflação
            if "itamar" in m["id_mandato"]:
                ipca_str = f"{_fmt(m.get('ipca_pos_real_pct'), '.1f', '%')} (pós-Real)*"
            else:
                ipca_str = _fmt(m["ipca_acumulado_pct"], ">8.1f", "%")

            # Formatação PIB
            pib_str = _fmt(m["pib_medio_anual_pct"], ">6.2f", "%")

            # Câmbio final
            cambio_str = "N/D" if m["cambio_final_usd_brl"] is None else f"R$ {m['cambio_final_usd_brl']:>5.2f}"

            # Salário mínimo em USD
            sal_usd = "N/D" if m["salario_minimo_final_usd"] is None else f"US$ {m['salario_minimo_final_usd']:>6.2f}"

            print(
                f"{pres:<26} | {partido:<6} | {periodo:<11} | {ipca_str:<15} | {pib_str:<12} | {cambio_str:<12} | {sal_usd}"
            )

        print("-" * 115)
        print("=" * 115 + "\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    pipeline = PresidentsEconomicSyncPipeline()
    pipeline.run()
