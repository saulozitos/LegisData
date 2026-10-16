"""Dados de domínio da API de presença e do ranking de autores em tabelas, não em constantes.

- `ref.tipo_presenca.justificada`: quais tipos de falta contam como justificadas.
- `ref.cobertura_presenca`: desde quando a fonte de cada Casa informa falta (`falta_desde`) e justificativa
  (`justificativa_desde`). Entre os dois marcos a falta só pode ser inferida.
- `ref.alias_filtro_partido`: nomes aceitos no filtro de partido para "governo" e "sem partido".
- `param.peso`, dimensão `CORTE_DIAGNOSTICO_AUTOR` (IALP v3): limiares do diagnóstico do ranking de autores.

Revision ID: 0023
Revises: 0022
"""

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE ref.tipo_presenca ADD COLUMN justificada boolean NOT NULL DEFAULT false")
    op.execute(
        "UPDATE ref.tipo_presenca SET justificada = true "
        "WHERE codigo IN ('AUSENCIA_JUSTIFICADA', 'LICENCA_MEDICA', 'MISSAO_OFICIAL')"
    )
    op.execute(
        """
        CREATE TABLE ref.cobertura_presenca (
            casa_id smallint PRIMARY KEY REFERENCES ref.casa_legislativa(id),
            falta_desde date NOT NULL,
            justificativa_desde date NOT NULL,
            observacao text
        )
        """
    )
    op.execute(
        """
        INSERT INTO ref.cobertura_presenca (casa_id, falta_desde, justificativa_desde, observacao)
        SELECT id, DATE '2003-02-03', DATE '2020-01-01',
               'Antes de 2003-02-03 só há presença; de 2003 a 2019 a falta é inferida; desde 2020 a fonte oficial '
               'informa falta e justificativa.'
        FROM ref.casa_legislativa WHERE codigo = 'CAMARA_DOS_DEPUTADOS'
        UNION ALL
        SELECT id, DATE '1995-01-01', DATE '1995-01-01', 'Falta e justificativa derivadas das votações nominais.'
        FROM ref.casa_legislativa WHERE codigo = 'SENADO_FEDERAL'
        """
    )
    op.execute(
        """
        CREATE TABLE ref.alias_filtro_partido (
            alias text PRIMARY KEY,
            tipo text NOT NULL CHECK (tipo IN ('EXECUTIVO', 'SEM_PARTIDO'))
        )
        """
    )
    op.execute(
        """
        INSERT INTO ref.alias_filtro_partido (alias, tipo) VALUES
            ('GOV', 'EXECUTIVO'), ('GOVERNO', 'EXECUTIVO'), ('PODER EXECUTIVO', 'EXECUTIVO'),
            ('S.PART.', 'SEM_PARTIDO'), ('SEM PARTIDO', 'SEM_PARTIDO')
        """
    )
    op.execute(
        """
        INSERT INTO param.peso (metodologia_id, dimensao, chave, valor)
        SELECT m.id, 'CORTE_DIAGNOSTICO_AUTOR', c.chave, c.valor
        FROM param.metodologia m
        CROSS JOIN (VALUES ('APROVADAS_ALTA', 2), ('APROVADAS_MEDIA', 1), ('LIDERANCA_VOLUME_ALTO', 20),
                           ('COAUTORIA_SOBRE_LIDERANCA', 2), ('LIDERANCA_PROPOSITIVA', 10)) AS c(chave, valor)
        WHERE m.codigo = 'IALP' AND m.versao = 3
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM param.peso WHERE dimensao = 'CORTE_DIAGNOSTICO_AUTOR'")
    op.execute("DROP TABLE IF EXISTS ref.alias_filtro_partido")
    op.execute("DROP TABLE IF EXISTS ref.cobertura_presenca")
    op.execute("ALTER TABLE ref.tipo_presenca DROP COLUMN IF EXISTS justificada")
