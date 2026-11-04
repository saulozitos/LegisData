"""
Carga do histórico de mandatos dos deputados (API da Câmara) no PostgreSQL: staging via COPY e merge em SQL
(`etl.merge_camara_historico`), que grava mandato, situações de exercício/licença/suplência e o partido por período.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from etl.utils.bootstrap import ensure_backend_on_path
from etl.utils.copia import contar, copiar_linhas, esvaziar, transacao_de_carga
from etl.utils.execucao import registrar_execucao

ensure_backend_on_path()

from app.services.derivados_service import reservar_derivados  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402

logger = logging.getLogger("CamaraHistoricoLoader")

FONTE = "CAMARA_API"
COLUNAS = [
    "id", "uri", "nome", "nomeEleitoral", "siglaPartido", "uriPartido", "siglaUf", "idLegislatura", "email", "urlFoto",
    "dataHora", "situacao", "condicaoEleitoral", "descricaoStatus",
]  # fmt: skip


def carregar_staging(
    engine: Engine, eventos: List[Dict[str, Any]], legislaturas: List[Dict[str, Any]]
) -> Dict[str, int]:
    tabelas = ["stg.camara_historico", "stg.camara_legislatura"]
    with registrar_execucao(engine, FONTE, "CARREGAR", {"tabelas": tabelas}) as execucao:
        with transacao_de_carga(engine) as cursor:
            esvaziar(cursor, tabelas)
            copiar_linhas(cursor, tabelas[0], COLUNAS, ([e.get(c) for c in COLUNAS] for e in eventos))
            copiar_linhas(
                cursor,
                tabelas[1],
                ["id", "dataInicio", "dataFim"],
                ([str(leg["id"]), leg["dataInicio"], leg["dataFim"]] for leg in legislaturas),
            )
            gravadas = sum(contar(cursor, tabela) for tabela in tabelas)
        execucao.lidas = len(eventos) + len(legislaturas)
        execucao.gravadas = gravadas
        execucao.rejeitadas = 0
    return {"eventos": len(eventos), "legislaturas": len(legislaturas)}


def carregar(engine: Engine, raw_dir: Path) -> Dict[str, Any]:
    """Lê o cache baixado por CamaraHistoricoExtractor, faz o staging e o merge."""
    raw_dir = Path(raw_dir)
    legislaturas = json.loads((raw_dir / "_legislaturas.json").read_text(encoding="utf-8"))
    eventos: List[Dict[str, Any]] = []
    for caminho in sorted(raw_dir.glob("[0-9]*.json")):
        eventos.extend(json.loads(caminho.read_text(encoding="utf-8")))
    contagem = carregar_staging(engine, eventos, legislaturas)
    with engine.begin() as conexao:
        reservar_derivados(conexao)  # trava de controle dos derivados antes de qualquer linha de dado
        resumo = conexao.execute(text("SELECT etl.merge_camara_historico()")).scalar_one()
        conexao.execute(text("SELECT etl.aplicar_linhagens()"))
    logger.info("Merge do histórico da Câmara: %s", resumo)
    return {"staging": contagem, "merge": dict(resumo)}
