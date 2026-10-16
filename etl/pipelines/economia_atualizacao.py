"""
Atualização diária das séries econômicas: extrai (BCB, IBGE, INPE, IPEA) com o cache do dia e recarrega `eco`.

Falha de extração interrompe antes de qualquer carga (os extratores levantam erro se uma série essencial vier vazia), então
o banco nunca fica com a série pela metade. As cargas só regravam séries que o arquivo trouxe.
"""

import logging
from typing import Any, Dict

from etl.pipelines.economia_loader import carregar as carregar_series
from etl.pipelines.presidencia_loader import carregar as carregar_presidencia
from etl.pipelines.presidents_economic_sync import PresidentsEconomicSyncPipeline
from etl.utils.bootstrap import ensure_backend_on_path

ensure_backend_on_path()

from sqlalchemy.engine import Engine  # noqa: E402

logger = logging.getLogger("EconomiaAtualizacao")


def atualizar(engine: Engine) -> Dict[str, Any]:
    extracao = PresidentsEconomicSyncPipeline().run(use_cache=True)
    series = carregar_series(engine)
    presidentes = carregar_presidencia(engine)
    resumo = {"anos_resumo": extracao.get("annual_records"), "series": len(series), "presidentes": presidentes}
    logger.info("Séries econômicas atualizadas: %s", resumo)
    return resumo
