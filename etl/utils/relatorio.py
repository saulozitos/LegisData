"""
Relatório de uma rodada do ETL: o que cada fonte carregou, o que foi rejeitado e por quê, e quais verificações não
passaram. Lê só `etl.execucao`, `etl.rejeito` e `etl.verificacao`; não grava nada. O relatório sai no terminal ao fim da
esteira (`run_etl`) e pode ser pedido a qualquer momento (`python -m etl.run_etl --relatorio`).
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

LIMITE_REJEITOS = 15  # motivos de rejeição listados por execução


def execucoes_desde(engine: Engine, desde: datetime) -> List[Dict[str, Any]]:
    """As execuções iniciadas a partir de `desde`, na ordem em que começaram."""
    with engine.connect() as conexao:
        linhas = conexao.execute(
            text(
                "SELECT e.id, coalesce(f.codigo, '-') AS fonte, e.estagio, e.status, e.linhas_lidas, e.linhas_gravadas, "
                "e.linhas_rejeitadas, e.parametros, e.erro, "
                "extract(epoch FROM (coalesce(e.finalizado_em, now()) - e.iniciado_em)) AS segundos "
                "FROM etl.execucao e LEFT JOIN etl.fonte f ON f.id = e.fonte_id "
                "WHERE e.iniciado_em >= :desde ORDER BY e.id"
            ),
            {"desde": desde},
        ).mappings()
        return [dict(linha) for linha in linhas]


def _rejeitos(engine: Engine, execucao_id: int) -> List[Dict[str, Any]]:
    with engine.connect() as conexao:
        return [
            dict(linha)
            for linha in conexao.execute(
                text(
                    "SELECT recurso, motivo, sum(coalesce((payload->>'total')::int, 1)) AS total FROM etl.rejeito "
                    "WHERE execucao_id = :id "
                    "GROUP BY recurso, motivo ORDER BY total DESC, recurso, motivo LIMIT :limite"
                ),
                {"id": execucao_id, "limite": LIMITE_REJEITOS},
            ).mappings()
        ]


def _verificacoes_reprovadas(engine: Engine, execucao_id: int) -> List[Dict[str, Any]]:
    with engine.connect() as conexao:
        return [
            dict(linha)
            for linha in conexao.execute(
                text("SELECT nome, detalhe FROM etl.verificacao WHERE execucao_id = :id AND NOT passou ORDER BY id"),
                {"id": execucao_id},
            ).mappings()
        ]


def _numero(valor: Optional[int]) -> str:
    return "n/d" if valor is None else f"{valor:,}".replace(",", ".")  # desconhecido não é zero


def montar_relatorio(engine: Engine, desde: datetime) -> str:
    """O texto do relatório das execuções iniciadas desde `desde`."""
    execucoes = execucoes_desde(engine, desde)
    if not execucoes:
        return "Relatório do ETL: nenhuma execução registrada nesta rodada."
    linhas = ["Relatório do ETL", "=" * 70]
    com_problema = 0
    for e in execucoes:
        recurso = (e["parametros"] or {}).get("recurso")
        rotulo = f"{e['fonte']}/{e['estagio']}" + (f" [{recurso}]" if recurso else "")
        linhas.append(
            f"{rotulo:<44} {e['status']:<10} lidas {_numero(e['linhas_lidas'])} · gravadas "
            f"{_numero(e['linhas_gravadas'])} · rejeitadas {_numero(e['linhas_rejeitadas'])} · {e['segundos']:.1f}s"
        )
        if e["erro"]:
            linhas.append(f"    erro: {e['erro']}")
        rejeitos = _rejeitos(engine, e["id"])
        for r in rejeitos:
            linhas.append(f"    rejeitos: {r['recurso']} / {r['motivo']}: {_numero(r['total'])}")
        reprovadas = _verificacoes_reprovadas(engine, e["id"])
        for v in reprovadas:
            linhas.append(f"    verificação que não passou: {v['nome']} {v['detalhe'] or ''}".rstrip())
        if e["status"] != "OK" or reprovadas:
            com_problema += 1
    linhas.append("=" * 70)
    linhas.append(
        f"{len(execucoes)} execuções; {com_problema} com alerta, erro ou verificação reprovada."
        if com_problema
        else f"{len(execucoes)} execuções, todas OK."
    )
    return "\n".join(linhas)
