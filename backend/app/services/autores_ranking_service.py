"""Ranking de produtividade dos autores de proposições, pontuado pelo IALP (metodologia única em `param.peso`)."""

from typing import Any, Dict, List, Optional, Tuple

from app.core.errors import ErroDeDominio
from app.core.query_utils import escape_like, is_filter_all
from app.services.derivados_service import garantir_atualizados
from app.services.party_catalog_service import SEM_PARTIDO_SIGLA
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

STATUS_LEI = ("APROVADA_E_SANCIONADA", "APROVADA_E_PROMULGADA")
CRITERIOS = ("efetividade", "volume", "lideranca", "coautoria")

_CORTES_DEFAULT = {
    "APROVADAS_ALTA": 2.0,
    "APROVADAS_MEDIA": 1.0,
    "LIDERANCA_VOLUME_ALTO": 20.0,
    "COAUTORIA_SOBRE_LIDERANCA": 2.0,
    "LIDERANCA_PROPOSITIVA": 10.0,
}

_CORTES_SQL = text(
    """
    SELECT p.chave, p.valor FROM param.peso p JOIN param.metodologia m ON m.id = p.metodologia_id
    WHERE m.codigo = 'IALP' AND p.dimensao = 'CORTE_DIAGNOSTICO_AUTOR'
      AND m.versao = (SELECT max(versao) FROM param.metodologia WHERE codigo = 'IALP')
    """
)

_AGREGADO_SQL = text(
    """
    SELECT v.pessoa_id AS author_id,
           count(*) AS total_props,
           count(*) FILTER (WHERE v.tipo_autoria = 'AUTOR_PRINCIPAL') AS lideranca,
           count(*) FILTER (WHERE v.tipo_autoria = 'COAUTOR') AS coautoria,
           count(*) FILTER (WHERE v.status_codigo IN :leis) AS aprovadas,
           count(*) FILTER (WHERE p.reforma_estrutural OR v.tipo_proposicao IN ('PEC', 'PLP')) AS estruturantes,
           round(sum(v.pontos_ialp)::numeric, 1) AS score
    FROM leg.mv_autoria_pontuada_unica v
    JOIN leg.proposicao p ON p.id = v.proposicao_id
    WHERE (cardinality(CAST(:setores AS text[])) = 0 OR p.area_tematica ILIKE ANY (CAST(:setores AS text[])))
      AND (CAST(:partido AS text) IS NULL OR EXISTS (
            SELECT 1 FROM core.vw_partido_atual pa
             WHERE pa.pessoa_id = v.pessoa_id AND pa.canonico_sigla_normalizada = ref.normalizar_texto(:partido)))
    GROUP BY v.pessoa_id
    """
).bindparams(bindparam("leis", expanding=True))

_AUTORES_DETALHE_SQL = text(
    """
    SELECT pe.id, pe.uid, pe.nome_exibicao,
           (SELECT n.nome FROM core.pessoa_nome n WHERE n.pessoa_id = pe.id AND n.tipo = 'CIVIL' LIMIT 1) AS nome_civil,
           fm.url_origem AS foto, pa.canonico_id AS partido_id, mand.uf, mand.cargo
    FROM core.pessoa pe
    LEFT JOIN core.midia fm ON fm.id = pe.foto_midia_id
    LEFT JOIN core.vw_partido_atual pa ON pa.pessoa_id = pe.id
    LEFT JOIN LATERAL (
        SELECT coalesce(ci.uf, 'BR') AS uf, c.codigo AS cargo
        FROM core.mandato m JOIN ref.cargo c ON c.id = m.cargo_id JOIN ref.circunscricao ci ON ci.id = m.circunscricao_id
        WHERE m.pessoa_id = pe.id AND m.condicao <> 'NOMEADO' ORDER BY m.inicio DESC LIMIT 1
    ) mand ON true
    WHERE pe.id = ANY(:ids)
    """
)

_SETORES_SQL = text(
    """
    SELECT a.pessoa_id, p.area_tematica, count(*) AS total_setor
    FROM leg.autoria a JOIN leg.proposicao p ON p.id = a.proposicao_id
    WHERE a.pessoa_id = ANY(:ids) AND a.tipo_codigo <> 'INSTITUCIONAL'
    GROUP BY a.pessoa_id, p.area_tematica
    ORDER BY a.pessoa_id, total_setor DESC
    """
)

_PARTIDOS_SQL = text("SELECT id, sigla, espectro_politico FROM core.vw_partido WHERE id = ANY(:ids)")


def _cortes(db: Session) -> Dict[str, float]:
    return {**_CORTES_DEFAULT, **{str(chave): float(valor) for chave, valor in db.execute(_CORTES_SQL)}}


def _diagnostico(cortes: Dict[str, float], aprovadas: int, lideranca: int, coautoria: int) -> str:
    if aprovadas >= cortes["APROVADAS_ALTA"]:
        return "Alta Eficácia Legislativa"
    if aprovadas >= cortes["APROVADAS_MEDIA"]:
        return "Média Eficácia"
    if lideranca >= cortes["LIDERANCA_VOLUME_ALTO"]:
        return "Volume Alto sem Leis Aprovadas"
    if coautoria > lideranca * cortes["COAUTORIA_SOBRE_LIDERANCA"]:
        return "Articulação & Apoio Político"
    if lideranca >= cortes["LIDERANCA_PROPOSITIVA"]:
        return "Liderança Propositiva"
    return "Em Tramitação"


def _termos_do_setor(setor: Optional[str]) -> List[str]:
    """Padrões LIKE do setor: o texto inteiro e, se houver, só o tema principal (antes de '&' ou '/')."""
    if is_filter_all(setor):
        return []
    limpo = str(setor).strip()
    principal = limpo.split("&")[0].split("/")[0].strip()
    termos = [limpo] + ([principal] if principal and principal != limpo else [])
    return [f"%{escape_like(t)}%" for t in termos]


_CHAVES_DE_ORDEM = {
    "volume": ("total_props", "score", "author_id"),
    "lideranca": ("autoria_principal_count", "score", "total_props", "author_id"),
    "coautoria": ("coautoria_count", "score", "total_props", "author_id"),
    "efetividade": ("score", "aprovadas", "autoria_principal_count", "estruturantes", "total_props", "author_id"),
}


def _ordenar(autores: List[Dict[str, Any]], criterio: str) -> None:
    """Ordena por critério, com desempate determinístico pelo id do autor."""
    campos = _CHAVES_DE_ORDEM[criterio]
    autores.sort(key=lambda a: tuple(a[c] for c in campos), reverse=True)


def ranking_autores(
    db: Session, limite: int, partido: Optional[str], setor: Optional[str], criterio: str
) -> List[Dict[str, Any]]:
    criterio = criterio.lower().strip()
    if criterio not in CRITERIOS:
        raise ErroDeDominio(422, f"Critério inválido. Use um de: {', '.join(CRITERIOS)}.")

    parametros: Dict[str, Any] = {
        "leis": list(STATUS_LEI),
        "setores": _termos_do_setor(setor),
        "partido": None if is_filter_all(partido) else str(partido).strip(),
    }
    garantir_atualizados(db)
    linhas = db.execute(_AGREGADO_SQL, parametros).mappings().all()
    if not linhas:
        return []

    cortes = _cortes(db)
    autores: List[Dict[str, Any]] = []
    for r in linhas:
        total, lider = int(r["total_props"] or 0), int(r["lideranca"] or 0)
        coaut, aprovadas = int(r["coautoria"] or 0), int(r["aprovadas"] or 0)
        autores.append(
            {
                "author_id": r["author_id"],
                "total_props": total,
                "autoria_principal_count": lider,
                "coautoria_count": coaut,
                "aprovadas": aprovadas,
                "estruturantes": int(r["estruturantes"] or 0),
                "taxa_eficiencia_pct": round(aprovadas / max(lider, 1) * 100, 1) if lider > 0 else 0.0,
                "score": float(r["score"] or 0),
                "diagnostico": _diagnostico(cortes, aprovadas, lider, coaut),
            }
        )
    _ordenar(autores, criterio)

    selecionados = autores[:limite]
    pessoa_ids = [a["author_id"] for a in selecionados]
    detalhes = {r["id"]: r for r in db.execute(_AUTORES_DETALHE_SQL, {"ids": pessoa_ids}).mappings()}
    partidos = {
        r["id"]: r
        for r in db.execute(
            _PARTIDOS_SQL, {"ids": [d["partido_id"] for d in detalhes.values() if d["partido_id"]]}
        ).mappings()
    }
    setores: Dict[int, List[Tuple[str, int]]] = {}
    for pessoa_id, area, quantidade in db.execute(_SETORES_SQL, {"ids": pessoa_ids}).all():
        setores.setdefault(pessoa_id, []).append((area or "Geral", quantidade))

    ranking = []
    for posicao, item in enumerate(selecionados, start=1):
        pol = detalhes.get(item["author_id"])
        if not pol:
            continue
        partido_obj = partidos.get(pol["partido_id"]) if pol["partido_id"] else None
        do_autor = setores.get(item["author_id"], [])
        principal_setor = do_autor[0][0] if do_autor else "Geral"
        total_principal = do_autor[0][1] if do_autor else item["total_props"]
        total = item["total_props"]
        ranking.append(
            {
                "posicao": posicao,
                "politico_id": str(pol["uid"]),
                "nome_eleitoral": pol["nome_exibicao"],
                "nome_civil": pol["nome_civil"] or pol["nome_exibicao"],
                "partido_sigla": partido_obj["sigla"] if partido_obj else SEM_PARTIDO_SIGLA,
                "espectro_politico": partido_obj["espectro_politico"] if partido_obj else None,
                "uf": pol["uf"],
                "cargo": pol["cargo"],
                "foto_url": pol["foto"],
                "total_proposicoes": total,
                "autoria_principal_count": item["autoria_principal_count"],
                "coautoria_count": item["coautoria_count"],
                "proposicoes_aprovadas": item["aprovadas"],
                "proposicoes_estruturantes": item["estruturantes"],
                "taxa_eficiencia_pct": item["taxa_eficiencia_pct"],
                "score_produtividade": item["score"],
                "score_ponderado": item["score"],
                "score_ialp": item["score"],
                "desvio_foco": {
                    "estruturais": item["estruturantes"],
                    "burocraticas": max(0, total - item["estruturantes"]),
                    "proporcao_estrutural_pct": round(item["estruturantes"] / total * 100, 1) if total > 0 else 0.0,
                },
                "classificacao_efetividade": item["diagnostico"],
                "principal_setor": principal_setor,
                "total_principal_setor": total_principal,
                "distribuicao_setores": [
                    {"setor": st, "total": cnt, "percentual": round(cnt / total * 100, 1) if total > 0 else 0}
                    for st, cnt in do_autor
                ],
            }
        )
    return ranking
