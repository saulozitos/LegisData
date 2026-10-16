"""
Atualização diária das séries econômicas: extrai (BCB, IBGE, INPE, IPEA) com o cache do dia e recarrega `eco`.

Falha de extração interrompe antes de qualquer carga (os extratores levantam erro se uma série essencial vier vazia), então
o banco nunca fica com a série pela metade. As cargas só regravam séries que o arquivo trouxe.
"""

import logging
from typing import Any, Dict

from etl.pipelines.carga_economica import carregar_tudo
from etl.pipelines.presidents_economic_sync import PresidentsEconomicSyncPipeline
from etl.utils.bootstrap import ensure_backend_on_path

ensure_backend_on_path()

from sqlalchemy.engine import Engine  # noqa: E402

logger = logging.getLogger("EconomiaAtualizacao")


def atualizar(engine: Engine) -> Dict[str, Any]:
    extracao = PresidentsEconomicSyncPipeline().run(use_cache=True)
    # Só séries e mandatos: a composição e a PNAD são curadoria/microdados estáticos, carregados pelo deploy e pelo ETL
    cargas = carregar_tudo(engine, chaves=("series", "presidencia"))
    resumo = {
        "anos_resumo": extracao.get("annual_records"),
        "series": len(cargas["series"]),
        "presidentes": cargas["presidencia"],
    }
    logger.info("Séries econômicas atualizadas: %s", resumo)
    return resumo
