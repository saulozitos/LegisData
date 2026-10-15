"""Ranking de ausências no Congresso (parlamentares e partidos), lido de `leg.presenca`.

Só entram dias em que a falta é conhecida: Senado em todo o período; Câmara a partir de 2003-02-03 (antes disso a
fonte publica apenas presença). Falta oficial (justificada ou não) e falta inferida (Câmara antes de 2020) aparecem
separadas. Os pontos IALP vêm de `leg.vw_autoria_pontuada` e dão o contraste entre faltar e produzir.
"""

from datetime import date
from typing import Any, Dict, List, Optional

from app.core.database import get_db
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

router = APIRouter()

FALTA_CONHECIDA_DESDE = date(2003, 2, 3)
MIN_DIAS_PARA_TAXA = 20
MIN_DIAS_PARTIDO = 2000
CASAS = {"CAMARA": "CAMARA_DOS_DEPUTADOS", "SENADO": "SENADO_FEDERAL"}
_JUSTIFICADAS = "('AUSENCIA_JUSTIFICADA', 'LICENCA_MEDICA', 'MISSAO_OFICIAL')"

_BASE = """
    SELECT p.pessoa_id, p.mandato_id, p.partido_id AS partido_dia, p.data_sessao, p.tipo_codigo, c.codigo AS casa
    FROM leg.presenca p JOIN ref.casa_legislativa c ON c.id = p.casa_id
    WHERE (c.codigo <> 'CAMARA_DOS_DEPUTADOS' OR p.data_sessao >= :falta_desde)
      AND p.data_sessao >= :inicio AND p.data_sessao <= :fim
      AND (CAST(:casa AS text) IS NULL OR c.codigo = :casa)
"""

_AGREGADOS = f"""
    count(*) AS sessoes,
    count(*) FILTER (WHERE tipo_codigo = 'PRESENTE') AS presencas,
    count(*) FILTER (WHERE tipo_codigo <> 'PRESENTE') AS faltas,
    count(*) FILTER (WHERE tipo_codigo IN {_JUSTIFICADAS}) AS faltas_justificadas,
    count(*) FILTER (WHERE tipo_codigo = 'AUSENCIA_NAO_JUSTIFICADA') AS faltas_nao_justificadas,
    count(*) FILTER (WHERE tipo_codigo = 'AUSENCIA_INFERIDA') AS faltas_inferidas
"""


def _parametros(casa: Optional[str], ano_inicio: Optional[int], ano_fim: Optional[int]) -> Dict[str, Any]:
    chave = (casa or "ALL").strip().upper()
    if chave != "ALL" and chave not in CASAS:
        raise HTTPException(status_code=422, detail="Casa inválida. Use ALL, CAMARA ou SENADO.")
    if ano_inicio and ano_fim and ano_inicio > ano_fim:
        raise HTTPException(status_code=422, detail="O ano inicial não pode ser maior que o final.")
    return {
        "falta_desde": FALTA_CONHECIDA_DESDE,
        "inicio": date(ano_inicio, 1, 1) if ano_inicio else date(1995, 1, 1),
        "fim": date(ano_fim, 12, 31) if ano_fim else date(2100, 1, 1),
        "casa": CASAS.get(chave),
    }


def _taxa_ausencia(faltas: int, sessoes: int) -> Optional[float]:
    return round(faltas / sessoes * 100, 1) if sessoes else None


@router.get("/ranking/politicians")
def ranking_parlamentares(
    casa: Optional[str] = Query("ALL", description="ALL, CAMARA ou SENADO"),
    ano_inicio: Optional[int] = Query(None, ge=1995, le=2100),
    ano_fim: Optional[int] = Query(None, ge=1995, le=2100),
    ordenar: str = Query("faltas", description="'faltas' (total), 'taxa' (percentual) ou 'nao_justificadas'"),
    limit: int = Query(30, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Parlamentares com mais ausências no período, com a taxa de ausência e os pontos IALP para comparar."""
    if ordenar not in {"faltas", "taxa", "nao_justificadas", "baixa_producao"}:
        raise HTTPException(
            status_code=422, detail="Ordenação inválida. Use faltas, taxa, nao_justificadas ou baixa_producao."
        )
    params = _parametros(casa, ano_inicio, ano_fim)
    ordem = {
        "faltas": "a.faltas DESC, a.sessoes DESC",
        "taxa": "a.faltas::numeric / a.sessoes DESC, a.faltas DESC",
        "nao_justificadas": "a.faltas_nao_justificadas DESC, a.faltas DESC",
        # taxa de ausência atenuada pela produção: quanto mais pontos IALP, menor o índice
        "baixa_producao": "(a.faltas::numeric / a.sessoes * 100 / (100 + a.pontos_ialp)) DESC, a.faltas DESC",
    }[ordenar]
    # a taxa só é comparável com amostra mínima de dias
    minimo = f"WHERE a.sessoes >= {MIN_DIAS_PARA_TAXA}" if ordenar in {"taxa", "baixa_producao"} else ""
    linhas = (
        db.execute(
            text(
                f"""
                WITH base AS ({_BASE}),
                agg AS (
                    SELECT g.*, (SELECT coalesce(sum(v.pontos_ialp), 0) FROM leg.vw_autoria_pontuada v
                                  WHERE v.pessoa_id = g.pessoa_id) AS pontos_ialp
                    FROM (SELECT pessoa_id, {_AGREGADOS} FROM base GROUP BY pessoa_id) g
                )
                SELECT pe.uid, pe.nome_exibicao, fm.url_origem AS foto, a.*,
                       (SELECT cp.canonico_sigla FROM core.mandato m
                          JOIN core.vw_partido_canonico cp ON cp.id = m.partido_id
                         WHERE m.pessoa_id = a.pessoa_id ORDER BY m.inicio DESC LIMIT 1) AS partido,
                       (SELECT string_agg(DISTINCT c.codigo, ',') FROM base b
                          JOIN ref.casa_legislativa c ON c.codigo = b.casa WHERE b.pessoa_id = a.pessoa_id) AS casas
                FROM agg a
                JOIN core.pessoa pe ON pe.id = a.pessoa_id
                LEFT JOIN core.midia fm ON fm.id = pe.foto_midia_id
                {minimo}
                ORDER BY {ordem}, pe.nome_exibicao
                LIMIT :limite
                """
            ),
            {**params, "limite": limit},
        )
        .mappings()
        .all()
    )
    return {
        "criterio": ordenar,
        "minimo_dias_para_taxa": MIN_DIAS_PARA_TAXA,
        "itens": [
            {
                "politico_id": str(r["uid"]),
                "nome_eleitoral": r["nome_exibicao"],
                "foto_url": r["foto"],
                "partido_sigla": r["partido"] or "S.PART.",
                "casas": (r["casas"] or "").split(","),
                "dias_registrados": r["sessoes"],
                "presencas": r["presencas"],
                "faltas": r["faltas"],
                "faltas_justificadas": r["faltas_justificadas"],
                "faltas_nao_justificadas": r["faltas_nao_justificadas"],
                "faltas_inferidas": r["faltas_inferidas"],
                "taxa_ausencia_pct": _taxa_ausencia(r["faltas"], r["sessoes"]),
                "pontos_ialp": round(float(r["pontos_ialp"]), 1),
                "indice_baixa_producao": (
                    round(r["faltas"] / r["sessoes"] * 100 / (100 + float(r["pontos_ialp"])), 2)
                    if r["sessoes"]
                    else None
                ),
            }
            for r in linhas
        ],
        "aviso": (
            "Câmara: antes de 2020 a fonte não publica falta nem justificativa; as faltas de 2003 a 2019 são "
            "inferidas (parlamentar em exercício sem presença em dia de sessão deliberativa). Antes de 2003 não há "
            "faltas. Senado: presença derivada das votações nominais."
        ),
    }


@router.get("/ranking/parties")
def ranking_partidos(
    casa: Optional[str] = Query("ALL", description="ALL, CAMARA ou SENADO"),
    ano_inicio: Optional[int] = Query(None, ge=1995, le=2100),
    ano_fim: Optional[int] = Query(None, ge=1995, le=2100),
    db: Session = Depends(get_db),
):
    """Partidos por taxa de ausência. O partido é o do mandato na data (sigla vigente da linhagem)."""
    params = _parametros(casa, ano_inicio, ano_fim)
    linhas = (
        db.execute(
            text(
                f"""
                WITH base AS ({_BASE}),
                com_partido AS (
                    SELECT b.*, coalesce(b.partido_dia, mp.partido_id, m.partido_id) AS partido_id
                    FROM base b
                    LEFT JOIN core.mandato m ON m.id = b.mandato_id
                    LEFT JOIN core.mandato_partido mp ON mp.mandato_id = b.mandato_id AND mp.periodo @> b.data_sessao
                ),
                por_partido AS (
                    SELECT cp.canonico_sigla AS sigla, {_AGREGADOS.replace('tipo_codigo', 'x.tipo_codigo')},
                           count(DISTINCT x.pessoa_id) AS parlamentares
                    FROM com_partido x JOIN core.vw_partido_canonico cp ON cp.id = x.partido_id
                    GROUP BY cp.canonico_sigla
                )
                SELECT *, (SELECT count(*) FROM com_partido WHERE partido_id IS NULL) AS sem_partido
                FROM por_partido WHERE sessoes >= :minimo ORDER BY faltas::numeric / sessoes DESC, sigla
                """
            ),
            {**params, "minimo": MIN_DIAS_PARTIDO},
        )
        .mappings()
        .all()
    )
    return {
        "itens": [
            {
                "sigla": r["sigla"],
                "parlamentares": r["parlamentares"],
                "dias_registrados": r["sessoes"],
                "faltas": r["faltas"],
                "faltas_justificadas": r["faltas_justificadas"],
                "faltas_nao_justificadas": r["faltas_nao_justificadas"],
                "faltas_inferidas": r["faltas_inferidas"],
                "taxa_ausencia_pct": _taxa_ausencia(r["faltas"], r["sessoes"]),
            }
            for r in linhas
        ],
        "dias_sem_partido_identificado": int(linhas[0]["sem_partido"]) if linhas else 0,
        "aviso": (
            "Taxa = faltas ÷ dias registrados de todos os parlamentares do partido no período. Dias de parlamentares "
            "sem partido identificado no mandato ficam de fora (informados em dias_sem_partido_identificado)."
        ),
    }


@router.get("/coverage")
def cobertura_presenca(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """Cobertura anual da base de presença por Casa e origem, para auditar lacunas."""
    linhas = db.execute(
        text(
            """
            SELECT extract(year FROM p.data_sessao)::int AS ano, c.codigo AS casa, coalesce(f.codigo, 'SEM_FONTE') AS fonte,
                   count(*) AS registros, count(DISTINCT p.data_sessao) AS dias, count(DISTINCT p.pessoa_id) AS parlamentares,
                   count(*) FILTER (WHERE p.tipo_codigo <> 'PRESENTE') AS faltas
            FROM leg.presenca p JOIN ref.casa_legislativa c ON c.id = p.casa_id LEFT JOIN etl.fonte f ON f.id = p.fonte_id
            GROUP BY 1, 2, 3 ORDER BY 1, 2, 3
            """
        )
    ).mappings()
    return [dict(r) for r in linhas]
