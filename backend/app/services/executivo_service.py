"""Painel do Executivo: mandatos presidenciais e indicadores mensais de fonte oficial (BCB e IBGE via `eco`)."""

from datetime import date, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.core.errors import ErroDeDominio
from app.services.mandato_economia_service import do_mandato
from sqlalchemy import text
from sqlalchemy.orm import Session

_MANDATOS_SQL = text(
    """
    SELECT m.uid, m.inicio, m.fim, pe.nome_exibicao, mp.rotulo, pt.sigla AS partido, mi.url_origem AS foto_url
    FROM core.mandato_presidencial mp
    JOIN core.mandato m ON m.id = mp.mandato_id
    JOIN core.pessoa pe ON pe.id = m.pessoa_id
    LEFT JOIN core.vw_partido pt ON pt.id = m.partido_id
    LEFT JOIN core.midia mi ON mi.id = pe.foto_midia_id
    ORDER BY m.inicio
    """
)

_SERIE_SQL = text(
    """
    SELECT o.referencia, o.valor
    FROM eco.observacao o JOIN eco.serie s ON s.id = o.serie_id
    WHERE s.codigo = :codigo AND o.uf IS NULL ORDER BY o.referencia
    """
)

# indicador devolvido -> série de `eco` (a inflação é calculada: acumulado em 12 meses do IPCA mensal)
INDICADORES = {
    "inflacao_ipca": "IPCA_MENSAL",
    "desemprego_pnad": "DESEMPREGO_PNADC_MENSAL",
    "cambio_usd_brl": "CAMBIO_MENSAL",
    "selic_meta": "SELIC_META",
}


def _nome(r: Any) -> str:
    return f"{r['nome_exibicao']} ({r['rotulo']})" if r["rotulo"] else r["nome_exibicao"]


def listar_mandatos(db: Session) -> List[Dict[str, Any]]:
    return [
        {
            "id": r["uid"],
            "nome": _nome(r),
            "inicio": r["inicio"],
            "fim": r["fim"],
            "partido": r["partido"] or "",
            "foto_url": r["foto_url"],
        }
        for r in db.execute(_MANDATOS_SQL).mappings()
    ]


def _mandato(db: Session, mandate_id: UUID) -> Dict[str, Any]:
    for r in db.execute(_MANDATOS_SQL).mappings():
        if r["uid"] == mandate_id:
            return dict(r)
    raise ErroDeDominio(404, "Mandato não encontrado.")


def acumulado_12_meses(serie: List[tuple]) -> List[tuple]:
    """IPCA acumulado nos 12 meses até cada mês; mês sem os 11 anteriores seguidos fica de fora."""
    por_mes = {(d.year, d.month): v for d, v in serie}
    resultado = []
    for d, _ in serie:
        fator, completo = 1.0, True
        for atras in range(12):
            indice = d.year * 12 + (d.month - 1) - atras
            valor = por_mes.get((indice // 12, indice % 12 + 1))
            if valor is None:
                completo = False
                break
            fator *= 1.0 + valor / 100.0
        if completo:
            resultado.append((d, round((fator - 1.0) * 100.0, 4)))
    return resultado


def _series_do_mandato(db: Session, inicio: date, fim: Optional[date]) -> Dict[str, List[tuple]]:
    fim_exclusivo = fim if fim is not None else date.today() + timedelta(days=1)
    series: Dict[str, List[tuple]] = {}
    for indicador, codigo in INDICADORES.items():
        bruta = [(r[0], float(r[1])) for r in db.execute(_SERIE_SQL, {"codigo": codigo})]
        if indicador == "inflacao_ipca":
            bruta = acumulado_12_meses(bruta)
        recorte = do_mandato(bruta, inicio, fim_exclusivo)
        if recorte:
            series[indicador] = recorte
    return series


def _estatisticas(valores: List[float]) -> Dict[str, float]:
    return {
        "primeiro": round(valores[0], 2),
        "ultimo": round(valores[-1], 2),
        "minimo": round(min(valores), 2),
        "maximo": round(max(valores), 2),
        "media": round(sum(valores) / len(valores), 2),
    }


def resumo_do_mandato(db: Session, mandate_id: UUID) -> Dict[str, Any]:
    mandato = _mandato(db, mandate_id)
    series = _series_do_mandato(db, mandato["inicio"], mandato["fim"])
    kpis: Dict[str, Any] = {chave: _estatisticas([v for _, v in pontos]) for chave, pontos in series.items()}
    if "inflacao_ipca" in kpis:
        ipca = kpis["inflacao_ipca"]
        ipca["variacao_pp"] = round(ipca["ultimo"] - ipca["primeiro"], 2)
    return {
        "mandate_id": str(mandate_id),
        "nome": _nome(mandato),
        "partido": mandato["partido"] or "",
        "inicio": mandato["inicio"].isoformat(),
        "fim": mandato["fim"].isoformat() if mandato["fim"] else None,
        "foto_url": mandato["foto_url"],
        "kpis": kpis,
        "total_meses": len(series.get("inflacao_ipca", [])),
    }


def indicadores_do_mandato(db: Session, mandate_id: UUID) -> List[Dict[str, Any]]:
    """Série mensal agrupada por data, pronta para o gráfico; mês sem um indicador não traz a chave."""
    mandato = _mandato(db, mandate_id)
    por_data: Dict[str, Dict[str, Any]] = {}
    for chave, pontos in _series_do_mandato(db, mandato["inicio"], mandato["fim"]).items():
        for referencia, valor in pontos:
            por_data.setdefault(referencia.isoformat(), {"data": referencia.isoformat()})[chave] = valor
    return [por_data[data] for data in sorted(por_data)]
