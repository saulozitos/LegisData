"""Cobertura de cada painel: fonte, período disponível, última atualização e se a base está completa ou parcial.

Uma usuária apontou que o calendário dizia "o Congresso realizou votações em apenas um dia de 2026", o que parece uma
conclusão sobre toda a atividade do Congresso quando é só o que a base tem. `ref.cobertura_painel` guarda, por painel, o
nome da fonte, as fontes do ETL que o alimentam e o ano em que a base pretende começar (`inicio_alvo`); `ref.vw_cobertura_painel`
junta a isso a data da última carga bem-sucedida dessas fontes (de `etl.execucao`, que a API não lê direto). O período real e
a quantidade de registros saem das tabelas de domínio no serviço da API; "parcial" é período real começando depois do alvo.

Revision ID: 0043
Revises: 0042
"""

from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None

# (painel, título, fontes por extenso, códigos das fontes do ETL, ano em que a base pretende começar)
PAINEIS = [
    (
        "votacoes",
        "Votações nominais",
        "Dados Abertos da Câmara dos Deputados e do Senado Federal",
        ["CAMARA_API", "SENADO_API"],
        1995,
    ),
    (
        "proposicoes",
        "Proposições",
        "Dados Abertos da Câmara dos Deputados (arquivos anuais) e do Senado Federal",
        ["CAMARA_CSV", "CAMARA_API", "SENADO_API"],
        1995,
    ),
    (
        "parlamentares",
        "Parlamentares, mandatos e partidos",
        "Dados Abertos da Câmara dos Deputados e do Senado Federal",
        ["CAMARA_API", "SENADO_API", "CURADORIA"],
        1995,
    ),
    (
        "presenca",
        "Presença em plenário",
        "Portal da Câmara dos Deputados e votações nominais do Senado Federal",
        ["CAMARA_PORTAL", "SENADO_API", "CAMARA_API"],
        1995,
    ),
    (
        "gastos",
        "Gastos da cota parlamentar e emendas",
        "Dados Abertos da Câmara dos Deputados, do Senado Federal e Portal da Transparência",
        ["CAMARA_API", "SENADO_API", "PORTAL_TRANSPARENCIA"],
        2019,
    ),
]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE ref.cobertura_painel (
            painel text PRIMARY KEY,
            titulo text NOT NULL,
            fontes_texto text NOT NULL,
            fontes_codigos text[] NOT NULL,
            inicio_alvo integer NOT NULL
        )
        """
    )
    bind = op.get_bind()
    for linha in PAINEIS:
        bind.exec_driver_sql("INSERT INTO ref.cobertura_painel VALUES (%s, %s, %s, %s, %s)", linha)
    # a visão roda com os direitos de quem a criou: a API lê a data da última carga sem acessar o schema etl
    op.execute(
        """
        CREATE VIEW ref.vw_cobertura_painel AS
        SELECT p.painel, p.titulo, p.fontes_texto, p.inicio_alvo,
               (SELECT max(e.finalizado_em) FROM etl.execucao e JOIN etl.fonte f ON f.id = e.fonte_id
                 WHERE f.codigo = ANY (p.fontes_codigos) AND e.estagio = 'CARREGAR'
                   AND e.status IN ('OK', 'COM_ALERTA')) AS atualizado_em
        FROM ref.cobertura_painel p
        """
    )
    op.execute("GRANT SELECT ON ref.cobertura_painel, ref.vw_cobertura_painel TO legisdata_leitura")


def downgrade() -> None:
    op.execute("DROP VIEW ref.vw_cobertura_painel")
    op.execute("DROP TABLE ref.cobertura_painel")
