"""
Atualização das votações nominais (Câmara e Senado) sem refazer a carga completa do banco.

Extrai os anos pedidos e carrega direto em `core`/`leg`: as pessoas que votaram (pelo identificador oficial), as sessões, os
votos e as orientações. Idempotente; o corte da última carga fica em `etl.corte`.
"""

import logging
from datetime import date
from typing import Any, Dict, Optional

from etl.carga.base import data_de_corte
from etl.carga.orquestra import Carga
from etl.config import PROCESSED_DATA_DIR
from etl.extractors.votacoes_extractor import run_votacoes
from etl.utils.bootstrap import ensure_backend_on_path
from etl.utils.manutencao import posprocessar_carga

ensure_backend_on_path()

from app.core.database import engine  # noqa: E402

logger = logging.getLogger("VotacoesAtualizacao")


def atualizar(ano_inicio: Optional[int] = None, force: bool = False, derivados: bool = False) -> Dict[str, Any]:
    """
    Extrai de `ano_inicio` (padrão: o ano anterior ao do corte; sem corte, o ano anterior ao atual) até hoje e carrega.
    `derivados=True` também refaz os derivados do legislativo (quem chama a consolidação diária faz isso uma vez, no fim).
    """
    hoje = date.today()
    if ano_inicio is None:
        corte = data_de_corte(engine, "CAMARA_API", "votacoes")
        ano_inicio = min(corte.year - 1, hoje.year - 1) if corte else hoje.year - 1
    anos = list(range(ano_inicio, hoje.year + 1))
    extracao = run_votacoes(anos=anos, force=force)
    carga = Carga(data_dir=PROCESSED_DATA_DIR, engine=engine, votacoes_ano_inicio=ano_inicio)
    resultados = carga.carregar(["partidos", "pessoas", "votacoes"])
    if derivados:
        posprocessar_carga(engine)
    resumo: Dict[str, Any] = {
        "anos": anos,
        "extracao": {k: v for k, v in extracao.items() if k != "parlamentares_historicos"},
        "carga": {recurso: vars(r.contagem) for recurso, r in resultados.items()},
    }
    if extracao_falhas := {
        casa: dados["falhas"]
        for casa, dados in extracao.items()
        if casa in ("camara", "senado") and dados.get("falhas")
    }:
        logger.warning("Votações extraídas com falhas (arquivos preservados): %s", extracao_falhas)
    logger.info("Votações atualizadas: %s", resumo)
    return resumo


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    atualizar(derivados=True)
