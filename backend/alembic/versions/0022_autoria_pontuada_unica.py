"""Visão com uma linha por pessoa e proposição, para somar pontos IALP sem contar a mesma proposição duas vezes.

A fonte às vezes repete o mesmo parlamentar como autor principal e como coautor (ou relator) da mesma proposição.
`leg.vw_autoria_pontuada` mantém cada linha de autoria; esta visão fica com uma só por pessoa e proposição,
prevalecendo o papel de autor principal, depois o de relator e por fim o de coautor. Dossiê, ROI, ranking de autores e
ranking de ausências somam os pontos desta visão, de modo que o mesmo parlamentar tem o mesmo total em todas as telas.

Revision ID: 0022
Revises: 0021
"""

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE VIEW leg.vw_autoria_pontuada_unica AS
        SELECT DISTINCT ON (v.pessoa_id, v.proposicao_id) v.*
        FROM leg.vw_autoria_pontuada v
        WHERE v.pessoa_id IS NOT NULL
        ORDER BY v.pessoa_id, v.proposicao_id,
                 CASE v.tipo_autoria WHEN 'AUTOR_PRINCIPAL' THEN 0 WHEN 'RELATOR' THEN 1 ELSE 2 END,
                 v.pontos_ialp DESC, v.autoria_id
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS leg.vw_autoria_pontuada_unica")
