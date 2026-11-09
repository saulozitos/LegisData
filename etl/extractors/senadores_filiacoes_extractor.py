"""
Gera `senadores_filiacoes.json`: as filiações partidárias de cada senador (`/senador/{codigo}/filiacoes`, Dados Abertos do
Senado), com o período de cada partido. É o que diz a que partido o senador pertencia em cada dia do mandato; sem isto só se
sabe o partido que a lista informa (o atual, ou o da última legislatura), que não vale para o mandato inteiro.
Falha da API deixa o senador sem filiações (desconhecido), nunca chute. Quem tem todas as filiações encerradas e já foi baixado
não é pedido de novo; quem tem filiação em curso é atualizado a cada execução.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from etl.config import PROCESSED_DATA_DIR
from etl.extractors.senado_extractor import SenadoExtractor
from etl.extractors.senadores_basicos_extractor import ler_senadores_basicos
from etl.extractors.votacoes_extractor import ARQUIVO_ANTERIORES
from etl.pipelines.loader_helpers import inteiro
from etl.utils.datafiles import load_json, load_senadores
from etl.utils.http_client import HttpClient
from etl.utils.io_utils import atomic_write_json

logger = logging.getLogger("SenadoresFiliacoes")

ARQUIVO = "senadores_filiacoes.json"
FONTE = "Senado (/senador/{codigo}/filiacoes) — Dados Abertos"


def ler_filiacoes(processed_dir: Path = PROCESSED_DATA_DIR) -> List[Dict[str, Any]]:
    dados = load_json(Path(processed_dir) / ARQUIVO, {}) or {}
    return [s for s in dados.get("senadores") or [] if isinstance(s, dict) and s.get("senado_id")]


def _codigos(processed_dir: Path) -> Set[int]:
    """Todo senador que as fontes conhecem: a lista atual, os ex-senadores e quem só consta nos votos e na presença."""
    codigos: Set[int] = set()
    for s in load_senadores(processed_dir):
        codigos.add(inteiro(s.get("senado_id")) or 0)
    anteriores = load_json(Path(processed_dir) / ARQUIVO_ANTERIORES, {}) or {}
    for s in anteriores.get("senadores") or []:
        codigos.add(inteiro(s.get("senado_id")) or 0)
    for s in ler_senadores_basicos(processed_dir):
        codigos.add(inteiro(s.get("senado_id")) or 0)
    codigos.discard(0)
    return codigos


def _encerrada(registro: Optional[Dict[str, Any]]) -> bool:
    filiacoes = (registro or {}).get("filiacoes")
    return bool(filiacoes) and all(f.get("fim") for f in filiacoes)


def gerar(processed_dir: Path = PROCESSED_DATA_DIR, http: Optional[HttpClient] = None) -> Dict[str, Any]:
    processed_dir = Path(processed_dir)
    codigos = _codigos(processed_dir)
    if not codigos:
        logger.warning("Nenhum senador conhecido: nada a baixar.")
        return {"senadores": 0, "baixados": 0, "sem_resposta": 0}
    http = http or HttpClient(timeout=60.0, max_retries=4, min_interval=0.2)
    detalhe = SenadoExtractor(http=http)
    anteriores = {int(s["senado_id"]): s for s in ler_filiacoes(processed_dir)}
    baixados = sem_resposta = 0
    saida: List[Dict[str, Any]] = []
    for codigo in sorted(codigos):
        registro = anteriores.get(codigo)
        if not _encerrada(registro):
            filiacoes = detalhe.filiacoes(codigo)
            baixados += 1
            if filiacoes is None:
                sem_resposta += 1
                if registro is not None:
                    saida.append(registro)  # a API falhou: fica o que já se sabia
                continue
            registro = {"senado_id": codigo, "filiacoes": filiacoes}
        saida.append(registro)  # type: ignore[arg-type]
    atomic_write_json(processed_dir / ARQUIVO, {"fonte": FONTE, "is_synthetic": False, "senadores": saida}, indent=None)
    logger.info("Filiações de %d senadores (%d baixados agora, %d sem resposta).", len(saida), baixados, sem_resposta)
    return {"senadores": len(saida), "baixados": baixados, "sem_resposta": sem_resposta}
