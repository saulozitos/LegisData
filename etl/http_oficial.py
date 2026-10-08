"""
Cliente HTTP mínimo (somente stdlib) para fontes oficiais do governo.

- Cache em disco: cada URL vira um arquivo em ``cache_dir``; se o arquivo existe,
  não há nova requisição (use ``refresh=True`` para forçar).
- Rate limit: intervalo mínimo entre requisições (padrão 1,1 s, ou seja, < 1 req/s).
- Retentativas com backoff exponencial para 429/5xx e erros de rede.
- Timeout explícito em toda requisição.

Fica fora de ``etl/extractors`` de propósito: o ``__init__`` daquele pacote importa
extratores que dependem de pandas, e este módulo precisa ser importável (e testável)
só com a biblioteca padrão.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Mapping, Optional

logger = logging.getLogger("HttpOficial")

USER_AGENT = "LegisDataBot/1.0 (Transparência Pública; contato@legisdata.org)"


class HttpOficialError(RuntimeError):
    """Falha definitiva ao obter um recurso oficial (após as retentativas)."""


class CachedHttpClient:
    def __init__(
        self,
        cache_dir: Path,
        min_interval_s: float = 1.1,
        timeout_s: float = 60.0,
        max_retries: int = 4,
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval_s = min_interval_s
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self._last_request_at = 0.0
        self.requests_made = 0

    @staticmethod
    def build_url(base: str, params: Optional[Mapping[str, object]] = None) -> str:
        if not params:
            return base
        # "/" é mantido literal porque o WS legado da Câmara espera DD/MM/AAAA.
        return f"{base}?{urllib.parse.urlencode(params, safe='/')}"

    def cache_path(self, url: str, suffix: str) -> Path:
        slug = re.sub(r"[^A-Za-z0-9]+", "_", url.split("://", 1)[-1])[:90].strip("_")
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
        return self.cache_dir / f"{slug}_{digest}{suffix}"

    def _throttle(self) -> None:
        wait = self.min_interval_s - (time.monotonic() - self._last_request_at)
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.monotonic()

    def get_bytes(
        self,
        base: str,
        params: Optional[Mapping[str, object]] = None,
        accept: str = "*/*",
        suffix: str = ".bin",
        refresh: bool = False,
    ) -> bytes:
        url = self.build_url(base, params)
        path = self.cache_path(url, suffix)
        if path.exists() and not refresh:
            return path.read_bytes()

        headers = {"User-Agent": USER_AGENT, "Accept": accept}
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            self._throttle()
            try:
                self.requests_made += 1
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    body = resp.read()
                tmp = path.with_suffix(path.suffix + ".part")
                tmp.write_bytes(body)
                tmp.replace(path)
                return body
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code not in (429, 500, 502, 503, 504):
                    raise HttpOficialError(f"HTTP {exc.code} em {url}") from exc
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                last_error = exc
            backoff = 2.0 * (2 ** attempt)
            logger.warning("Falha em %s (%s); nova tentativa em %.0fs", url, last_error, backoff)
            time.sleep(backoff)
        raise HttpOficialError(f"Falha após {self.max_retries} tentativas em {url}: {last_error}")
