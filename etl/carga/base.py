"""Peças comuns da carga direta: tabela temporária, arquivo SQL, rejeitos, data de corte e a execução registrada."""

import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Sequence

from etl.utils.copia import copiar_linhas, transacao_de_carga
from etl.utils.execucao import Contagem, Execucao, registrar_execucao

logger = logging.getLogger("Carga")

SQL_DIR = Path(__file__).parent / "sql"
# motivo de rejeição da linha -> quantas; as tabelas temporárias de cada SQL gravam aqui (`_rej`)
TABELA_DE_REJEITOS = "_rej"


@dataclass
class Resultado:
    """O que um recurso devolve: a contagem, até que data baixou (para o corte) e números extras para o log."""

    contagem: Contagem
    ate: Optional[date] = None
    extras: Dict[str, Any] = field(default_factory=dict)


def texto_sql(nome: str) -> str:
    return (SQL_DIR / f"{nome}.sql").read_text(encoding="utf-8")


def tabela_temporaria(cursor: Any, nome: str, colunas: Mapping[str, str], linhas: Iterable[Sequence[Any]]) -> int:
    """Cria `nome` (vive até o fim da transação) com as colunas `{coluna: tipo}` e copia as linhas. Devolve quantas."""
    definicao = ", ".join('"' + coluna + '" ' + tipo for coluna, tipo in colunas.items())
    cursor.execute(
        f"CREATE TEMP TABLE {nome} ({definicao}) ON COMMIT DROP"
    )  # nosec B608 - nomes constantes dos módulos
    total = copiar_linhas(cursor, nome, list(colunas), linhas)
    cursor.execute(
        f"ANALYZE {nome}"
    )  # tabela nova não tem estatística: sem isso o plano dos joins é às cegas  # nosec B608
    return total


def criar_rejeitos(cursor: Any) -> None:
    cursor.execute(f"CREATE TEMP TABLE IF NOT EXISTS {TABELA_DE_REJEITOS} (motivo text, n int) ON COMMIT DROP")


def executar_sql(cursor: Any, *nomes: str) -> None:
    """Roda os arquivos SQL de `etl/carga/sql` na ordem, na transação do cursor."""
    for nome in nomes:
        cursor.execute(texto_sql(nome))


def ler_rejeitos(cursor: Any) -> Dict[str, int]:
    cursor.execute(
        f"SELECT motivo, sum(n)::int FROM {TABELA_DE_REJEITOS} WHERE n > 0 GROUP BY motivo ORDER BY motivo"
    )  # nosec B608
    return {motivo: int(n) for motivo, n in cursor.fetchall()}


def escalar(cursor: Any, sql: str, *parametros: Any) -> Any:
    cursor.execute(sql, parametros or None)
    return cursor.fetchone()[0]


def contagem_de(lidas: int, rejeitos: Mapping[str, int]) -> Contagem:
    """`lidas` = o que a fonte trouxe; o que não foi rejeitado com motivo foi gravado (ou já estava gravado)."""
    contagem = Contagem(lidas=lidas)
    for motivo, quantas in rejeitos.items():
        contagem.rejeitar(motivo, quantas)
    contagem.gravadas = max(0, lidas - contagem.rejeitadas)
    return contagem


# ---------------------------------------------------------------------------------------------------- corte
def data_de_corte(engine: Any, fonte: str, recurso: str) -> Optional[date]:
    """Até que data o recurso já foi baixado (None: nunca; baixe tudo desde a janela de dados)."""
    conexao = engine.raw_connection()
    try:
        cursor = conexao.cursor()
        cursor.execute("SELECT ultima_data FROM etl.corte WHERE fonte = %s AND recurso = %s", (fonte, recurso))
        linha = cursor.fetchone()
        return linha[0] if linha else None
    finally:
        conexao.close()


def avancar_corte(cursor: Any, fonte: str, recurso: str, ate: Optional[date], execucao_id: int) -> None:
    """Grava o corte na transação da carga: só avança (nunca volta) e só vale se a carga confirmar."""
    if ate is None:
        return
    cursor.execute(
        "INSERT INTO etl.corte (fonte, recurso, ultima_data, ultima_execucao_id) VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (fonte, recurso) DO UPDATE SET "
        "ultima_data = greatest(etl.corte.ultima_data, EXCLUDED.ultima_data), "
        "ultima_execucao_id = EXCLUDED.ultima_execucao_id, atualizado_em = now()",
        (fonte, recurso, ate, execucao_id),
    )


def rodar(
    engine: Any,
    fonte: str,
    recurso: str,
    tarefa: Callable[[Any, Execucao], Resultado],
    parametros: Optional[Dict[str, Any]] = None,
) -> Resultado:
    """
    Uma carga: abre a execução (`etl.execucao`, `CARREGAR`), roda `tarefa(cursor, execucao)` numa transação que começa reservando os
    derivados do legislativo, avança o corte na mesma transação e fecha a execução com a contagem. A transação inteira
    desfaz se a tarefa levantar; a execução fica `ERRO`.
    """
    with registrar_execucao(engine, fonte, "CARREGAR", {"recurso": recurso, **(parametros or {})}) as execucao:
        with transacao_de_carga(engine) as cursor:
            cursor.execute("SELECT leg.reservar_derivados()")  # primeiro comando: evita deadlock entre cargas
            resultado = tarefa(cursor, execucao)
            avancar_corte(cursor, fonte, recurso, resultado.ate, execucao.id)
        execucao.aplicar(resultado.contagem)
        logger.info("%s/%s: %s", fonte, recurso, {**resultado.extras, "contagem": resultado.contagem})
    return resultado
