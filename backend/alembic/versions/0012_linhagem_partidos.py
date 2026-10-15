"""Linhagem de partidos: siglas renomeadas e variantes de grafia somam no mesmo partido.

As fontes misturam a sigla da época e a sigla atual (PMDB e MDB, PFL e DEM, "REPUBLIC", "SOLIDARI"...). Sem uma linhagem,
a pontuação (fonte de autoria) e as cadeiras (fonte de mandato) caem em linhas diferentes e o IPPM sai errado.
`core.partido.linhagem_id` aponta a sigla vigente; nada é apagado nem reapontado (reversível).
Só renomeações puras entram aqui. Fusões e incorporações (DEM+PSL = UNIÃO, PTB+PATRIOTA = PRD...) continuam sendo
partidos distintos ligados por core.partido_sucessao.

Revision ID: 0012
Revises: 0011
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

# (sigla na fonte, sigla vigente, observação)
RENOMEACOES = [
    ("PMDB", "MDB", "Renomeação (2017)"),
    ("PFL", "DEM", "Renomeação (2007)"),
    ("PPB", "PP", "Renomeação (2003)"),
    ("PPS", "CIDADANIA", "Renomeação (2019)"),
    ("PTdoB", "AVANTE", "Renomeação (2017)"),
    ("PTN", "PODE", "Renomeação (2016/2017)"),
    ("PEN", "PATRIOTA", "Renomeação (2018)"),
    ("PRB", "REPUBLICANOS", "Renomeação (2019)"),
    ("PR", "PL", "Renomeação (2019)"),
    ("PSDC", "DC", "Renomeação (2018)"),
    ("SD", "SOLIDARIEDADE", "Renomeação"),
    ("PATRI", "PATRIOTA", "Grafia da fonte"),
    ("REPUBLIC", "REPUBLICANOS", "Sigla truncada pela fonte"),
    ("SOLIDARI", "SOLIDARIEDADE", "Sigla truncada pela fonte"),
    ("SOLIDARIED", "SOLIDARIEDADE", "Sigla truncada pela fonte"),
    ("S. PART.", "S.PART.", "Grafia da fonte"),
    ("S.PART", "S.PART.", "Grafia da fonte"),
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
    RETURN v_n;
END
$fn$;
"""


def upgrade() -> None:
    op.execute("ALTER TABLE core.partido ADD COLUMN linhagem_id bigint REFERENCES core.partido(id)")
    op.execute(
        "ALTER TABLE core.partido ADD CONSTRAINT ck_partido_linhagem CHECK (linhagem_id IS NULL OR linhagem_id <> id)"
    )
    op.execute(
        """
        CREATE TABLE ref.partido_renomeacao (
            sigla_antiga text PRIMARY KEY,
            sigla_atual text NOT NULL,
            observacao text
        )
        """
    )
    bind = op.get_bind()
    for antiga, atual, obs in RENOMEACOES:
        bind.exec_driver_sql("INSERT INTO ref.partido_renomeacao VALUES (%s, %s, %s)", (antiga, atual, obs))
    op.execute(APLICAR)

    # partido vigente de cada linha: o próprio, ou a sigla para onde a linhagem aponta
    op.execute(
        """
        CREATE VIEW core.vw_partido_canonico AS
        SELECT p.id, c.id AS canonico_id, c.sigla AS canonico_sigla, c.sigla_normalizada AS canonico_sigla_normalizada
        FROM core.partido p JOIN core.partido c ON c.id = coalesce(p.linhagem_id, p.id)
        """
    )
    op.execute("DROP VIEW core.vw_partido")
    op.execute(
        """
        CREATE VIEW core.vw_partido AS
        SELECT p.id, p.uid, p.sigla, p.nome, p.numero_eleitoral, p.data_fundacao, p.data_extincao, p.cor_hex,
               lm.url_origem AS logo_url, p.ideologia_texto, p.lema, p.catalogo, p.linhagem_id,
               (SELECT pi.espectro FROM core.partido_posicao_ideologica pi
                 WHERE pi.partido_id = p.id AND pi.escala = 'ESPECTRO_5'
                 ORDER BY pi.ano_referencia DESC NULLS LAST, pi.id DESC LIMIT 1) AS espectro_politico
        FROM core.partido p LEFT JOIN core.midia lm ON lm.id = p.logo_midia_id
        """
    )
    op.execute("DROP VIEW core.vw_historico_mandato")
    op.execute(
        """
        CREATE VIEW core.vw_historico_mandato AS
        SELECT s.id, m.pessoa_id, m.partido_id, pc.canonico_sigla AS partido_sigla,
               pc.canonico_sigla_normalizada AS partido_sigla_normalizada, fm.url_origem AS foto_url,
               CASE c.codigo WHEN 'DEPUTADO_FEDERAL' THEN 'CAMARA' WHEN 'SENADOR' THEN 'SENADO' ELSE 'OUTRO' END AS casa,
               CASE WHEN m.motivo_encerramento IS NOT NULL AND upper(s.periodo) IS NULL THEN 'ENCERRADO'
                    ELSE s.situacao END AS situacao,
               lower(s.periodo) AS data_inicio, upper(s.periodo) - 1 AS data_fim, s.motivo AS observacao
        FROM core.mandato_situacao s
        JOIN core.mandato m ON m.id = s.mandato_id
        JOIN ref.cargo c ON c.id = m.cargo_id
        JOIN core.pessoa pe ON pe.id = m.pessoa_id
        LEFT JOIN core.midia fm ON fm.id = pe.foto_midia_id
        LEFT JOIN core.vw_partido_canonico pc ON pc.id = m.partido_id
        """
    )
    op.execute("SELECT etl.aplicar_linhagens()")


def downgrade() -> None:
    raise NotImplementedError("Migração de linhagem de partidos (0012) não é reversível.")
