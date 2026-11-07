"""Identificador `CPF_HMAC`: o CPF nunca é guardado, só o HMAC-SHA256 dele com uma chave secreta (`CPF_HMAC_KEY`).

O CPF das fontes oficiais (detalhe do deputado na API da Câmara; `consulta_cand` do TSE) liga a mesma pessoa mesmo quando o
nome muda entre as fontes. Sem a chave ninguém desfaz o valor gravado (um hash simples seria quebrado por força bruta: são
só 10^9 CPFs possíveis). Quem perder a chave perde só a capacidade de ligar CPFs novos aos antigos.

Revision ID: 0043
Revises: 0042
"""

from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE core.pessoa_identificador DROP CONSTRAINT pessoa_identificador_tipo_check")
    op.execute(
        "ALTER TABLE core.pessoa_identificador ADD CONSTRAINT pessoa_identificador_tipo_check "
        "CHECK (tipo = ANY (ARRAY['CAMARA_ID', 'SENADO_ID', 'TSE_ID', 'DATAJUD_ID', 'CURADORIA_ID', 'CPF_HMAC']))"
    )


def downgrade() -> None:
    op.execute("DELETE FROM core.pessoa_identificador WHERE tipo = 'CPF_HMAC'")
    op.execute("ALTER TABLE core.pessoa_identificador DROP CONSTRAINT pessoa_identificador_tipo_check")
    op.execute(
        "ALTER TABLE core.pessoa_identificador ADD CONSTRAINT pessoa_identificador_tipo_check "
        "CHECK (tipo = ANY (ARRAY['CAMARA_ID', 'SENADO_ID', 'TSE_ID', 'DATAJUD_ID', 'CURADORIA_ID']))"
    )
