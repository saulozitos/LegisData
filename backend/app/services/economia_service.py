"""Séries econômicas anuais e mensais lidas de `eco` (fonte oficial, janela de 1995 em diante)."""

from typing import Any, Dict, List, Optional

from app.core.errors import ErroDeDominio
from app.services.periodos import PRIMEIRO_ANO, SLUG_MANDATO, intervalo_de_anos, nome_do_mandato, valor_opcional
from sqlalchemy import text
from sqlalchemy.orm import Session

_MANDATO_SQL = text(
    """
    SELECT mp.slug, m.inicio, m.fim
    FROM core.mandato_presidencial mp JOIN core.mandato m ON m.id = mp.mandato_id
    WHERE mp.slug = :slug
    """
)

# Presidente dominante de cada ano de série: quem ficou mais dias no cargo (desempate por ordem de posse).
_DOMINANTE_DO_ANO_SQL = text(
    """
    WITH anos AS (
        SELECT DISTINCT extract(year FROM o.referencia)::int AS ano
        FROM eco.observacao o JOIN eco.serie s ON s.id = o.serie_id
        WHERE s.periodicidade = 'ANUAL' AND s.abrangencia = 'BR'),
    sobreposicao AS (
        SELECT a.ano, m.id AS mandato_id, p.nome_exibicao, mp.rotulo,
               greatest(0, least(coalesce(m.fim, current_date + 1), make_date(a.ano + 1, 1, 1))
                           - greatest(m.inicio, make_date(a.ano, 1, 1))) AS dias
        FROM anos a
        JOIN core.mandato m ON m.inicio < make_date(a.ano + 1, 1, 1)
                           AND coalesce(m.fim, current_date + 1) > make_date(a.ano, 1, 1)
        JOIN core.mandato_presidencial mp ON mp.mandato_id = m.id
        JOIN core.pessoa p ON p.id = m.pessoa_id)
    SELECT DISTINCT ON (ano) ano, mandato_id, nome_exibicao, rotulo
    FROM sobreposicao ORDER BY ano, dias DESC, mandato_id
    """
)

_RESUMO_SQL = text("SELECT * FROM eco.vw_resumo_anual WHERE ano BETWEEN :primeiro AND :ultimo ORDER BY ano")

# Inflação acumulada desde a posse, ao fim de cada ano do mandato (o mês vale para quem estava no cargo no dia 15).
_IPCA_MANDATO_SQL = text(
    """
    WITH mensal AS (
        SELECT o.referencia, o.valor, m.id AS mandato_id
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
    SELECT o.referencia, o.valor, s.nome, s.unidade
    FROM eco.observacao o JOIN eco.serie s ON s.id = o.serie_id
    WHERE s.codigo = 'IPCA_MENSAL'
      AND (CAST(:ano_inicio AS int) IS NULL OR extract(year FROM o.referencia) >= :ano_inicio)
      AND (CAST(:ano_fim AS int) IS NULL OR extract(year FROM o.referencia) <= :ano_fim)
    ORDER BY o.referencia
    """
)

# Código do IPCA mensal no SGS do Banco Central (o contrato da API sempre o devolveu).
CODIGO_SGS_IPCA_MENSAL = 433


def dominantes_por_ano(db: Session) -> Dict[int, Dict[str, Any]]:
    """Presidente dominante de cada ano de série (mandato, nome e rótulo)."""
    return {r["ano"]: dict(r) for r in db.execute(_DOMINANTE_DO_ANO_SQL).mappings()}


def resumo_anual(db: Session, mandate_id: Optional[str]) -> List[Dict[str, Any]]:
    """Série anual consolidada, com o presidente dominante do ano e a inflação acumulada no mandato."""
    ultimo_ano = db.execute(text("SELECT max(ano) FROM eco.vw_resumo_anual")).scalar()
    if ultimo_ano is None:
        raise ErroDeDominio(404, "Resumo macroeconômico não encontrado. Execute o ETL.")
    primeiro, ultimo = PRIMEIRO_ANO, int(ultimo_ano)
    if mandate_id:
        if not SLUG_MANDATO.match(mandate_id):
            raise ErroDeDominio(404, "Mandato não encontrado.")
        mandato = db.execute(_MANDATO_SQL, {"slug": mandate_id}).mappings().first()
        if mandato is None:
            raise ErroDeDominio(404, f"Mandato '{mandate_id}' não encontrado.")
        primeiro, ultimo = intervalo_de_anos(mandato["inicio"], mandato["fim"], int(ultimo_ano))

    dominantes = dominantes_por_ano(db)
    acumulado = _acumulado_no_mandato(db, dominantes)
    linhas: List[Dict[str, Any]] = []
    for r in db.execute(_RESUMO_SQL, {"primeiro": primeiro, "ultimo": ultimo}).mappings():
        ano = r["ano"]
        presidente = dominantes.get(ano)
        ipca = valor_opcional(r["ipca_acumulado_ano_pct"])
        pib = valor_opcional(r["pib_crescimento_real_pct"])
        salario = valor_opcional(r["salario_minimo"])
        linhas.append(
            {
                "ano": ano,
                "presidente_dominante": (
                    nome_do_mandato(presidente["nome_exibicao"], presidente["rotulo"]) if presidente else None
                ),
                "ipca_acumulado_ano_pct": ipca,
                "pib_crescimento_real_pct": pib,
                # Aliases do contrato legado com o frontend (mesmo valor das colunas acima)
                "crescimento_pib_percentual": pib,
                "inflacao_anual_ipca": ipca,
                "inflacao_acumulada_mandato": acumulado.get(ano),
                "taxa_desemprego_anual": valor_opcional(r["taxa_desemprego_anual"]),
                "taxa_desmatamento_amazonia": valor_opcional(r["taxa_desmatamento_amazonia"]),
                "inseguranca_alimentar_pct": valor_opcional(r["inseguranca_alimentar_pct"]),
                "cambio_dolar_medio": valor_opcional(r["cambio_dolar_medio"]),
                "cotacao_dolar_fechamento": valor_opcional(r["cotacao_dolar_fechamento"]),
                "salario_minimo": salario,
                "salario_minimo_nominal_brl": salario,
                "taxa_homicidios": valor_opcional(r["taxa_homicidios"]),
                "taxa_feminicidios": None,
                "divida_liquida_pct_pib": valor_opcional(r["divida_liquida_pct_pib"]),
            }
        )
    return linhas


def _acumulado_no_mandato(db: Session, dominantes: Dict[int, Any]) -> Dict[int, Optional[float]]:
    """Inflação acumulada desde a posse do presidente dominante até o fim de cada ano."""
    por_mandato = {
        (r["mandato_id"], r["ano"]): valor_opcional(r["pct"]) for r in db.execute(_IPCA_MANDATO_SQL).mappings()
    }
    return {ano: por_mandato.get((d["mandato_id"], ano)) for ano, d in dominantes.items()}


def ipca_mensal(db: Session, ano_inicio: Optional[int], ano_fim: Optional[int]) -> List[Dict[str, Any]]:
    """IPCA mensal desde 1995. Filtro sem resultado devolve lista vazia; 404 só se a série inteira não foi carregada."""
    if ano_inicio is not None and ano_fim is not None and ano_inicio > ano_fim:
        raise ErroDeDominio(422, "ano_inicio não pode ser maior que ano_fim.")
    linhas = db.execute(_IPCA_MENSAL_SQL, {"ano_inicio": ano_inicio, "ano_fim": ano_fim}).mappings().all()
    if (
        not linhas
        and not db.execute(
            text(
                "SELECT 1 FROM eco.serie s JOIN eco.observacao o ON o.serie_id = s.id "
                "WHERE s.codigo = 'IPCA_MENSAL' LIMIT 1"
            )
        ).first()
    ):
        raise ErroDeDominio(404, "Série histórica do IPCA não encontrada.")
    return [
        {
            "data": r["referencia"].isoformat(),
            "ano": r["referencia"].year,
            "mes": r["referencia"].month,
            "dia": 1,
            "valor": valor_opcional(r["valor"]),
            "codigo_serie": CODIGO_SGS_IPCA_MENSAL,
            "nome_serie": r["nome"],
            "unidade": r["unidade"],
        }
        for r in linhas
    ]
