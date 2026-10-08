"""Download em streaming de arquivos grandes (zips dos dados abertos), com escrita atômica e retry."""

import logging
import os
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

from etl.config import DEFAULT_USER_AGENT

logger = logging.getLogger("Download")

Opener = Callable[..., Any]


class DownloadError(RuntimeError):
    """Falha definitiva ao baixar um arquivo (tentativas esgotadas ou arquivo truncado)."""


class NotFoundError(DownloadError):
    """O servidor respondeu 404: o arquivo não existe (não vale a pena repetir)."""


def _request(url: str, method: str, timeout: float, opener: Opener, user_agent: str):
    req = urllib.request.Request(url, method=method, headers={"User-Agent": user_agent})
    return opener(req, timeout=timeout)


def remote_size(url: str, timeout: float, opener: Opener, user_agent: str) -> Optional[int]:
    """Content-Length do arquivo remoto; None se indisponível. Propaga 404 como NotFoundError."""
    try:
        with _request(url, "HEAD", timeout, opener, user_agent) as resp:
            value = resp.headers.get("Content-Length")
            return int(value) if value else None
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise NotFoundError(f"{url}: 404") from exc
        logger.warning("HEAD falhou em %s: %s", url, exc)
        return None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        logger.warning("HEAD falhou em %s: %s", url, exc)
        return None


def download_file(
    url: str,
    dest: Path,
    *,
    force: bool = False,
    attempts: int = 4,
    timeout: float = 120.0,
    opener: Opener = urllib.request.urlopen,
    user_agent: str = DEFAULT_USER_AGENT,
    sleep: Callable[[float], None] = time.sleep,
) -> Path:
    """Baixa `url` para `dest` (atômico). Reaproveita o cache quando o tamanho confere com o remoto."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    expected = remote_size(url, timeout, opener, user_agent)

    if dest.exists() and not force:
        if expected is None or dest.stat().st_size == expected:
            logger.info("Cache válido: %s", dest.name)
            return dest
        logger.warning("Cache de %s com tamanho divergente; baixando de novo.", dest.name)

    last_error: Optional[BaseException] = None
    for attempt in range(1, max(1, attempts) + 1):
        fd, tmp_name = tempfile.mkstemp(prefix=f".{dest.name}.", suffix=".part", dir=str(dest.parent))
        os.close(fd)
        try:
            written = 0
            with _request(url, "GET", timeout, opener, user_agent) as resp, open(tmp_name, "wb") as out:
                if expected is None:
                    value = resp.headers.get("Content-Length")
                    expected = int(value) if value else None
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    written += len(chunk)
                out.flush()
                os.fsync(out.fileno())
            if expected is not None and written != expected:
                raise DownloadError(f"Download truncado ({written} de {expected} bytes)")
            os.replace(tmp_name, dest)
            logger.info("Baixado %s (%.1f MB)", dest.name, written / 1e6)
            return dest
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise NotFoundError(f"{url}: 404") from exc
            last_error = exc
        except (urllib.error.URLError, TimeoutError, OSError, DownloadError) as exc:
            last_error = exc
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        logger.warning("Falha ao baixar %s (tentativa %d/%d): %s", url, attempt, attempts, last_error)
        if attempt < attempts:
            sleep(2.0**attempt)
    raise DownloadError(f"Não foi possível baixar {url}: {last_error}")
