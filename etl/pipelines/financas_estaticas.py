"""
Carga das finanças que NÃO são atualizadas todo dia: remuneração, patrimônio, doações e certidões do TSE.

O deploy usa esta carga quando o `fin` já tem dados (CEAP e emendas vêm do timer diário e não podem voltar ao retrato
versionado no git, que é mais antigo e faria as emendas novas serem apagadas e voltarem com outro `uid`).
"""

from typing import Any, Dict

from etl.pipelines import financas_loader
from etl.utils.bootstrap import ensure_backend_on_path

ensure_backend_on_path()

from sqlalchemy.engine import Engine  # noqa: E402


def carregar(engine: Engine) -> Dict[str, Any]:
    return financas_loader.carregar(engine, chaves=financas_loader.CHAVES_ESTATICAS)
