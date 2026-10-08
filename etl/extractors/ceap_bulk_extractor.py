"""
Extrator em lote da Cota Parlamentar (CEAP Câmara + CEAPS Senado) a partir dos
arquivos/APIs oficiais anuais — substitui a consulta por deputado (limitada a 35).

Fontes:
  Câmara: https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip  (todas as notas do ano)
  Senado: https://adm.senado.gov.br/adm-dadosabertos/api/v1/senadores/despesas_ceaps/{ano}

Os arquivos brutos ficam em etl/data/raw/ (cache por Content-Length/Last-Modified
para a Câmara; o JSON do Senado é regravado a cada execução, pois é pequeno e a API
não expõe Last-Modified). A leitura do CSV é feita em streaming com o módulo csv.
"""

import csv
import io
import json
import logging
import time
import zipfile
from pathlib import Path
from typing import Dict, Iterator, Optional

import requests

from etl.config import DEFAULT_USER_AGENT, RAW_DATA_DIR
from etl.parsers.ceap import (
    URL_CAMARA_CEAP_ANO,
    URL_SENADO_CEAPS_ANO,
    normalizar_item_senado,
    normalizar_linha_camara,
)

logger = logging.getLogger("CeapBulkExtractor")


class CeapBulkExtractor:
    def __init__(self, raw_dir: Path = RAW_DATA_DIR, timeout: int = 180, tentativas: int = 4):
        self.raw_dir = raw_dir
        self.timeout = timeout
        self.tentativas = tentativas
        self.headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json, application/zip, */*"}

    # ------------------------------------------------------------ HTTP helpers
    def _get(self, url: str, **kw) -> requests.Response:
        """GET com nova tentativa em 429/5xx, respeitando Retry-After."""
        ultimo_erro: Optional[Exception] = None
        for t in range(1, self.tentativas + 1):
            try:
                resp = requests.get(url, headers=self.headers, timeout=self.timeout, **kw)
                if resp.status_code == 429 or resp.status_code >= 500:
                    espera = int(resp.headers.get("Retry-After", "0") or 0) or 10 * t
                    logger.warning(f"{url}: HTTP {resp.status_code}; nova tentativa em {espera}s")
                    resp.close()
                    time.sleep(min(espera, 120))
                    continue
                resp.raise_for_status()
                return resp
            except requests.RequestException as e:
                ultimo_erro = e
                time.sleep(5 * t)
        raise IOError(f"Falha ao obter {url}: {ultimo_erro or 'limite de tentativas'}")

    # ------------------------------------------------------------ Câmara
    def baixar_camara(self, ano: int, use_cache: bool = True) -> Path:
        url = URL_CAMARA_CEAP_ANO.format(ano=ano)
        destino = self.raw_dir / f"ceap_camara_Ano-{ano}.csv.zip"
        meta = destino.with_suffix(".zip.meta.json")
        head = requests.head(url, headers=self.headers, timeout=60, allow_redirects=True)
        remoto = {"content_length": head.headers.get("Content-Length"), "last_modified": head.headers.get("Last-Modified")}
        if use_cache and destino.exists() and meta.exists() and (remoto["content_length"] or remoto["last_modified"]):
            try:
                local = json.loads(meta.read_text(encoding="utf-8"))
            except ValueError:
                local = {}
            if local == remoto and str(destino.stat().st_size) == str(remoto["content_length"]):
                logger.info(f"[Câmara {ano}] cache válido ({destino.name}).")
                return destino

        tmp = destino.with_suffix(".zip.part")
        with self._get(url, stream=True) as resp, open(tmp, "wb") as f:
            for bloco in resp.iter_content(chunk_size=1 << 20):
                if bloco:
                    f.write(bloco)
        if remoto["content_length"] and tmp.stat().st_size != int(remoto["content_length"]):
            tmp.unlink(missing_ok=True)
            raise IOError(f"[Câmara {ano}] download incompleto")
        if not zipfile.is_zipfile(tmp):
            tmp.unlink(missing_ok=True)
            raise IOError(f"[Câmara {ano}] arquivo baixado não é ZIP")
        tmp.replace(destino)
        meta.write_text(json.dumps(remoto), encoding="utf-8")
        logger.info(f"[Câmara {ano}] baixado {destino.stat().st_size:,} bytes.")
        return destino

    def iter_camara(self, ano: int, use_cache: bool = True, stats: Optional[Dict[str, int]] = None) -> Iterator[dict]:
        """Itera despesas de deputados (linhas de liderança, sem ideCadastro, são ignoradas)."""
        stats = stats if stats is not None else {}
        zip_path = self.baixar_camara(ano, use_cache)
        fonte = URL_CAMARA_CEAP_ANO.format(ano=ano)
        with zipfile.ZipFile(zip_path) as z:
            nome = next(n for n in z.namelist() if n.lower().endswith(".csv"))
            with z.open(nome) as f:
                leitor = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig", newline=""), delimiter=";")
                for linha in leitor:
                    stats["linhas"] = stats.get("linhas", 0) + 1
                    reg = normalizar_linha_camara(linha, fonte)
                    if reg is None:
                        stats["sem_deputado"] = stats.get("sem_deputado", 0) + 1
                        continue
                    yield reg

    # ------------------------------------------------------------ Senado
    def iter_senado(self, ano: int, stats: Optional[Dict[str, int]] = None) -> Iterator[dict]:
        stats = stats if stats is not None else {}
        url = URL_SENADO_CEAPS_ANO.format(ano=ano)
        resp = self._get(url)
        dados = resp.json()
        if not isinstance(dados, list):
            raise ValueError(f"[Senado {ano}] resposta inesperada: {type(dados).__name__}")
        (self.raw_dir / f"ceaps_senado_{ano}.json").write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
        for item in dados:
            stats["linhas"] = stats.get("linhas", 0) + 1
            reg = normalizar_item_senado(item, url)
            if reg is None:
                stats["invalidas"] = stats.get("invalidas", 0) + 1
                continue
            yield reg
