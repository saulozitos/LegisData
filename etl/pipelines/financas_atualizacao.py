"""
Atualização diária das finanças: extrai a CEAP (Câmara e Senado) e as emendas e recarrega o schema `fin`.

A CEAP de cada ano já fechado (depois de 1º de abril do ano seguinte) vem do cache em `etl/data/raw/ceap_por_ano` e não é
baixada de novo: só o ano corrente (e o anterior até março) vai à rede. As emendas são um único arquivo do Portal da
Transparência, baixado por inteiro. Se alguma extração falha, os arquivos anteriores são preservados e a carga não roda
(o `fin` fica como estava e a próxima execução tenta de novo). A carga é a mesma do deploy e do `run_etl --load-economia`
(`carregar_tudo`), com a proteção contra encolhimento.

Uso: python -m etl.pipelines.financas_atualizacao
"""

import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

from etl.config import RAW_DATA_DIR
from etl.pipelines import sync_ceap_emendas
from etl.pipelines.carga_economica import carregar_tudo
from etl.utils.bootstrap import ensure_backend_on_path

ensure_backend_on_path()

from sqlalchemy.engine import Engine  # noqa: E402

logger = logging.getLogger("FinancasAtualizacao")

ANO_INICIAL = 2019  # a CEAP e as emendas do arquivo começam aqui (mesmo padrão de `run_etl --ceap-ano-inicio`)
CACHE_DIR = RAW_DATA_DIR / sync_ceap_emendas.PASTA_DO_CACHE


def atualizar(engine: Engine, hoje: Optional[date] = None, cache_dir: Optional[Path] = None) -> Dict[str, Any]:
    hoje = hoje or date.today()
    resumo = sync_ceap_emendas.run(
        ano_inicio=ANO_INICIAL, ano_fim=hoje.year, cache_dir=cache_dir or CACHE_DIR, hoje=hoje
    )
    if resumo.get("ceap_gravado") is False or resumo.get("emendas_gravado") is False:
        raise RuntimeError(f"CEAP/emendas não gravadas (arquivos anteriores preservados, `fin` não alterado): {resumo}")
    cargas = carregar_tudo(engine, chaves=("financas",))
    resultado = {"extracao": resumo, "carga": cargas["financas"]}
    logger.info("Finanças atualizadas: %s", resultado)
    return resultado


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    ensure_backend_on_path()
    from app.core.database import engine

    try:
        atualizar(engine)
    except Exception as exc:  # noqa: BLE001 - o serviço do systemd registra o código de saída
        logger.error("Atualização das finanças falhou: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
