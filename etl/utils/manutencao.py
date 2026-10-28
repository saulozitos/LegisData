"""Manutenção do banco depois de uma carga em massa."""

import logging

from app.services.derivados_service import (
    ESPERA_DO_ETL,
    ESTADO_OCUPADO,
    ESTADO_REFEITO,
    VISOES_MATERIALIZADAS,
    atualizar_para_carga,
)
from sqlalchemy import text

logger = logging.getLogger("Manutencao")

ESTADO_FALHOU = "falhou"
ANALYZE_DO_BANCO = "ANALYZE"
ANALYZE_DOS_DERIVADOS = "ANALYZE " + ", ".join(VISOES_MATERIALIZADAS)


def atualizar_derivados(engine) -> str:
    """
    Refaz as visões materializadas do legislativo se alguma tabela de que dependem mudou (`leg.atualizar_derivados`),
    para o primeiro leitor depois da carga não pagar o refresh. Devolve `'refeito'`, `'em_dia'` (nada mudou), `'ocupado'`
    (não conseguiu a vez em `ESPERA_DO_ETL`; registra AVISO, a leitura refaz por conta própria) ou `'falhou'`.
    """
    try:
        estado = atualizar_para_carga(engine)
    except Exception as exc:  # noqa: BLE001 - a carga já terminou; o leitor refaz se precisar
        logger.warning("Derivados do legislativo não atualizados: %s", exc)
        return ESTADO_FALHOU
    if estado == ESTADO_OCUPADO:
        logger.warning(
            "Derivados do legislativo NÃO atualizados: não consegui a vez em %s; o primeiro leitor os refaz",
            ESPERA_DO_ETL,
        )
    else:
        logger.info("Derivados do legislativo: %s.", estado)
    return estado


def analisar_banco(engine, apenas_derivados: bool = False) -> bool:
    """
    `ANALYZE` no banco inteiro (ou só nas visões dos derivados), para o planejador conhecer as tabelas que a carga acabou de encher
    (sem isso, a primeira consulta pesada depois de uma carga grande escolhe plano com estatística velha: o ranking de
    partidos caiu de 3,5 s para 1,8 s só com o `ANALYZE`). Nunca derruba a carga: devolve False e registra o motivo se não
    conseguir.
    """
    comando = ANALYZE_DOS_DERIVADOS if apenas_derivados else ANALYZE_DO_BANCO
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text(comando))
        logger.info("%s concluído.", comando)
        return True
    except Exception as exc:  # noqa: BLE001 - a carga já terminou; a manutenção é um extra
        logger.warning("ANALYZE não executado: %s", exc)
        return False


def posprocessar_carga(engine) -> str:
    """
    O que toda carga que grava no banco faz ao terminar: `ANALYZE` das tabelas (o refresh dos derivados é planejado com
    estatística nova), depois os derivados, depois `ANALYZE` das visões refeitas. Devolve o estado dos derivados
    (`'refeito'`, `'em_dia'`, `'ocupado'` ou `'falhou'`) para quem chamou registrá-lo; nunca levanta.
    """
    analisar_banco(engine)
    estado = atualizar_derivados(engine)
    if estado == ESTADO_REFEITO:
        analisar_banco(engine, apenas_derivados=True)
    return estado
