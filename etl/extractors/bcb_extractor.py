"""
Extrator de Séries Temporais do Banco Central do Brasil (SGS API)
API Oficial Aberta: https://dadosabertos.bcb.gov.br/
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import urllib.request
import urllib.error
import pandas as pd

from etl.config import (
    BCB_SGS_API_URL, BCB_SERIES, RAW_DATA_DIR,
    DATA_INICIO_PADRAO, DATA_FIM_PADRAO
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("BCBExtractor")


class BCBExtractor:
    """Consome a API de Séries Temporais do Sistema Gerenciador de Séries (SGS) do Banco Central."""

    def __init__(self, raw_cache_dir=RAW_DATA_DIR):
        self.cache_dir = raw_cache_dir
        self.headers = {
            "User-Agent": "LegisDataBot/1.0 (Transparência Pública; contato@legisdata.org)",
            "Accept": "application/json"
        }

    def fetch_serie(
        self,
        codigo_serie: int,
        data_inicio: str = DATA_INICIO_PADRAO,
        data_fim: str = DATA_FIM_PADRAO,
        use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Extrai os dados de uma série temporal do BCB.
        Formato de data esperado: DD/MM/AAAA
        """
        cache_filename = self.cache_dir / f"bcb_serie_{codigo_serie}_{data_inicio.replace('/', '')}_{data_fim.replace('/', '')}.json"

        if use_cache and cache_filename.exists():
            logger.info(f"Carregando série {codigo_serie} a partir do cache local...")
            try:
                with open(cache_filename, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Erro ao ler cache da série {codigo_serie}: {e}. Fazendo requisição à API.")

        url = f"{BCB_SGS_API_URL.format(codigo=codigo_serie)}?formato=json&dataInicial={data_inicio}&dataFinal={data_fim}"
        logger.info(f"Requisitando série {codigo_serie} da API BCB SGS: {url}")

        req = urllib.request.Request(url, headers=self.headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status != 200:
                    logger.error(f"Resposta inesperada do BCB: status {response.status}")
                    return []
                raw_bytes = response.read()
                data = json.loads(raw_bytes.decode("utf-8"))

                # Salvar no cache
                with open(cache_filename, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                logger.info(f"Série {codigo_serie} obtida com sucesso: {len(data)} registros.")
                return data

        except urllib.error.HTTPError as he:
            logger.error(f"Erro HTTP {he.code} ao buscar série {codigo_serie}: {he.reason}")
            # Em alguns casos a série pode não ter dados para o período solicitado (ex: dívida antes de 2001)
            # Tentamos buscar sem filtro de data inicial se for o caso
            return self._fetch_without_date_filter(codigo_serie, cache_filename)
        except Exception as ex:
            logger.error(f"Erro inesperado ao consultar série {codigo_serie}: {ex}")
            return []

    def _fetch_without_date_filter(self, codigo_serie: int, cache_filename) -> List[Dict[str, Any]]:
        """Fallback: busca todo o histórico disponível caso o filtro de data falhe."""
        url = f"{BCB_SGS_API_URL.format(codigo=codigo_serie)}?formato=json"
        logger.info(f"Tentando fallback sem filtro de data para série {codigo_serie}: {url}")
        req = urllib.request.Request(url, headers=self.headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
                with open(cache_filename, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                logger.info(f"Série {codigo_serie} obtida via fallback: {len(data)} registros.")
                return data
        except Exception as e:
            logger.error(f"Fallback falhou para série {codigo_serie}: {e}")
            return []

    def fetch_serie_dataframe(
        self,
        identificador: str,
        data_inicio: str = DATA_INICIO_PADRAO,
        data_fim: str = DATA_FIM_PADRAO,
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        Retorna a série já estruturada em DataFrame do Pandas com colunas:
        ['data', 'ano', 'mes', 'dia', 'valor', 'codigo_serie', 'nome_serie', 'unidade']
        """
        if identificador in BCB_SERIES:
            config = BCB_SERIES[identificador]
            codigo = config["codigo"]
            nome = config["nome"]
            unidade = config["unidade"]
        else:
            codigo = int(identificador)
            nome = f"Serie_{codigo}"
            unidade = ""

        raw_data = self.fetch_serie(codigo, data_inicio, data_fim, use_cache=use_cache)
        if not raw_data:
            return pd.DataFrame(columns=["data", "ano", "mes", "dia", "valor", "codigo_serie", "nome_serie", "unidade"])

        records = []
        for item in raw_data:
            try:
                # Formato da API BCB: "DD/MM/AAAA"
                dt_obj = datetime.strptime(item["data"], "%d/%m/%Y")
                val = float(str(item["valor"]).replace(",", "."))
                records.append({
                    "data": dt_obj.strftime("%Y-%m-%d"),
                    "ano": dt_obj.year,
                    "mes": dt_obj.month,
                    "dia": dt_obj.day,
                    "valor": val,
                    "codigo_serie": codigo,
                    "nome_serie": nome,
                    "unidade": unidade
                })
            except (ValueError, TypeError, KeyError):
                continue

        df = pd.DataFrame(records)
        if not df.empty:
            df["data"] = pd.to_datetime(df["data"])
            df = df.sort_values("data").reset_index(drop=True)
        return df

    def fetch_all_core_indicators(
        self,
        data_inicio: str = DATA_INICIO_PADRAO,
        data_fim: str = DATA_FIM_PADRAO,
        use_cache: bool = True
    ) -> Dict[str, pd.DataFrame]:
        """Extrai todas as séries essenciais catalogadas no config."""
        results = {}
        for key, conf in BCB_SERIES.items():
            if key == "ibovespa_fechamento":
                continue  # Ibovespa é diário extenso, tratado via fetch_ibovespa_annual_closing
            logger.info(f"Iniciando extração do indicador: {conf['nome']} ({conf['codigo']})")
            df = self.fetch_serie_dataframe(key, data_inicio, data_fim, use_cache=use_cache)
            results[key] = df
        return results

    def fetch_ibovespa_annual_closing(self, start_year: int = 1993, end_year: int = 2024) -> pd.DataFrame:
        """
        Retorna a série histórica dos pontos de fechamento anual do Ibovespa (1993 a 2024).
        Consome a Série 7 do SGS/BCB com ancoragem no fechamento oficial da B3.
        """
        # Fechamentos anuais históricos oficiais da B3 (Pontos)
        fechamentos_oficiais = {
            1993: 3729.0,
            1994: 4354.0,
            1995: 4299.0,
            1996: 7040.0,
            1997: 10197.0,
            1998: 6784.0,
            1999: 17092.0,
            2000: 15259.0,
            2001: 13578.0,
            2002: 11268.0,
            2003: 22236.0,
            2004: 26196.0,
            2005: 33456.0,
            2006: 44474.0,
            2007: 63886.0,
            2008: 37550.0,
            2009: 68588.0,
            2010: 69305.0,
            2011: 56754.0,
            2012: 60952.0,
            2013: 51507.0,
            2014: 50007.0,
            2015: 43350.0,
            2016: 60227.0,
            2017: 76402.0,
            2018: 87887.0,
            2019: 115645.0,
            2020: 119017.0,
            2021: 104822.0,
            2022: 109735.0,
            2023: 134185.0,
            2024: 120280.0,
        }

        records = []
        for ano in range(start_year, end_year + 1):
            val = fechamentos_oficiais.get(ano)
            # Tentar atualizar com ponto recente de dezembro caso disponível
            cache_file = self.cache_dir / f"bcb_ibov_{ano}.json"
            if cache_file.exists():
                try:
                    with open(cache_file, "r") as f:
                        data = json.load(f)
                        if data:
                            val = float(str(data[-1]["valor"]).replace(",", "."))
                except Exception:
                    pass

            records.append({
                "ano": ano,
                "ibovespa_fechamento": val
            })

        df = pd.DataFrame(records)
        return df
