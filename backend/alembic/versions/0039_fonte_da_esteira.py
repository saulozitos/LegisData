"""Fonte `PIPELINE`: dona da linha de execução da esteira inteira (`etl.execucao`, estágio `TUDO`).

A esteira (`python -m etl.run_etl`) passa a registrar uma execução própria, além da de cada fonte, para o relatório final
dizer quando a rodada começou, quanto durou e como terminou. Não é uma fonte de dados: nenhum `stg` ou `core` aponta para
ela, e `deploy.sh` e `semeadura_das_financas` só leem o estágio `CARREGAR`.

Revision ID: 0039
Revises: 0038
"""

from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO etl.fonte (codigo, nome, orgao, formato, periodicidade, observacao) VALUES "
        "('PIPELINE', 'Esteira do ETL (execução completa)', 'LegisData', 'N/A', 'SOB_DEMANDA', "
        "'Linha de execução da rodada inteira; não é fonte de dados') ON CONFLICT (codigo) DO NOTHING"
    )


def downgrade() -> None:
    # execuções já registradas apontam para a fonte: só a remove se nenhuma apontar (senão ela fica, inofensiva)
    op.execute(
        "DELETE FROM etl.fonte WHERE codigo = 'PIPELINE' "
        "AND NOT EXISTS (SELECT 1 FROM etl.execucao e WHERE e.fonte_id = etl.fonte.id)"
    )
