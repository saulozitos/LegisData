"""Categoria do tipo de proposição: a taxa de eficácia passa a considerar só projetos.

Requerimentos, indicações e pedidos de informação (REQ, INC, RIC, RCP, RQC) são pedidos formais e quase nunca "viram
norma"; contados no denominador eles diluem a taxa (cerca de 0,5% em 2024) e favorecem quem protocola menos pedidos.
Eles continuam pontuando no IPPM (peso 0,1). A fronteira é dado de referência, não código.

Revision ID: 0013
Revises: 0012
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

PEDIDOS = ("REQ", "INC", "RIC", "RCP", "RQC")


def upgrade() -> None:
    op.execute(
        "ALTER TABLE ref.tipo_proposicao ADD COLUMN categoria text NOT NULL DEFAULT 'PROJETO' "
        "CHECK (categoria IN ('PROJETO', 'PEDIDO'))"
    )
    lista = ", ".join(f"'{t}'" for t in PEDIDOS)
    op.execute(f"UPDATE ref.tipo_proposicao SET categoria = 'PEDIDO' WHERE codigo IN ({lista})")

    op.execute("DROP VIEW leg.vw_autoria_pontuada")
    op.execute(
        """
        CREATE VIEW leg.vw_autoria_pontuada AS
        SELECT a.id AS autoria_id, a.proposicao_id, a.pessoa_id, a.tipo_codigo AS tipo_autoria,
               p.tipo_codigo AS tipo_proposicao, t.categoria AS categoria_proposicao, p.status_codigo,
               p.data_apresentacao, p.id_camara IS NOT NULL AS da_camara, p.id_senado IS NOT NULL AS do_senado,
               coalesce(a.partido_id, f.partido_id,
                        (SELECT m.partido_id FROM core.mandato m
                          WHERE m.pessoa_id = a.pessoa_id AND m.partido_id IS NOT NULL
                            AND NOT EXISTS (SELECT 1 FROM core.filiacao x WHERE x.pessoa_id = a.pessoa_id)
                          ORDER BY m.inicio DESC LIMIT 1)) AS partido_id,
               (a.tipo_codigo = 'COAUTOR' AND p.tipo_codigo = 'PEC') AS apoio_quorum,
               param.peso_de('IALP', 'PESO_TIPO', p.tipo_codigo)
                 * coalesce(param.peso_opcional('IALP', 'PESO_AUTORIA_POR_TIPO', p.tipo_codigo || ':' || a.tipo_codigo),
                            param.peso_de('IALP', 'PESO_AUTORIA', a.tipo_codigo))
                 * param.peso_de('IALP', 'PESO_STATUS', p.status_codigo) AS pontos_ialp,
               param.peso_de('IALP', 'PESO_TIPO', p.tipo_codigo) AS pontos_relatoria
        FROM leg.autoria a
        JOIN leg.proposicao p ON p.id = a.proposicao_id
        JOIN ref.tipo_proposicao t ON t.codigo = p.tipo_codigo
        LEFT JOIN core.filiacao f ON f.pessoa_id = a.pessoa_id AND f.periodo @> p.data_apresentacao
        WHERE a.tipo_codigo <> 'INSTITUCIONAL' AND (a.pessoa_id IS NOT NULL OR a.partido_id IS NOT NULL)
        """
    )


def downgrade() -> None:
    raise NotImplementedError("Migração de categoria de proposição (0013) não é reversível.")
