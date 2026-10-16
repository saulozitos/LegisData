"""Desempenho econômico de cada mandato presidencial, calculado de `eco` (séries oficiais) e `core` (mandatos)."""

import math
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.services.economia_service import intervalo_de_anos
from sqlalchemy import text
from sqlalchemy.orm import Session

_MANDATOS_SQL = text(
    """
    SELECT m.id, mp.slug, mp.rotulo, mp.status, mp.vice_texto, mp.motivo_inicio, m.inicio, m.fim,
           pe.nome_exibicao, pt.sigla AS partido
    FROM core.mandato_presidencial mp
    JOIN core.mandato m ON m.id = mp.mandato_id
    JOIN core.pessoa pe ON pe.id = m.pessoa_id
    LEFT JOIN core.vw_partido pt ON pt.id = m.partido_id
    ORDER BY m.inicio
    """
)

_SERIES_SQL = text(
    """
    SELECT s.codigo, o.referencia, o.valor
    FROM eco.observacao o JOIN eco.serie s ON s.id = o.serie_id
    WHERE o.uf IS NULL AND s.codigo = ANY(:codigos)
    ORDER BY s.codigo, o.referencia
    """
)

_MINISTROS_SQL = text(
    """
    SELECT m.nomeado_por_mandato_id AS mandato_id, pe.nome_exibicao
    FROM core.mandato m JOIN core.pessoa pe ON pe.id = m.pessoa_id
    WHERE m.funcao_destaque = 'ECONOMIA' AND m.nomeado_por_mandato_id IS NOT NULL
    ORDER BY m.nomeado_por_mandato_id, m.inicio
    """
)

_MARCOS_SQL = text("SELECT mandato_id, texto FROM core.marco_governo ORDER BY mandato_id, ordem")

CODIGOS = [
    "IPCA_MENSAL",
    "CAMBIO_MENSAL",
    "DIVIDA_LIQUIDA_PIB_MENSAL",
    "SALARIO_MINIMO_MENSAL",
    "PIB_CRESC_REAL",
    "DESEMPREGO_ANUAL",
    "DESMATAMENTO_AMAZONIA",
    "INSEGURANCA_ALIMENTAR_PCT",
    "HOMICIDIOS_TAXA",
    "IPCA_ACUM_ANO",
    "CAMBIO_MEDIO_ANO",
    "CAMBIO_FECHAMENTO_ANO",
    "SALARIO_MINIMO",
]

Serie = List[Tuple[date, float]]


def composto(taxas_pct: List[float]) -> Optional[float]:
    if not taxas_pct:
        return None
    fator = 1.0
    for taxa in taxas_pct:
        fator *= 1.0 + taxa / 100.0
    return round((fator - 1.0) * 100.0, 4)


def _media(valores: List[float], casas: int) -> Optional[float]:
    return round(sum(valores) / len(valores), casas) if valores else None


def do_mandato(serie: Serie, inicio: date, fim_exclusivo: date) -> Serie:
    """Meses do mandato: cada mês vale para quem estava no cargo no meio dele (dia 15)."""
    return [(d, v) for d, v in serie if inicio <= d + timedelta(days=14) < fim_exclusivo]


def _por_ano(serie: Serie) -> Dict[int, float]:
    return {d.year: v for d, v in serie}


def _carregar_series(db: Session) -> Dict[str, Serie]:
    series: Dict[str, Serie] = {codigo: [] for codigo in CODIGOS}
    for codigo, referencia, valor in db.execute(_SERIES_SQL, {"codigos": CODIGOS}):
        series[codigo].append((referencia, float(valor)))
    return series


def _usd(reais: Optional[float], cambio: Optional[float]) -> Optional[float]:
    return round(reais / cambio, 2) if reais and cambio and cambio > 0 else None


def _limpo(valor: Optional[float]) -> Optional[float]:
    return None if valor is None or not math.isfinite(valor) else valor


def matriz_de_mandatos(db: Session, hoje: Optional[date] = None) -> List[Dict[str, Any]]:
    """Uma linha por mandato presidencial, com os indicadores do período e a trajetória anual."""
    hoje = hoje or date.today()
    series = _carregar_series(db)
    ministros: Dict[int, List[str]] = {}
    for mandato_id, nome in db.execute(_MINISTROS_SQL):
        ministros.setdefault(mandato_id, [])
        if nome not in ministros[mandato_id]:
            ministros[mandato_id].append(nome)
    marcos: Dict[int, List[str]] = {}
    for mandato_id, texto in db.execute(_MARCOS_SQL):
        marcos.setdefault(mandato_id, []).append(texto)

    pib, desemprego = _por_ano(series["PIB_CRESC_REAL"]), _por_ano(series["DESEMPREGO_ANUAL"])
    desmatamento, fome = _por_ano(series["DESMATAMENTO_AMAZONIA"]), _por_ano(series["INSEGURANCA_ALIMENTAR_PCT"])
    homicidios = _por_ano(series["HOMICIDIOS_TAXA"])
    ipca_ano, cambio_medio = _por_ano(series["IPCA_ACUM_ANO"]), _por_ano(series["CAMBIO_MEDIO_ANO"])
    cambio_fechamento, salario_ano = _por_ano(series["CAMBIO_FECHAMENTO_ANO"]), _por_ano(series["SALARIO_MINIMO"])
    ultimo_ano = max([d.year for d, _ in series["IPCA_MENSAL"]] or [hoje.year])

    resultado: List[Dict[str, Any]] = []
    for r in db.execute(_MANDATOS_SQL).mappings():
        inicio, fim = r["inicio"], r["fim"]
        fim_exclusivo = fim if fim is not None else hoje + timedelta(days=1)
        ano_ini, ano_fim = intervalo_de_anos(inicio, fim, ultimo_ano)
        ano_fim = min(ano_fim, hoje.year)
        anos = list(range(ano_ini, ano_fim + 1))

        ipca = do_mandato(series["IPCA_MENSAL"], inicio, fim_exclusivo)
        cambio = do_mandato(series["CAMBIO_MENSAL"], inicio, fim_exclusivo)
        divida = do_mandato(series["DIVIDA_LIQUIDA_PIB_MENSAL"], inicio, fim_exclusivo)
        salario = do_mandato(series["SALARIO_MINIMO_MENSAL"], inicio, fim_exclusivo)
        ipca_acumulado = composto([v for _, v in ipca])
        pib_anos = [pib[a] for a in anos if a in pib]
        pib_acumulado = composto(pib_anos)
        cambio_ini, cambio_fim = (cambio[0][1], cambio[-1][1]) if cambio else (None, None)
        divida_ini, divida_fim = (divida[0][1], divida[-1][1]) if divida else (None, None)
        sal_ini, sal_fim = (salario[0][1], salario[-1][1]) if salario else (None, None)
        desemp = [desemprego[a] for a in anos if a in desemprego]
        desmat = [desmatamento[a] for a in anos if a in desmatamento]
        fomes = [fome[a] for a in anos if a in fome]
        homic = [homicidios[a] for a in anos if a in homicidios]

        resultado.append(
            {
                "id_mandato": r["slug"],
                "presidente": f"{r['nome_exibicao']} ({r['rotulo']})" if r["rotulo"] else r["nome_exibicao"],
                "partido": r["partido"],
                "data_inicio": inicio.isoformat(),
                "data_fim": (fim or hoje).isoformat(),
                "status_mandato": r["status"],
                "anos_cobertos": f"{ano_ini} - {ano_fim}",
                "ipca_acumulado_pct": ipca_acumulado,
                "ipca_pos_real_pct": ipca_acumulado,
                "pib_crescimento_acumulado_pct": None if pib_acumulado is None else round(pib_acumulado, 2),
                "pib_medio_anual_pct": _media(pib_anos, 2),
                "cambio_inicial_usd_brl": cambio_ini,
                "cambio_final_usd_brl": cambio_fim,
                "cambio_variacao_pct": (
                    round((cambio_fim / cambio_ini - 1.0) * 100.0, 2) if cambio_ini and cambio_fim else None
                ),
                "divida_liquida_inicial_pct_pib": divida_ini,
                "divida_liquida_final_pct_pib": divida_fim,
                "divida_liquida_delta_pct": (
                    round(divida_fim - divida_ini, 2) if divida_ini is not None and divida_fim is not None else None
                ),
                "salario_minimo_inicial_brl": sal_ini,
                "salario_minimo_final_brl": sal_fim,
                "salario_minimo_inicial_usd": _usd(sal_ini, cambio_ini),
                "salario_minimo_final_usd": _usd(sal_fim, cambio_fim),
                "desemprego_inicial_pct": desemp[0] if desemp else None,
                "desemprego_final_pct": desemp[-1] if desemp else None,
                "desemprego_medio_pct": _media(desemp, 2),
                "desmatamento_acumulado_km2": round(sum(desmat), 1) if desmat else None,
                "desmatamento_medio_anual_km2": _media(desmat, 1),
                "fome_inicial_pct": fomes[0] if fomes else None,
                "fome_final_pct": fomes[-1] if fomes else None,
                "fome_media_pct": _media(fomes, 2),
                "homicidios_inicial": homic[0] if homic else None,
                "homicidios_final": homic[-1] if homic else None,
                "homicidios_medio": _media(homic, 2),
                "feminicidios_inicial": None,
                "feminicidios_final": None,
                "feminicidios_medio": None,
                "valores_anuais": [
                    {
                        "ano": a,
                        "pib_crescimento_real_pct": pib.get(a),
                        "crescimento_pib_percentual": pib.get(a),
                        "ipca_acumulado_ano_pct": ipca_ano.get(a),
                        "inflacao_anual_ipca": ipca_ano.get(a),
                        "cotacao_dolar_fechamento": cambio_fechamento.get(a),
                        "cambio_dolar_medio": cambio_medio.get(a),
                        "salario_minimo": salario_ano.get(a),
                        "salario_minimo_nominal_brl": salario_ano.get(a),
                        "taxa_desemprego_anual": desemprego.get(a),
                        "taxa_homicidios": homicidios.get(a),
                        "taxa_feminicidios": None,
                        "taxa_desmatamento_amazonia": desmatamento.get(a),
                        "inseguranca_alimentar_pct": fome.get(a),
                    }
                    for a in anos
                ],
                "ministros_fazenda_principais": ministros.get(r["id"], []),
                "marcos_economicos_principais": marcos.get(r["id"], [])[:2],
                "vice_presidente": r["vice_texto"],
                "motivo_inicio": r["motivo_inicio"],
            }
        )
    for linha in resultado:
        for chave, valor in list(linha.items()):
            if isinstance(valor, float):
                linha[chave] = _limpo(valor)
    return resultado
