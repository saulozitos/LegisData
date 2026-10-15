"""Pesos do IPPM em param, função de consulta e view de autoria pontuada.

Os pesos replicam exatamente os CASE WHEN que estavam no SQL de party_productivity_service.py (comportamento
preservado). Há três conjuntos de pesos divergentes no código legado (IPPM, IALP do ranking de autores e o dicionário
PESO_*); manter os três como metodologias separadas torna a divergência visível e decidível.

Revision ID: 0007
Revises: 0006
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

# chave '*' = valor padrão (o ELSE do CASE original)
PESOS_IPPM = {
    "PESO_TIPO": {
        "PEC": 3.0,
        "PLP": 2.5,
        "PL": 2.0,
        "MPV": 2.0,
        "PDL": 1.0,
        "PR": 1.0,
        "PRC": 1.0,
        "PDS": 1.0,
        "REQ": 0.1,
        "INC": 0.1,
        "*": 0.5,
    },
    "PESO_TIPO_RELATORIA": {
        "PEC": 3.0,
        "PLP": 2.5,
        "PL": 2.0,
        "MPV": 2.0,
        "PDL": 1.0,
        "PR": 1.0,
        "PRC": 1.0,
        "PDS": 1.0,
        "*": 0.1,
    },
    "PESO_AUTORIA": {"AUTOR_PRINCIPAL": 1.0, "RELATOR": 0.8, "COAUTOR": 0.2, "*": 0.0},
    "PESO_STATUS": {
        "APROVADA_E_SANCIONADA": 3.0,
        "APROVADA_E_PROMULGADA": 3.0,
        "APROVADO_PLENARIO": 2.0,
        "APROVADO_COMISSAO": 1.5,
        "EM_TRAMITACAO": 1.0,
        "ARQUIVADA": 0.8,
        "REJEITADA": 0.5,
        "*": 1.0,
    },
}
STATUS_APROVADOS = ("APROVADA_E_SANCIONADA", "APROVADA_E_PROMULGADA", "APROVADO_PLENARIO")


def upgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql(
        "INSERT INTO param.metodologia (codigo, versao, descricao) VALUES "
        "('IPPM', 1, 'Índice de Produtividade Partidária Média: pesos do SQL de party_productivity_service.py')"
    )
    for dimensao, pesos in PESOS_IPPM.items():
        for chave, valor in pesos.items():
            bind.exec_driver_sql(
                "INSERT INTO param.peso (metodologia_id, dimensao, chave, valor) "
                "SELECT id, %s, %s, %s FROM param.metodologia WHERE codigo = 'IPPM' AND versao = 1",
                (dimensao, chave, valor),
            )

    # Peso vigente (maior versão) de uma metodologia; cai no valor '*' quando a chave não existe
    op.execute(
        """
        CREATE FUNCTION param.peso_de(p_metodologia text, p_dimensao text, p_chave text) RETURNS numeric
        LANGUAGE sql STABLE AS $$
            SELECT p.valor
            FROM param.peso p
            JOIN param.metodologia m ON m.id = p.metodologia_id
            WHERE m.codigo = p_metodologia AND p.dimensao = p_dimensao AND p.chave IN (p_chave, '*')
              AND m.versao = (SELECT max(versao) FROM param.metodologia WHERE codigo = p_metodologia)
            ORDER BY (p.chave = '*') LIMIT 1
        $$
        """
    )

    # Uma linha por (proposição, autor) com o partido do autor NA DATA DE APRESENTAÇÃO e a pontuação do IPPM.
    # Autoria institucional ou sem pessoa identificada não pontua.
    op.execute(
        """
        CREATE VIEW leg.vw_autoria_ippm AS
        SELECT a.id AS autoria_id, a.proposicao_id, a.pessoa_id, a.tipo_codigo AS tipo_autoria,
               p.tipo_codigo AS tipo_proposicao, p.status_codigo, p.id_camara IS NOT NULL AS da_camara,
               p.id_senado IS NOT NULL AS do_senado,
               coalesce(f.partido_id,
                        (SELECT m.partido_id FROM core.mandato m
                          WHERE m.pessoa_id = a.pessoa_id AND m.partido_id IS NOT NULL
                            AND NOT EXISTS (SELECT 1 FROM core.filiacao x WHERE x.pessoa_id = a.pessoa_id)
                          ORDER BY m.inicio DESC LIMIT 1)) AS partido_id,
               param.peso_de('IPPM', 'PESO_TIPO', p.tipo_codigo)
                 * param.peso_de('IPPM', 'PESO_AUTORIA', a.tipo_codigo)
                 * param.peso_de('IPPM', 'PESO_STATUS', p.status_codigo) AS pontos_ialp,
               param.peso_de('IPPM', 'PESO_TIPO_RELATORIA', p.tipo_codigo) AS pontos_relatoria
        FROM leg.autoria a
        JOIN leg.proposicao p ON p.id = a.proposicao_id
        LEFT JOIN core.filiacao f ON f.pessoa_id = a.pessoa_id AND f.periodo @> p.data_apresentacao
        WHERE a.pessoa_id IS NOT NULL AND a.tipo_codigo <> 'INSTITUCIONAL'
        """
    )

    # O histórico por partido agora precisa de foto e sigla normalizada (consumidos pelo IPPM e pela linha do tempo)
    op.execute("DROP VIEW core.vw_historico_mandato")
    op.execute(
        """
        CREATE VIEW core.vw_historico_mandato AS
        SELECT s.id, m.pessoa_id, m.partido_id, pa.sigla AS partido_sigla,
               pa.sigla_normalizada AS partido_sigla_normalizada, fm.url_origem AS foto_url,
               CASE c.codigo WHEN 'DEPUTADO_FEDERAL' THEN 'CAMARA' WHEN 'SENADOR' THEN 'SENADO' ELSE 'OUTRO' END AS casa,
               CASE WHEN m.motivo_encerramento IS NOT NULL AND upper(s.periodo) IS NULL THEN 'ENCERRADO'
                    ELSE s.situacao END AS situacao,
               lower(s.periodo) AS data_inicio, upper(s.periodo) - 1 AS data_fim, s.motivo AS observacao
        FROM core.mandato_situacao s
        JOIN core.mandato m ON m.id = s.mandato_id
        JOIN ref.cargo c ON c.id = m.cargo_id
        JOIN core.pessoa pe ON pe.id = m.pessoa_id
        LEFT JOIN core.midia fm ON fm.id = pe.foto_midia_id
        LEFT JOIN core.partido pa ON pa.id = m.partido_id
        """
    )

    # Placar de cada votação: contagem dos votos nominais quando existem, senão o informado pela fonte
    op.execute(
        """
        CREATE VIEW leg.vw_votacao_placar AS
        SELECT v.id AS votacao_id,
               coalesce(n.total, 0) > 0 AS tem_voto_nominal,
               CASE WHEN coalesce(n.total, 0) > 0 THEN n.sim ELSE coalesce(v.total_sim_fonte, 0) END AS sim,
               CASE WHEN coalesce(n.total, 0) > 0 THEN n.nao ELSE coalesce(v.total_nao_fonte, 0) END AS nao,
               CASE WHEN coalesce(n.total, 0) > 0 THEN n.abstencao ELSE coalesce(v.total_abstencao_fonte, 0) END AS abstencao,
               CASE WHEN coalesce(n.total, 0) > 0 THEN n.obstrucao ELSE coalesce(v.total_obstrucao_fonte, 0) END AS obstrucao
        FROM leg.votacao v
        LEFT JOIN (
            SELECT votacao_id, count(*) AS total,
                   count(*) FILTER (WHERE opcao_codigo = 'SIM') AS sim,
                   count(*) FILTER (WHERE opcao_codigo = 'NAO') AS nao,
                   count(*) FILTER (WHERE opcao_codigo = 'ABSTENCAO') AS abstencao,
                   count(*) FILTER (WHERE opcao_codigo = 'OBSTRUCAO') AS obstrucao
            FROM leg.voto GROUP BY votacao_id
        ) n ON n.votacao_id = v.id
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS leg.vw_votacao_placar, leg.vw_autoria_ippm")
    op.execute("DROP VIEW core.vw_historico_mandato")
    op.execute(
        """
        CREATE VIEW core.vw_historico_mandato AS
        SELECT s.id, m.pessoa_id, m.partido_id, pa.sigla AS partido_sigla,
               CASE c.codigo WHEN 'DEPUTADO_FEDERAL' THEN 'CAMARA' WHEN 'SENADOR' THEN 'SENADO' ELSE 'OUTRO' END AS casa,
               CASE WHEN m.motivo_encerramento IS NOT NULL AND upper(s.periodo) IS NULL THEN 'ENCERRADO'
                    ELSE s.situacao END AS situacao,
               lower(s.periodo) AS data_inicio, upper(s.periodo) - 1 AS data_fim, s.motivo AS observacao
        FROM core.mandato_situacao s
        JOIN core.mandato m ON m.id = s.mandato_id
        JOIN ref.cargo c ON c.id = m.cargo_id
        LEFT JOIN core.partido pa ON pa.id = m.partido_id
        """
    )
    op.execute("DROP FUNCTION IF EXISTS param.peso_de(text, text, text)")
    op.execute("DELETE FROM param.metodologia WHERE codigo = 'IPPM' AND versao = 1")
