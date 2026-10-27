"""
Carga de repasses federais por UF (`eco.repasse_federal`) e de resultados presidenciais por UF
(`eco.resultado_eleitoral_uf`) a partir dos arquivos processados.

Regras:
- Só entra registro de fonte oficial (D7). Os repasses vêm de `repasses_federais_uf.json` (Portal da Transparência) e só
  valem os que trazem proveniência e não são sintéticos. Os resultados eleitorais vêm de `eleicoes_presidenciais_uf_tse.csv`
  e só valem as linhas `verificado` contra o TSE: a digitação manual antiga nunca é carregada.
- O arquivo de repasses é um retrato completo do período de cada mandato: a carga substitui as linhas dos mandatos que ele
  traz, em vez de acumular. Os resultados eleitorais substituem as eleições (ano) que o arquivo traz.
- Mandato que não existe em `core.mandato_presidencial` (slug desconhecido) tira o repasse da carga e é contado.
- Arquivo ausente ou sem nenhuma linha válida não apaga a base. Idempotente.
"""

import csv
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from etl.config import PROCESSED_DATA_DIR
from etl.pipelines.loader_helpers import ler_repasse, ler_resultado_eleitoral
from etl.utils.bootstrap import ensure_backend_on_path
from etl.utils.datafiles import load_json

ensure_backend_on_path()

from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import Connection, Engine  # noqa: E402

logger = logging.getLogger("TerritorialLoader")

REPASSES_ARQUIVO = "repasses_federais_uf.json"
ELEICOES_ARQUIVO = "eleicoes_presidenciais_uf_tse.csv"
FONTE_REPASSES = "PORTAL_TRANSPARENCIA"
FONTE_ELEICOES = "TSE"

_INSERCAO_DE_REPASSES = text(
    "INSERT INTO eco.repasse_federal (mandato_id, uf, area_tematica, ano_referencia, valor_pago, populacao_estimada, "
    "valor_per_capita, periodo_inicio, periodo_fim, meses_cobertos, parcial, fonte_id) "
    "VALUES (:mandato_id, :uf, :area, :ano, :valor, :populacao, :per_capita, :inicio, :fim, :meses, :parcial, :f) "
    "ON CONFLICT (mandato_id, uf, area_tematica) DO UPDATE SET ano_referencia = EXCLUDED.ano_referencia, "
    "valor_pago = EXCLUDED.valor_pago, populacao_estimada = EXCLUDED.populacao_estimada, "
    "valor_per_capita = EXCLUDED.valor_per_capita, periodo_inicio = EXCLUDED.periodo_inicio, "
    "periodo_fim = EXCLUDED.periodo_fim, meses_cobertos = EXCLUDED.meses_cobertos, parcial = EXCLUDED.parcial, "
    "fonte_id = EXCLUDED.fonte_id, carregado_em = now()"
)
_INSERCAO_DE_ELEICOES = text(
    "INSERT INTO eco.resultado_eleitoral_uf (ano_eleicao, turno, uf, mandato_id, vencedor_nome, vencedor_partido, "
    "vencedor_votos_pct, segundo_nome, segundo_partido, segundo_votos_pct, total_votos_validos, fonte_id) "
    "VALUES (:ano, :turno, :uf, :mandato_id, :vencedor, :vencedor_partido, :vencedor_pct, :segundo, "
    ":segundo_partido, :segundo_pct, :total_votos, :f) "
    "ON CONFLICT (ano_eleicao, turno, uf) DO UPDATE SET mandato_id = EXCLUDED.mandato_id, "
    "vencedor_nome = EXCLUDED.vencedor_nome, vencedor_partido = EXCLUDED.vencedor_partido, "
    "vencedor_votos_pct = EXCLUDED.vencedor_votos_pct, segundo_nome = EXCLUDED.segundo_nome, "
    "segundo_partido = EXCLUDED.segundo_partido, segundo_votos_pct = EXCLUDED.segundo_votos_pct, "
    "total_votos_validos = EXCLUDED.total_votos_validos, fonte_id = EXCLUDED.fonte_id, carregado_em = now()"
)


def _id_da_fonte(conn: Connection, codigo: str) -> int:
    achado = conn.execute(text("SELECT id FROM etl.fonte WHERE codigo = :c"), {"c": codigo}).scalar()
    if achado is None:
        raise ValueError(f"Fonte {codigo} fora do catálogo etl.fonte")
    return int(achado)


def _mandatos_presidenciais(conn: Connection) -> Dict[str, int]:
    return {
        slug: mandato for slug, mandato in conn.execute(text("SELECT slug, mandato_id FROM core.mandato_presidencial"))
    }


def linhas_dos_repasses(dados: Any, mandatos: Dict[str, int]) -> tuple:
    """(linhas prontas para o INSERT, contagem do que ficou de fora). Duas linhas da mesma chave: vale a última."""
    contagem: Dict[str, int] = {"sem_proveniencia": 0, "invalidas": 0, "sem_mandato": 0}
    unicas: Dict[tuple, Dict[str, Any]] = {}
    for item in dados if isinstance(dados, list) else []:
        lido, motivo = ler_repasse(item)
        if lido is None:
            contagem[str(motivo)] += 1
            continue
        mandato_id = mandatos.get(lido["mandato"])
        if mandato_id is None:
            contagem["sem_mandato"] += 1
            continue
        unicas[(mandato_id, lido["uf"], lido["area"])] = {**lido, "mandato_id": mandato_id}
    return list(unicas.values()), contagem


def linhas_das_eleicoes(linhas: List[Dict[str, str]], mandatos: Dict[str, int]) -> tuple:
    contagem: Dict[str, int] = {"nao_verificada": 0, "invalidas": 0}
    unicas: Dict[tuple, Dict[str, Any]] = {}
    for linha in linhas:
        lido, motivo = ler_resultado_eleitoral(linha)
        if lido is None:
            contagem[str(motivo)] += 1
            continue
        unicas[(lido["ano"], lido["turno"], lido["uf"])] = {**lido, "mandato_id": mandatos.get(lido["mandato"] or "")}
    return list(unicas.values()), contagem


def _ler_csv(caminho: Path) -> Optional[List[Dict[str, str]]]:
    if not caminho.exists():
        return None
    with open(caminho, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def carregar(engine: Engine, processed_dir: Optional[Path] = None) -> Dict[str, int]:
    pasta = Path(processed_dir or PROCESSED_DATA_DIR)
    resultado: Dict[str, int] = {"repasses": 0, "eleicoes": 0}
    with engine.begin() as conn:
        mandatos = _mandatos_presidenciais(conn)

        repasses, contagem = linhas_dos_repasses(load_json(pasta / REPASSES_ARQUIVO, None), mandatos)
        if repasses:
            fonte = _id_da_fonte(conn, FONTE_REPASSES)
            for mandato_id in sorted({r["mandato_id"] for r in repasses}):
                conn.execute(text("DELETE FROM eco.repasse_federal WHERE mandato_id = :m"), {"m": mandato_id})
            conn.execute(_INSERCAO_DE_REPASSES, [{**r, "f": fonte} for r in repasses])
        else:
            logger.warning(
                "Repasses: nenhuma linha válida em %s (%s); a base não foi alterada.", REPASSES_ARQUIVO, contagem
            )
        resultado.update({"repasses": len(repasses), **{f"repasses_{k}": v for k, v in contagem.items() if v}})

        csv_eleicoes = _ler_csv(pasta / ELEICOES_ARQUIVO)
        eleicoes, contagem = linhas_das_eleicoes(csv_eleicoes or [], mandatos)
        if eleicoes:
            fonte = _id_da_fonte(conn, FONTE_ELEICOES)
            for ano in sorted({e["ano"] for e in eleicoes}):
                conn.execute(text("DELETE FROM eco.resultado_eleitoral_uf WHERE ano_eleicao = :a"), {"a": ano})
            conn.execute(_INSERCAO_DE_ELEICOES, [{**e, "f": fonte} for e in eleicoes])
        else:
            logger.warning(
                "Eleições: nenhuma linha válida em %s (%s); a base não foi alterada.", ELEICOES_ARQUIVO, contagem
            )
        resultado.update({"eleicoes": len(eleicoes), **{f"eleicoes_{k}": v for k, v in contagem.items() if v}})
    logger.info("Repasses e eleições em eco: %s", resultado)
    return resultado
