"""
Carga do histórico de mandatos dos deputados (API da Câmara) no PostgreSQL: staging via COPY e merge em SQL
(`etl.merge_camara_historico`), que grava mandato, situações de exercício/licença/suplência e o partido por período.
"""

import csv
import io
import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List

from etl.utils.bootstrap import ensure_backend_on_path

ensure_backend_on_path()

from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402

logger = logging.getLogger("CamaraHistoricoLoader")

COLUNAS = [
    "id", "uri", "nome", "nomeEleitoral", "siglaPartido", "uriPartido", "siglaUf", "idLegislatura", "email", "urlFoto",
    "dataHora", "situacao", "condicaoEleitoral", "descricaoStatus",
]  # fmt: skip


def _linhas(eventos: Iterable[Dict[str, Any]]) -> str:
    saida = io.StringIO()
    escritor = csv.writer(saida)
    for evento in eventos:
        escritor.writerow(["" if evento.get(c) is None else evento.get(c) for c in COLUNAS])
    return saida.getvalue()


def carregar_staging(
    engine: Engine, eventos: List[Dict[str, Any]], legislaturas: List[Dict[str, Any]]
) -> Dict[str, int]:
    conexao = engine.raw_connection()
    try:
        cursor = conexao.cursor()
        cursor.execute("TRUNCATE stg.camara_historico, stg.camara_legislatura")
        cursor.copy_expert(
            "COPY stg.camara_historico FROM STDIN WITH (FORMAT csv, HEADER false)", io.StringIO(_linhas(eventos))
        )
        for leg in legislaturas:
            cursor.execute(
                'INSERT INTO stg.camara_legislatura ("id", "dataInicio", "dataFim") VALUES (%s, %s, %s)',
                (str(leg["id"]), leg["dataInicio"], leg["dataFim"]),
            )
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()
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
        resumo = conexao.execute(text("SELECT etl.merge_camara_historico()")).scalar_one()
        conexao.execute(text("SELECT etl.aplicar_linhagens()"))
    logger.info("Merge do histórico da Câmara: %s", resumo)
    return {"staging": contagem, "merge": dict(resumo)}
