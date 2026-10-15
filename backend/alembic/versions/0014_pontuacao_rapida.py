"""Pontuação em lote: pesos por junção (sem chamar função por linha) e partido resolvido só quando falta.

Com ~700 mil autorias, chamar param.peso_de() três vezes por linha deixava o ranking em 4 a 10 segundos. Os pesos vigentes
passam a vir de uma view e entram por junção; o resultado é o mesmo. Falta de peso continua sendo erro: a view devolve
NULL e a verificação etl.verificar_pesos() acusa qualquer tipo, status ou autoria sem peso.

Revision ID: 0014
Revises: 0013
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE VIEW param.vw_peso_vigente AS
        SELECT m.codigo AS metodologia, p.dimensao, p.chave, p.valor
        FROM param.peso p JOIN param.metodologia m ON m.id = p.metodologia_id
        WHERE m.versao = (SELECT max(x.versao) FROM param.metodologia x WHERE x.codigo = m.codigo)
        """
    )
    op.execute(
        """
        CREATE FUNCTION etl.verificar_pesos() RETURNS TABLE (dimensao text, chave text)
        LANGUAGE sql STABLE AS $$
            SELECT 'PESO_TIPO', t.codigo FROM ref.tipo_proposicao t
              WHERE NOT EXISTS (SELECT 1 FROM param.vw_peso_vigente w
                                 WHERE w.metodologia = 'IALP' AND w.dimensao = 'PESO_TIPO' AND w.chave = t.codigo)
            UNION ALL
            SELECT 'PESO_STATUS', s.codigo FROM ref.status_tramitacao s
              WHERE NOT EXISTS (SELECT 1 FROM param.vw_peso_vigente w
                                 WHERE w.metodologia = 'IALP' AND w.dimensao = 'PESO_STATUS' AND w.chave = s.codigo)
            UNION ALL
            SELECT 'PESO_AUTORIA', a.codigo FROM ref.tipo_autoria a
              WHERE NOT EXISTS (SELECT 1 FROM param.vw_peso_vigente w
                                 WHERE w.metodologia = 'IALP' AND w.dimensao = 'PESO_AUTORIA' AND w.chave = a.codigo)
        $$
        """
    )
    op.execute("DROP VIEW leg.vw_autoria_pontuada")
    op.execute(
        """
        CREATE VIEW leg.vw_autoria_pontuada AS
        SELECT a.id AS autoria_id, a.proposicao_id, a.pessoa_id, a.tipo_codigo AS tipo_autoria,
               p.tipo_codigo AS tipo_proposicao, t.categoria AS categoria_proposicao, p.status_codigo,
               p.data_apresentacao, p.id_camara IS NOT NULL AS da_camara, p.id_senado IS NOT NULL AS do_senado,
               coalesce(a.partido_id,
                        (SELECT f.partido_id FROM core.filiacao f
                          WHERE f.pessoa_id = a.pessoa_id AND f.periodo @> p.data_apresentacao LIMIT 1),
                        (SELECT m.partido_id FROM core.mandato m
                          WHERE m.pessoa_id = a.pessoa_id AND m.partido_id IS NOT NULL
                            AND NOT EXISTS (SELECT 1 FROM core.filiacao x WHERE x.pessoa_id = a.pessoa_id)
                          ORDER BY m.inicio DESC LIMIT 1)) AS partido_id,
               (a.tipo_codigo = 'COAUTOR' AND p.tipo_codigo = 'PEC') AS apoio_quorum,
               wt.valor * coalesce(wx.valor, wa.valor) * ws.valor AS pontos_ialp,
               wt.valor AS pontos_relatoria
        FROM leg.autoria a
        JOIN leg.proposicao p ON p.id = a.proposicao_id
        JOIN ref.tipo_proposicao t ON t.codigo = p.tipo_codigo
        LEFT JOIN param.vw_peso_vigente wt
               ON wt.metodologia = 'IALP' AND wt.dimensao = 'PESO_TIPO' AND wt.chave = p.tipo_codigo
        LEFT JOIN param.vw_peso_vigente wa
               ON wa.metodologia = 'IALP' AND wa.dimensao = 'PESO_AUTORIA' AND wa.chave = a.tipo_codigo
        LEFT JOIN param.vw_peso_vigente ws
               ON ws.metodologia = 'IALP' AND ws.dimensao = 'PESO_STATUS' AND ws.chave = p.status_codigo
        LEFT JOIN param.vw_peso_vigente wx
               ON wx.metodologia = 'IALP' AND wx.dimensao = 'PESO_AUTORIA_POR_TIPO'
              AND wx.chave = p.tipo_codigo || ':' || a.tipo_codigo
        WHERE a.tipo_codigo <> 'INSTITUCIONAL' AND (a.pessoa_id IS NOT NULL OR a.partido_id IS NOT NULL)
        """
    )
    op.execute("ANALYZE leg.autoria")
    op.execute("ANALYZE leg.proposicao")


def downgrade() -> None:
    raise NotImplementedError("Migração de pontuação em lote (0014) não é reversível.")
