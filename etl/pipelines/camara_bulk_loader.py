"""
Carga dos CSV anuais da Câmara (proposições e autores) no PostgreSQL, em dois passos:

1. staging: `COPY` dos arquivos para `stg.camara_proposicao` e `stg.camara_autor` (texto puro, sem regra de negócio);
2. merge em SQL: `etl.merge_camara_bulk()` grava proposição, autoria, pessoas, partidos e entidades, e registra
   rejeitos e verificações (cobertura por tipo) no próprio banco.

Reexecutar é seguro: o staging é refeito e o merge é idempotente.
"""

import logging
from typing import Any, Dict, Iterable

from etl.extractors.camara_bulk_extractor import ArquivoBaixado
from etl.utils.bootstrap import ensure_backend_on_path
from etl.utils.copia import contar, contar_linhas_csv, copiar_arquivo, esvaziar, transacao_de_carga
from etl.utils.execucao import registrar_arquivo_bruto, registrar_execucao

ensure_backend_on_path()

from app.services.derivados_service import reservar_derivados  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402

logger = logging.getLogger("CamaraBulkLoader")

FONTE = "CAMARA_CSV"
TABELAS = {"proposicoes": "stg.camara_proposicao", "proposicoesAutores": "stg.camara_autor"}


def carregar_staging(engine: Engine, arquivos: Iterable[ArquivoBaixado]) -> Dict[str, int]:
    """Recarrega o staging com os arquivos informados; registra a execução e cada arquivo em etl.arquivo_bruto."""
    arquivos = list(arquivos)
    contagem = {tabela: 0 for tabela in TABELAS.values()}
    lidas = 0
    with registrar_execucao(engine, FONTE, "CARREGAR", {"tabelas": sorted(TABELAS.values())}) as execucao:
        with transacao_de_carga(engine) as cursor:
            esvaziar(cursor, list(TABELAS.values()))
            for arquivo in sorted(arquivos, key=lambda a: (a.recurso, a.ano)):
                tabela = TABELAS[arquivo.recurso]
                # lidas vem do arquivo e gravadas do staging: se o COPY perdesse linha, as contagens deixariam de fechar;
                # contar aqui, dentro da transação, faz uma falha de leitura desfazer a carga inteira em vez de a deixar pela metade
                lidas += contar_linhas_csv(arquivo.caminho)
                copiar_arquivo(cursor, tabela, arquivo.caminho)
                registrar_arquivo_bruto(
                    cursor, FONTE, arquivo.url, arquivo.sha256, arquivo.bytes, str(arquivo.caminho), execucao.id
                )
                logger.info("Staging: %s (%d bytes) -> %s", arquivo.caminho.name, arquivo.bytes, tabela)
            for tabela in TABELAS.values():
                contagem[tabela] = contar(cursor, tabela)
        execucao.lidas = lidas
        execucao.gravadas = sum(contagem.values())
        execucao.rejeitadas = 0  # o COPY não rejeita linha: o que a fusão recusa vai para etl.rejeito
    return contagem


def mesclar(engine: Engine) -> Dict[str, Any]:
    """Executa o merge em SQL sobre o que está no staging."""
    with engine.begin() as conexao:
        reservar_derivados(conexao)  # trava de controle dos derivados antes de qualquer linha de dado
        resumo = conexao.execute(text("SELECT etl.merge_camara_bulk()")).scalar_one()
        conexao.execute(text("SELECT etl.aplicar_linhagens()"))
    logger.info("Merge Câmara (lote): %s", resumo)
    return dict(resumo)


def carregar(engine: Engine, arquivos: Iterable[ArquivoBaixado]) -> Dict[str, Any]:
    """Staging + merge. Devolve contagens do staging e o resumo do merge."""
    contagem = carregar_staging(engine, arquivos)
    return {"staging": contagem, "merge": mesclar(engine)}
