"""
Extrator dos arquivos anuais em lote (CSV) de proposições da Câmara dos Deputados.

Fonte oficial: https://dadosabertos.camara.leg.br/arquivos/ — um arquivo por ano e recurso, atualizado diariamente:
- proposicoes/csv/proposicoes-{ano}.csv: todas as proposições do ano, com a situação da tramitação (`ultimoStatus_*`);
- proposicoesAutores/csv/proposicoesAutores-{ano}.csv: autores/signatários, inclusive órgãos e o Poder Executivo.

Esta etapa só baixa e registra (caminho, tamanho, SHA-256). A leitura e a carga no banco são feitas por
`etl.pipelines.camara_bulk_loader` (staging + merge em SQL).
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, List, Optional

from etl.config import RAW_DATA_DIR
from etl.utils.download import DownloadError, NotFoundError, download_file

logger = logging.getLogger("CamaraBulkExtractor")

BASE_URL = "https://dadosabertos.camara.leg.br/arquivos"
RECURSOS = ("proposicoes", "proposicoesAutores")
# Janela de dados do projeto (decisão D8): a partir de 1995
ANO_INICIAL = 1995


@dataclass(frozen=True)
class ArquivoBaixado:
    recurso: str
    ano: int
    url: str
    caminho: Path
    bytes: int
    sha256: str


def url_do_arquivo(recurso: str, ano: int) -> str:
    return f"{BASE_URL}/{recurso}/csv/{recurso}-{ano}.csv"


def _sha256(caminho: Path) -> str:
    digest = hashlib.sha256()
    with open(caminho, "rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


class CamaraBulkExtractor:
    def __init__(self, raw_dir: Optional[Path] = None, anos: Optional[Iterable[int]] = None):
        self.raw_dir = Path(raw_dir) if raw_dir else RAW_DATA_DIR / "camara_bulk"
        self.anos = list(anos) if anos is not None else list(range(ANO_INICIAL, date.today().year + 1))

    def run(self, force: bool = False) -> List[ArquivoBaixado]:
        baixados: List[ArquivoBaixado] = []
        for ano in self.anos:
            for recurso in RECURSOS:
                url = url_do_arquivo(recurso, ano)
                destino = self.raw_dir / recurso / f"{recurso}-{ano}.csv"
                try:
                    caminho = download_file(url, destino, force=force)
                except NotFoundError:
                    logger.warning("Arquivo inexistente na fonte: %s", url)
                    continue
                except DownloadError as exc:
                    logger.error("Falha ao baixar %s: %s", url, exc)
                    raise
                baixados.append(ArquivoBaixado(recurso, ano, url, caminho, caminho.stat().st_size, _sha256(caminho)))
        logger.info("%d arquivos disponíveis em %s", len(baixados), self.raw_dir)
        return baixados
