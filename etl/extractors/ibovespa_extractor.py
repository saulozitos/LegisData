"""
Fechamento anual do Ibovespa (^BVSP) a partir da API pública de gráficos do Yahoo Finance.

Para cada ano encerrado, o fechamento é o `close` da barra mensal de dezembro (último pregão do ano). Para o ano
em curso o valor é o último fechamento disponível e sai marcado `parcial=True` — nunca como fechamento anual.
Yahoo Finance cobre a partir de abril/1993; anos anteriores (e falhas de rede) caem na tabela digitada da B3 ou
na série 7 do SGS, e cada linha informa a `fonte` usada.
"""

import json
import logging
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from etl.config import RAW_DATA_DIR
from etl.utils.http_client import HttpClient, HttpError
from etl.utils.io_utils import atomic_write_json

logger = logging.getLogger("IbovespaExtractor")

YAHOO_URL = "https://query2.finance.yahoo.com/v8/finance/chart/%5EBVSP?range=max&interval=1mo"
# O Yahoo recusa user agents identificados como bot; usamos um agente de navegador genérico.
YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko)"}
FONTE_YAHOO = "Yahoo Finance (^BVSP, fechamento mensal de dezembro)"
CACHE_TTL_HORAS = 24
DIVERGENCIA_MAXIMA = 0.01  # alerta se o Yahoo divergir mais de 1% da tabela da B3


def fechamentos_anuais(payload: Dict[str, Any], hoje: Optional[date] = None) -> Dict[int, Dict[str, Any]]:
    """Extrai {ano: {valor, parcial}} do JSON do Yahoo (barras mensais)."""
    hoje = hoje or date.today()
    try:
        resultado = payload["chart"]["result"][0]
        timestamps: List[int] = resultado["timestamp"]
        closes: List[Optional[float]] = resultado["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError, TypeError) as exc:
        raise HttpError(YAHOO_URL, None, f"Resposta inesperada do Yahoo Finance: {exc}") from exc

    por_ano: Dict[int, Dict[str, Any]] = {}
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        momento = datetime.fromtimestamp(ts, tz=timezone.utc)
        ano, mes = momento.year, momento.month
        if ano < hoje.year and mes != 12:
            continue  # em anos encerrados só interessa a barra de dezembro
        atual = por_ano.get(ano)
        if atual is None or mes >= atual["mes"]:
            por_ano[ano] = {"valor": round(float(close), 2), "mes": mes, "parcial": ano >= hoje.year}
    return {a: {"valor": v["valor"], "parcial": v["parcial"]} for a, v in por_ano.items()}


class IbovespaExtractor:
    def __init__(self, raw_cache_dir: Path = RAW_DATA_DIR, http: Optional[HttpClient] = None):
        self.cache_file = Path(raw_cache_dir) / "yahoo" / "bvsp_mensal.json"
        self.http = http or HttpClient(timeout=60.0, max_retries=4, min_interval=1.0)

    def _payload(self, use_cache: bool = True) -> Dict[str, Any]:
        if (
            use_cache
            and self.cache_file.exists()
            and (time.time() - self.cache_file.stat().st_mtime) < CACHE_TTL_HORAS * 3600
        ):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as fh:
                    return json.load(fh)
            except (OSError, ValueError):
                pass
        payload = self.http.get_json(YAHOO_URL, headers=YAHOO_HEADERS)
        fechamentos_anuais(payload)  # valida o formato antes de gravar o cache
        atomic_write_json(self.cache_file, payload, indent=None)
        return payload

    def fetch(
        self,
        tabela_b3: Optional[Dict[int, float]] = None,
        hoje: Optional[date] = None,
        use_cache: bool = True,
    ) -> Dict[int, Dict[str, Any]]:
        """{ano: {valor, parcial, fonte}}. Confronta o Yahoo com a tabela da B3 e avisa divergências."""
        try:
            anuais = fechamentos_anuais(self._payload(use_cache=use_cache), hoje=hoje)
        except HttpError as exc:
            logger.warning("Yahoo Finance indisponível (%s): usando só a tabela da B3.", exc)
            return {}
        saida: Dict[int, Dict[str, Any]] = {}
        for ano, item in anuais.items():
            esperado = (tabela_b3 or {}).get(ano)
            if esperado and not item["parcial"] and abs(item["valor"] - esperado) / esperado > DIVERGENCIA_MAXIMA:
                logger.warning(
                    "Ibovespa %s: Yahoo=%.0f diverge da tabela da B3=%.0f (>%.0f%%).",
                    ano,
                    item["valor"],
                    esperado,
                    DIVERGENCIA_MAXIMA * 100,
                )
            saida[ano] = {**item, "fonte": FONTE_YAHOO}
        return saida
