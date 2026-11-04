"""
`COPY` para as tabelas de staging: o jeito único de despejar um arquivo (ou linhas já normalizadas) em `stg`.

Texto puro, sem regra de negócio. Linhas normalizadas (`copiar_linhas`): vazio e `None` viram `NULL`, nunca zero nem texto
vazio (o `FORCE_NULL` cobre também a linha de uma coluna só, que o `csv.writer` grava entre aspas). Arquivos de fonte
(`copiar_arquivo`): o conteúdo vai como está, e um campo vazio entre aspas continua texto vazio, porque é isso que a fonte
publica e a regra de negócio fica para a função de fusão.

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
from typing import Any, Iterable, Iterator, List, Sequence

logger = logging.getLogger("Copia")

csv.field_size_limit(sys.maxsize)

# Colunas de controle do ETL que a fonte não traz: ficam fora da conferência do cabeçalho e da lista de colunas do COPY,
# então o COPY as deixa NULL. Quem carrega e precisa delas as preenche depois (o COPY não sabe a execução)
COLUNAS_DE_CONTROLE = ("execucao_id",)

# `tabela` e `delimitador` entram no texto do comando (identificador e literal não aceitam parâmetro ligado): só nomes
# simples em minúsculas, com schema opcional, e um único caractere que não seja aspa, barra invertida ou quebra de linha
_TABELA = re.compile(r"[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)?")
_DELIMITADORES_PROIBIDOS = "'\"\\\r\n"


def _validar_tabela(tabela: str, com_schema: bool = False) -> str:
    if not _TABELA.fullmatch(tabela) or (com_schema and "." not in tabela):
        exigencia = " (informe schema.nome)" if com_schema else ""
        raise ValueError(f"nome de tabela inválido para o COPY{exigencia}: {tabela!r}")
    return tabela


def _validar_delimitador(delimitador: str) -> str:
    if len(delimitador) != 1 or delimitador in _DELIMITADORES_PROIBIDOS:
        raise ValueError(f"delimitador inválido para o COPY: {delimitador!r}")
    return delimitador


def _identificador(nome: str) -> str:
    return '"' + nome.replace('"', '""') + '"'


def _lista(colunas: Sequence[str]) -> str:
    return ", ".join(_identificador(c) for c in colunas)


def colunas_da_tabela(cursor: Any, tabela: str) -> List[str]:
    """As colunas da tabela `esquema.nome` na ordem da tabela, sem as de controle do ETL."""
    esquema, nome = _validar_tabela(tabela, com_schema=True).split(".")
    cursor.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND table_name = %s "
        "ORDER BY ordinal_position",
        (esquema, nome),
    )
    return [linha[0] for linha in cursor.fetchall() if linha[0] not in COLUNAS_DE_CONTROLE]


def cabecalho_do_arquivo(caminho: Path, delimitador: str = ";") -> List[str]:
    """A primeira linha do CSV; arquivo vazio devolve lista vazia (e `copiar_arquivo` o recusa como layout mudado)."""
    with open(caminho, encoding="utf-8-sig", newline="") as arquivo:
        return next(csv.reader(arquivo, delimiter=_validar_delimitador(delimitador)), [])


def contar_linhas_csv(caminho: Path, delimitador: str = ";") -> int:
    """
    Quantas linhas de dados o CSV tem (sem o cabeçalho; um campo com quebra de linha entre aspas conta uma vez). É a medida
    de entrada, independente do `COPY`: um CSV malformado (aspa solta no meio de um campo, que o Python lê como literal e o
    Postgres como abertura de aspas) faz as contagens deixarem de fechar, e a execução sai `COM_ALERTA`.
    """
    with open(caminho, encoding="utf-8-sig", newline="") as arquivo:
        return max(0, sum(1 for _ in csv.reader(arquivo, delimiter=_validar_delimitador(delimitador))) - 1)


def copiar_arquivo(cursor: Any, tabela: str, caminho: Path, delimitador: str = ";") -> None:
    """
    Copia um CSV com cabeçalho para a tabela. O cabeçalho tem de ser igual às colunas da tabela, na mesma ordem: se a
    fonte mudou o layout, a carga para em vez de gravar coluna trocada.
    """
    _validar_delimitador(delimitador)
    esperadas = colunas_da_tabela(cursor, tabela)
    cabecalho = cabecalho_do_arquivo(caminho, delimitador)
    if cabecalho != esperadas:
        raise ValueError(
            f"Cabeçalho inesperado em {caminho.name}: o layout da fonte mudou "
            f"(esperado {len(esperadas)} colunas, veio {len(cabecalho)})."
        )
    comando = (
        f"COPY {tabela} ({_lista(esperadas)}) FROM STDIN "
        f"WITH (FORMAT csv, DELIMITER '{delimitador}', QUOTE '\"', HEADER true, ENCODING 'UTF8')"
    )
    with open(caminho, "rb") as conteudo:
        cursor.copy_expert(comando, conteudo)


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
