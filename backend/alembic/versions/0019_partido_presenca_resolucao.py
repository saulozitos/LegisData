"""Resolução do partido de cada dia de presença, com a origem registrada.

Ordem: sigla informada na votação (Senado) > partido do mandato no dia > filiação vigente no dia > partido da
presença mais próxima do mesmo parlamentar. A origem fica em `partido_origem` para que se saiba quando o partido é
aproximado.

Revision ID: 0019
Revises: 0018
"""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

FUNCAO = r"""
CREATE OR REPLACE FUNCTION etl.resolver_partido_presenca() RETURNS jsonb LANGUAGE plpgsql AS $fn$
DECLARE v_votacao int; v_mandato int; v_filiacao int; v_proxima int; v_restante bigint;
BEGIN
    UPDATE leg.presenca SET partido_origem = 'VOTACAO' WHERE partido_id IS NOT NULL AND partido_origem IS NULL;
    GET DIAGNOSTICS v_votacao = ROW_COUNT;

    UPDATE leg.presenca p SET partido_id = x.partido_id, partido_origem = 'MANDATO'
    FROM (
        SELECT p2.pessoa_id, p2.casa_id, p2.data_sessao, coalesce(mp.partido_id, m.partido_id) AS partido_id
        FROM leg.presenca p2
        JOIN core.mandato m ON m.id = p2.mandato_id
        LEFT JOIN core.mandato_partido mp ON mp.mandato_id = m.id AND mp.periodo @> p2.data_sessao
        WHERE p2.partido_id IS NULL
    ) x
    WHERE x.partido_id IS NOT NULL AND p.pessoa_id = x.pessoa_id AND p.casa_id = x.casa_id
      AND p.data_sessao = x.data_sessao;
    GET DIAGNOSTICS v_mandato = ROW_COUNT;

    UPDATE leg.presenca p SET partido_id = x.partido_id, partido_origem = 'FILIACAO'
    FROM (
        SELECT DISTINCT ON (p2.pessoa_id, p2.casa_id, p2.data_sessao)
               p2.pessoa_id, p2.casa_id, p2.data_sessao, f.partido_id
        FROM leg.presenca p2 JOIN core.filiacao f ON f.pessoa_id = p2.pessoa_id AND f.periodo @> p2.data_sessao
        WHERE p2.partido_id IS NULL
        ORDER BY p2.pessoa_id, p2.casa_id, p2.data_sessao, lower(f.periodo) DESC
    ) x
    WHERE p.pessoa_id = x.pessoa_id AND p.casa_id = x.casa_id AND p.data_sessao = x.data_sessao;
    GET DIAGNOSTICS v_filiacao = ROW_COUNT;

    UPDATE leg.presenca p SET partido_id = x.partido_id, partido_origem = 'PRESENCA_PROXIMA'
    FROM (
        SELECT p2.pessoa_id, p2.casa_id, p2.data_sessao,
               (SELECT q.partido_id FROM leg.presenca q
                 WHERE q.pessoa_id = p2.pessoa_id AND q.partido_id IS NOT NULL
                 ORDER BY abs(q.data_sessao - p2.data_sessao) LIMIT 1) AS partido_id
        FROM leg.presenca p2 WHERE p2.partido_id IS NULL
          AND EXISTS (SELECT 1 FROM leg.presenca q WHERE q.pessoa_id = p2.pessoa_id AND q.partido_id IS NOT NULL)
    ) x
    WHERE x.partido_id IS NOT NULL AND p.pessoa_id = x.pessoa_id AND p.casa_id = x.casa_id
      AND p.data_sessao = x.data_sessao;
    GET DIAGNOSTICS v_proxima = ROW_COUNT;

    SELECT count(*) INTO v_restante FROM leg.presenca WHERE partido_id IS NULL;
    RETURN jsonb_build_object('votacao', v_votacao, 'mandato', v_mandato, 'filiacao', v_filiacao,
                              'presenca_proxima', v_proxima, 'sem_partido', v_restante);
END
$fn$;
"""


def upgrade() -> None:
    op.execute(
        "ALTER TABLE leg.presenca ADD COLUMN partido_origem text "
        "CHECK (partido_origem IN ('VOTACAO', 'MANDATO', 'FILIACAO', 'PRESENCA_PROXIMA'))"
    )
    op.execute(FUNCAO)


def downgrade() -> None:
    raise NotImplementedError("Migração 0019 não é reversível.")
