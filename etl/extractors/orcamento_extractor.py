#!/usr/bin/env python3
"""
Repasses federais por Estado (UF).

Antes este módulo era um MODELO ESTATÍSTICO (população × peso FPE × fator de escala inventado) apresentado como
execução orçamentária. Agora é um invólucro fino sobre `TransferenciasExtractor`, que soma as transferências
OFICIAIS do Portal da Transparência (CGU) por UF, função e mandato. Não há mais dado sintético aqui.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from etl.config import PROCESSED_DATA_DIR
from etl.extractors.transferencias_extractor import TransferenciasExtractor

logger = logging.getLogger("OrcamentoExtractor")


class OrcamentoExtractor:
    """Extrai os repasses federais por UF (fonte oficial)."""

    def __init__(self, output_dir: Path = PROCESSED_DATA_DIR, extractor: Optional[TransferenciasExtractor] = None):
        self.output_dir = Path(output_dir)
        self._extractor = extractor

    def run(self, allow_synthetic: bool = False, use_cache: bool = True) -> Dict[str, Any]:
        """`allow_synthetic` é aceito só por compatibilidade: nada sintético é gerado."""
        extractor = self._extractor or TransferenciasExtractor(output_dir=self.output_dir)
        return extractor.run(use_cache=use_cache)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print(OrcamentoExtractor().run())
