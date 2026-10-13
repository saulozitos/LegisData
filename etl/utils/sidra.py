"""
Cliente da API SIDRA/IBGE (https://apisidra.ibge.gov.br) com cache em disco.

Devolve linhas já normalizadas: os valores não numéricos do SIDRA ("-", "..", "...", "X") viram None
(nunca zero) para que lacunas de pesquisa continuem lacunas.
"""

import gzip
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from etl.config import RAW_DATA_DIR
from etl.utils.http_client import HttpClient, HttpError
from etl.utils.io_utils import atomic_write_json

logger = logging.getLogger("SidraClient")

SIDRA_VALUES_URL = "https://apisidra.ibge.gov.br/values"
CACHE_TTL_HORAS = 24 * 7

# Níveis territoriais usados: N1 = Brasil, N3 = Unidades da Federação.
NIVEL_BRASIL = 1
NIVEL_UF = 3

# Código IBGE da UF -> sigla.
UF_POR_CODIGO_IBGE: Dict[int, str] = {
    11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO",
    21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB", 26: "PE", 27: "AL", 28: "SE", 29: "BA",
    31: "MG", 32: "ES", 33: "RJ", 35: "SP",
    41: "PR", 42: "SC", 43: "RS",
    50: "MS", 51: "MT", 52: "GO", 53: "DF",
}  # fmt: skip

_VALORES_AUSENTES = {"-", "..", "...", "X", "x", ""}


def parse_valor(texto: Any) -> Optional[float]:
    """Converte o campo `V` do SIDRA em float; sigilo/ausência/'não se aplica' viram None."""
    if texto is None:
        return None
    s = str(texto).strip()
    if s in _VALORES_AUSENTES:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _descomprimir(raw: bytes) -> bytes:
    # O servidor às vezes devolve gzip mesmo sem `Accept-Encoding`.
    return gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw


class SidraClient:
    """Consulta `values/t/{tabela}/n{nivel}/{locais}/v/{variaveis}/p/{periodos}/c{classif}/{categorias}`."""

    def __init__(
        self,
        http: Optional[HttpClient] = None,
        cache_dir: Optional[Path] = None,
        use_cache: bool = True,
        ttl_horas: float = CACHE_TTL_HORAS,
    ):
        self.http = http or HttpClient(timeout=90.0, max_retries=4, min_interval=0.3)
        self.cache_dir = Path(cache_dir) if cache_dir is not None else RAW_DATA_DIR / "sidra"
        self.use_cache = use_cache
        self.ttl_horas = ttl_horas

    # ------------------------------------------------------------------ URL / cache
    @staticmethod
    def build_url(
        tabela: int,
        nivel: int = NIVEL_BRASIL,
        locais: str = "all",
        variaveis: str = "all",
        periodos: str = "all",
        classificacoes: Optional[Dict[int, str]] = None,
    ) -> str:
        partes = [f"t/{tabela}", f"n{nivel}/{locais}", f"v/{variaveis}", f"p/{periodos}"]
        for cod, cats in (classificacoes or {}).items():
            partes.append(f"c{cod}/{cats}")
        return f"{SIDRA_VALUES_URL}/" + "/".join(partes) + "?formato=json"

    def _cache_path(self, url: str) -> Path:
        return self.cache_dir / f"{hashlib.sha1(url.encode('utf-8')).hexdigest()[:16]}.json"

    def _ler_cache(self, url: str) -> Optional[List[Dict[str, Any]]]:
        if not self.use_cache:
            return None
        path = self._cache_path(url)
        if not path.exists() or (time.time() - path.stat().st_mtime) > self.ttl_horas * 3600:
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                dados = json.load(fh)
            return dados if isinstance(dados, list) else None
        except (OSError, ValueError):
            return None

    # ------------------------------------------------------------------ consulta
    def values(
        self,
        tabela: int,
        nivel: int = NIVEL_BRASIL,
        locais: str = "all",
        variaveis: str = "all",
        periodos: str = "all",
        classificacoes: Optional[Dict[int, str]] = None,
    ) -> List[Dict[str, Any]]:
        """Devolve as linhas de dados (sem o cabeçalho). Levanta HttpError se a consulta falhar."""
        url = self.build_url(tabela, nivel, locais, variaveis, periodos, classificacoes)
        cached = self._ler_cache(url)
        if cached is not None:
            return cached

        raw = _descomprimir(self.http.get_bytes(url))
        try:
            dados = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HttpError(url, None, f"JSON inválido do SIDRA: {exc}") from exc
        if not isinstance(dados, list) or len(dados) < 1:
            raise HttpError(url, None, "Resposta inesperada do SIDRA")
        linhas = dados[1:]  # a 1ª linha é o cabeçalho
        if self.use_cache:
            atomic_write_json(self._cache_path(url), linhas, indent=None)
        return linhas

    def try_values(self, *args, **kwargs) -> List[Dict[str, Any]]:
        """Como `values`, mas devolve [] em falha (loga). Para fontes opcionais."""
        try:
            return self.values(*args, **kwargs)
        except HttpError as exc:
            logger.warning("SIDRA indisponível: %s", exc)
            return []


# ---------------------------------------------------------------------- helpers de leitura
def serie_por_ano(linhas: Sequence[Dict[str, Any]], campo_ano: str = "D3C") -> Dict[int, Optional[float]]:
    """{ano: valor} a partir de linhas em que `campo_ano` é o código do período anual (AAAA)."""
    saida: Dict[int, Optional[float]] = {}
    for r in linhas:
        try:
            ano = int(str(r[campo_ano])[:4])
        except (KeyError, ValueError):
            continue
        saida[ano] = parse_valor(r.get("V"))
    return saida


def serie_por_uf_ano(
    linhas: Sequence[Dict[str, Any]], campo_uf: str, campo_ano: str
) -> Dict[str, Dict[int, Optional[float]]]:
    """{uf: {ano: valor}}; `campo_uf` traz o código IBGE (11..53) da UF."""
    saida: Dict[str, Dict[int, Optional[float]]] = {}
    for r in linhas:
        try:
            uf = UF_POR_CODIGO_IBGE[int(r[campo_uf])]
            ano = int(str(r[campo_ano])[:4])
        except (KeyError, ValueError):
            continue
        saida.setdefault(uf, {})[ano] = parse_valor(r.get("V"))
    return saida
