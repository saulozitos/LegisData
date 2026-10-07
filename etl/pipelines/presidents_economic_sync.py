"""
Pipeline Principal de ETL: Sincronização de Presidentes e Indicadores Econômicos Básicos (BCB / IBGE)
"""

import os
import json
import logging
from typing import Dict, Any, List
import pandas as pd

from etl.config import PROCESSED_DATA_DIR, RAW_DATA_DIR
from etl.extractors.presidents_extractor import PresidentsExtractor
from etl.extractors.bcb_extractor import BCBExtractor
from etl.extractors.ibge_extractor import IBGEExtractor
from etl.extractors.inpe_extractor import INPEExtractor
from etl.extractors.social_indicators_extractor import SocialIndicatorsExtractor
from etl.extractors.seguranca_extractor import SegurancaExtractor
from etl.transformers.economic_normalizer import EconomicNormalizer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ETLPipeline")


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
        logger.info("INICIANDO PIPELINE: PRESIDENTES E INDICADORES MACROECONÔMICOS (1992 - PRESENTE)")
        logger.info("=" * 70)

        # 1. Obter catálogo histórico de presidentes
        logger.info("Passo 1/5: Extraindo lista histórica de presidentes (Itamar Franco -> Presente)...")
        presidents = self.presidents_extractor.get_presidents()
        logger.info(f"-> {len(presidents)} mandatos presidenciais mapeados com sucesso.")

        # 2. Extrair dados das APIs públicas do Banco Central e IBGE
        logger.info("Passo 2/5: Extraindo indicadores econômicos das APIs do Banco Central (SGS) e IBGE...")
        
        # IPCA Mensal (Série 433 BCB)
        ipca_df = self.bcb_extractor.fetch_serie_dataframe("ipca_mensal", use_cache=use_cache)
        logger.info(f"-> IPCA Mensal: {len(ipca_df)} registros obtidos ({ipca_df['data'].min()} a {ipca_df['data'].max()})")

        # Câmbio USD/BRL (Série 3698 BCB)
        cambio_df = self.bcb_extractor.fetch_serie_dataframe("cambio_usd_brl_venda", use_cache=use_cache)
        logger.info(f"-> Câmbio USD/BRL: {len(cambio_df)} registros obtidos.")

        # PIB Variação Anual Real (Série 7326 BCB)
        pib_anual_df = self.bcb_extractor.fetch_serie_dataframe("pib_variacao_anual", use_cache=use_cache)
        logger.info(f"-> PIB Variação Anual: {len(pib_anual_df)} anos registrados.")

        # Dívida Líquida (% PIB - Série 4513 BCB)
        divida_df = self.bcb_extractor.fetch_serie_dataframe("divida_liquida_pib", use_cache=use_cache)
        logger.info(f"-> Dívida Líquida / PIB: {len(divida_df)} registros obtidos.")

        # Salário Mínimo Nominal (Série 1619 BCB)
        salario_min_df = self.bcb_extractor.fetch_serie_dataframe("salario_minimo_nominal", use_cache=use_cache)
        logger.info(f"-> Salário Mínimo: {len(salario_min_df)} registros obtidos.")

        # Ibovespa Fechamento Anual (Série 7 BCB / B3)
        ibovespa_df = self.bcb_extractor.fetch_ibovespa_annual_closing()
        logger.info(f"-> Ibovespa Fechamento Anual: {len(ibovespa_df)} anos registrados.")

        # 2.1 Extrair indicadores socioambientais expandidos
        logger.info("-> Extraindo dados de desemprego (IBGE), desmatamento (INPE/PRODES) e fome...")
        unemployment_dict = self.social_extractor.get_annual_unemployment_history()
        
        deforest_df = self.inpe_extractor.fetch_deforestation_history(use_cache=use_cache)
        deforestation_dict = dict(zip(deforest_df["ano"], deforest_df["desmatamento_km2"])) if not deforest_df.empty else {}
        
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
            feminicide_dict=feminicide_dict
        )

        logger.info("Passo 4/5: Construindo série histórica macroeconômica anual consolidada (1993 a presente)...")
        annual_summary_df = self.normalizer.build_annual_summaries(
            ipca_df=ipca_df,
            pib_anual_df=pib_anual_df,
            cambio_df=cambio_df,
            salario_min_df=salario_min_df,
            divida_df=divida_df,
            presidents=presidents,
            ibovespa_df=ibovespa_df,
            unemployment_dict=unemployment_dict,
            deforestation_dict=deforestation_dict,
            food_insecurity_dict=food_insecurity_dict,
            homicide_dict=homicide_dict,
            feminicide_dict=feminicide_dict
        )

        # 4. Exportação dos Dados Estruturados
        logger.info("Passo 5/5: Salvando arquivos processados em etl/data/processed/...")
        
        # Salvar JSON dos presidentes
        presidents_file = PROCESSED_DATA_DIR / "presidentes_historico.json"
        with open(presidents_file, "w", encoding="utf-8") as f:
            json.dump(presidents, f, ensure_ascii=False, indent=2)

        # Salvar resumo de mandatos (JSON e CSV)
        mandates_json_file = PROCESSED_DATA_DIR / "indicadores_por_mandato.json"
        with open(mandates_json_file, "w", encoding="utf-8") as f:
            json.dump(mandates_summary, f, ensure_ascii=False, indent=2)

        mandates_df = pd.DataFrame(mandates_summary)
        # Converter listas para strings para compatibilidade CSV
        mandates_df_export = mandates_df.copy()
        mandates_df_export["ministros_fazenda_principais"] = mandates_df_export["ministros_fazenda_principais"].apply(lambda x: ", ".join(x) if isinstance(x, list) else x)
        mandates_df_export["marcos_economicos_principais"] = mandates_df_export["marcos_economicos_principais"].apply(lambda x: " | ".join(x) if isinstance(x, list) else x)
        mandates_df_export.to_csv(PROCESSED_DATA_DIR / "indicadores_por_mandato.csv", index=False, encoding="utf-8")

        # Salvar resumo anual
        annual_summary_df.to_csv(PROCESSED_DATA_DIR / "resumo_macroeconomico_anual.csv", index=False, encoding="utf-8")

        # Salvar série de IPCA mensal tratada
        if not ipca_df.empty:
            ipca_df.to_csv(PROCESSED_DATA_DIR / "ipca_mensal_historico.csv", index=False, encoding="utf-8")

        logger.info(f"Arquivos gerados com sucesso em {PROCESSED_DATA_DIR}")

        # 5. Exibir Relatório Sintético no Console
        self._print_terminal_dashboard(mandates_summary)

        return {
            "total_presidents": len(presidents),
            "mandates_summary": mandates_summary,
            "annual_records": len(annual_summary_df),
            "output_directory": str(PROCESSED_DATA_DIR)
        }

    def _print_terminal_dashboard(self, mandates_summary: List[Dict[str, Any]]) -> None:
        """Gera um painel comparativo elegante no terminal."""
        print("\n" + "=" * 115)
        print("          PAINEL ANALÍTICO COMPARATIVO: GOVERNOS E INDICADORES ECONÔMICOS (1992 - PRESENTE)")
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
                ipca_str = f"33.0% (pós-Real)*"
            else:
                ipca_str = f"{m['ipca_acumulado_pct']:>8.1f}%"

            # Formatação PIB
            pib_str = f"{m['pib_medio_anual_pct']:>6.2f}%" if m['pib_medio_anual_pct'] else "N/D"

            # Câmbio final
            cambio_str = f"R$ {m['cambio_final_usd_brl']:>5.2f}" if m['cambio_final_usd_brl'] else "N/D"

            # Salário mínimo em USD
            sal_usd = f"US$ {m['salario_minimo_final_usd']:>6.2f}" if m['salario_minimo_final_usd'] else "N/D"

            print(f"{pres:<26} | {partido:<6} | {periodo:<11} | {ipca_str:<15} | {pib_str:<12} | {cambio_str:<12} | {sal_usd}")

        print("-" * 115)
        print("* Nota: No governo Itamar Franco, a inflação pré-Real atingiu patamar hiperinflacionário de 4 dígitos;")
        print("        o valor de 33.0% refere-se à inflação controlada nos 6 meses após o lançamento do Real (01/07/1994 a 31/12/1994).")
        print("=" * 115 + "\n")


if __name__ == "__main__":
    pipeline = PresidentsEconomicSyncPipeline()
    pipeline.run()

