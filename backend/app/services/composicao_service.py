"""Composição do Congresso durante cada mandato presidencial, lida de `leg` (bancadas, presidentes das Casas, TSE)."""

import math
from typing import Any, Dict, List, Optional

from app.core.errors import ErroDeDominio
from app.services.periodos import SLUG_MANDATO, nome_do_mandato
from sqlalchemy import text
from sqlalchemy.orm import Session

CASAS = {"camara": "CAMARA_DOS_DEPUTADOS", "senado": "SENADO_FEDERAL"}
COR_PADRAO = "#64748b"

_MANDATO_SQL = text(
    """
    SELECT m.id, mp.slug, mp.rotulo, p.nome_exibicao, m.inicio, m.fim
    FROM core.mandato_presidencial mp JOIN core.mandato m ON m.id = mp.mandato_id JOIN core.pessoa p ON p.id = m.pessoa_id
    WHERE mp.slug = :slug
    """
)

_COMPOSICAO_SQL = text(
    """
    SELECT c.*, k.codigo AS casa_codigo
    FROM leg.composicao_mandato c JOIN ref.casa_legislativa k ON k.id = c.casa_id
    WHERE c.mandato_id = (SELECT mandato_id FROM core.mandato_presidencial WHERE slug = :slug)
    """
)

_BANCADAS_SQL = text(
    """
    SELECT b.partido_sigla, b.cadeiras, b.cadeiras_tse, b.alinhamento, b.cor_hex, k.codigo AS casa_codigo
    FROM leg.bancada_mandato b JOIN ref.casa_legislativa k ON k.id = b.casa_id
    WHERE b.mandato_id = (SELECT mandato_id FROM core.mandato_presidencial WHERE slug = :slug)
    ORDER BY b.ordem
    """
)

_PRESIDENTES_SQL = text(
    """
    SELECT pc.nome, pc.partido_sigla, pc.uf, pcm.rotulo_periodo, pc.foto_url, k.codigo AS casa_codigo
    FROM leg.presidencia_casa_mandato pcm
    JOIN leg.presidencia_casa pc ON pc.id = pcm.presidencia_id
    JOIN ref.casa_legislativa k ON k.id = pc.casa_id
    WHERE pcm.mandato_id = (SELECT mandato_id FROM core.mandato_presidencial WHERE slug = :slug)
    ORDER BY pcm.ordem
    """
)


def _pct(parte: float, total: float) -> float:
    return round(parte / total * 100, 1) if total else 0.0


def bancadas_da_casa(db: Session, slug: str, codigo_casa: str) -> List[Dict[str, Any]]:
    """Bancadas exibidas (curadoria ou TSE) na Casa durante o mandato, da maior para a menor."""
    return [
        {
            "partido": r["partido_sigla"],
            "cadeiras": r["cadeiras"],
            "alinhamento": r["alinhamento"],
            "cor_hex": r["cor_hex"] or COR_PADRAO,
        }
        for r in db.execute(_BANCADAS_SQL, {"slug": slug}).mappings()
        if r["casa_codigo"] == codigo_casa and r["cadeiras"] is not None
    ]


def total_de_cadeiras(db: Session, slug: str, codigo_casa: str) -> Optional[int]:
    for r in db.execute(_COMPOSICAO_SQL, {"slug": slug}).mappings():
        if r["casa_codigo"] == codigo_casa:
            return int(r["total_cadeiras"])
    return None


def cadeiras_da_oposicao(bancadas: List[Dict[str, Any]]) -> Optional[int]:
    """Soma da oposição; None quando não há bancadas ou nenhuma foi classificada (base/centro/oposição)."""
    classificadas = [b for b in bancadas if b.get("alinhamento") not in (None, "NAO_CLASSIFICADO")]
    return sum(b["cadeiras"] for b in classificadas if b["alinhamento"] == "OPOSICAO") if classificadas else None


def governabilidade(total: int, bancadas: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Base aliada, centro e oposição calculados das bancadas; sem classificação, tudo `None` (nada inventado)."""
    vazio = {
        "base_aliada_cadeiras": None,
        "base_aliada_pct": None,
        "centro_cadeiras": None,
        "centro_pct": None,
        "oposicao_cadeiras": None,
        "oposicao_pct": None,
        "maioria_simples_atingida": None,
        "maioria_pec_atingida": None,
    }
    if cadeiras_da_oposicao(bancadas) is None:
        return vazio
    soma = {"BASE_GOVERNO": 0, "INDEPENDENTE_CENTRO": 0, "OPOSICAO": 0}
    for b in bancadas:
        if b["alinhamento"] in soma:
            soma[b["alinhamento"]] += b["cadeiras"]
    base = soma["BASE_GOVERNO"]
    return {
        "base_aliada_cadeiras": base,
        "base_aliada_pct": _pct(base, total),
        "centro_cadeiras": soma["INDEPENDENTE_CENTRO"],
        "centro_pct": _pct(soma["INDEPENDENTE_CENTRO"], total),
        "oposicao_cadeiras": soma["OPOSICAO"],
        "oposicao_pct": _pct(soma["OPOSICAO"], total),
        "maioria_simples_atingida": base > total / 2,
        "maioria_pec_atingida": base >= math.ceil(total * 3 / 5),
    }


def _verificacao(meta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not meta["tse_status"]:
        return None
    saida: Dict[str, Any] = {"status": meta["tse_status"]}
    for chave, coluna in (
        ("ano_legislatura", "tse_ano_legislatura"),
        ("total_eleitos_tse", "tse_total_eleitos"),
        ("total_esperado", "tse_total_esperado"),
        ("conferido", "tse_conferido"),
        ("nota", "tse_nota"),
        ("motivo", "tse_motivo"),
    ):
        if meta[coluna] is not None:
            saida[chave] = meta[coluna]
    if meta["tse_divergencias"] is not None:
        saida["divergencias"] = meta["tse_divergencias"]
    return saida


def _presidentes(todos: List[Dict[str, Any]], codigo_casa: str) -> List[Dict[str, Any]]:
    return [
        {
            "nome": p["nome"],
            "partido": p["partido_sigla"] or "",
            "uf": p["uf"] or "",
            "periodo": p["rotulo_periodo"],
            "foto_url": p["foto_url"],
        }
        for p in todos
        if p["casa_codigo"] == codigo_casa
    ]


def composicao_do_mandato(db: Session, slug: str) -> Dict[str, Any]:
    """Composição do Congresso no mandato: bancadas, presidentes das Casas, governabilidade e conferência com o TSE."""
    from app.services.iple_service import get_mandate_iple

    if not SLUG_MANDATO.match(slug):
        raise ErroDeDominio(404, f"Mandato '{slug}' não encontrado na composição do Congresso.")
    mandato = db.execute(_MANDATO_SQL, {"slug": slug}).mappings().first()
    metas = {r["casa_codigo"]: dict(r) for r in db.execute(_COMPOSICAO_SQL, {"slug": slug}).mappings()}
    if mandato is None or not metas:
        raise ErroDeDominio(404, f"Mandato '{slug}' não encontrado na composição do Congresso.")
    linhas = [dict(r) for r in db.execute(_BANCADAS_SQL, {"slug": slug}).mappings()]
    presidentes = [dict(r) for r in db.execute(_PRESIDENTES_SQL, {"slug": slug}).mappings()]
    ano_inicio = mandato["inicio"].year

    resultado: Dict[str, Any] = {
        "mandato_id": slug,
        "presidente_republica": nome_do_mandato(mandato["nome_exibicao"], mandato["rotulo"]),
        "periodo": f"{ano_inicio} - {mandato['fim'].year - 1 if mandato['fim'] else 'Presente'}",
    }
    fonte = None
    for chave, codigo in CASAS.items():
        meta = metas.get(codigo)
        if meta is None:
            continue
        do_casa = [r for r in linhas if r["casa_codigo"] == codigo]
        total = int(meta["total_cadeiras"])
        bancadas = [
            {
                "partido": r["partido_sigla"],
                "cadeiras": r["cadeiras"],
                "percentual": _pct(r["cadeiras"], total),
                "alinhamento": r["alinhamento"],
                "cor_hex": r["cor_hex"] or COR_PADRAO,
            }
            for r in do_casa
            if r["cadeiras"] is not None
        ]
        gov = governabilidade(total, bancadas)
        gov["iple"] = get_mandate_iple(db, slug, "CAMARA" if chave == "camara" else "SENADO")
        casa: Dict[str, Any] = {
            "total_cadeiras": total,
            "presidentes": _presidentes(presidentes, codigo),
            "bancadas": bancadas,
            "governabilidade": gov,
        }
        eleitos = [r for r in do_casa if r["cadeiras_tse"] is not None]
        if eleitos:
            base = meta["tse_total_eleitos"] or total
            casa["bancadas_eleitas_tse"] = [
                {
                    "partido": r["partido_sigla"],
                    "cadeiras": r["cadeiras_tse"],
                    "percentual": _pct(r["cadeiras_tse"], base),
                }
                for r in sorted(eleitos, key=lambda r: (-r["cadeiras_tse"], r["partido_sigla"]))
            ]
        if meta["bancadas_origem"] == "TSE":
            casa["bancadas_origem"] = "TSE — candidatos eleitos (sem classificação base/oposição)"
        verificacao = _verificacao(meta)
        if verificacao:
            casa["verificacao_tse"] = verificacao
        resultado[chave] = casa
        fonte = fonte or meta["fonte_texto"]
    incompleto = any(resultado[c]["governabilidade"]["oposicao_cadeiras"] is None for c in CASAS if c in resultado)
    if incompleto:
        resultado["dados_incompletos"] = True
        resultado["observacao"] = next((m["observacao"] for m in metas.values() if m["observacao"]), None)
    resultado["fonte_curadoria"] = fonte
    resultado["iple"] = get_mandate_iple(db, slug)
    return resultado
