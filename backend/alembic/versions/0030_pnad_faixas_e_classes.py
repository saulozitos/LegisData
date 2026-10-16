"""Distribuição de renda da PNAD Contínua em `eco`: faixas de salário mínimo, classes sociais e resultados por ano.

- `eco.pnad_faixa`: as 8 faixas de renda em múltiplos do salário mínimo (a posição de cada uma é o índice da lista
  `percentual` de `eco.pnad_distribuicao`).
- `eco.classe_social`: classes A a E, com a faixa de renda, o texto explicativo e as faixas da PNAD que cada uma reúne.
- `eco.pnad_ano`, `eco.pnad_distribuicao` e `eco.pnad_metodologia`: o que o ETL calcula dos microdados do IBGE. Não
  existe mais estimativa "de referência" digitada: sem os microdados do ano, a API não mostra percentual.

Revision ID: 0030
Revises: 0029
"""

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

FAIXAS = [
    (0, "sem_rendimento", "Sem rendimento", None, None),
    (1, "ate_0_5", "Até 1/2 SM", 0.0, 0.5),
    (2, "0_5_a_1", "Mais de 1/2 a 1 SM", 0.5, 1.0),
    (3, "1_a_2", "Mais de 1 a 2 SM", 1.0, 2.0),
    (4, "2_a_4", "Mais de 2 a 4 SM", 2.0, 4.0),
    (5, "4_a_10", "Mais de 4 a 10 SM", 4.0, 10.0),
    (6, "10_a_20", "Mais de 10 a 20 SM", 10.0, 20.0),
    (7, "mais_de_20", "Mais de 20 SM", 20.0, None),
]

# (ordem, classe, rótulo da faixa, mínimo, máximo, faixas da PNAD, descrição, cor, destaque)
CLASSES = [
    (
        1,
        "Classe A",
        "Mais de 20 salários mínimos",
        20.0,
        None,
        [7],
        "Alta renda e topo da pirâmide. Proprietários de empresas, altos executivos, juízes e servidores do topo do funcionalismo.",
        "#10b981",
        "Topo 3%",
    ),
    (
        2,
        "Classe B",
        "De 10 a 20 salários mínimos",
        10.0,
        20.0,
        [6],
        "Classe média alta. Profissionais liberais consolidados, média gerência, professores universitários e empresários médios.",
        "#3b82f6",
        "Média Alta",
    ),
    (
        3,
        "Classe C",
        "De 4 a 10 salários mínimos",
        4.0,
        10.0,
        [5],
        "Classe média tradicional / baixa. Pequenos comerciantes, técnicos especializados, professores do ensino básico e servidores médios.",
        "#f59e0b",
        "Média Tradicional",
    ),
    (
        4,
        "Classe D",
        "De 2 a 4 salários mínimos",
        2.0,
        4.0,
        [4],
        "Trabalhadores formais e autônomos de serviços essenciais, operários, comércio e transporte.",
        "#f97316",
        "Maior Grupo Formal",
    ),
    (
        5,
        "Classe E",
        "Até 2 salários mínimos",
        0.0,
        2.0,
        [0, 1, 2, 3],
        "Base da pirâmide e vulnerabilidade extrema. Dependentes de programas sociais, diaristas, desempregados e informais.",
        "#ef4444",
        "Vulnerabilidade",
    ),
]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE eco.pnad_faixa (
            posicao smallint PRIMARY KEY,
            codigo text NOT NULL UNIQUE,
            rotulo text NOT NULL,
            min_sm numeric(6, 2),
            max_sm numeric(6, 2)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE eco.classe_social (
            ordem smallint PRIMARY KEY,
            codigo text NOT NULL UNIQUE,
            faixa_rotulo text NOT NULL,
            min_sm numeric(6, 2) NOT NULL,
            max_sm numeric(6, 2),
            faixas_pnad smallint[] NOT NULL CHECK (faixas_pnad <@ ARRAY[0, 1, 2, 3, 4, 5, 6, 7]::smallint[]),
            descricao text NOT NULL,
            cor_hex char(7) NOT NULL,
            destaque text NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE eco.pnad_ano (
            ano smallint PRIMARY KEY CHECK (ano >= 1995),
            visita smallint NOT NULL,
            salario_minimo_brl numeric(10, 2) NOT NULL CHECK (salario_minimo_brl > 0),
            arquivo_microdados text,
            dicionario text,
            extraido_em timestamptz,
            linhas_lidas integer,
            populacao_total_estimada bigint
        )
        """
    )
    op.execute(
        """
        CREATE TABLE eco.pnad_distribuicao (
            ano smallint NOT NULL REFERENCES eco.pnad_ano(ano) ON DELETE CASCADE,
            escopo text NOT NULL,
            distribuicao text NOT NULL CHECK (distribuicao IN ('domicilios_renda_total', 'pessoas_renda_domiciliar',
                'pessoas_renda_per_capita', 'ocupados_renda_trabalho')),
            total_estimado bigint,
            media_nominal_brl numeric(12, 2),
            percentual numeric(6, 2)[] NOT NULL,
            PRIMARY KEY (ano, escopo, distribuicao),
            CHECK (cardinality(percentual) = 8)
        )
        """
    )
    op.execute("CREATE TABLE eco.pnad_metodologia (chave text PRIMARY KEY, texto text NOT NULL)")
    bind = op.get_bind()
    for posicao, codigo, rotulo, minimo, maximo in FAIXAS:
        bind.execute(
            sa.text(
                "INSERT INTO eco.pnad_faixa (posicao, codigo, rotulo, min_sm, max_sm) "
                "VALUES (:posicao, :codigo, :rotulo, :minimo, :maximo)"
            ),
            {"posicao": posicao, "codigo": codigo, "rotulo": rotulo, "minimo": minimo, "maximo": maximo},
        )
    for ordem, codigo, rotulo, minimo, maximo, faixas, descricao, cor, destaque in CLASSES:
        bind.execute(
            sa.text(
                "INSERT INTO eco.classe_social (ordem, codigo, faixa_rotulo, min_sm, max_sm, faixas_pnad, descricao, "
                "cor_hex, destaque) VALUES (:ordem, :codigo, :rotulo, :minimo, :maximo, "
                "CAST(:faixas AS smallint[]), :descricao, :cor, :destaque)"
            ),
            {
                "ordem": ordem,
                "codigo": codigo,
                "rotulo": rotulo,
                "minimo": minimo,
                "maximo": maximo,
                "faixas": faixas,
                "descricao": descricao,
                "cor": cor,
                "destaque": destaque,
            },
        )


def downgrade() -> None:
    for tabela in ("pnad_metodologia", "pnad_distribuicao", "pnad_ano", "classe_social", "pnad_faixa"):
        op.execute(f"DROP TABLE eco.{tabela}")
