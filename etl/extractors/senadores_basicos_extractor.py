"""
Gera `senadores_dados_basicos.json`: nome completo, nascimento, sexo e naturalidade (detalhe `/senador/{codigo}` do Senado)
de todo senador que aparece nas fontes sem esses dados: quem só consta nos votos e na presença, e os ex-senadores da lista
por legislatura sem nascimento. É o que prova que o ex-senador é a mesma pessoa de um cadastro de outra fonte.
Falha da API deixa o campo nulo (desconhecido), nunca chute; o que já foi baixado não é pedido de novo.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from etl.config import PROCESSED_DATA_DIR
from etl.extractors.presenca_extractor import ARQ_RESUMO
from etl.extractors.senado_extractor import SenadoExtractor
from etl.extractors.votacoes_extractor import ARQUIVO_ANTERIORES, ler_json_gz, listar_arquivos_processados
from etl.pipelines.loader_helpers import inteiro
from etl.utils.datafiles import load_json
from etl.utils.http_client import HttpClient
from etl.utils.io_utils import atomic_write_json

logger = logging.getLogger("SenadoresBasicos")

ARQUIVO = "senadores_dados_basicos.json"
FONTE = "Senado (/senador/{codigo}) — Dados Abertos"


def ler_senadores_basicos(processed_dir: Path = PROCESSED_DATA_DIR) -> List[Dict[str, Any]]:
    dados = load_json(Path(processed_dir) / ARQUIVO, {}) or {}
    return [s for s in dados.get("senadores") or [] if isinstance(s, dict) and s.get("senado_id")]


def _senadores_das_fontes(processed_dir: Path) -> Dict[int, str]:
    """codigo -> nome de quem aparece nos votos, na presença e na lista por legislatura sem nascimento."""
    nomes: Dict[int, str] = {}

    def anotar(codigo: Any, nome: Any) -> None:
        numero = inteiro(codigo)
        if numero is not None:  # registro sem código não tem como ser pedido ao Senado
            nomes.setdefault(numero, str(nome or ""))

    for arquivo in listar_arquivos_processados(processed_dir, "senado"):
        for codigo, info in (ler_json_gz(arquivo).get("parlamentares") or {}).items():
            anotar(codigo, (info or {}).get("nome"))
    resumo = load_json(Path(processed_dir) / ARQ_RESUMO, {}) or {}
    for r in resumo.get("resumos", []):
        if r.get("casa") == "SENADO":
            anotar(r.get("parlamentar_id"), r.get("nome"))
    anteriores = load_json(Path(processed_dir) / ARQUIVO_ANTERIORES, {}) or {}
    for s in anteriores.get("senadores") or []:
        if not s.get("data_nascimento"):
            anotar(s.get("senado_id"), s.get("nome_eleitoral"))
    return nomes


def gerar(processed_dir: Path = PROCESSED_DATA_DIR, http: Optional[HttpClient] = None) -> Dict[str, Any]:
    processed_dir = Path(processed_dir)
    nomes = _senadores_das_fontes(processed_dir)
    if not nomes:
        logger.warning("Nenhum senador sem dados básicos nas fontes: nada a baixar.")
        return {"senadores": 0, "baixados": 0}
    http = http or HttpClient(timeout=60.0, max_retries=4, min_interval=0.2)
    detalhe = SenadoExtractor(http=http)
    ja_baixados = {int(s["senado_id"]): s for s in ler_senadores_basicos(processed_dir)}
    baixados = 0
    saida: List[Dict[str, Any]] = []
    for codigo, nome in sorted(nomes.items()):
        registro = ja_baixados.get(codigo)
        if registro is None or not registro.get("nome_civil"):
            registro = {
                "senado_id": codigo,
                "nome": nome,
                **{k: v for k, v in detalhe.dados_basicos(codigo).items() if v},
            }
            baixados += 1
        saida.append(registro)
    atomic_write_json(processed_dir / ARQUIVO, {"fonte": FONTE, "is_synthetic": False, "senadores": saida}, indent=None)
    logger.info("Senadores com dados básicos: %d (%d baixados agora).", len(saida), baixados)
    return {"senadores": len(saida), "baixados": baixados}
