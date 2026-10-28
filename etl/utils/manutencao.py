"""Manutenção do banco depois de uma carga em massa."""

import logging

from sqlalchemy import text

logger = logging.getLogger("Manutencao")


def atualizar_derivados(engine) -> bool:
    """
    Refaz as visões materializadas do legislativo se alguma tabela de que dependem mudou (`leg.atualizar_derivados()`),
    para o primeiro leitor depois da carga não pagar o refresh. Devolve False, sem erro, se nada precisava, se não deu
    para esperar uma trava ou se o banco falhou: a leitura ainda garante a atualização por conta própria.
    """
    try:
        with engine.begin() as conn:
            refeito = bool(conn.execute(text("SELECT leg.atualizar_derivados()")).scalar())
        logger.info("Derivados do legislativo %s.", "refeitos" if refeito else "sem mudança (ou carga em andamento)")
        return refeito
    except Exception as exc:  # noqa: BLE001 - a carga já terminou; o leitor refaz se precisar
        logger.warning("Derivados do legislativo não atualizados: %s", exc)
        return False


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


def posprocessar_carga(engine) -> None:
    """O que toda carga que grava no banco faz ao terminar: derivados primeiro, depois `ANALYZE` (que já os enxerga)."""
    atualizar_derivados(engine)
    analisar_banco(engine)
