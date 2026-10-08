"""
Extrator de Emendas Parlamentares — Portal da Transparência (CGU).

Fonte oficial (arquivo único, todas as emendas desde 2014):
    https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares/UNICO
    (redireciona para dadosabertos-download.cgu.gov.br/.../EmendasParlamentares.zip)

Saída: etl/data/processed/emendas_parlamentares_cgu.json — uma linha por linha do CSV
oficial (a mesma emenda aparece em mais de uma linha quando é dividida por
localidade/função/ação), apenas para emendas INDIVIDUAIS com autor identificado.
Ver etl/parsers/emendas.py para os valores reais de "Tipo de Emenda" e o porquê do filtro.

Uso:
    python -m etl.extractors.emendas_cgu_extractor            # baixa (se mudou) e processa
    python -m etl.extractors.emendas_cgu_extractor --no-cache # força novo download
"""

import argparse
import json
import logging
import sys
import zipfile
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from etl.config import DEFAULT_USER_AGENT, PROCESSED_DATA_DIR, RAW_DATA_DIR
from etl.parsers.emendas import (
    COLUNAS,
    ENCODING_EMENDAS_CSV,
    FONTE_EMENDAS_URL,
    PREFIXO_TIPO_INDIVIDUAL,
    filtrar_linhas,
    validar_cabecalho,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("EmendasCguExtractor")

MEMBRO_CSV = "EmendasParlamentares.csv"
ARQUIVO_SAIDA = "emendas_parlamentares_cgu.json"


class EmendasCguExtractor:
    def __init__(
        self,
        raw_dir: Path = RAW_DATA_DIR,
        processed_dir: Path = PROCESSED_DATA_DIR,
        url: str = FONTE_EMENDAS_URL,
        timeout: int = 120,
        chunksize: int = 20_000,
    ):
        self.raw_dir = raw_dir
        self.processed_dir = processed_dir
        self.url = url
        self.timeout = timeout
        self.chunksize = chunksize
        self.zip_path = raw_dir / "EmendasParlamentares.zip"
        self.meta_path = raw_dir / "EmendasParlamentares.zip.meta.json"
        self.headers = {"User-Agent": DEFAULT_USER_AGENT}

    # ------------------------------------------------------------------ download
    def _metadados_remotos(self) -> dict:
        resp = requests.head(self.url, headers=self.headers, timeout=self.timeout, allow_redirects=True)
        resp.raise_for_status()
        return {
            "url_final": resp.url,
            "content_length": resp.headers.get("Content-Length"),
            "last_modified": resp.headers.get("Last-Modified"),
        }

    def _cache_valido(self, remoto: dict) -> bool:
        if not self.zip_path.exists() or not self.meta_path.exists():
            return False
        try:
            local = json.loads(self.meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if not remoto.get("content_length") and not remoto.get("last_modified"):
            return False
        return (
            local.get("content_length") == remoto.get("content_length")
            and local.get("last_modified") == remoto.get("last_modified")
            and str(self.zip_path.stat().st_size) == str(remoto.get("content_length"))
        )

    def baixar(self, use_cache: bool = True) -> Path:
        remoto = self._metadados_remotos()
        if use_cache and self._cache_valido(remoto):
            logger.info(f"Cache válido de {self.zip_path.name} (Last-Modified {remoto['last_modified']}).")
            return self.zip_path

        logger.info(f"Baixando {remoto['url_final']} ({remoto.get('content_length')} bytes)...")
        tmp = self.zip_path.with_suffix(".zip.part")
        with requests.get(self.url, headers=self.headers, timeout=self.timeout, stream=True) as resp:
            resp.raise_for_status()
            with open(tmp, "wb") as f:
                for bloco in resp.iter_content(chunk_size=1 << 20):
                    if bloco:
                        f.write(bloco)
        esperado = remoto.get("content_length")
        if esperado and tmp.stat().st_size != int(esperado):
            tmp.unlink(missing_ok=True)
            raise IOError(f"Download incompleto: {tmp.stat().st_size} de {esperado} bytes")
        if not zipfile.is_zipfile(tmp):
            tmp.unlink(missing_ok=True)
            raise IOError("Arquivo baixado não é um ZIP válido")
        tmp.replace(self.zip_path)
        self.meta_path.write_text(json.dumps(remoto, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.zip_path

    # ------------------------------------------------------------------ parsing
    def processar(self, zip_path: Optional[Path] = None) -> Path:
        zip_path = zip_path or self.zip_path
        registros = []
        lidas = 0
        individuais = 0
        with zipfile.ZipFile(zip_path) as z:
            with z.open(MEMBRO_CSV) as f:
                leitor = pd.read_csv(
                    f,
                    sep=";",
                    encoding=ENCODING_EMENDAS_CSV,
                    dtype=str,
                    keep_default_na=False,
                    usecols=list(COLUNAS.keys()),
                    chunksize=self.chunksize,
                )
                for i, chunk in enumerate(leitor):
                    if i == 0:
                        faltando = validar_cabecalho(list(chunk.columns))
                        if faltando:
                            raise ValueError(f"Cabeçalho inesperado; colunas ausentes: {faltando}")
                    lidas += len(chunk)
                    chunk = chunk[chunk["Tipo de Emenda"].str.startswith(PREFIXO_TIPO_INDIVIDUAL)]
                    individuais += len(chunk)
                    registros.extend(filtrar_linhas(chunk.to_dict("records"), self.url))

        saida = self.processed_dir / ARQUIVO_SAIDA
        with open(saida, "w", encoding="utf-8") as f:
            json.dump(registros, f, ensure_ascii=False)
        autores = {(r["codigo_autor_siafi"], r["nome_autor"]) for r in registros}
        logger.info(
            f"{lidas:,} linhas lidas; {individuais:,} individuais; {len(registros):,} com autor identificado "
            f"({len(autores):,} pares código/nome de autor). Gravado em {saida}."
        )
        return saida

    def run(self, use_cache: bool = True) -> Path:
        return self.processar(self.baixar(use_cache=use_cache))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-cache", action="store_true", help="Força novo download do ZIP")
    args = parser.parse_args()
    EmendasCguExtractor().run(use_cache=not args.no_cache)


if __name__ == "__main__":
    main()
