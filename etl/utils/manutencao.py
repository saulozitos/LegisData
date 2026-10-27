"""Manutenção do banco depois de uma carga em massa."""

import logging

from sqlalchemy import text

logger = logging.getLogger("Manutencao")


def analisar_banco(engine) -> bool:
    """
    `ANALYZE` no banco inteiro, para o planejador conhecer as tabelas que a carga acabou de encher (sem isso, a primeira
    consulta pesada depois de uma carga grande escolhe plano com estatística velha: o ranking de partidos caiu de 3,5 s
    para 1,8 s só com o `ANALYZE`). Nunca derruba a carga: devolve False e registra o motivo se não conseguir.
    """
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("ANALYZE"))
        logger.info("ANALYZE concluído.")
        return True
    except Exception as exc:  # noqa: BLE001 - a carga já terminou; a manutenção é um extra
        logger.warning("ANALYZE não executado: %s", exc)
        return False
