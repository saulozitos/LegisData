"""Situação oficial nova da Câmara: "Aguardando Chancela e Publicação do Despacho".

A Câmara passou a informar essa situação em proposições de 2026 (50 projetos de lei na carga de 9 de novembro de 2026). Sem
linha em `ref.situacao_camara` a carga rejeitava a proposição (`SITUACAO_SEM_MAPEAMENTO`) e a verificação
`camara_bulk_cobertura` ficava com alerta. É a mesma etapa de "Aguardando Despacho do Presidente da Câmara dos Deputados
(Chancela)" (despacho já decidido, à espera de chancela e publicação): a proposição segue em tramitação.

Revision ID: 0040
Revises: 0039
"""

from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None

DESCRICAO = "Aguardando Chancela e Publicação do Despacho"


def upgrade() -> None:
    op.execute(
        "INSERT INTO ref.situacao_camara (descricao, status_codigo, observacao) "
        f"SELECT '{DESCRICAO}', 'EM_TRAMITACAO', 'Mesma etapa de Aguardando Despacho do Presidente da Câmara dos Deputados (Chancela)' "
        f"WHERE NOT EXISTS (SELECT 1 FROM ref.situacao_camara WHERE descricao = '{DESCRICAO}' AND tipo_codigo IS NULL)"
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM ref.situacao_camara WHERE descricao = '{DESCRICAO}' AND tipo_codigo IS NULL")
