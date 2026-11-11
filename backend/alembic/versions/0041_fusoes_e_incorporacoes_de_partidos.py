"""Fusões e incorporações de partidos: mudança de legenda que não é troca de partido.

O feedback de uma usuária apontou que a passagem de PMDB para MDB entrava na contagem de trocas de partido. A renomeação já
estava em `ref.partido_renomeacao` (linhagem), mas a contagem olhava as siglas cruas. Esta migração acrescenta a mesma
semente para fusões e incorporações (tabela `ref.partido_sucessao_semente`, dado de domínio no banco, não no código) e faz
`etl.aplicar_linhagens()` gravá-las em `core.partido_sucessao` (tipos FUSAO e INCORPORACAO, que o CHECK da tabela já aceita).
Só entra par em que os dois partidos existem em `core.partido`. Data só onde é conhecida com certeza; o resto fica nulo.

Revision ID: 0041
Revises: 0040
"""

from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None

# (sigla do partido que deixou de existir, sigla do partido resultante, tipo, data do registro no TSE ou None, observação)
SUCESSOES = [
    ("DEM", "UNIÃO", "FUSAO", "2022-02-08", "Fusão DEM + PSL = União Brasil"),
    ("PSL", "UNIÃO", "FUSAO", "2022-02-08", "Fusão DEM + PSL = União Brasil"),
    ("PTB", "PRD", "FUSAO", None, "Fusão PTB + Patriota = PRD"),
    ("PATRIOTA", "PRD", "FUSAO", None, "Fusão PTB + Patriota = PRD"),
    ("PHS", "PODE", "INCORPORACAO", None, "Incorporação do PHS pelo Podemos"),
    ("PSC", "PODE", "INCORPORACAO", None, "Incorporação do PSC pelo Podemos"),
    ("PPL", "PCdoB", "INCORPORACAO", None, "Incorporação do PPL pelo PCdoB"),
    ("PROS", "SOLIDARIEDADE", "INCORPORACAO", None, "Incorporação do PROS pelo Solidariedade"),
    ("PRP", "PATRIOTA", "INCORPORACAO", None, "Incorporação do PRP pelo Patriota"),
]

APLICAR = r"""
CREATE OR REPLACE FUNCTION etl.aplicar_linhagens() RETURNS int
LANGUAGE plpgsql AS $fn$
DECLARE
    v_n int;
BEGIN
    UPDATE core.partido p SET linhagem_id = d.id
    FROM ref.partido_renomeacao r
    JOIN core.partido d ON d.sigla_normalizada = ref.normalizar_texto(r.sigla_atual)
    WHERE p.sigla_normalizada = ref.normalizar_texto(r.sigla_antiga) AND p.id <> d.id
      AND p.linhagem_id IS DISTINCT FROM d.id;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    INSERT INTO core.partido_sucessao (partido_origem_id, partido_destino_id, tipo)
    SELECT p.id, p.linhagem_id, 'RENOMEACAO' FROM core.partido p
    WHERE p.linhagem_id IS NOT NULL ON CONFLICT DO NOTHING;
    INSERT INTO core.partido_sucessao (partido_origem_id, partido_destino_id, tipo, data, fonte_id)
    SELECT o.id, d.id, s.tipo, s.data, (SELECT id FROM etl.fonte WHERE codigo = 'CURADORIA')
    FROM ref.partido_sucessao_semente s
    JOIN core.partido o ON o.sigla_normalizada = ref.normalizar_texto(s.sigla_origem)
    JOIN core.partido d ON d.sigla_normalizada = ref.normalizar_texto(s.sigla_destino)
    WHERE o.id <> d.id
    ON CONFLICT DO NOTHING;
    RETURN v_n;
END
$fn$;
"""

APLICAR_ANTERIOR = r"""
CREATE OR REPLACE FUNCTION etl.aplicar_linhagens() RETURNS int
LANGUAGE plpgsql AS $fn$
DECLARE
    v_n int;
BEGIN
    UPDATE core.partido p SET linhagem_id = d.id
    FROM ref.partido_renomeacao r
    JOIN core.partido d ON d.sigla_normalizada = ref.normalizar_texto(r.sigla_atual)
    WHERE p.sigla_normalizada = ref.normalizar_texto(r.sigla_antiga) AND p.id <> d.id
      AND p.linhagem_id IS DISTINCT FROM d.id;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    INSERT INTO core.partido_sucessao (partido_origem_id, partido_destino_id, tipo)
    SELECT p.id, p.linhagem_id, 'RENOMEACAO' FROM core.partido p
    WHERE p.linhagem_id IS NOT NULL ON CONFLICT DO NOTHING;
    RETURN v_n;
END
$fn$;
"""


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE ref.partido_sucessao_semente (
            sigla_origem text NOT NULL,
            sigla_destino text NOT NULL,
            tipo text NOT NULL CHECK (tipo IN ('FUSAO', 'INCORPORACAO')),
            data date,
            observacao text,
            PRIMARY KEY (sigla_origem, sigla_destino)
        )
        """
    )
    bind = op.get_bind()
    for origem, destino, tipo, data, obs in SUCESSOES:
        bind.exec_driver_sql(
            "INSERT INTO ref.partido_sucessao_semente VALUES (%s, %s, %s, %s, %s)", (origem, destino, tipo, data, obs)
        )
    op.execute(APLICAR)
    op.execute("SELECT etl.aplicar_linhagens()")


def downgrade() -> None:
    op.execute(
        "DELETE FROM core.partido_sucessao WHERE tipo IN ('FUSAO', 'INCORPORACAO') "
        "AND fonte_id = (SELECT id FROM etl.fonte WHERE codigo = 'CURADORIA')"
    )
    op.execute(APLICAR_ANTERIOR)
    op.execute("DROP TABLE ref.partido_sucessao_semente")
