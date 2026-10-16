"""Composição do Congresso durante cada mandato presidencial, lida de `leg` (bancadas, presidentes das Casas, TSE)."""

from typing import Any, Dict, List, Optional

from app.core.errors import ErroDeDominio
from app.services import bancadas_service, iple_service
from app.services.bancadas_service import CASAS, pct
from app.services.periodos import SLUG_MANDATO, nome_do_mandato, rotulo_do_periodo
from sqlalchemy import text
from sqlalchemy.orm import Session

_MANDATO_SQL = text(
    """
    SELECT m.id, mp.slug, mp.rotulo, p.nome_exibicao, m.inicio, m.fim
    FROM core.mandato_presidencial mp JOIN core.mandato m ON m.id = mp.mandato_id JOIN core.pessoa p ON p.id = m.pessoa_id
    WHERE mp.slug = :slug
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


def _bancadas_eleitas_tse(linhas: List[Dict[str, Any]], meta: Dict[str, Any], total: int) -> List[Dict[str, Any]]:
    """Bancadas eleitas segundo o TSE (conferência), da maior para a menor; vazio se a Casa não tem esse dado."""
    eleitos = [r for r in linhas if r["cadeiras_tse"] is not None]
    base = meta["tse_total_eleitos"] or total
    return [
        {"partido": r["partido_sigla"], "cadeiras": r["cadeiras_tse"], "percentual": pct(r["cadeiras_tse"], base)}
        for r in sorted(eleitos, key=lambda r: (-r["cadeiras_tse"], r["partido_sigla"]))
    ]


def _montar_casa(
    meta: Dict[str, Any],
    linhas: List[Dict[str, Any]],
    presidentes: List[Dict[str, Any]],
    iple: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Bloco de uma Casa: presidentes, bancadas, governabilidade (com o IPLE da Casa) e conferência com o TSE."""
    total = int(meta["total_cadeiras"])
    bancadas = bancadas_service.bancadas_exibidas(linhas, total)
    casa: Dict[str, Any] = {
        "total_cadeiras": total,
        "presidentes": presidentes,
        "bancadas": bancadas,
        "governabilidade": {**bancadas_service.governabilidade(total, bancadas), "iple": iple},
    }
    eleitas_tse = _bancadas_eleitas_tse(linhas, meta, total)
    if eleitas_tse:
        casa["bancadas_eleitas_tse"] = eleitas_tse
    if meta["bancadas_origem"] == "TSE":
        casa["bancadas_origem"] = "TSE — candidatos eleitos (sem classificação base/oposição)"
    verificacao = _verificacao(meta)
    if verificacao:
        casa["verificacao_tse"] = verificacao
    return casa


def composicao_do_mandato(db: Session, slug: str) -> Dict[str, Any]:
    """Composição do Congresso no mandato: bancadas, presidentes das Casas, governabilidade e conferência com o TSE."""
    nao_encontrado = ErroDeDominio(404, f"Mandato '{slug}' não encontrado na composição do Congresso.")
    if not SLUG_MANDATO.match(slug):
        raise nao_encontrado
    mandato = db.execute(_MANDATO_SQL, {"slug": slug}).mappings().first()
    metas = bancadas_service.composicoes(db, slug)
    if mandato is None or not metas:
        raise nao_encontrado
    linhas = bancadas_service.linhas_de_bancada(db, slug)
    todos_presidentes = [dict(r) for r in db.execute(_PRESIDENTES_SQL, {"slug": slug}).mappings()]
    producao = iple_service.producoes(db, slug)
    iples = iple_service.iple_das_casas(db, producao[0], metas=metas, linhas=linhas) if producao else {}

    resultado: Dict[str, Any] = {
        "mandato_id": slug,
        "presidente_republica": nome_do_mandato(mandato["nome_exibicao"], mandato["rotulo"]),
        "periodo": rotulo_do_periodo(mandato["inicio"], mandato["fim"]),
    }
    for chave, codigo in CASAS.items():
        if codigo in metas:
            resultado[chave] = _montar_casa(
                metas[codigo],
                [r for r in linhas if r["casa_codigo"] == codigo],
                _presidentes(todos_presidentes, codigo),
                iples.get(chave),
            )
    if any(
        resultado[c]["governabilidade"]["oposicao_cadeiras"] is None
        or resultado[c]["governabilidade"]["nao_classificadas_cadeiras"]
        for c in CASAS
        if c in resultado
    ):
        resultado["dados_incompletos"] = True
        resultado["observacao"] = next((m["observacao"] for m in metas.values() if m["observacao"]), None)
    resultado["fonte_curadoria"] = next((metas[c]["fonte_texto"] for c in CASAS.values() if c in metas), None)
    resultado["iple"] = iples.get("camara")
    return resultado
