"""IALP v2: um único conjunto de pesos (fonte de verdade) em param.peso.

Decisão de 2026-10-15 (ver docs/PLANO_REFATORACAO_BANCO_DE_DADOS.md): unifica os conjuntos divergentes do SQL do
IPPM, de legislative_scoring.py e dos dicionários PESO_*. Pesos conforme docs/METODOLOGIA_ATIVIDADE_LEGISLATIVA.md,
com veto parcial = 1,5; veto total = 0,8; decreto presidencial e lei delegada = 1,0. Não existe valor padrão ('*'):
tipos e status são explícitos e param.peso_de() falha quando falta peso.

Revision ID: 0008
Revises: 0007
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

PESOS = {
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
        "DECRETO_PRES": 1.0,
        "LEI_DELEGADA": 1.0,
    },
    "PESO_AUTORIA": {"AUTOR_PRINCIPAL": 1.0, "RELATOR": 0.8, "COAUTOR": 0.2, "INSTITUCIONAL": 0.0},
    "PESO_STATUS": {
        "APROVADA_E_SANCIONADA": 3.0,
        "APROVADA_E_PROMULGADA": 3.0,
        "APROVADO_PLENARIO": 2.0,
        "APROVADO_COMISSAO": 1.5,
        "EM_TRAMITACAO": 1.0,
        "ARQUIVADA": 0.8,
        "REJEITADA": 0.5,
        "VETADA_PARCIAL": 1.5,
        "VETADA_TOTAL": 0.8,
    },
}


def upgrade() -> None:
    op.execute("DROP VIEW leg.vw_autoria_ippm")
    # Os snapshots v1 (cópias das constantes do código) deixam de existir; IPLE permanece
    op.execute("DELETE FROM param.metodologia WHERE (codigo, versao) IN (('IALP', 1), ('IPPM', 1))")

    bind = op.get_bind()
    bind.exec_driver_sql(
        "INSERT INTO param.metodologia (codigo, versao, descricao) VALUES "
        "('IALP', 2, 'Índice de Atividade Legislativa Ponderado: conjunto único de pesos (IPPM, ranking de autores "
        "e perfil do parlamentar). Fonte: docs/METODOLOGIA_ATIVIDADE_LEGISLATIVA.md')"
    )
    for dimensao, pesos in PESOS.items():
        for chave, valor in pesos.items():
            bind.exec_driver_sql(
                "INSERT INTO param.peso (metodologia_id, dimensao, chave, valor) "
                "SELECT id, %s, %s, %s FROM param.metodologia WHERE codigo = 'IALP' AND versao = 2",
                (dimensao, chave, valor),
            )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION param.peso_de(p_metodologia text, p_dimensao text, p_chave text) RETURNS numeric
        LANGUAGE plpgsql STABLE AS $$
        DECLARE
            v_valor numeric;
        BEGIN
            SELECT p.valor INTO v_valor
            FROM param.peso p
            JOIN param.metodologia m ON m.id = p.metodologia_id
            WHERE m.codigo = p_metodologia AND p.dimensao = p_dimensao AND p.chave = p_chave
              AND m.versao = (SELECT max(versao) FROM param.metodologia WHERE codigo = p_metodologia);
            IF v_valor IS NULL THEN
                RAISE EXCEPTION 'Peso não configurado: metodologia=%, dimensao=%, chave=%',
                    p_metodologia, p_dimensao, p_chave;
            END IF;
            RETURN v_valor;
        END $$
        """
    )

    # Uma linha por (proposição, autor) com o partido do autor NA DATA DE APRESENTAÇÃO e as pontuações do IALP.
    # Autoria institucional ou sem pessoa identificada não pontua.
    op.execute(
        """
        CREATE VIEW leg.vw_autoria_pontuada AS
        SELECT a.id AS autoria_id, a.proposicao_id, a.pessoa_id, a.tipo_codigo AS tipo_autoria,
               p.tipo_codigo AS tipo_proposicao, p.status_codigo, p.id_camara IS NOT NULL AS da_camara,
               p.id_senado IS NOT NULL AS do_senado,
               coalesce(f.partido_id,
                        (SELECT m.partido_id FROM core.mandato m
                          WHERE m.pessoa_id = a.pessoa_id AND m.partido_id IS NOT NULL
                            AND NOT EXISTS (SELECT 1 FROM core.filiacao x WHERE x.pessoa_id = a.pessoa_id)
                          ORDER BY m.inicio DESC LIMIT 1)) AS partido_id,
               param.peso_de('IALP', 'PESO_TIPO', p.tipo_codigo)
                 * param.peso_de('IALP', 'PESO_AUTORIA', a.tipo_codigo)
                 * param.peso_de('IALP', 'PESO_STATUS', p.status_codigo) AS pontos_ialp,
               param.peso_de('IALP', 'PESO_TIPO', p.tipo_codigo) AS pontos_relatoria
        FROM leg.autoria a
        JOIN leg.proposicao p ON p.id = a.proposicao_id
        LEFT JOIN core.filiacao f ON f.pessoa_id = a.pessoa_id AND f.periodo @> p.data_apresentacao
        WHERE a.pessoa_id IS NOT NULL AND a.tipo_codigo <> 'INSTITUCIONAL'
        """
    )


def downgrade() -> None:
    raise NotImplementedError(
        "A unificação dos pesos (IALP v2) não é reversível: os conjuntos v1 divergentes foram removidos."
    )
