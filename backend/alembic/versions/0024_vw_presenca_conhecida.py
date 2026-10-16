"""Visão das presenças em que a falta é conhecida, com a casa, a justificativa e o tipo de falta já resolvidos.

Só entram dias a partir de `ref.cobertura_presenca.falta_desde` de cada Casa (a Câmara antes de 2003-02-03 publica
apenas presença). `com_justificativa` indica que a fonte do dia informa justificativa; `na_inferencia`, que a falta
daquele dia só pode ser inferida. Os rankings de ausências e o dossiê leem desta visão.

Revision ID: 0024
Revises: 0023
"""

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE VIEW leg.vw_presenca_conhecida AS
        SELECT p.pessoa_id, p.mandato_id, p.partido_id, p.partido_origem, p.data_sessao, p.tipo_codigo,
               c.codigo AS casa, t.presente, t.justificada,
               p.data_sessao >= cob.justificativa_desde AS com_justificativa,
               p.data_sessao < cob.justificativa_desde AS na_inferencia
        FROM leg.presenca p
        JOIN ref.casa_legislativa c ON c.id = p.casa_id
        JOIN ref.cobertura_presenca cob ON cob.casa_id = p.casa_id
        JOIN ref.tipo_presenca t ON t.codigo = p.tipo_codigo
        WHERE p.data_sessao >= cob.falta_desde
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS leg.vw_presenca_conhecida")
