"""Evolução do IPPM por partido ao longo dos anos, calculada em lote (uma consulta de cadeiras e uma de produção).

Usa as mesmas regras do ranking de um ano (party_productivity_service): pontos do IALP dos projetos apresentados no
ano ÷ cadeiras-dia do partido no mesmo ano. Anos sem cadeiras registradas ficam sem valor (nada é inventado).
"""

from datetime import date
from typing import Any, Dict, List, Optional

from app.services.party_productivity_service import STATUS_APROVADOS
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

PRIMEIRO_ANO_COM_CADEIRAS = 2003  # a Câmara só publica posse, licença e troca de partido a partir da 52ª legislatura
MAX_ANOS = 40
CARGOS_POR_CASA = {"CAMARA": ["DEPUTADO_FEDERAL"], "SENADO": ["SENADOR"]}

_CADEIRAS_SQL = text(
    """
    WITH anos AS (
        SELECT a AS ano, make_date(a, 1, 1) AS ini, least(make_date(a, 12, 31), current_date) AS fim
        FROM generate_series(CAST(:ano_inicio AS int), CAST(:ano_fim AS int)) a
    ),
    exercicio AS (
        SELECT m.pessoa_id, pa.canonico_id AS partido_id, s.periodo * mp.periodo AS periodo
        FROM core.mandato_situacao s
        JOIN core.mandato m ON m.id = s.mandato_id
        JOIN ref.cargo c ON c.id = m.cargo_id
        JOIN core.mandato_partido mp ON mp.mandato_id = m.id
        JOIN core.vw_partido_canonico pa ON pa.id = mp.partido_id
        WHERE s.situacao IN ('EXERCICIO', 'SUPLENCIA') AND c.codigo = ANY(:cargos)
        UNION ALL
        SELECT m.pessoa_id, pa.canonico_id, s.periodo * f.periodo
        FROM core.mandato_situacao s
        JOIN core.mandato m ON m.id = s.mandato_id
        JOIN ref.cargo c ON c.id = m.cargo_id
        JOIN core.filiacao f ON f.pessoa_id = m.pessoa_id
        JOIN core.vw_partido_canonico pa ON pa.id = f.partido_id
        WHERE s.situacao IN ('EXERCICIO', 'SUPLENCIA') AND c.codigo = ANY(:cargos)
          AND NOT EXISTS (SELECT 1 FROM core.mandato_partido x WHERE x.mandato_id = m.id)
        UNION ALL
        SELECT m.pessoa_id, pa.canonico_id, s.periodo
        FROM core.mandato_situacao s
        JOIN core.mandato m ON m.id = s.mandato_id
        JOIN ref.cargo c ON c.id = m.cargo_id
        JOIN core.vw_partido_canonico pa ON pa.id = m.partido_id
        WHERE s.situacao IN ('EXERCICIO', 'SUPLENCIA') AND c.codigo = ANY(:cargos)
          AND NOT EXISTS (SELECT 1 FROM core.mandato_partido x WHERE x.mandato_id = m.id)
          AND NOT EXISTS (SELECT 1 FROM core.filiacao x WHERE x.pessoa_id = m.pessoa_id)
    )
    SELECT a.ano, e.partido_id, count(DISTINCT e.pessoa_id) AS parlamentares,
           sum(upper(x.i) - lower(x.i)) AS dias, max(a.fim - a.ini + 1) AS dias_periodo
    FROM anos a
    JOIN exercicio e ON NOT isempty(e.periodo)
    CROSS JOIN LATERAL (SELECT e.periodo * daterange(a.ini, a.fim, '[]') AS i) x
    WHERE NOT isempty(x.i)
    GROUP BY a.ano, e.partido_id
    """
)

_PRODUCAO_SQL = text(
    """
    SELECT extract(year FROM v.data_apresentacao)::int AS ano, pc.canonico_id AS partido_id,
           sum(v.pontos_ialp) AS ialp,
           count(DISTINCT v.proposicao_id) FILTER (
               WHERE v.tipo_autoria = 'AUTOR_PRINCIPAL' AND v.categoria_proposicao = 'PROJETO') AS projetos,
           count(DISTINCT v.proposicao_id) FILTER (
               WHERE v.tipo_autoria = 'AUTOR_PRINCIPAL' AND v.categoria_proposicao = 'PROJETO'
                 AND v.status_codigo IN :aprovados) AS aprovados
    FROM leg.vw_autoria_pontuada v
    JOIN core.vw_partido_canonico pc ON pc.id = v.partido_id
    WHERE v.data_apresentacao BETWEEN make_date(CAST(:ano_inicio AS int), 1, 1) AND make_date(CAST(:ano_fim AS int), 12, 31)
      AND (CAST(:casa AS text) IS NULL OR (:casa = 'CAMARA' AND v.da_camara) OR (:casa = 'SENADO' AND v.do_senado))
    GROUP BY 1, 2
    """
).bindparams(bindparam("aprovados", expanding=True))


def calculate_party_ippm_evolution(
    db: Session,
    ano_inicio: Optional[int] = None,
    ano_fim: Optional[int] = None,
    casa: Optional[str] = "ALL",
) -> Dict[str, Any]:
    hoje = date.today()
    inicio = max(ano_inicio or PRIMEIRO_ANO_COM_CADEIRAS, 1995)
    fim = min(ano_fim or hoje.year, hoje.year)
    fim = max(fim, inicio)
    if fim - inicio + 1 > MAX_ANOS:
        inicio = fim - MAX_ANOS + 1
    casa_limpa = (casa or "ALL").upper().strip()
    casa_param = casa_limpa if casa_limpa in CARGOS_POR_CASA else None
    cargos = CARGOS_POR_CASA.get(casa_limpa) or [c for lista in CARGOS_POR_CASA.values() for c in lista]

    cadeiras = {
        (r.ano, r.partido_id): (int(r.parlamentares), float(r.dias), int(r.dias_periodo))
        for r in db.execute(_CADEIRAS_SQL, {"ano_inicio": inicio, "ano_fim": fim, "cargos": cargos})
    }
    producao = {
        (r.ano, r.partido_id): (float(r.ialp or 0), int(r.projetos), int(r.aprovados))
        for r in db.execute(
            _PRODUCAO_SQL,
            {"ano_inicio": inicio, "ano_fim": fim, "casa": casa_param, "aprovados": list(STATUS_APROVADOS)},
        )
    }
    partidos = {
        r.id: r
        for r in db.execute(
            text(
                "SELECT id, sigla, nome, cor_hex FROM core.vw_partido "
                "WHERE sigla <> 'S.PART.' AND linhagem_id IS NULL"
            )
        )
    }

    anos = list(range(inicio, fim + 1))
    series: Dict[int, List[Dict[str, Any]]] = {}
    for (ano, partido_id), (parlamentares, dias, dias_periodo) in cadeiras.items():
        if partido_id not in partidos:
            continue
        ialp, projetos, aprovados = producao.get((ano, partido_id), (0.0, 0, 0))
        cadeiras_dia = max(0.1, round(dias / max(1, dias_periodo), 2))
        series.setdefault(partido_id, []).append(
            {
                "ano": ano,
                "ippm": round(round(ialp, 2) / cadeiras_dia, 2),
                "pontuacao_bruta_ialp": round(ialp, 2),
                "cadeiras_dia_equivalentes": cadeiras_dia,
                "parlamentares": parlamentares,
                "projetos_apresentados": projetos,
                "projetos_aprovados": aprovados,
                "taxa_eficacia_pct": round(aprovados / max(1, projetos) * 100.0, 1),
            }
        )

    resultado = []
    for partido_id, pontos in series.items():
        pontos.sort(key=lambda p: p["ano"])
        info = partidos[partido_id]
        resultado.append(
            {
                "sigla": info.sigla,
                "nome_completo": info.nome,
                "cor_hex": info.cor_hex or "#64748b",
                "serie": pontos,
            }
        )
    resultado.sort(key=lambda p: (p["serie"][-1]["ano"], p["serie"][-1]["ippm"]), reverse=True)
    return {"periodo": {"ano_inicio": inicio, "ano_fim": fim, "casa": casa_limpa}, "anos": anos, "partidos": resultado}
