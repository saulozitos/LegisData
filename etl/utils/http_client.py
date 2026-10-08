"""
Cliente HTTP único do ETL: timeout obrigatório, verificação de status, retentativas com backoff
e limitação de taxa compartilhada entre threads.

Substitui os `urllib.request.urlopen` espalhados pelos extractors, que engoliam exceções,
não verificavam status e não tinham retry consistente.
"""

import http.client
import json
import logging
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from etl.config import DEFAULT_USER_AGENT

logger = logging.getLogger("HttpClient")

RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


class HttpError(Exception):
    """Falha definitiva de uma requisição (status não recuperável ou tentativas esgotadas)."""

    def __init__(self, url: str, status: Optional[int], message: str):
        super().__init__(f"{message} [{status}] {url}")
        self.url = url
        self.status = status


class RateLimiter:
    """Garante um intervalo mínimo entre requisições, mesmo com várias threads."""

    def __init__(self, min_interval: float = 0.0):
        self.min_interval = max(0.0, float(min_interval))
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self) -> None:
        if self.min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            sleep_for = self._next_allowed - now
            self._next_allowed = max(now, self._next_allowed) + self.min_interval
        if sleep_for > 0:
            time.sleep(sleep_for)


class HttpClient:
    """GET com retry/backoff; retorna bytes, texto ou JSON validados por status."""

    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: float = 30.0,
        max_retries: int = 4,
        min_interval: float = 0.0,
        backoff_base: float = 1.5,
        sleep=time.sleep,
    ):
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_retries = max(1, int(max_retries))
        self.backoff_base = backoff_base
        self.limiter = RateLimiter(min_interval)
        self._sleep = sleep

    def get_bytes(self, url: str, headers: Optional[Dict[str, str]] = None, timeout: Optional[float] = None) -> bytes:
        """Baixa `url`. Levanta HttpError em status definitivo ou após esgotar as tentativas."""
        hdrs = {"User-Agent": self.user_agent}
        if headers:
            hdrs.update(headers)

        last_error: Optional[Exception] = None
        last_status: Optional[int] = None
        for attempt in range(1, self.max_retries + 1):
            self.limiter.wait()
            try:
                req = urllib.request.Request(url, headers=hdrs)
                with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                    status = getattr(resp, "status", 200)
                    if status != 200:
                        raise HttpError(url, status, "Status inesperado")
                    return resp.read()
            except http.client.IncompleteRead as exc:
                # Corpo truncado NÃO é resposta válida: tenta de novo em vez de aceitar `exc.partial`.
                last_error = exc
                logger.warning("IncompleteRead em %s (tentativa %d/%d)", url, attempt, self.max_retries)
            except urllib.error.HTTPError as exc:
                last_status = exc.code
                last_error = exc
                if exc.code not in RETRYABLE_STATUS:
                    raise HttpError(url, exc.code, f"HTTP {exc.reason}") from exc
                logger.warning("HTTP %s em %s (tentativa %d/%d)", exc.code, url, attempt, self.max_retries)
            except HttpError as exc:
                last_status = exc.status
                last_error = exc
                if exc.status is not None and exc.status not in RETRYABLE_STATUS:
                    raise
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
                last_error = exc
                logger.warning("Falha de rede em %s: %s (tentativa %d/%d)", url, exc, attempt, self.max_retries)

            if attempt < self.max_retries:
                self._sleep(self.backoff_base**attempt)

        raise HttpError(url, last_status, f"Tentativas esgotadas ({last_error})")

    def get_json(self, url: str, headers: Optional[Dict[str, str]] = None, timeout: Optional[float] = None) -> Any:
        hdrs = {"Accept": "application/json"}
        if headers:
            hdrs.update(headers)
        raw = self.get_bytes(url, headers=hdrs, timeout=timeout)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HttpError(url, None, f"JSON inválido: {exc}") from exc

    def try_get_json(self, url: str, **kwargs) -> Optional[Any]:
        """Como get_json, mas devolve None em falha (loga o motivo). Use quando a ausência é tolerável."""
        try:
            return self.get_json(url, **kwargs)
        except HttpError as exc:
            logger.warning("Requisição falhou: %s", exc)
            return None
