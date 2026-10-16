"""Série do subsídio parlamentar em `eco`, com o decreto legislativo de cada valor.

O subsídio de deputados e senadores é fixado por decreto legislativo, então a fonte é a norma: cada observação guarda o
número do decreto em `nota`. Valor sem norma citada não entra (o de 2026 estava sem respaldo e foi descartado).

Revision ID: 0029
Revises: 0028
"""

from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO etl.fonte (codigo, nome, orgao, url_base, formato, periodicidade) VALUES "
        "('LEGISLACAO', 'Decretos legislativos do subsídio parlamentar', 'Congresso Nacional', "
        "'https://www.congressonacional.leg.br/legislacao-e-publicacoes/glossario-legislativo', 'CSV', 'ANUAL') "
        "ON CONFLICT (codigo) DO NOTHING"
    )
    op.execute(
        "INSERT INTO eco.serie (codigo, nome, categoria, periodicidade, unidade, abrangencia, fonte_id, descricao) "
        "SELECT 'SUBSIDIO_PARLAMENTAR', 'Subsídio mensal de deputado federal e senador', 'SALARIO', 'ANUAL', 'R$', "
        "'BR', f.id, 'Valor vigente no fim do ano, fixado por decreto legislativo (citado em cada observação).' "
        "FROM etl.fonte f WHERE f.codigo = 'LEGISLACAO'"
    )


def downgrade() -> None:
    op.execute("DELETE FROM eco.observacao WHERE serie_id IN (SELECT id FROM eco.serie WHERE codigo = 'SUBSIDIO_PARLAMENTAR')")
    op.execute("DELETE FROM eco.serie WHERE codigo = 'SUBSIDIO_PARLAMENTAR'")
    op.execute("DELETE FROM etl.fonte WHERE codigo = 'LEGISLACAO'")
