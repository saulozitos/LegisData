"""
Extrator de Certidões Judiciais e Ficha Limpa.

Não existe aqui integração com os tribunais: portanto, por padrão, NENHUMA certidão é emitida e o status
de processos é DESCONHECIDO (None). Antes, todo parlamentar recebia "Nada Consta" com número de processo,
data (15/08/2022) e código de autenticidade inventados — o que podia limpar a ficha de quem tem processos.

O modo sintético (`allow_synthetic=True`) serve só para demonstração de interface: os registros saem
claramente marcados, sem número de processo, data ou código de autenticidade.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from etl.config import PROCESSED_DATA_DIR, RAW_DATA_DIR
from etl.utils.provenance import mark_synthetic

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("JusticaExtractor")


class JusticaExtractor:
    """Consolida certidões judiciais (Ficha Limpa / TSE / Tribunais) quando houver fonte verificável."""

    def __init__(self, raw_dir: Path = RAW_DATA_DIR, processed_dir: Path = PROCESSED_DATA_DIR):
        self.raw_dir = raw_dir
        self.processed_dir = processed_dir

    def get_certidoes_for_politician(
        self,
        politician_name: str,
        uf: str = "BR",
        allow_synthetic: bool = False,
    ) -> Tuple[Optional[bool], List[Dict[str, Any]]]:
        """
        Retorna (possui_processos_declarados, certidoes).
        Sem fonte oficial => (None, []): "não sabemos", jamais "Nada Consta".
        """
        if not allow_synthetic:
            return None, []

        uf_clean = uf if uf and uf != "BR" else "DF"
        orgaos = [
            ("STF (Supremo Tribunal Federal)", "Ações Penais Originárias"),
            ("TSE (Tribunal Superior Eleitoral)", "Quitação Eleitoral e Ficha Limpa (LC 135/2010)"),
            (f"TJ-{uf_clean} (Tribunal de Justiça Estadual)", "Distribuição Cível e Falências"),
        ]
        certidoes = [
            mark_synthetic(
                {
                    "orgao": orgao,
                    "tipo_certidao": tipo,
                    "status_ficha": "NÃO VERIFICADO",
                    "detalhes": "Registro sintético de demonstração. Não corresponde a certidão real.",
                    "numero_processo": None,
                    "data_emissao": None,
                    "link_comprovacao": None,
                    "codigo_autenticidade": None,
                }
            )
            for orgao, tipo in orgaos
        ]
        return None, certidoes
