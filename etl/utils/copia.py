"""
`COPY` de linhas já normalizadas para tabelas TEMPORÁRIAS da transação de carga (`etl.carga`), mais a conferência de CSV.

Texto puro, sem regra de negócio. Linhas normalizadas (`copiar_linhas`): vazio e `None` viram `NULL`, nunca zero nem texto
vazio (o `FORCE_NULL` cobre também a linha de uma coluna só, que o `csv.writer` grava entre aspas).

O nome da tabela e o delimitador entram no texto do comando por f-string (não aceitam parâmetro ligado) e passam por
allowlist antes. O bandit do CI só varre `backend/app`: se um dia varrer `etl/`, essas linhas precisam de `# nosec B608`.
"""

import csv
import io
import logging
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

logger = logging.getLogger("Copia")

csv.field_size_limit(sys.maxsize)

# `tabela` e `delimitador` entram no texto do comando (identificador e literal não aceitam parâmetro ligado): só nomes
# simples em minúsculas, com schema opcional, e um único caractere que não seja aspa, barra invertida ou quebra de linha
_TABELA = re.compile(r"[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)?")
_DELIMITADORES_PROIBIDOS = "'\"\\\r\n"


def _validar_tabela(tabela: str) -> str:
    if not _TABELA.fullmatch(tabela):
        raise ValueError(f"nome de tabela inválido para o COPY: {tabela!r}")
    return tabela


def _validar_delimitador(delimitador: str) -> str:
    if len(delimitador) != 1 or delimitador in _DELIMITADORES_PROIBIDOS:
        raise ValueError(f"delimitador inválido para o COPY: {delimitador!r}")
    return delimitador


def _identificador(nome: str) -> str:
    return '"' + nome.replace('"', '""') + '"'


def _lista(colunas: Sequence[str]) -> str:
    return ", ".join(_identificador(c) for c in colunas)


def contar_linhas_csv(caminho: Path, delimitador: str = ";") -> int:
    """
    Quantas linhas de dados o CSV tem (sem o cabeçalho; um campo com quebra de linha entre aspas conta uma vez). É a medida
    de entrada, independente do `COPY`: um CSV malformado (aspa solta no meio de um campo, que o Python lê como literal e o
    Postgres como abertura de aspas) faz as contagens deixarem de fechar, e a execução sai `COM_ALERTA`.
    """
    with open(caminho, encoding="utf-8-sig", newline="") as arquivo:
        return max(0, sum(1 for _ in csv.reader(arquivo, delimiter=_validar_delimitador(delimitador))) - 1)


def copiar_linhas(cursor: Any, tabela: str, colunas: Sequence[str], linhas: Iterable[Sequence[Any]]) -> int:
    """Copia linhas já normalizadas (sequências na ordem de `colunas`); `None` vira `NULL`. Devolve quantas copiou."""
    saida = io.StringIO()
    escritor = csv.writer(saida)
    total = 0
    for linha in linhas:
        escritor.writerow(["" if valor is None else valor for valor in linha])
        total += 1
    saida.seek(0)
    lista = _lista(colunas)
    comando = (
        f"COPY {_validar_tabela(tabela)} ({lista}) FROM STDIN WITH (FORMAT csv, HEADER false, FORCE_NULL ({lista}))"
    )
    cursor.copy_expert(comando, saida)
    return total


def esvaziar(cursor: Any, tabelas: Sequence[str]) -> None:
    """`TRUNCATE` de uma ou mais tabelas de staging num só comando, com os nomes validados como no `COPY`."""
    if not tabelas:
        raise ValueError("esvaziar precisa de ao menos uma tabela")
    cursor.execute("TRUNCATE " + ", ".join(_validar_tabela(tabela) for tabela in tabelas))


def contar(cursor: Any, tabela: str) -> int:
    cursor.execute(f"SELECT count(*) FROM {_validar_tabela(tabela)}")
    return int(cursor.fetchone()[0])


@contextmanager
def transacao_de_carga(engine: Any) -> Iterator[Any]:
    """
    Uma transação de carga sobre uma conexão DB-API (a que o `COPY` exige): entrega o cursor, confirma ao sair e desfaz
    se a carga levantar. A conexão volta ao pool de qualquer jeito.
    """
    conexao = engine.raw_connection()
    try:
        yield conexao.cursor()
        conexao.commit()
    except BaseException:
        conexao.rollback()
        raise
    finally:
        conexao.close()
