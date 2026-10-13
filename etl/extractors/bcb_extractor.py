"""
Extrator de Séries Temporais do Banco Central do Brasil (SGS API)
API Oficial Aberta: https://dadosabertos.bcb.gov.br/
"""

import json
import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from etl.config import (
    BCB_SERIES,
    BCB_SGS_API_URL,
    DATA_INICIO_PADRAO,
    RAW_DATA_DIR,
    data_fim_padrao,
)
from etl.extractors.ibovespa_extractor import IbovespaExtractor
from etl.utils.http_client import HttpClient, HttpError
from etl.utils.io_utils import atomic_write_json

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("BCBExtractor")

# Desde 2025 o SGS limita séries diárias a janelas de 10 anos por consulta.
JANELA_MAXIMA_ANOS = 10
CACHE_MAX_IDADE_HORAS = 24

# Fechamentos anuais do Ibovespa (pontos) digitados a partir de dados da B3. Anos sem valor ficam None
# (ou são buscados na série 7 do SGS quando o ano já terminou) — nunca preenchidos com palpite.
IBOVESPA_DIVERGENCIA_MAXIMA = 0.01  # Yahoo x tabela da B3: acima disso o ano é descartado, não "escolhido"
IBOVESPA_FECHAMENTOS_B3: Dict[int, float] = {
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


def _parse_data(texto: str) -> date:
    return datetime.strptime(texto, "%d/%m/%Y").date()


def janelas(inicio: date, fim: date, anos: int = JANELA_MAXIMA_ANOS) -> List[tuple]:
    """Divide [inicio, fim] em janelas consecutivas de no máximo `anos` anos (sem sobreposição)."""
    resultado = []
    atual = inicio
    while atual <= fim:
        try:
            limite = atual.replace(year=atual.year + anos) - timedelta(days=1)
        except ValueError:  # 29/02
            limite = atual.replace(year=atual.year + anos, day=28) - timedelta(days=1)
        fim_janela = min(limite, fim)
        resultado.append((atual, fim_janela))
        atual = fim_janela + timedelta(days=1)
    return resultado


def resposta_valida(data: Any) -> bool:
    """O SGS devolve lista de {data, valor}; um objeto (ex.: {"error": ...}) é resposta de erro, não dado."""
    return (
        isinstance(data, list)
        and len(data) > 0
        and all(isinstance(x, dict) and "data" in x and "valor" in x for x in data[:5])
    )


class BCBExtractor:
    """Consome a API de Séries Temporais do Sistema Gerenciador de Séries (SGS) do Banco Central."""

    def __init__(
        self,
        raw_cache_dir=RAW_DATA_DIR,
        http: Optional[HttpClient] = None,
        cache_max_idade_horas: int = CACHE_MAX_IDADE_HORAS,
    ):
        self.cache_dir = Path(raw_cache_dir)
        self.http = http or HttpClient(timeout=30.0, max_retries=4)
        self.cache_max_idade_horas = cache_max_idade_horas

    # ------------------------------------------------------------------ cache
    def _cache_path(self, codigo_serie: int, data_inicio: str) -> Path:
        # A data final NÃO entra no nome: antes, o nome mudava todo dia e o cache nunca era reaproveitado.
        return self.cache_dir / f"bcb_serie_{codigo_serie}_{data_inicio.replace('/', '')}.json"

    def _ler_cache(self, path: Path) -> Optional[List[Dict[str, Any]]]:
        if not path.exists():
            return None
        idade_h = (time.time() - path.stat().st_mtime) / 3600.0
        if idade_h > self.cache_max_idade_horas:
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return None
        return data if resposta_valida(data) else None

    # ------------------------------------------------------------------ fetch
    def _consultar(self, codigo_serie: int, inicio: str, fim: str) -> Optional[List[Dict[str, Any]]]:
        url = f"{BCB_SGS_API_URL.format(codigo=codigo_serie)}?formato=json&dataInicial={inicio}&dataFinal={fim}"
        data = self.http.get_json(url)  # HttpError sobe para o chamador decidir (ex.: janela maior que o limite)
        if not resposta_valida(data):
            logger.error("Resposta inválida do BCB para a série %s (%s a %s): %.200s", codigo_serie, inicio, fim, data)
            return None
        return data

    def _consultar_em_janelas(self, codigo_serie: int, data_inicio: str, data_fim: str) -> List[Dict[str, Any]]:
        resultado: List[Dict[str, Any]] = []
        for ini, fim in janelas(_parse_data(data_inicio), _parse_data(data_fim)):
            try:
                parte = self._consultar(codigo_serie, ini.strftime("%d/%m/%Y"), fim.strftime("%d/%m/%Y"))
            except HttpError as exc:
                logger.error("Janela %s-%s da série %s falhou: %s", ini, fim, codigo_serie, exc)
                return []  # janela faltando = série incompleta: não devolve parcial
            if parte:
                resultado.extend(parte)
        return resultado

    def fetch_serie(
        self,
        codigo_serie: int,
        data_inicio: str = DATA_INICIO_PADRAO,
        data_fim: Optional[str] = None,
        use_cache: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Extrai os dados de uma série do BCB (datas DD/MM/AAAA). Devolve [] em falha — e NUNCA grava cache
        de resposta inválida (antes, um dict de erro 200 era cacheado e virava DataFrame vazio sem aviso).
        """
        data_fim = data_fim or data_fim_padrao()
        cache_path = self._cache_path(codigo_serie, data_inicio)

        if use_cache:
            em_cache = self._ler_cache(cache_path)
            if em_cache is not None:
                logger.info(f"Série {codigo_serie} carregada do cache local (< {self.cache_max_idade_horas}h).")
                return em_cache

        logger.info(f"Requisitando série {codigo_serie} da API BCB SGS ({data_inicio} a {data_fim})...")
        try:
            data = self._consultar(codigo_serie, data_inicio, data_fim)
        except HttpError as exc:
            if exc.status in (400, 404, 406):
                logger.warning(
                    "BCB recusou a janela completa (%s); repetindo em janelas de %d anos.", exc, JANELA_MAXIMA_ANOS
                )
                data = self._consultar_em_janelas(codigo_serie, data_inicio, data_fim)
            else:
                logger.error("Falha ao buscar a série %s: %s", codigo_serie, exc)
                return []

        if not data:
            return []

        atomic_write_json(cache_path, data)
        logger.info(f"Série {codigo_serie} obtida com sucesso: {len(data)} registros.")
        return data

    def fetch_serie_dataframe(
        self,
        identificador: str,
        data_inicio: str = DATA_INICIO_PADRAO,
        data_fim: Optional[str] = None,
        use_cache: bool = True,
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
                records.append(
                    {
                        "data": dt_obj.strftime("%Y-%m-%d"),
                        "ano": dt_obj.year,
                        "mes": dt_obj.month,
                        "dia": dt_obj.day,
                        "valor": val,
                        "codigo_serie": codigo,
                        "nome_serie": nome,
                        "unidade": unidade,
                    }
                )
            except (ValueError, TypeError, KeyError):
                continue

        df = pd.DataFrame(records)
        if not df.empty:
            df["data"] = pd.to_datetime(df["data"])
            df = df.sort_values("data").reset_index(drop=True)
        return df

    def fetch_all_core_indicators(
        self, data_inicio: str = DATA_INICIO_PADRAO, data_fim: Optional[str] = None, use_cache: bool = True
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

    def _ibovespa_fechamento_sgs(self, ano: int) -> Optional[float]:
        """Último fechamento do ano na série 7 do SGS (janela de fim de ano, bem abaixo do limite de 10 anos)."""
        cache_file = self.cache_dir / f"bcb_ibov_{ano}.json"
        dados = None
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    dados = json.load(f)
            except (OSError, ValueError):
                dados = None
        if not resposta_valida(dados):
            try:
                dados = self._consultar(7, f"15/12/{ano}", f"31/12/{ano}")
            except HttpError as exc:
                logger.warning("Ibovespa %s indisponível no SGS: %s", ano, exc)
                return None
            if not dados:
                return None
            atomic_write_json(cache_file, dados)
        try:
            return float(str(dados[-1]["valor"]).replace(",", "."))
        except (KeyError, ValueError, TypeError):
            return None

    def fetch_ibovespa_annual_closing(
        self, start_year: int = 1993, end_year: Optional[int] = None, ibovespa: Optional[IbovespaExtractor] = None
    ) -> pd.DataFrame:
        """
        Fechamento anual do Ibovespa. Fonte principal: Yahoo Finance (^BVSP, barra de dezembro), conferida contra a
        tabela da B3. Sem Yahoo, usa a tabela da B3 (1993-2024) e, para anos encerrados fora dela, a série 7 do SGS.
        O ano em curso NÃO tem fechamento: `ibovespa_fechamento` fica None e o último pregão vai em
        `ibovespa_ultimo_pregao` com `parcial=True`. Cada linha informa a `fonte` usada; nada é estimado.
        """
        hoje = date.today()
        end_year = end_year or hoje.year
        yahoo = (ibovespa or IbovespaExtractor(raw_cache_dir=self.cache_dir, http=self.http)).fetch(
            tabela_b3=IBOVESPA_FECHAMENTOS_B3, hoje=hoje
        )
        registros = []
        for ano in range(start_year, end_year + 1):
            item = yahoo.get(ano)
            fechamento: Optional[float] = None
            ultimo: Optional[float] = None
            parcial = False
            fonte: Optional[str] = None
            if ano >= hoje.year:
                if item:
                    ultimo, parcial, fonte = item["valor"], True, item["fonte"]
            elif item and not item["parcial"]:
                b3 = IBOVESPA_FECHAMENTOS_B3.get(ano)
                if b3 is None:
                    fechamento, fonte = item["valor"], item["fonte"]
                elif abs(item["valor"] - b3) / b3 <= IBOVESPA_DIVERGENCIA_MAXIMA:
                    # Fechamento oficial da B3, corroborado pelo Yahoo (que pode vir do último pregão ± 1 dia)
                    fechamento, fonte = b3, "B3 (tabela de fechamentos anuais), conferida com Yahoo Finance"
                else:
                    logger.error(
                        "Ibovespa %s: Yahoo (%.0f) e tabela da B3 (%.0f) divergem; valor descartado.",
                        ano,
                        item["valor"],
                        b3,
                    )
            elif IBOVESPA_FECHAMENTOS_B3.get(ano) is not None:
                fechamento, fonte = IBOVESPA_FECHAMENTOS_B3[ano], "B3 (tabela de fechamentos anuais, sem conferência)"
            else:
                fechamento = self._ibovespa_fechamento_sgs(ano)
                fonte = "BCB SGS 7" if fechamento is not None else None
            registros.append(
                {
                    "ano": ano,
                    "ibovespa_fechamento": fechamento,
                    "ibovespa_ultimo_pregao": ultimo,
                    "parcial": parcial,
                    "fonte": fonte,
                }
            )
        return pd.DataFrame(registros)
