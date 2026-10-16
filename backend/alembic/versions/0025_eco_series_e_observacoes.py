"""Schema `eco`: catálogo de séries e observações econômicas e sociais com fonte oficial.

- `eco.serie`: uma linha por indicador (código, unidade, periodicidade, abrangência e fonte).
- `eco.observacao`: um valor por série, período e UF. Valor desconhecido não é gravado (nunca vira zero).
- `eco.vw_resumo_anual`: pivô anual com os nomes de coluna que a API já devolve.

A janela dos dados começa em 1995-01-01 (decisão D8); a carga e a restrição de tabela recusam datas anteriores.
Só entram séries com fonte oficial rastreável em `etl.fonte` (decisão D7).

Revision ID: 0025
Revises: 0024
"""

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

FONTES = [
    (
        "INPE_PRODES",
        "INPE / PRODES (TerraBrasilis)",
        "Instituto Nacional de Pesquisas Espaciais",
        "https://terrabrasil.dpi.inpe.br",
        "JSON",
        "ANUAL",
    ),
    (
        "IPEA_ATLAS",
        "Atlas da Violência (IPEA, SIM/DataSUS)",
        "Instituto de Pesquisa Econômica Aplicada",
        "https://www.ipea.gov.br/atlasviolencia",
        "JSON",
        "ANUAL",
    ),
]

# (codigo, nome, categoria, periodicidade, unidade, abrangencia, fonte, descricao)
SERIES = [
    ("IPCA_MENSAL", "IPCA, variação mensal", "INFLACAO", "MENSAL", "%", "BR", "BCB_SGS", "SGS 433."),
    ("IPCA_ACUM_ANO", "IPCA acumulado no ano", "INFLACAO", "ANUAL", "%", "BR", "BCB_SGS", "Composição do SGS 433."),
    ("CAMBIO_MENSAL", "Câmbio médio mensal (R$ por US$)", "CAMBIO", "MENSAL", "R$/US$", "BR", "BCB_SGS", "SGS 3698."),
    (
        "DIVIDA_LIQUIDA_PIB_MENSAL",
        "Dívida líquida do setor público, mensal",
        "DIVIDA",
        "MENSAL",
        "% do PIB",
        "BR",
        "BCB_SGS",
        "SGS 4513.",
    ),
    (
        "SALARIO_MINIMO_MENSAL",
        "Salário mínimo nominal, mensal",
        "SALARIO",
        "MENSAL",
        "R$",
        "BR",
        "BCB_SGS",
        "SGS 1619.",
    ),
    (
        "SELIC_META",
        "Meta da taxa Selic",
        "JUROS",
        "MENSAL",
        "% a.a.",
        "BR",
        "BCB_SGS",
        "SGS 432, último valor do mês.",
    ),
    (
        "DESEMPREGO_PNADC_MENSAL",
        "Taxa de desocupação, PNAD Contínua",
        "DESEMPREGO",
        "MENSAL",
        "%",
        "BR",
        "BCB_SGS",
        "SGS 24369 (trimestre móvel); disponível desde 2012.",
    ),
    ("PIB_CRESC_REAL", "PIB, crescimento real", "PIB", "ANUAL", "%", "BR", "BCB_SGS", "SGS 7326 (IBGE)."),
    (
        "DESEMPREGO_ANUAL",
        "Taxa de desemprego",
        "DESEMPREGO",
        "ANUAL",
        "%",
        "BR",
        "BCB_SGS",
        "PME até 2011 (SGS 10777) e PNAD Contínua desde 2012; quebra metodológica em 2012.",
    ),
    ("CAMBIO_MEDIO_ANO", "Câmbio médio (R$ por US$)", "CAMBIO", "ANUAL", "R$/US$", "BR", "BCB_SGS", "SGS 3698."),
    (
        "CAMBIO_FECHAMENTO_ANO",
        "Câmbio no fechamento do ano (R$ por US$)",
        "CAMBIO",
        "ANUAL",
        "R$/US$",
        "BR",
        "BCB_SGS",
        "SGS 10813.",
    ),
    ("SALARIO_MINIMO", "Salário mínimo nominal", "SALARIO", "ANUAL", "R$", "BR", "BCB_SGS", "SGS 1619."),
    (
        "DIVIDA_LIQUIDA_PIB",
        "Dívida líquida do setor público",
        "DIVIDA",
        "ANUAL",
        "% do PIB",
        "BR",
        "BCB_SGS",
        "SGS 4513, dezembro de cada ano.",
    ),
    (
        "DESMATAMENTO_AMAZONIA",
        "Desmatamento na Amazônia Legal",
        "AMBIENTE",
        "ANUAL",
        "km²",
        "BR",
        "INPE_PRODES",
        "Taxa consolidada do PRODES.",
    ),
    (
        "HOMICIDIOS_TAXA",
        "Taxa de homicídios",
        "SEGURANCA",
        "ANUAL",
        "por 100 mil",
        "BR",
        "IPEA_ATLAS",
        "Atlas da Violência, séries 328 e 20.",
    ),
    ("HOMICIDIOS_TOTAL", "Homicídios", "SEGURANCA", "ANUAL", "pessoas", "BR", "IPEA_ATLAS", "Atlas da Violência."),
    ("GINI", "Índice de Gini", "DESIGUALDADE", "ANUAL", "índice", "BR", "IBGE_SIDRA", "PNAD (t1167) e PNADC (t7435)."),
    ("ANALFABETISMO", "Analfabetismo, 15 anos ou mais", "EDUCACAO", "ANUAL", "%", "BR", "IBGE_SIDRA", "SIDRA t7113."),
    ("EXTREMA_POBREZA_PCT", "Extrema pobreza", "POBREZA", "ANUAL", "%", "BR", "IBGE_SIDRA", "SIDRA t5817."),
    (
        "EXTREMA_POBREZA_MILHOES",
        "Pessoas em extrema pobreza",
        "POBREZA",
        "ANUAL",
        "milhões",
        "BR",
        "IBGE_SIDRA",
        "SIDRA t5817 e população.",
    ),
    ("POBREZA_PCT", "Pobreza", "POBREZA", "ANUAL", "%", "BR", "IBGE_SIDRA", "SIDRA t5877."),
    (
        "INSEGURANCA_ALIMENTAR_PCT",
        "Domicílios com insegurança alimentar",
        "FOME",
        "ANUAL",
        "%",
        "BR",
        "IBGE_SIDRA",
        "SIDRA t3017 e t9552.",
    ),
    (
        "INSEGURANCA_ALIMENTAR_MILHOES",
        "Pessoas com insegurança alimentar",
        "FOME",
        "ANUAL",
        "milhões",
        "BR",
        "IBGE_SIDRA",
        "SIDRA t3017 e t9552.",
    ),
    ("GINI_UF", "Índice de Gini por UF", "DESIGUALDADE", "ANUAL", "índice", "UF", "IBGE_SIDRA", "PNAD e PNADC."),
    ("ANALFABETISMO_UF", "Analfabetismo por UF", "EDUCACAO", "ANUAL", "%", "UF", "IBGE_SIDRA", "SIDRA t7113."),
    ("EXTREMA_POBREZA_UF", "Extrema pobreza por UF", "POBREZA", "ANUAL", "%", "UF", "IBGE_SIDRA", "SIDRA t5817."),
    ("POBREZA_UF", "Pobreza por UF", "POBREZA", "ANUAL", "%", "UF", "IBGE_SIDRA", "SIDRA t5877."),
    (
        "INSEGURANCA_ALIMENTAR_UF",
        "Insegurança alimentar por UF",
        "FOME",
        "ANUAL",
        "%",
        "UF",
        "IBGE_SIDRA",
        "SIDRA t3017 e t9552.",
    ),
]

# Coluna da API no pivô anual -> código da série.
PIVO_ANUAL = [
    ("ipca_acumulado_ano_pct", "IPCA_ACUM_ANO"),
    ("pib_crescimento_real_pct", "PIB_CRESC_REAL"),
    ("taxa_desemprego_anual", "DESEMPREGO_ANUAL"),
    ("taxa_desmatamento_amazonia", "DESMATAMENTO_AMAZONIA"),
    ("inseguranca_alimentar_pct", "INSEGURANCA_ALIMENTAR_PCT"),
    ("cambio_dolar_medio", "CAMBIO_MEDIO_ANO"),
    ("cotacao_dolar_fechamento", "CAMBIO_FECHAMENTO_ANO"),
    ("salario_minimo", "SALARIO_MINIMO"),
    ("taxa_homicidios", "HOMICIDIOS_TAXA"),
    ("divida_liquida_pct_pib", "DIVIDA_LIQUIDA_PIB"),
]


def _q(valor: str) -> str:
    return "'" + valor.replace("'", "''") + "'"


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS eco")
    for codigo, nome, orgao, url, formato, periodicidade in FONTES:
        op.execute(
            "INSERT INTO etl.fonte (codigo, nome, orgao, url_base, formato, periodicidade) VALUES "
            f"({_q(codigo)}, {_q(nome)}, {_q(orgao)}, {_q(url)}, {_q(formato)}, {_q(periodicidade)}) "
            "ON CONFLICT (codigo) DO NOTHING"
        )
    op.execute(
        """
        CREATE TABLE eco.serie (
            id smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            codigo text NOT NULL UNIQUE,
            nome text NOT NULL,
            categoria text NOT NULL,
            periodicidade text NOT NULL CHECK (periodicidade IN ('DIARIA', 'MENSAL', 'TRIMESTRAL', 'ANUAL')),
            unidade text NOT NULL,
            abrangencia text NOT NULL CHECK (abrangencia IN ('BR', 'UF')),
            fonte_id smallint NOT NULL REFERENCES etl.fonte(id),
            descricao text
        )
        """
    )
    op.execute(
        """
        CREATE TABLE eco.observacao (
            serie_id smallint NOT NULL REFERENCES eco.serie(id),
            referencia date NOT NULL CHECK (referencia >= DATE '1995-01-01'),
            uf char(2) REFERENCES ref.uf(sigla),
            uf_chave char(2) GENERATED ALWAYS AS (coalesce(uf, 'BR')) STORED,
            valor numeric(24, 6) NOT NULL,
            parcial boolean NOT NULL DEFAULT false,
            nota text,
            carregado_em timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (serie_id, referencia, uf_chave)
        )
        """
    )
    op.execute("CREATE INDEX ix_observacao_referencia ON eco.observacao (referencia)")
    for codigo, nome, categoria, periodicidade, unidade, abrangencia, fonte, descricao in SERIES:
        op.execute(
            "INSERT INTO eco.serie (codigo, nome, categoria, periodicidade, unidade, abrangencia, fonte_id, descricao) "
            f"SELECT {_q(codigo)}, {_q(nome)}, {_q(categoria)}, {_q(periodicidade)}, {_q(unidade)}, "
            f"{_q(abrangencia)}, f.id, {_q(descricao)} FROM etl.fonte f WHERE f.codigo = {_q(fonte)}"
        )
    colunas = ",\n            ".join(
        f"max(o.valor) FILTER (WHERE s.codigo = {_q(codigo)}) AS {coluna}" for coluna, codigo in PIVO_ANUAL
    )
    op.execute(
        f"""
        CREATE VIEW eco.vw_resumo_anual AS
        SELECT extract(year FROM o.referencia)::int AS ano,
            {colunas}
        FROM eco.observacao o JOIN eco.serie s ON s.id = o.serie_id
        WHERE s.periodicidade = 'ANUAL' AND s.abrangencia = 'BR'
        GROUP BY 1
        """
    )


def downgrade() -> None:
    op.execute("DROP SCHEMA eco CASCADE")
    op.execute("DELETE FROM etl.fonte WHERE codigo IN ('INPE_PRODES', 'IPEA_ATLAS')")
