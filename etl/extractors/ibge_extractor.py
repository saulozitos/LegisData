"""
Extrator de Indicadores Econômicos do IBGE (API SIDRA / Agregados)
Documentação oficial: https://servicodados.ibge.gov.br/api/docs/agregados
"""

import json
import logging
from typing import Dict, Any, List, Optional
import urllib.request
import urllib.error
import pandas as pd

from etl.config import IBGE_SIDRA_API_URL, RAW_DATA_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("IBGEExtractor")


class IBGEExtractor:
    """Extrai séries e agregados econômicos da API oficial de agregados do IBGE (SIDRA)."""

    def __init__(self, raw_cache_dir=RAW_DATA_DIR):
        self.cache_dir = raw_cache_dir
        self.headers = {
            "User-Agent": "LegisDataBot/1.0 (Transparência Pública; contato@legisdata.org)",
            "Accept": "application/json"
        }

    def fetch_agregado(
        self,
        agregado_id: int,
        variaveis: str,
        periodos: str = "all",
        localidade: str = "N1[all]",
        use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Consulta um agregado do IBGE.
        Exemplo: Agregado 1737 (IPCA), Variavel 63 (IPCA variação mensal), períodos 'all'
        """
        cache_filename = self.cache_dir / f"ibge_agregado_{agregado_id}_{variaveis}_{periodos.replace('|', '_')}.json"

        if use_cache and cache_filename.exists():
            logger.info(f"Carregando agregado IBGE {agregado_id} a partir do cache local...")
            try:
                with open(cache_filename, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Erro ao ler cache do agregado {agregado_id}: {e}")

        url = f"{IBGE_SIDRA_API_URL}/{agregado_id}/periodos/{periodos}/variaveis/{variaveis}?localidades={localidade}"
        logger.info(f"Consultando API IBGE: {url}")

        req = urllib.request.Request(url, headers=self.headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status != 200:
                    logger.error(f"Erro IBGE: status {response.status}")
                    return []
                data = json.loads(response.read().decode("utf-8"))

                with open(cache_filename, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                logger.info(f"Dados do Agregado {agregado_id} obtidos com sucesso: {len(data)} blocos.")
                return data
        except Exception as ex:
            logger.error(f"Erro ao requisitar Agregado {agregado_id} do IBGE: {ex}")
            return []

    def fetch_ipca_historico(self, use_cache: bool = True) -> pd.DataFrame:
        """
        Extrai o histórico mensal do IPCA (Tabela 1737, Variável 63 - Variação mensal).
        """
        raw_data = self.fetch_agregado(agregado_id=1737, variaveis="63", periodos="all", use_cache=use_cache)
        if not raw_data:
            return pd.DataFrame()

        records = []
        try:
            series_list = raw_data[0]["resultados"][0]["series"]
            for serie in series_list:
                serie_data = serie["serie"]
                for periodo_str, valor_str in serie_data.items():
                    # Formato periodo: "AAAAMM" (ex: "199407")
                    try:
                        ano = int(periodo_str[:4])
                        mes = int(periodo_str[4:])
                        if valor_str in ("...", "-", ""):
                            continue
                        valor = float(valor_str)
                        records.append({
                            "data": f"{ano:04d}-{mes:02d}-01",
                            "ano": ano,
                            "mes": mes,
                            "valor": valor,
                            "fonte": "IBGE - SIDRA Tabela 1737",
                            "indicador": "IPCA_MENSAL"
                        })
                    except (ValueError, IndexError):
                        continue
        except (KeyError, IndexError) as err:
            logger.error(f"Erro ao analisar estrutura de resposta do IBGE IPCA: {err}")

        df = pd.DataFrame(records)
        if not df.empty:
            df["data"] = pd.to_datetime(df["data"])
            df = df.sort_values("data").reset_index(drop=True)
        return df
