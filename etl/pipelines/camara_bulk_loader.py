"""
Carga dos CSV anuais da Câmara (proposições e autores) no PostgreSQL, em dois passos:

1. staging: `COPY` dos arquivos para `stg.camara_proposicao` e `stg.camara_autor` (texto puro, sem regra de negócio);
2. merge em SQL: `etl.merge_camara_bulk()` grava proposição, autoria, pessoas, partidos e entidades, e registra
   rejeitos e verificações (cobertura por tipo) no próprio banco.

Reexecutar é seguro: o staging é refeito e o merge é idempotente.
"""

import csv
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

from etl.extractors.camara_bulk_extractor import ArquivoBaixado
from etl.utils.bootstrap import ensure_backend_on_path

ensure_backend_on_path()

from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402

logger = logging.getLogger("CamaraBulkLoader")

TABELAS = {"proposicoes": "stg.camara_proposicao", "proposicoesAutores": "stg.camara_autor"}
COPY_SQL = "COPY {tabela} FROM STDIN WITH (FORMAT csv, DELIMITER ';', QUOTE '\"', HEADER true, ENCODING 'UTF8')"

csv.field_size_limit(sys.maxsize)


def _cabecalho(caminho: Path) -> List[str]:
    with open(caminho, encoding="utf-8-sig", newline="") as arquivo:
        return next(csv.reader(arquivo, delimiter=";"))


def _colunas_da_tabela(conexao: Any, tabela: str) -> List[str]:
    esquema, nome = tabela.split(".")
    cursor = conexao.cursor()
    cursor.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND table_name = %s "
        "ORDER BY ordinal_position",
        (esquema, nome),
    )
    return [linha[0] for linha in cursor.fetchall()]


def carregar_staging(engine: Engine, arquivos: Iterable[ArquivoBaixado]) -> Dict[str, int]:
    """Recarrega o staging com os arquivos informados e registra cada um em etl.arquivo_bruto."""
    arquivos = list(arquivos)
    conexao = engine.raw_connection()
    contagem = {tabela: 0 for tabela in TABELAS.values()}
    try:
        cursor = conexao.cursor()
        cursor.execute("TRUNCATE " + ", ".join(TABELAS.values()))
        esperadas = {recurso: _colunas_da_tabela(conexao, tabela) for recurso, tabela in TABELAS.items()}
        for arquivo in sorted(arquivos, key=lambda a: (a.recurso, a.ano)):
            tabela = TABELAS[arquivo.recurso]
            cabecalho = _cabecalho(arquivo.caminho)
            if cabecalho != esperadas[arquivo.recurso]:
                raise ValueError(
                    f"Cabeçalho inesperado em {arquivo.caminho.name}: o layout da fonte mudou "
                    f"(esperado {len(esperadas[arquivo.recurso])} colunas, veio {len(cabecalho)})."
                )
            with open(arquivo.caminho, "rb") as conteudo:
                cursor.copy_expert(COPY_SQL.format(tabela=tabela), conteudo)
            cursor.execute(
                "INSERT INTO etl.arquivo_bruto (fonte_id, url, sha256, bytes, http_status, caminho) "
                "SELECT id, %s, %s, %s, 200, %s FROM etl.fonte WHERE codigo = 'CAMARA_CSV' "
                "ON CONFLICT (fonte_id, sha256) DO NOTHING",
                (arquivo.url, arquivo.sha256, arquivo.bytes, str(arquivo.caminho)),
            )
            logger.info("Staging: %s (%d bytes) -> %s", arquivo.caminho.name, arquivo.bytes, tabela)
        for tabela in TABELAS.values():
            cursor.execute(f"SELECT count(*) FROM {tabela}")
            contagem[tabela] = cursor.fetchone()[0]
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()
    return contagem


def mesclar(engine: Engine) -> Dict[str, Any]:
    """Executa o merge em SQL sobre o que está no staging."""
    with engine.begin() as conexao:
        resumo = conexao.execute(text("SELECT etl.merge_camara_bulk()")).scalar_one()
        conexao.execute(text("SELECT etl.aplicar_linhagens()"))
    logger.info("Merge Câmara (lote): %s", resumo)
    return dict(resumo)


def carregar(engine: Engine, arquivos: Iterable[ArquivoBaixado]) -> Dict[str, Any]:
    """Staging + merge. Devolve contagens do staging e o resumo do merge."""
    contagem = carregar_staging(engine, arquivos)
    return {"staging": contagem, "merge": mesclar(engine)}
