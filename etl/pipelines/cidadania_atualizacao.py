"""
Atualização diária do Participe (Votações): coleta as consultas públicas abertas nos portais oficiais e grava a foto do dia
em `leg.consulta_publica`, que é o que a API serve.

Roda todo dia pelo timer do cadastro (`scripts/deploy/atualizar_cadastro.sh`). Se as fontes oficiais estiverem fora do ar a
foto anterior continua valendo e o programa termina com erro, para a falha aparecer no `systemctl` e nos logs em vez de a tela
ficar parada em silêncio.

Uso: python -m etl.pipelines.cidadania_atualizacao
"""

import logging
import sys
from typing import Any, Dict

from etl.utils.bootstrap import ensure_backend_on_path

ensure_backend_on_path()

from app.core.database import SessionLocal  # noqa: E402
from app.services import cidadania_service  # noqa: E402

logger = logging.getLogger("CidadaniaAtualizacao")


def atualizar() -> Dict[str, Any]:
    db = SessionLocal()
    try:
        return cidadania_service.atualizar_consultas(db)
    finally:
        db.close()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    resultado = atualizar()
    if not resultado["atualizado"]:
        logger.error("Nenhuma consulta coletada nas fontes oficiais: a foto anterior foi mantida.")
        return 1
    logger.info(
        "Participe atualizado: %d consultas gravadas, %d abertas para votação.",
        resultado["itens"],
        resultado["abertas"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
