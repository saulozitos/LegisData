"""Ranking de ausências no Congresso (parlamentares e partidos), lido de `leg.vw_presenca_conhecida`.

Só entram dias em que a falta é conhecida (`ref.cobertura_presenca`): Senado em todo o período; Câmara a partir de
2003-02-03, quando antes disso a fonte publica apenas presença. Falta oficial (justificada ou não) e falta inferida
(Câmara antes de 2020) aparecem separadas; categoria que o recorte não permite saber vem como None, nunca como zero.
Os pontos IALP vêm de `leg.mv_autoria_pontuada_unica` e dão o contraste entre faltar e produzir.
"""

from datetime import date
from typing import Any, Dict, List, Optional

from app.core.errors import ErroDeDominio
from app.services.derivados_service import garantir_atualizados
from sqlalchemy import text
from sqlalchemy.orm import Session

MIN_DIAS_PARA_TAXA = 20
MIN_DIAS_PARTIDO = 2000
CASAS = {"CAMARA": "CAMARA_DOS_DEPUTADOS", "SENADO": "SENADO_FEDERAL"}
ORDENACOES = ("faltas", "taxa", "nao_justificadas", "baixa_producao")
INICIO_DA_BASE = date(1995, 1, 1)
FIM_ABERTO = date(2100, 1, 1)

_RANKING_POLITICOS = text(
    """
    WITH agg AS (
        SELECT g.*,
               (SELECT coalesce(sum(v.pontos_ialp), 0) FROM leg.mv_autoria_pontuada_unica v
                 WHERE v.pessoa_id = g.pessoa_id AND v.data_apresentacao BETWEEN :pontos_inicio AND :fim) AS pontos_ialp
        FROM (
            SELECT b.pessoa_id,
                   count(*) AS sessoes,
                   count(*) FILTER (WHERE b.presente) AS presencas,
                   count(*) FILTER (WHERE NOT b.presente) AS faltas,
                   count(*) FILTER (WHERE b.justificada) AS faltas_justificadas,
                   count(*) FILTER (WHERE b.tipo_codigo = 'AUSENCIA_NAO_JUSTIFICADA') AS faltas_nao_justificadas,
                   count(*) FILTER (WHERE b.tipo_codigo = 'AUSENCIA_INFERIDA') AS faltas_inferidas,
                   count(*) FILTER (WHERE b.com_justificativa) AS dias_com_justificativa,
                   count(*) FILTER (WHERE b.na_inferencia) AS dias_na_inferencia,
                   string_agg(DISTINCT b.casa, ',') AS casas
            FROM leg.vw_presenca_conhecida b
            WHERE b.data_sessao BETWEEN :inicio AND :fim AND (CAST(:casa AS text) IS NULL OR b.casa = :casa)
            GROUP BY b.pessoa_id
        ) g
    ),
    pontuado AS (
        SELECT a.*, CASE WHEN a.sessoes > 0 THEN a.faltas::numeric / a.sessoes * 100 / (100 + a.pontos_ialp) END
                    AS indice_baixa_producao
        FROM agg a
    )
    SELECT pe.uid, pe.nome_exibicao, fm.url_origem AS foto, a.*,
           (SELECT pa.canonico_sigla FROM core.vw_partido_atual pa WHERE pa.pessoa_id = a.pessoa_id) AS partido
    FROM pontuado a
    JOIN core.pessoa pe ON pe.id = a.pessoa_id
    LEFT JOIN core.midia fm ON fm.id = pe.foto_midia_id
    WHERE (:ordem NOT IN ('taxa', 'baixa_producao') OR a.sessoes >= :minimo)
    ORDER BY CASE WHEN :ordem = 'faltas' THEN a.faltas END DESC NULLS LAST,
             CASE WHEN :ordem = 'taxa' THEN a.faltas::numeric / a.sessoes END DESC NULLS LAST,
             CASE WHEN :ordem = 'nao_justificadas' THEN a.faltas_nao_justificadas END DESC NULLS LAST,
             CASE WHEN :ordem = 'baixa_producao' THEN a.indice_baixa_producao END DESC NULLS LAST,
             a.faltas DESC, a.sessoes DESC, pe.nome_exibicao
    LIMIT :limite
    """
)

_RANKING_PARTIDOS = text(
    """
    WITH base AS (
        SELECT b.* FROM leg.vw_presenca_conhecida b
        WHERE b.data_sessao BETWEEN :inicio AND :fim AND (CAST(:casa AS text) IS NULL OR b.casa = :casa)
    ),
    por_partido AS (
        SELECT cp.canonico_sigla AS sigla,
               count(*) AS sessoes,
               count(*) FILTER (WHERE x.presente) AS presencas,
               count(*) FILTER (WHERE NOT x.presente) AS faltas,
               count(*) FILTER (WHERE x.justificada) AS faltas_justificadas,
               count(*) FILTER (WHERE x.tipo_codigo = 'AUSENCIA_NAO_JUSTIFICADA') AS faltas_nao_justificadas,
               count(*) FILTER (WHERE x.tipo_codigo = 'AUSENCIA_INFERIDA') AS faltas_inferidas,
               count(*) FILTER (WHERE x.com_justificativa) AS dias_com_justificativa,
               count(*) FILTER (WHERE x.na_inferencia) AS dias_na_inferencia,
               count(DISTINCT x.pessoa_id) AS parlamentares
        FROM base x JOIN core.vw_partido_canonico cp ON cp.id = x.partido_id
        GROUP BY cp.canonico_sigla
    )
    SELECT * FROM por_partido WHERE sessoes >= :minimo ORDER BY faltas::numeric / sessoes DESC, sigla
    """
)

_PARTIDOS_PENDENTES = text(
    """
    SELECT count(*) FILTER (WHERE b.partido_id IS NULL) AS sem_partido,
           count(*) FILTER (WHERE b.partido_origem = 'PRESENCA_PROXIMA') AS partido_aproximado
    FROM leg.vw_presenca_conhecida b
    WHERE b.data_sessao BETWEEN :inicio AND :fim AND (CAST(:casa AS text) IS NULL OR b.casa = :casa)
    """
)

_COBERTURA = text(
    """
    SELECT extract(year FROM p.data_sessao)::int AS ano, c.codigo AS casa, coalesce(f.codigo, 'SEM_FONTE') AS fonte,
           count(*) AS registros, count(DISTINCT p.data_sessao) AS dias, count(DISTINCT p.pessoa_id) AS parlamentares,
           count(*) FILTER (WHERE p.tipo_codigo <> 'PRESENTE') AS faltas
    FROM leg.presenca p JOIN ref.casa_legislativa c ON c.id = p.casa_id LEFT JOIN etl.fonte f ON f.id = p.fonte_id
    GROUP BY 1, 2, 3 ORDER BY 1, 2, 3
    """
)

AVISO_POLITICOS = (
    "Câmara: antes de 2020 a fonte não publica falta nem justificativa; as faltas de 2003 a 2019 são inferidas "
    "(parlamentar em exercício sem presença em dia de sessão deliberativa). Antes de 2003 não há faltas. Senado: "
    "presença derivada das votações nominais. Onde o período não permite saber (justificativa na Câmara antes de "
    "2020, falta inferida no Senado e na Câmara desde 2020) o valor vem vazio, não zero. Em períodos mistos, as "
    "justificadas e as não justificadas contam só os dias em que a fonte as informa."
)
AVISO_PARTIDOS = (
    "Taxa = faltas ÷ dias registrados de todos os parlamentares do partido no período. Dias de parlamentares sem "
    "nenhuma informação de partido ficam de fora (dias_sem_partido_identificado). O partido do dia vem da votação "
    "(Senado), do mandato ou da filiação; quando faltam as três, usa-se o da presença mais próxima do mesmo "
    "parlamentar (dias_com_partido_aproximado)."
)


def _parametros(casa: Optional[str], ano_inicio: Optional[int], ano_fim: Optional[int]) -> Dict[str, Any]:
    chave = (casa or "ALL").strip().upper()
    if chave != "ALL" and chave not in CASAS:
        raise ErroDeDominio(422, "Casa inválida. Use ALL, CAMARA ou SENADO.")
    if ano_inicio and ano_fim and ano_inicio > ano_fim:
        raise ErroDeDominio(422, "O ano inicial não pode ser maior que o final.")
    return {
        "inicio": date(ano_inicio, 1, 1) if ano_inicio else INICIO_DA_BASE,
        "fim": date(ano_fim, 12, 31) if ano_fim else FIM_ABERTO,
        "casa": CASAS.get(chave),
        # os pontos IALP acompanham o período pedido; sem ano inicial valem para toda a carreira
        "pontos_inicio": date(ano_inicio, 1, 1) if ano_inicio else date(1900, 1, 1),
    }


def _taxa_ausencia(faltas: int, sessoes: int) -> Optional[float]:
    return round(faltas / sessoes * 100, 1) if sessoes else None


def _contagens_por_categoria(r: Any) -> Dict[str, Optional[int]]:
    """Faltas por categoria; None quando o recorte não tem nenhum dia em que a fonte distinga a categoria."""
    informa_justificativa = r["dias_com_justificativa"] > 0
    return {
        "faltas_justificadas": r["faltas_justificadas"] if informa_justificativa else None,
        "faltas_nao_justificadas": r["faltas_nao_justificadas"] if informa_justificativa else None,
        "faltas_inferidas": r["faltas_inferidas"] if r["dias_na_inferencia"] > 0 else None,
    }


def ranking_parlamentares(
    db: Session, casa: Optional[str], ano_inicio: Optional[int], ano_fim: Optional[int], ordenar: str, limite: int
) -> Dict[str, Any]:
    """Parlamentares com mais ausências no período, com a taxa de ausência e os pontos IALP para comparar."""
    if ordenar not in ORDENACOES:
        raise ErroDeDominio(422, "Ordenação inválida. Use faltas, taxa, nao_justificadas ou baixa_producao.")
    parametros = _parametros(casa, ano_inicio, ano_fim)
    garantir_atualizados(db)
    linhas = (
        db.execute(_RANKING_POLITICOS, {**parametros, "ordem": ordenar, "minimo": MIN_DIAS_PARA_TAXA, "limite": limite})
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
                **_contagens_por_categoria(r),
                "taxa_ausencia_pct": _taxa_ausencia(r["faltas"], r["sessoes"]),
                "pontos_ialp": round(float(r["pontos_ialp"]), 1),
                "indice_baixa_producao": (
                    round(float(r["indice_baixa_producao"]), 2) if r["indice_baixa_producao"] is not None else None
                ),
            }
            for r in linhas
        ],
        "aviso": AVISO_POLITICOS,
    }


def ranking_partidos(
    db: Session, casa: Optional[str], ano_inicio: Optional[int], ano_fim: Optional[int]
) -> Dict[str, Any]:
    """Partidos por taxa de ausência. O partido é o do dia (sigla vigente da linhagem)."""
    parametros = _parametros(casa, ano_inicio, ano_fim)
    linhas = db.execute(_RANKING_PARTIDOS, {**parametros, "minimo": MIN_DIAS_PARTIDO}).mappings().all()
    pendentes = db.execute(_PARTIDOS_PENDENTES, parametros).mappings().one()
    return {
        "minimo_dias": MIN_DIAS_PARTIDO,
        "itens": [
            {
                "sigla": r["sigla"],
                "parlamentares": r["parlamentares"],
                "dias_registrados": r["sessoes"],
                "faltas": r["faltas"],
                **_contagens_por_categoria(r),
                "taxa_ausencia_pct": _taxa_ausencia(r["faltas"], r["sessoes"]),
            }
            for r in linhas
        ],
        "dias_sem_partido_identificado": int(pendentes["sem_partido"]),
        "dias_com_partido_aproximado": int(pendentes["partido_aproximado"]),
        "aviso": AVISO_PARTIDOS,
    }


def cobertura_presenca(db: Session) -> List[Dict[str, Any]]:
    """Cobertura anual da base de presença por Casa e origem, para auditar lacunas."""
    return [dict(r) for r in db.execute(_COBERTURA).mappings()]
