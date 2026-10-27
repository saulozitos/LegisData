"""
Leituras de `eco` que as telas de análise usam: indicadores sociais anuais e por UF, resultados presidenciais por UF e
repasses federais por mandato. Estado e região vêm de `ref.uf`; o mandato presidencial é identificado pelo `slug`
público (`lula-2023`) de `core.mandato_presidencial`. Dado que a fonte não publicou fica ausente (nunca zero).
"""

from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

# campo devolvido -> código da série anual nacional
_SOCIAIS_ANUAIS = {
    "analfabetismo_pct": "ANALFABETISMO",
    "extrema_pobreza_pct": "EXTREMA_POBREZA_PCT",
    "extrema_pobreza_milhoes": "EXTREMA_POBREZA_MILHOES",
    "inseguranca_alimentar_pct": "INSEGURANCA_ALIMENTAR_PCT",
    "inseguranca_alimentar_milhoes": "INSEGURANCA_ALIMENTAR_MILHOES",
    "gini": "GINI",
    "pobreza_pct": "POBREZA_PCT",
    "inseguranca_alimentar_total_pct": "INSEGURANCA_ALIMENTAR_TOTAL_PCT",
    "desemprego_pct": "DESEMPREGO_ANUAL",
}
# campo devolvido -> código da série anual por UF
_SOCIAIS_POR_UF = {
    "taxa_analfabetismo_pct": "ANALFABETISMO_UF",
    "extrema_pobreza_pct": "EXTREMA_POBREZA_UF",
    "inseguranca_alimentar_pct": "INSEGURANCA_ALIMENTAR_UF",
    "indice_gini": "GINI_UF",
}
# Nas consultas abaixo, `initcap(replace(u.regiao, '_', '-'))` vira "CENTRO_OESTE" -> "Centro-Oeste", o rótulo que as
# telas já mostravam.


def indicadores_sociais_anuais(db: Session) -> List[Dict[str, Any]]:
    """
    Histórico anual nacional, só dos anos com algum dado, do mais antigo ao mais novo. `serie_gini` é a pesquisa de onde
    sai o Gini do ano (há quebra metodológica em 2012) e `fonte` reúne as fontes das séries que têm dado no ano.
    """
    codigo_para_campo = {codigo: campo for campo, codigo in _SOCIAIS_ANUAIS.items()}
    linhas = db.execute(
        text(
            """
            SELECT extract(year FROM o.referencia)::int AS ano, s.codigo, o.valor, o.nota, f.nome AS fonte
            FROM eco.observacao o
            JOIN eco.serie s ON s.id = o.serie_id
            JOIN etl.fonte f ON f.id = s.fonte_id
            WHERE o.uf IS NULL AND s.periodicidade = 'ANUAL' AND s.codigo = ANY(:codigos)
            ORDER BY 1, s.codigo
            """
        ),
        {"codigos": list(codigo_para_campo)},
    ).mappings()
    por_ano: Dict[int, Dict[str, Any]] = {}
    fontes: Dict[int, List[str]] = {}
    for linha in linhas:
        ano = linha["ano"]
        item = por_ano.setdefault(ano, {"ano": ano, **{campo: None for campo in _SOCIAIS_ANUAIS}, "serie_gini": None})
        item[codigo_para_campo[linha["codigo"]]] = float(linha["valor"])
        if linha["codigo"] == "GINI":
            item["serie_gini"] = linha["nota"]
        if linha["fonte"] not in fontes.setdefault(ano, []):
            fontes[ano].append(linha["fonte"])
    resultado = []
    for ano in sorted(por_ano):
        item = por_ano[ano]
        resultado.append({**item, "fonte": " e ".join(sorted(fontes[ano]))})
    return resultado


def indicadores_sociais_por_uf(db: Session, ano: int) -> Dict[str, Dict[str, Optional[float]]]:
    """Indicadores sociais de cada UF no ano (sem dado do ano, o campo fica ausente; nunca usa outro ano)."""
    codigo_para_campo = {codigo: campo for campo, codigo in _SOCIAIS_POR_UF.items()}
    por_uf: Dict[str, Dict[str, Optional[float]]] = {}
    for uf, codigo, valor in db.execute(
        text(
            """
            SELECT o.uf, s.codigo, o.valor
            FROM eco.observacao o JOIN eco.serie s ON s.id = o.serie_id
            WHERE o.uf IS NOT NULL AND s.codigo = ANY(:codigos) AND o.referencia = make_date(:ano, 1, 1)
            """
        ),
        {"codigos": list(codigo_para_campo), "ano": ano},
    ):
        por_uf.setdefault(uf, {})[codigo_para_campo[codigo]] = float(valor)
    return por_uf


def resultados_presidenciais(db: Session, ano: int) -> List[Dict[str, Any]]:
    """Primeiro e segundo colocados de cada UF na eleição presidencial do ano, por UF."""
    return [
        dict(linha)
        for linha in db.execute(
            text(
                """
                SELECT e.uf, u.nome AS estado_nome, initcap(replace(u.regiao, '_', '-')) AS regiao, e.ano_eleicao, e.turno,
                       e.vencedor_nome, e.vencedor_partido, e.vencedor_votos_pct,
                       e.segundo_nome, e.segundo_partido, e.segundo_votos_pct
                FROM eco.resultado_eleitoral_uf e JOIN ref.uf u ON u.sigla = e.uf
                WHERE e.ano_eleicao = :ano
                ORDER BY e.uf, e.turno
                """
            ),
            {"ano": ano},
        ).mappings()
    ]


def repasses_federais(db: Session, mandato: Optional[str] = None, area: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Repasses da União por UF e área. `mandato` filtra pelo slug público; `area` é um trecho do nome (sem diferenciar
    maiúsculas, com `%`, `_` e `\\` tratados como texto). Período em `AAAA-MM`; população, per capita, período e
    cobertura que a fonte não informa vêm como None.
    """
    escapada = area.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") if area else None
    consulta = text(
        """
        SELECT p.slug AS mandato_id_ref, r.uf, u.nome AS estado_nome, initcap(replace(u.regiao, '_', '-')) AS regiao,
               r.area_tematica, r.valor_pago AS valor_pago_brl, r.populacao_estimada,
               r.valor_per_capita AS valor_per_capita_brl,
               to_char(r.periodo_inicio, 'YYYY-MM') AS periodo_inicio, to_char(r.periodo_fim, 'YYYY-MM') AS periodo_fim,
               r.meses_cobertos, r.parcial
        FROM eco.repasse_federal r
        JOIN core.mandato_presidencial p ON p.mandato_id = r.mandato_id
        JOIN ref.uf u ON u.sigla = r.uf
        WHERE (CAST(:mandato AS text) IS NULL OR p.slug = :mandato)
          AND (CAST(:area AS text) IS NULL OR r.area_tematica ILIKE :area ESCAPE '\\')
        ORDER BY r.uf, r.area_tematica
        """
    )
    parametros = {"mandato": mandato, "area": f"%{escapada}%" if escapada else None}
    return [dict(linha) for linha in db.execute(consulta, parametros).mappings()]
