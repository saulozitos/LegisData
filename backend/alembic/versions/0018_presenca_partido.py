"""Partido do parlamentar no dia da presença (fonte: sigla informada pelo Senado em cada votação).

O Senado antes de 2023 não tem mandatos carregados; sem esta coluna o ranking de ausência por partido não
conseguiria atribuir um partido aos dias dos senadores desse período.

Revision ID: 0018
Revises: 0017
"""

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE leg.presenca ADD COLUMN partido_id bigint REFERENCES core.partido(id)")


def downgrade() -> None:
    op.execute("ALTER TABLE leg.presenca DROP COLUMN partido_id")
