"""O que foi votado: texto principal, urgência, destaque, emenda, parecer, requerimento.

Uma usuária apontou que o placar de um requerimento de urgência podia ser lido como aprovação do projeto. A fonte só traz o
texto livre da deliberação ("Aprovado o Requerimento de Urgência (Art. 155 do RICD)", "Mantido o texto", "Rejeitada a Emenda
de Plenário nº ..."), então o objeto é inferido por regras ordenadas guardadas no banco (dado de domínio, não código):
`ref.objeto_votacao` descreve cada objeto e `ref.objeto_votacao_regra` traz o padrão (regex do Postgres, aplicado ao texto
da deliberação e ao título da pauta em minúsculas). A primeira regra que casa vence; sem regra, o objeto é desconhecido e a
tela diz isso, em vez de supor.

Revision ID: 0042
Revises: 0041
"""

from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None

# (código, rótulo, o que a votação decide, decide o mérito do projeto?)
OBJETOS = [
    (
        "URGENCIA",
        "Requerimento de urgência",
        "Votação só do pedido de urgência para o projeto andar mais rápido. Aprovar a urgência não aprova o projeto.",
        False,
    ),
    (
        "REQUERIMENTO",
        "Requerimento",
        "Votação de um pedido de procedimento (adiar, retirar de pauta, votar em separado...). Não decide se o projeto é aprovado.",
        False,
    ),
    (
        "DESTAQUE",
        "Destaque",
        "Votação de um trecho do texto separado para ser votado à parte (mantido ou suprimido). Não é a votação do projeto inteiro.",
        False,
    ),
    (
        "EMENDA",
        "Emenda",
        "Votação de uma emenda, isto é, de uma mudança proposta ao texto. Não é a votação final do projeto.",
        False,
    ),
    (
        "PARECER",
        "Parecer",
        "Votação do parecer de uma comissão sobre a matéria. Não é a votação final do projeto.",
        False,
    ),
    (
        "REDACAO_FINAL",
        "Redação final",
        "Votação do texto final já aprovado, para ajustes de redação.",
        False,
    ),
    (
        "TEXTO_PRINCIPAL",
        "Texto principal",
        "Votação do projeto ou do texto principal da matéria.",
        True,
    ),
]

# (ordem, código, padrão): a primeira regra que casa vence, por isso urgência vem antes de requerimento
REGRAS = [
    (10, "URGENCIA", r"requerimento de urg[êe]ncia"),
    (20, "REQUERIMENTO", r"\mrequerimento\M"),
    (30, "DESTAQUE", r"(mantido|suprimido) o texto|destacad[oa]|destaque"),
    (
        40,
        "EMENDA",
        r"\memendas?\M +(de plen|de comiss|do senado|substitutiva|aglutinativa|n[ºo°]|de n)|subemenda|vota[çc][ãa]o nominal da emenda",
    ),
    (50, "PARECER", r"\mparecer\M"),
    (60, "REDACAO_FINAL", r"reda[çc][ãa]o final"),
    (
        70,
        "TEXTO_PRINCIPAL",
        r"(aprovad|rejeitad)[oa]s?\M.*(projeto|proposta de emenda|medida provis|substitutivo|decreto legislativo)"
        r"|vota[çc][ãa]o nominal d[oa]s? (projeto|proposta de emenda|medida)",
    ),
]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE ref.objeto_votacao (
            codigo text PRIMARY KEY,
            rotulo text NOT NULL,
            explicacao text NOT NULL,
            decide_merito boolean NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE ref.objeto_votacao_regra (
            ordem integer PRIMARY KEY,
            codigo text NOT NULL REFERENCES ref.objeto_votacao(codigo),
            padrao text NOT NULL
        )
        """
    )
    bind = op.get_bind()
    for linha in OBJETOS:
        bind.exec_driver_sql("INSERT INTO ref.objeto_votacao VALUES (%s, %s, %s, %s)", linha)
    for linha in REGRAS:
        bind.exec_driver_sql("INSERT INTO ref.objeto_votacao_regra VALUES (%s, %s, %s)", linha)


def downgrade() -> None:
    op.execute("DROP TABLE ref.objeto_votacao_regra")
    op.execute("DROP TABLE ref.objeto_votacao")
