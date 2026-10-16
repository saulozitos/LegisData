"""Partido por dia determinístico, ponte sem autoria duplicada e uma única definição de "partido atual".

- `etl.resolver_partido_presenca()`: na aproximação pela presença mais próxima, prefere a mesma Casa e desempata por
  data mais recente e id, de modo que duas execuções dão o mesmo partido.
- A ponte do legado (`etl.sincronizar_legado_leg`) passa a (a) apagar a autoria implícita (criada só a partir de
  `autorPoliticoId`) quando o legado ganha uma linha de autor principal para a mesma proposição, o que evitava
  contar a autoria duas vezes; e (b) chamar `etl.resolver_partido_presenca()` ao terminar, porque ela regrava as linhas
  de presença do legado sem partido.
- `core.vw_partido_atual`: uma linha por pessoa com o partido vigente (histórico do mandato, depois filiação aberta,
  depois partido do mandato mais recente). Os filtros e rótulos de partido da API leem desta visão.

Revision ID: 0021
Revises: 0020
"""

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

FUNCAO_RESOLVER = r"""
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
                 ORDER BY (q.casa_id <> p2.casa_id), abs(q.data_sessao - p2.data_sessao), q.data_sessao DESC,
                          q.partido_id LIMIT 1) AS partido_id
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

VIEW = """
CREATE VIEW core.vw_partido_atual AS
SELECT DISTINCT ON (x.pessoa_id) x.pessoa_id, x.partido_id, cp.canonico_id, cp.canonico_sigla,
       cp.canonico_sigla_normalizada, x.origem
FROM (
    SELECT m.pessoa_id, mp.partido_id, 1 AS prioridade, 'HISTORICO_MANDATO' AS origem, lower(mp.periodo) AS referencia
    FROM core.mandato m JOIN core.mandato_partido mp ON mp.mandato_id = m.id
    WHERE mp.periodo @> current_date
    UNION ALL
    SELECT f.pessoa_id, f.partido_id, 2, 'FILIACAO', lower(f.periodo) FROM core.filiacao f WHERE upper_inf(f.periodo)
    UNION ALL
    SELECT m.pessoa_id, m.partido_id, 3, 'MANDATO', m.inicio FROM core.mandato m WHERE m.partido_id IS NOT NULL
) x
JOIN core.vw_partido_canonico cp ON cp.id = x.partido_id
ORDER BY x.pessoa_id, x.prioridade, x.referencia DESC
"""

PROCURA_DELETE = """    DELETE FROM leg.autoria l WHERE l.legado_id IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM public.proposicoes_autores a WHERE a.id = l.legado_id)
        AND NOT EXISTS (SELECT 1 FROM public.proposicoes p WHERE p.id = l.legado_id AND p."autorPoliticoId" IS NOT NULL);
"""

NOVO_DELETE = """    DELETE FROM leg.autoria l WHERE l.legado_id IS NOT NULL
        AND (
            (NOT EXISTS (SELECT 1 FROM public.proposicoes_autores a WHERE a.id = l.legado_id)
             AND NOT EXISTS (SELECT 1 FROM public.proposicoes p
                              WHERE p.id = l.legado_id AND p."autorPoliticoId" IS NOT NULL))
            -- autoria implícita (legado_id = id da proposição) substituída por autor principal explícito
            OR EXISTS (SELECT 1 FROM public.proposicoes_autores a2
                        WHERE a2."proposicaoId" = l.legado_id AND a2."tipoAutoria" = 'AUTOR_PRINCIPAL')
        );
"""

PROCURA_RETORNO = "    RETURN jsonb_build_object('execucao_id', v_execucao, 'proposicoes', v_props,"


def upgrade() -> None:
    op.execute(FUNCAO_RESOLVER)
    op.execute(VIEW)
    # a ponte é patchada sobre a definição vigente no banco (não sobre o texto de outra revisão)
    op.execute(
        f"""
        DO $mig$
        DECLARE v_def text;
        BEGIN
            v_def := pg_get_functiondef('etl.sincronizar_legado_leg()'::regprocedure);
            IF position({_lit(PROCURA_DELETE)} in v_def) = 0 OR position({_lit(PROCURA_RETORNO)} in v_def) = 0 THEN
                RAISE EXCEPTION 'definição inesperada de etl.sincronizar_legado_leg';
            END IF;
            v_def := replace(v_def, {_lit(PROCURA_DELETE)}, {_lit(NOVO_DELETE)});
            v_def := replace(v_def, {_lit(PROCURA_RETORNO)},
                             '    PERFORM etl.resolver_partido_presenca();' || chr(10) || {_lit(PROCURA_RETORNO)});
            EXECUTE v_def;
        END
        $mig$
        """
    )
    op.execute("SELECT etl.sincronizar_legado_leg()")


def _lit(valor: str) -> str:
    return "'" + valor.replace("'", "''") + "'"


def downgrade() -> None:
    raise NotImplementedError("Migração 0021 não é reversível.")
