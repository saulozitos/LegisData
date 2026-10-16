"""
Atualização incremental diária da presença e das faltas (Câmara e Senado).

Reaproveita o cache das extrações: meses fechados do Senado e anos anteriores do portal da Câmara não são baixados de
novo. Baixa os arquivos de eventos do ano corrente e do anterior, extrai o portal de todos os deputados das
legislaturas e regrava as linhas oficiais em `leg.presenca`. A história anterior a 2020 (inferida) não é tocada.
"""

import logging
from datetime import date
from typing import Any, Dict, Optional

from etl.extractors.camara_presenca_eventos_extractor import CamaraPresencaEventosExtractor
from etl.extractors.presenca_extractor import PresencaExtractor
from etl.pipelines.presenca_leg_loader import carregar
from etl.utils.bootstrap import ensure_backend_on_path

ensure_backend_on_path()

from sqlalchemy.engine import Engine  # noqa: E402

logger = logging.getLogger("PresencaAtualizacao")


def atualizar(engine: Engine, hoje: Optional[date] = None) -> Dict[str, Any]:
    ano = (hoje or date.today()).year
    arquivos = CamaraPresencaEventosExtractor(anos=[ano - 1, ano]).run()
    extracao = PresencaExtractor().run(usar_cache=True, ids_camara=None)
    falhas = {casa: len(dados["falhas"]) for casa, dados in extracao.items()}
    if any(falhas.values()):
        # Uma carga com lacunas apagaria dias já gravados: interrompe e deixa o cache para a próxima tentativa.
        raise RuntimeError(f"Extração de presença com falhas {falhas}; carga não executada.")
    resumo = carregar(engine, anos_eventos=[])
    resumo["arquivos_eventos"] = len(arquivos)
    logger.info("Presença atualizada: %s", resumo)
    return resumo
