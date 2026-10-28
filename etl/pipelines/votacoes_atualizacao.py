"""
Atualização das votações nominais (Câmara e Senado) sem refazer a carga completa do banco.

Extrai os anos pedidos, carrega só as votações no schema legado (mesmos mapas de partidos, deputados e senadores que a
carga completa monta) e sincroniza o resultado para `leg` pela ponte. Idempotente.
"""

import logging
from datetime import date
from typing import Any, Dict, Optional

from etl.config import PROCESSED_DATA_DIR
from etl.extractors.votacoes_extractor import run_votacoes
from etl.pipelines.db_loader import DatabaseLoader
from etl.pipelines.votacoes_loader import carregar_votacoes
from etl.utils.bootstrap import ensure_backend_on_path
from etl.utils.manutencao import posprocessar_carga

ensure_backend_on_path()

from app.core.database import SessionLocal, engine  # noqa: E402
from app.services.staging_merge import merge_staging  # noqa: E402

logger = logging.getLogger("VotacoesAtualizacao")


def atualizar(ano_inicio: Optional[int] = None, force: bool = False, sincronizar: bool = True) -> Dict[str, Any]:
    """Extrai de `ano_inicio` (padrão: ano anterior) até hoje, carrega e sincroniza com o schema novo.

    Com `sincronizar=False` só o legado é atualizado: quem chama (a consolidação diária) roda a ponte uma única vez
    depois, em vez de reconstruir `leg.voto` a cada etapa.
    """
    hoje = date.today()
    anos = list(range(ano_inicio or hoje.year - 1, hoje.year + 1))
    extracao = run_votacoes(anos=anos, force=force)
    carregador = DatabaseLoader(data_dir=PROCESSED_DATA_DIR)
    with SessionLocal() as sessao:
        sessao.autoflush = True
        mapa_partidos = carregador._load_political_parties(sessao)
        _, mapa_deputados, mapa_senadores = carregador._load_politicians(sessao)
        contadores = carregar_votacoes(
            sessao, PROCESSED_DATA_DIR, mapa_deputados, mapa_senadores, mapa_partidos, carregador._ensure_party
        )
        sessao.commit()
        ponte = merge_staging(sessao) if sincronizar else None
    if sincronizar:
        posprocessar_carga(engine)  # derivados e ANALYZE; sem fusão, quem chamou os roda depois
    resumo = {"anos": anos, "extracao": {k: v for k, v in extracao.items() if k != "parlamentares_historicos"}}
    resumo["carga"] = contadores
    resumo["ponte"] = ponte
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
    atualizar()
