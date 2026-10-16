"""Desempenho econômico de cada mandato presidencial, calculado de `eco` (séries oficiais) e `core` (mandatos)."""

import math
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.services.periodos import Serie, composto, do_mandato, intervalo_de_anos, nome_do_mandato
from app.services.presidencia_service import mandatos_presidenciais, marcos_por_mandato, ministros_da_economia
from sqlalchemy import text
from sqlalchemy.orm import Session

_SERIES_SQL = text(
    """
    SELECT s.codigo, o.referencia, o.valor
    FROM eco.observacao o JOIN eco.serie s ON s.id = o.serie_id
    WHERE o.uf IS NULL AND s.codigo = ANY(:codigos)
    ORDER BY s.codigo, o.referencia
    """
)

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


def _media(valores: List[float], casas: int) -> Optional[float]:
    return round(sum(valores) / len(valores), casas) if valores else None


def _extremos(valores: List[float]) -> Tuple[Optional[float], Optional[float]]:
    return (valores[0], valores[-1]) if valores else (None, None)


class _Anuais:
    """Séries anuais indexadas por ano, lidas uma vez e reaproveitadas por todos os mandatos."""

    def __init__(self, series: Dict[str, Serie]) -> None:
        self.pib = _por_ano(series["PIB_CRESC_REAL"])
        self.desemprego = _por_ano(series["DESEMPREGO_ANUAL"])
        self.desmatamento = _por_ano(series["DESMATAMENTO_AMAZONIA"])
        self.fome = _por_ano(series["INSEGURANCA_ALIMENTAR_PCT"])
        self.homicidios = _por_ano(series["HOMICIDIOS_TAXA"])
        self.ipca = _por_ano(series["IPCA_ACUM_ANO"])
        self.cambio_medio = _por_ano(series["CAMBIO_MEDIO_ANO"])
        self.cambio_fechamento = _por_ano(series["CAMBIO_FECHAMENTO_ANO"])
        self.salario = _por_ano(series["SALARIO_MINIMO"])

    @staticmethod
    def dos_anos(por_ano: Dict[int, float], anos: List[int]) -> List[float]:
        return [por_ano[a] for a in anos if a in por_ano]


def valores_anuais(anuais: _Anuais, anos: List[int]) -> List[Dict[str, Any]]:
    """Trajetória ano a ano do mandato; ano sem fonte oficial fica null."""
    return [
        {
            "ano": a,
            "pib_crescimento_real_pct": anuais.pib.get(a),
            "crescimento_pib_percentual": anuais.pib.get(a),
            "ipca_acumulado_ano_pct": anuais.ipca.get(a),
            "inflacao_anual_ipca": anuais.ipca.get(a),
            "cotacao_dolar_fechamento": anuais.cambio_fechamento.get(a),
            "cambio_dolar_medio": anuais.cambio_medio.get(a),
            "salario_minimo": anuais.salario.get(a),
            "salario_minimo_nominal_brl": anuais.salario.get(a),
            "taxa_desemprego_anual": anuais.desemprego.get(a),
            "taxa_homicidios": anuais.homicidios.get(a),
            "taxa_feminicidios": None,
            "taxa_desmatamento_amazonia": anuais.desmatamento.get(a),
            "inseguranca_alimentar_pct": anuais.fome.get(a),
        }
        for a in anos
    ]


def indicadores_do_mandato(
    series: Dict[str, Serie], anuais: _Anuais, inicio: date, fim_exclusivo: date, anos: List[int]
) -> Dict[str, Any]:
    """Indicadores do período do mandato. Só usa dados da fonte: o que não existe fica None, nunca zero."""
    ipca = composto([v for _, v in do_mandato(series["IPCA_MENSAL"], inicio, fim_exclusivo)])
    cambio = do_mandato(series["CAMBIO_MENSAL"], inicio, fim_exclusivo)
    divida = do_mandato(series["DIVIDA_LIQUIDA_PIB_MENSAL"], inicio, fim_exclusivo)
    salario = do_mandato(series["SALARIO_MINIMO_MENSAL"], inicio, fim_exclusivo)
    cambio_ini, cambio_fim = _extremos([v for _, v in cambio])
    divida_ini, divida_fim = _extremos([v for _, v in divida])
    sal_ini, sal_fim = _extremos([v for _, v in salario])
    pib = anuais.dos_anos(anuais.pib, anos)
    pib_acumulado = composto(pib)
    desemprego = anuais.dos_anos(anuais.desemprego, anos)
    desmatamento = anuais.dos_anos(anuais.desmatamento, anos)
    fome = anuais.dos_anos(anuais.fome, anos)
    homicidios = anuais.dos_anos(anuais.homicidios, anos)
    desemp_ini, desemp_fim = _extremos(desemprego)
    fome_ini, fome_fim = _extremos(fome)
    homic_ini, homic_fim = _extremos(homicidios)
    return {
        "ipca_acumulado_pct": ipca,
        "ipca_pos_real_pct": ipca,
        "pib_crescimento_acumulado_pct": None if pib_acumulado is None else round(pib_acumulado, 2),
        "pib_medio_anual_pct": _media(pib, 2),
        "cambio_inicial_usd_brl": cambio_ini,
        "cambio_final_usd_brl": cambio_fim,
        "cambio_variacao_pct": round((cambio_fim / cambio_ini - 1.0) * 100.0, 2) if cambio_ini and cambio_fim else None,
        "divida_liquida_inicial_pct_pib": divida_ini,
        "divida_liquida_final_pct_pib": divida_fim,
        "divida_liquida_delta_pct": (
            round(divida_fim - divida_ini, 2) if divida_ini is not None and divida_fim is not None else None
        ),
        "salario_minimo_inicial_brl": sal_ini,
        "salario_minimo_final_brl": sal_fim,
        "salario_minimo_inicial_usd": _usd(sal_ini, cambio_ini),
        "salario_minimo_final_usd": _usd(sal_fim, cambio_fim),
        "desemprego_inicial_pct": desemp_ini,
        "desemprego_final_pct": desemp_fim,
        "desemprego_medio_pct": _media(desemprego, 2),
        "desmatamento_acumulado_km2": round(sum(desmatamento), 1) if desmatamento else None,
        "desmatamento_medio_anual_km2": _media(desmatamento, 1),
        "fome_inicial_pct": fome_ini,
        "fome_final_pct": fome_fim,
        "fome_media_pct": _media(fome, 2),
        "homicidios_inicial": homic_ini,
        "homicidios_final": homic_fim,
        "homicidios_medio": _media(homicidios, 2),
        "feminicidios_inicial": None,
        "feminicidios_final": None,
        "feminicidios_medio": None,
    }


def matriz_de_mandatos(db: Session, hoje: Optional[date] = None) -> List[Dict[str, Any]]:
    """
    Uma linha por mandato presidencial, com os indicadores do período e a trajetória anual.

    Os indicadores anuais usam só os anos do mandato que a fonte já publicou: num mandato em curso, o acumulado cobre
    os anos disponíveis (o campo `anos_cobertos` mostra o intervalo do mandato, não o dos dados).
    """
    hoje = hoje or date.today()
    series = _carregar_series(db)
    anuais = _Anuais(series)
    ministros = ministros_da_economia(db)
    marcos = marcos_por_mandato(db)
    ultimo_ano = max([d.year for d, _ in series["IPCA_MENSAL"]] or [hoje.year])

    resultado: List[Dict[str, Any]] = []
    for r in mandatos_presidenciais(db):
        inicio, fim = r["inicio"], r["fim"]
        fim_exclusivo = fim if fim is not None else hoje + timedelta(days=1)
        ano_ini, ano_fim = intervalo_de_anos(inicio, fim, ultimo_ano)
        ano_fim = min(ano_fim, hoje.year)
        anos = list(range(ano_ini, ano_fim + 1))
        resultado.append(
            {
                "id_mandato": r["slug"],
                "presidente": nome_do_mandato(r["nome_exibicao"], r["rotulo"]),
                "partido": r["partido_sigla"],
                "data_inicio": inicio.isoformat(),
                "data_fim": (fim or hoje).isoformat(),
                "status_mandato": r["status"],
                "anos_cobertos": f"{ano_ini} - {ano_fim}",
                **indicadores_do_mandato(series, anuais, inicio, fim_exclusivo, anos),
                "valores_anuais": valores_anuais(anuais, anos),
                "ministros_fazenda_principais": list(dict.fromkeys(m["nome"] for m in ministros.get(r["id"], []))),
                "marcos_economicos_principais": marcos.get(r["id"], [])[:2],
                "vice_presidente": r["vice_texto"],
                "motivo_inicio": r["motivo_inicio"],
            }
        )
    return [{k: _limpo(v) if isinstance(v, float) else v for k, v in linha.items()} for linha in resultado]
