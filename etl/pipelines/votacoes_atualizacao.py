"""
Atualização das votações nominais (Câmara e Senado) sem refazer a carga completa do banco.

Extrai os anos pedidos, carrega só as votações no staging (mesmos mapas de partidos, deputados e senadores que a carga
completa usa) e funde o resultado em `leg`. Idempotente.
"""

import logging
from datetime import date
from typing import Any, Dict, Optional

from etl.config import PROCESSED_DATA_DIR
from etl.extractors.votacoes_extractor import run_votacoes
from etl.pipelines.carga_cadastro import CargaCadastro
from etl.utils.bootstrap import ensure_backend_on_path
from etl.utils.manutencao import posprocessar_carga

ensure_backend_on_path()

from app.core.database import engine  # noqa: E402

logger = logging.getLogger("VotacoesAtualizacao")


def atualizar(ano_inicio: Optional[int] = None, force: bool = False, sincronizar: bool = True) -> Dict[str, Any]:
    """Extrai de `ano_inicio` (padrão: ano anterior) até hoje, carrega e sincroniza com o schema novo.

    Com `sincronizar=False` só o staging é atualizado: quem chama (a consolidação diária) roda a fusão uma única vez
    depois, em vez de reconstruir `leg.voto` a cada etapa.
    """
    hoje = date.today()
    anos = list(range(ano_inicio or hoje.year - 1, hoje.year + 1))
    extracao = run_votacoes(anos=anos, force=force)
    # Os mapas de partido, deputado e senador saem do próprio staging: partidos e políticos são recarregados antes (idempotente)
    carga = CargaCadastro(data_dir=PROCESSED_DATA_DIR, engine=engine)
    carga.load_all(recursos=["partidos", "politicos", "votacoes_historico"], fundir=sincronizar, migrar=False)
    contadores = {recurso: vars(contagem) for recurso, contagem in carga.contagens.items()}
    ponte = carga.resumo_fusao
    if sincronizar:
        posprocessar_carga(engine)  # sem fusão, quem chamou (o cron diário) roda `posprocessar_carga` depois
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
