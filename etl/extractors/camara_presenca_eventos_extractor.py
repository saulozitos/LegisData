"""
Extrator dos arquivos anuais de eventos e de presença em eventos da Câmara dos Deputados (1995 em diante).

Fonte oficial: https://dadosabertos.camara.leg.br/arquivos/
- eventos/csv/eventos-{ano}.csv: sessões e reuniões (tipo, local, data);
- eventosPresencaDeputados/csv/eventosPresencaDeputados-{ano}.csv: deputados registrados como presentes em cada evento.

O portal da Câmara só publica presença, falta e justificativa por dia a partir de 2020. Antes disso estes arquivos
são a única fonte oficial: trazem a presença, mas não a ausência. A leitura e a carga ficam em
`etl.pipelines.presenca_leg_loader`.
"""

import logging
from datetime import date
from pathlib import Path
from typing import Iterable, List, Optional

from etl.config import RAW_DATA_DIR
from etl.utils.download import DownloadError, NotFoundError, download_file

logger = logging.getLogger("CamaraPresencaEventosExtractor")

BASE_URL = "https://dadosabertos.camara.leg.br/arquivos"
RECURSOS = ("eventos", "eventosPresencaDeputados")
ANO_INICIAL = 1995


def url_do_arquivo(recurso: str, ano: int) -> str:
    return f"{BASE_URL}/{recurso}/csv/{recurso}-{ano}.csv"


def caminho_do_arquivo(raw_dir: Path, recurso: str, ano: int) -> Path:
    return raw_dir / recurso / f"{recurso}-{ano}.csv"


class CamaraPresencaEventosExtractor:
    def __init__(self, raw_dir: Optional[Path] = None, anos: Optional[Iterable[int]] = None):
        self.raw_dir = Path(raw_dir) if raw_dir else RAW_DATA_DIR / "camara_presenca_eventos"
        self.anos = list(anos) if anos is not None else list(range(ANO_INICIAL, date.today().year + 1))

    def run(self, force: bool = False) -> List[Path]:
        """Baixa os arquivos do ano corrente sempre (mudam todo dia) e os anos fechados só se ainda não existirem."""
        baixados: List[Path] = []
        for ano in self.anos:
            for recurso in RECURSOS:
                destino = caminho_do_arquivo(self.raw_dir, recurso, ano)
                atualizar = force or ano >= date.today().year - 1
                try:
                    baixados.append(download_file(url_do_arquivo(recurso, ano), destino, force=atualizar))
                except NotFoundError:
                    logger.warning("Arquivo inexistente na fonte: %s", url_do_arquivo(recurso, ano))
                except DownloadError as exc:
                    logger.error("Falha ao baixar %s: %s", url_do_arquivo(recurso, ano), exc)
                    raise
        logger.info("%d arquivos disponíveis em %s", len(baixados), self.raw_dir)
        return baixados
