"""Manutenção do banco depois de uma carga em massa."""

import logging

from sqlalchemy import text

logger = logging.getLogger("Manutencao")

# Quanto o ETL espera pela vez de atualizar os derivados (a leitura da API não espera: desiste em meio segundo)
ESPERA_DO_ETL = "120s"
ANALYZE_DO_BANCO = "ANALYZE"
ANALYZE_DOS_DERIVADOS = "ANALYZE leg.mv_autoria_pontuada_unica, leg.mv_coautoria_par"


def atualizar_derivados(engine) -> str:
    """
    Refaz as visões materializadas do legislativo se alguma tabela de que dependem mudou (`leg.atualizar_derivados`),
    para o primeiro leitor depois da carga não pagar o refresh. Devolve `'refeito'`, `'em_dia'` (nada mudou), `'ocupado'`
    (não conseguiu a vez em `ESPERA_DO_ETL`; registra AVISO, a leitura refaz por conta própria) ou `'falhou'`.
    """
    try:
        with engine.begin() as conn:
            estado = conn.execute(
                text("SELECT leg.atualizar_derivados(true, :espera)"), {"espera": ESPERA_DO_ETL}
            ).scalar()
    except Exception as exc:  # noqa: BLE001 - a carga já terminou; o leitor refaz se precisar
        logger.warning("Derivados do legislativo não atualizados: %s", exc)
        return "falhou"
    if estado == "ocupado":
        logger.warning(
            "Derivados do legislativo NÃO atualizados: não consegui a vez em %s; o primeiro leitor os refaz",
            ESPERA_DO_ETL,
        )
    else:
        logger.info("Derivados do legislativo: %s.", estado)
    return str(estado)


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


def posprocessar_carga(engine) -> None:
    """
    O que toda carga que grava no banco faz ao terminar: `ANALYZE` das tabelas (o refresh dos derivados é planejado com
    estatística nova), depois os derivados, depois `ANALYZE` das visões refeitas.
    """
    analisar_banco(engine)
    if atualizar_derivados(engine) == "refeito":
        analisar_banco(engine, apenas_derivados=True)
