"""
Fidelidade e migração partidária do Congresso: balanço de bancada por legenda e parlamentares que mais trocaram de
partido. Lê `core` (mandato, filiação, partido), a mesma fonte do restante da API; só entram os parlamentares em
exercício (deputado federal ou senador com mandato em curso).
"""

from collections import defaultdict
from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

SEM_FILIACAO = "OUTROS"
TOP_NOMADES = 35


def _resposta_vazia() -> Dict[str, Any]:
    return {
        "dados_disponiveis": False,
        "party_balance": [],
        "top_nomads": [],
        "summary": {
            "total_parlamentares": 0,
            "total_nomades": 0,
            "taxa_migracao_pct": 0,
            "partido_maior_ganho": None,
            "saldo_maior_ganho": 0,
            "partido_maior_perda": None,
            "saldo_maior_perda": 0,
        },
    }


def _mandatos_em_curso(db: Session, hoje: date) -> Dict[int, Dict[str, Any]]:
    """O mandato federal em curso de cada parlamentar (o mais recente, se houver mais de um), por `core.pessoa.id`."""
    linhas = (
        db.execute(
            text(
                """
                SELECT DISTINCT ON (m.pessoa_id)
                       m.pessoa_id, c.codigo AS cargo, ci.uf, pe.uid, pe.nome_exibicao, fm.url_origem AS foto,
                       (SELECT n.nome FROM core.pessoa_nome n WHERE n.pessoa_id = pe.id AND n.tipo = 'CIVIL'
                         ORDER BY n.id LIMIT 1) AS nome_civil
                FROM core.mandato m
                JOIN ref.cargo c ON c.id = m.cargo_id
                JOIN ref.circunscricao ci ON ci.id = m.circunscricao_id
                JOIN core.pessoa pe ON pe.id = m.pessoa_id
                LEFT JOIN core.midia fm ON fm.id = pe.foto_midia_id
                WHERE c.codigo IN ('DEPUTADO_FEDERAL', 'SENADOR') AND (m.fim IS NULL OR m.fim >= :hoje)
                ORDER BY m.pessoa_id, m.inicio DESC, m.id DESC
                """
            ),
            {"hoje": hoje},
        )
        .mappings()
        .all()
    )
    return {linha["pessoa_id"]: dict(linha) for linha in linhas}


def _filiacoes(db: Session, pessoas: List[int]) -> Dict[int, List[Dict[str, Any]]]:
    """Filiações de cada pessoa em ordem cronológica; `atual` é a filiação sem data de saída."""
    linhas = (
        db.execute(
            text(
                """
                SELECT f.pessoa_id, pa.sigla, lower(f.periodo) AS inicio,
                       CASE WHEN upper_inf(f.periodo) THEN NULL ELSE upper(f.periodo) - 1 END AS fim,
                       f.motivo_saida AS motivo, upper_inf(f.periodo) AS atual
                FROM core.filiacao f
                JOIN core.partido pa ON pa.id = f.partido_id
                WHERE f.pessoa_id = ANY(:ids)
                ORDER BY f.pessoa_id, lower(f.periodo), f.id
                """
            ),
            {"ids": pessoas},
        )
        .mappings()
        .all()
    )
    por_pessoa: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for linha in linhas:
        por_pessoa[linha["pessoa_id"]].append(dict(linha))
    return por_pessoa


def _nomade(mandato: Dict[str, Any], filiacoes: List[Dict[str, Any]], sigla_atual: str) -> Dict[str, Any]:
    historico = [
        {
            "partido": f["sigla"],
            "data_filiacao": f["inicio"].isoformat(),
            "data_desfiliacao": f["fim"].isoformat() if f["fim"] else None,
            "motivo": f["motivo"],
            "is_atual": bool(f["atual"]),
        }
        for f in filiacoes
    ]
    return {
        "id": str(mandato["uid"]),
        "nome_eleitoral": mandato["nome_exibicao"],
        "nome_civil": mandato["nome_civil"] or mandato["nome_exibicao"],
        "cargo": "SENADOR" if mandato["cargo"] == "SENADOR" else "DEPUTADO FEDERAL",
        "uf": mandato["uf"],
        "foto_url": mandato["foto"],
        "partido_atual": sigla_atual,
        "total_trocas": len(filiacoes) - 1,
        "total_partidos": len({h["partido"] for h in historico}),
        "siglas_sequencia": [h["partido"] for h in historico],
        "historico": historico,
    }


def analise_de_fidelidade(db: Session, hoje: Optional[date] = None) -> Dict[str, Any]:
    mandatos = _mandatos_em_curso(db, hoje or date.today())
    if not mandatos:
        return _resposta_vazia()
    por_pessoa = _filiacoes(db, list(mandatos))
    if not por_pessoa:
        return _resposta_vazia()

    ganhos: Dict[str, int] = defaultdict(int)
    perdas: Dict[str, int] = defaultdict(int)
    bancada_atual: Dict[str, int] = defaultdict(int)
    bancada_inicial: Dict[str, int] = defaultdict(int)
    nomades: List[Dict[str, Any]] = []

    for pessoa, filiacoes in por_pessoa.items():
        primeira = filiacoes[0]["sigla"]
        atual = next((f for f in reversed(filiacoes) if f["atual"]), filiacoes[-1])["sigla"]
        bancada_inicial[primeira] += 1
        bancada_atual[atual] += 1
        if len(filiacoes) > 1:
            if primeira != atual:
                perdas[primeira] += 1
                ganhos[atual] += 1
            nomades.append(_nomade(mandatos[pessoa], filiacoes, atual))

    nomades.sort(key=lambda x: (x["total_trocas"], x["total_partidos"], x["nome_eleitoral"]), reverse=True)

    balanco = [
        {
            "partido": p,
            "bancada_atual": bancada_atual[p],
            "bancada_inicial": bancada_inicial[p],
            "ganhos": ganhos[p],
            "perdas": perdas[p],
            "saldo_liquido": ganhos[p] - perdas[p],
        }
        for p in sorted(set(bancada_atual) | set(bancada_inicial))
        if p != SEM_FILIACAO
    ]
    balanco.sort(key=lambda x: (x["saldo_liquido"], x["partido"]), reverse=True)

    total = len(por_pessoa)
    return {
        "dados_disponiveis": True,
        "party_balance": balanco,
        "top_nomads": nomades[:TOP_NOMADES],
        "summary": {
            "total_parlamentares": total,
            "total_nomades": len(nomades),
            "taxa_migracao_pct": round(len(nomades) / total * 100, 1),
            "partido_maior_ganho": balanco[0]["partido"] if balanco else None,
            "saldo_maior_ganho": balanco[0]["saldo_liquido"] if balanco else 0,
            "partido_maior_perda": balanco[-1]["partido"] if balanco else None,
            "saldo_maior_perda": balanco[-1]["saldo_liquido"] if balanco else 0,
        },
    }
