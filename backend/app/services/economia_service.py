"""Séries econômicas anuais e mensais lidas de `eco` (fonte oficial, janela de 1995 em diante)."""

import re
from datetime import date
from typing import Any, Dict, List, Optional

from app.core.errors import ErroDeDominio
from sqlalchemy import text
from sqlalchemy.orm import Session

PRIMEIRO_ANO = 1995
_SLUG = re.compile(r"^[a-z0-9-]{1,60}$")

_MANDATO_SQL = text(
    """
    SELECT mp.slug, m.inicio, m.fim
    FROM core.mandato_presidencial mp JOIN core.mandato m ON m.id = mp.mandato_id
    WHERE mp.slug = :slug
    """
)

_PRESIDENTE_DO_ANO_SQL = text(
    """
    WITH anos AS (SELECT DISTINCT extract(year FROM referencia)::int AS ano FROM eco.observacao WHERE serie_id IN
                    (SELECT id FROM eco.serie WHERE periodicidade = 'ANUAL' AND abrangencia = 'BR')),
    sobreposicao AS (
        SELECT a.ano, p.nome_exibicao, coalesce(mp.rotulo, '') AS rotulo,
               greatest(0, least(coalesce(m.fim, current_date + 1), make_date(a.ano + 1, 1, 1)) - greatest(m.inicio, make_date(a.ano, 1, 1))) AS dias
        FROM anos a
        JOIN core.mandato m ON m.inicio < make_date(a.ano + 1, 1, 1) AND coalesce(m.fim, current_date + 1) > make_date(a.ano, 1, 1)
        JOIN core.mandato_presidencial mp ON mp.mandato_id = m.id
        JOIN core.pessoa p ON p.id = m.pessoa_id)
    SELECT DISTINCT ON (ano) ano, nome_exibicao, rotulo FROM sobreposicao ORDER BY ano, dias DESC
    """
)

_RESUMO_SQL = text("SELECT * FROM eco.vw_resumo_anual WHERE ano BETWEEN :primeiro AND :ultimo ORDER BY ano")

_IPCA_MANDATO_SQL = text(
    """
    WITH mensal AS (
        SELECT o.referencia, o.valor, m.id AS mandato_id, m.inicio
        FROM eco.observacao o
        JOIN eco.serie s ON s.id = o.serie_id AND s.codigo = 'IPCA_MENSAL'
        JOIN core.mandato m ON (o.referencia + 14) >= m.inicio AND (o.referencia + 14) < coalesce(m.fim, current_date + 1)
        JOIN core.mandato_presidencial mp ON mp.mandato_id = m.id),
    acumulado AS (
        SELECT mandato_id, referencia,
               (exp(sum(ln(1 + valor / 100)) OVER (PARTITION BY mandato_id ORDER BY referencia)) - 1) * 100 AS pct
        FROM mensal)
    SELECT DISTINCT ON (mandato_id, extract(year FROM referencia))
           mandato_id, extract(year FROM referencia)::int AS ano, pct
    FROM acumulado ORDER BY mandato_id, extract(year FROM referencia), referencia DESC
    """
)

_IPCA_MENSAL_SQL = text(
    """
    SELECT o.referencia, o.valor, s.codigo, s.nome, s.unidade
    FROM eco.observacao o JOIN eco.serie s ON s.id = o.serie_id
    WHERE s.codigo = 'IPCA_MENSAL'
      AND (CAST(:ano_inicio AS int) IS NULL OR extract(year FROM o.referencia) >= :ano_inicio)
      AND (CAST(:ano_fim AS int) IS NULL OR extract(year FROM o.referencia) <= :ano_fim)
    ORDER BY o.referencia
    """
)

_MANDATO_DO_ANO_SQL = text(
    """
    SELECT m.id, mp.slug, m.inicio, m.fim FROM core.mandato m
    JOIN core.mandato_presidencial mp ON mp.mandato_id = m.id ORDER BY m.inicio
    """
)


def _numero(valor: Any) -> Optional[float]:
    return None if valor is None else float(valor)


def intervalo_de_anos(inicio: date, fim: Optional[date], ultimo_ano_da_serie: int) -> tuple:
    """Anos inclusivos de um mandato. O fim é exclusivo: o mandato que termina em 01/01/AAAA não inclui AAAA."""
    primeiro = max(inicio.year, PRIMEIRO_ANO)
    if fim is not None:
        ultimo = date.fromordinal(fim.toordinal() - 1).year
    else:
        ultimo = max(ultimo_ano_da_serie, inicio.year)
    return primeiro, max(primeiro, ultimo)


def resumo_anual(db: Session, mandate_id: Optional[str]) -> List[Dict[str, Any]]:
    """Série anual consolidada, com o presidente dominante do ano e a inflação acumulada no mandato."""
    ultimo_ano = db.execute(text("SELECT max(ano) FROM eco.vw_resumo_anual")).scalar()
    if ultimo_ano is None:
        raise ErroDeDominio(404, "Resumo macroeconômico não encontrado. Execute o ETL.")
    primeiro, ultimo = PRIMEIRO_ANO, int(ultimo_ano)
    if mandate_id:
        if not _SLUG.match(mandate_id):
            raise ErroDeDominio(404, "Mandato não encontrado.")
        mandato = db.execute(_MANDATO_SQL, {"slug": mandate_id}).mappings().first()
        if mandato is None:
            raise ErroDeDominio(404, f"Mandato '{mandate_id}' não encontrado.")
        primeiro, ultimo = intervalo_de_anos(mandato["inicio"], mandato["fim"], int(ultimo_ano))

    presidentes = {r["ano"]: r for r in db.execute(_PRESIDENTE_DO_ANO_SQL).mappings()}
    acumulado = _acumulado_no_mandato(db)
    linhas: List[Dict[str, Any]] = []
    for r in db.execute(_RESUMO_SQL, {"primeiro": primeiro, "ultimo": ultimo}).mappings():
        ano = r["ano"]
        presidente = presidentes.get(ano)
        ipca = _numero(r["ipca_acumulado_ano_pct"])
        pib = _numero(r["pib_crescimento_real_pct"])
        salario = _numero(r["salario_minimo"])
        linhas.append(
            {
                "ano": ano,
                "presidente_dominante": (
                    f"{presidente['nome_exibicao']} ({presidente['rotulo']})"
                    if presidente and presidente["rotulo"]
                    else (presidente["nome_exibicao"] if presidente else None)
                ),
                "ipca_acumulado_ano_pct": ipca,
                "pib_crescimento_real_pct": pib,
                "crescimento_pib_percentual": pib,
                "inflacao_anual_ipca": ipca,
                "inflacao_acumulada_mandato": acumulado.get(ano),
                "taxa_desemprego_anual": _numero(r["taxa_desemprego_anual"]),
                "taxa_desmatamento_amazonia": _numero(r["taxa_desmatamento_amazonia"]),
                "inseguranca_alimentar_pct": _numero(r["inseguranca_alimentar_pct"]),
                "cambio_dolar_medio": _numero(r["cambio_dolar_medio"]),
                "cotacao_dolar_fechamento": _numero(r["cotacao_dolar_fechamento"]),
                "salario_minimo": salario,
                "salario_minimo_nominal_brl": salario,
                "taxa_homicidios": _numero(r["taxa_homicidios"]),
                "taxa_feminicidios": None,
                "divida_liquida_pct_pib": _numero(r["divida_liquida_pct_pib"]),
            }
        )
    return linhas


def _acumulado_no_mandato(db: Session) -> Dict[int, Optional[float]]:
    """Inflação acumulada desde a posse do presidente dominante até o fim de cada ano (por ano do mandato)."""
    por_mandato = {(r["mandato_id"], r["ano"]): _numero(r["pct"]) for r in db.execute(_IPCA_MANDATO_SQL).mappings()}
    dominante = {
        r["ano"]: r["mandato_id"]
        for r in db.execute(
            text(
                """
                SELECT DISTINCT ON (a.ano) a.ano, m.id AS mandato_id
                FROM (SELECT generate_series(1995, extract(year FROM current_date)::int) AS ano) a
                JOIN core.mandato m ON m.inicio < make_date(a.ano + 1, 1, 1) AND coalesce(m.fim, current_date + 1) > make_date(a.ano, 1, 1)
                JOIN core.mandato_presidencial mp ON mp.mandato_id = m.id
                ORDER BY a.ano, greatest(0, least(coalesce(m.fim, current_date + 1), make_date(a.ano + 1, 1, 1)) - greatest(m.inicio, make_date(a.ano, 1, 1))) DESC
                """
            )
        ).mappings()
    }
    return {ano: por_mandato.get((mandato_id, ano)) for ano, mandato_id in dominante.items()}


def ipca_mensal(db: Session, ano_inicio: Optional[int], ano_fim: Optional[int]) -> List[Dict[str, Any]]:
    if ano_inicio is not None and ano_fim is not None and ano_inicio > ano_fim:
        raise ErroDeDominio(422, "ano_inicio não pode ser maior que ano_fim.")
    linhas = db.execute(_IPCA_MENSAL_SQL, {"ano_inicio": ano_inicio, "ano_fim": ano_fim}).mappings().all()
    if not linhas:
        raise ErroDeDominio(404, "Série histórica do IPCA não encontrada.")
    return [
        {
            "data": r["referencia"].isoformat(),
            "ano": r["referencia"].year,
            "mes": r["referencia"].month,
            "dia": 1,
            "valor": _numero(r["valor"]),
            "codigo_serie": 433,
            "nome_serie": r["nome"],
            "unidade": "%",
        }
        for r in linhas
    ]
