"""Ponte legado -> leg (proposição, autoria, votação unificada, voto, orientação, presença).

Revision ID: 0006
Revises: 0005
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

FUNCAO = r"""
CREATE OR REPLACE FUNCTION etl.sincronizar_legado_leg() RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    v_fonte smallint := (SELECT id FROM etl.fonte WHERE codigo = 'LEGADO');
    v_execucao bigint;
    v_props int; v_autorias int; v_votacoes int; v_votos int; v_orient int; v_pres int; v_rej int;
BEGIN
    INSERT INTO etl.execucao (fonte_id, estagio) VALUES (v_fonte, 'LEGADO') RETURNING id INTO v_execucao;
    DELETE FROM etl.rejeito WHERE recurso IN ('proposicao','voto','presenca')
        AND execucao_id IN (SELECT id FROM etl.execucao WHERE fonte_id = v_fonte AND id <> v_execucao);

    -- ── proposições (janela de dados: a partir de 1995) ─────────────────────────────────────────
    INSERT INTO etl.rejeito (execucao_id, recurso, chave_natural, motivo, payload)
    SELECT v_execucao, 'proposicao', p.id::text, 'FORA_DA_JANELA_1995',
           jsonb_build_object('tipo', p.tipo, 'numero', p.numero, 'ano', p.ano)
    FROM public.proposicoes p WHERE p.ano < 1995 OR p."dataApresentacao" < DATE '1995-01-01';

    INSERT INTO leg.proposicao (uid, id_camara, id_senado, tipo_codigo, numero, ano, titulo, ementa, explicacao_ementa,
                                area_tematica, data_apresentacao, data_sancao_promulgacao, status_codigo,
                                url_texto_original, url_oficial, reforma_estrutural, iniciativa_executivo,
                                autor_pessoa_id, autor_nome, eixo_impacto, eixos_impacto, fonte_id)
    SELECT p.id, p."idExternoCamara", p."idExternoSenado", p.tipo::text, p.numero, p.ano, p.titulo, p.ementa,
           p."explicacaoEmenta", p."areaTematica", p."dataApresentacao", p."dataSancaoPromulgacao",
           p."statusTramitacao"::text, p."urlTextoOriginal", p."urlOficial", p."isReformaEstrutural",
           p."iniciativaPoderExecutivo", pe.id, p."autorNome", p."eixoImpacto", p."eixosImpacto", v_fonte
    FROM public.proposicoes p LEFT JOIN core.pessoa pe ON pe.uid = p."autorPoliticoId"
    WHERE p.ano >= 1995 AND p."dataApresentacao" >= DATE '1995-01-01'
    ON CONFLICT (uid) DO UPDATE SET
        id_camara = EXCLUDED.id_camara, id_senado = EXCLUDED.id_senado, tipo_codigo = EXCLUDED.tipo_codigo,
        numero = EXCLUDED.numero, ano = EXCLUDED.ano, titulo = EXCLUDED.titulo, ementa = EXCLUDED.ementa,
        explicacao_ementa = EXCLUDED.explicacao_ementa, area_tematica = EXCLUDED.area_tematica,
        data_apresentacao = EXCLUDED.data_apresentacao, data_sancao_promulgacao = EXCLUDED.data_sancao_promulgacao,
        status_codigo = EXCLUDED.status_codigo, url_texto_original = EXCLUDED.url_texto_original,
        url_oficial = EXCLUDED.url_oficial, reforma_estrutural = EXCLUDED.reforma_estrutural,
        iniciativa_executivo = EXCLUDED.iniciativa_executivo, autor_pessoa_id = EXCLUDED.autor_pessoa_id,
        autor_nome = EXCLUDED.autor_nome, eixo_impacto = EXCLUDED.eixo_impacto, eixos_impacto = EXCLUDED.eixos_impacto;
    GET DIAGNOSTICS v_props = ROW_COUNT;
    DELETE FROM leg.proposicao l WHERE l.fonte_id = v_fonte AND NOT EXISTS (SELECT 1 FROM public.proposicoes p WHERE p.id = l.uid);

    -- ── autoria ─────────────────────────────────────────────────────────────────────────────────
    INSERT INTO leg.autoria (proposicao_id, pessoa_id, nome_autor, tipo_codigo, ordem, legado_id)
    SELECT lp.id, pe.id, a."nomeAutor", a."tipoAutoria"::text, a.ordem, a.id
    FROM public.proposicoes_autores a
    JOIN leg.proposicao lp ON lp.uid = a."proposicaoId"
    LEFT JOIN core.pessoa pe ON pe.uid = a."politicoId"
    ON CONFLICT (legado_id) DO UPDATE SET
        proposicao_id = EXCLUDED.proposicao_id, pessoa_id = EXCLUDED.pessoa_id, nome_autor = EXCLUDED.nome_autor,
        tipo_codigo = EXCLUDED.tipo_codigo, ordem = EXCLUDED.ordem;
    GET DIAGNOSTICS v_autorias = ROW_COUNT;
    DELETE FROM leg.autoria l WHERE l.legado_id IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM public.proposicoes_autores a WHERE a.id = l.legado_id);

    -- ── votações: votacoes_proposicao + sessoes_votacao viram uma só ────────────────────────────
    CREATE TEMP TABLE _sv ON COMMIT DROP AS
    SELECT s.*, row_number() OVER (PARTITION BY s."proposicaoId", s."dataHoraVotacao" ORDER BY s.id) AS rn,
           EXISTS (SELECT 1 FROM public.votos_parlamentares v WHERE v."sessaoVotacaoId" = s.id) AS tem_votos
    FROM public.sessoes_votacao s;

    CREATE TEMP TABLE _vot ON COMMIT DROP AS
    SELECT coalesce(vp.id, sv.id) AS uid, vp.id AS vp_id, sv.id AS sv_id, lp.id AS proposicao_id,
           coalesce(vp.data_hora, sv."dataHoraVotacao") AS data_hora,
           sv."idExterno" AS id_externo,
           (SELECT c.id FROM ref.casa_legislativa c WHERE c.codigo = coalesce(sv."casaLegislativa"::text,
                CASE WHEN vp.local_deliberacao ILIKE '%senado%' THEN 'SENADO_FEDERAL'
                     WHEN vp.local_deliberacao ILIKE '%câmara%' OR vp.local_deliberacao ILIKE '%camara%'
                          OR vp.local_deliberacao ILIKE '%CCJC%' THEN 'CAMARA_DOS_DEPUTADOS' END)) AS casa_id,
           sv."tituloPauta" AS titulo_pauta, sv."descricaoDetalhada" AS descricao,
           CASE WHEN vp.tipo_deliberacao IS NOT NULL THEN vp.tipo_deliberacao
                WHEN sv.tem_votos THEN 'NOMINAL' WHEN sv."isVotacaoSecreta" THEN 'SECRETA' ELSE 'SIMBOLICA' END AS tipo,
           coalesce(sv."isVotacaoSecreta", false) AS secreta,
           coalesce(vp.aprovada, sv.aprovada) AS aprovada,
           vp.local_deliberacao, vp.nome_comissao, vp.link_ata_reuniao, vp.relator_nome, vp.parecer_relator_numero,
           vp.parecer_relator_texto, vp.link_parecer_relator, vp.resumo_decisao, sv."orientacaoGoverno" AS orientacao_governo,
           coalesce(nullif(vp.total_sim, 0), nullif(sv."totalSim", 0)) AS t_sim,
           coalesce(nullif(vp.total_nao, 0), nullif(sv."totalNao", 0)) AS t_nao,
           coalesce(nullif(vp.total_abstencao, 0), nullif(sv."totalAbstencao", 0)) AS t_abs,
           coalesce(nullif(vp.total_obstrucao, 0), nullif(sv."totalObstrucao", 0)) AS t_obs
    FROM (SELECT x.*, row_number() OVER (PARTITION BY x.proposicao_id, x.data_hora ORDER BY x.id) AS rnv
          FROM public.votacoes_proposicao x) vp
    FULL JOIN _sv sv
           ON sv."proposicaoId" = vp.proposicao_id AND sv."dataHoraVotacao" = vp.data_hora AND sv.rn = vp.rnv
    JOIN leg.proposicao lp ON lp.uid = coalesce(vp.proposicao_id, sv."proposicaoId");

    INSERT INTO leg.votacao (uid, id_externo, proposicao_id, casa_id, data_hora, titulo_pauta, descricao, tipo_deliberacao,
                             secreta, aprovada, local_deliberacao, nome_comissao, link_ata, relator_nome, parecer_numero,
                             parecer_texto, link_parecer, resumo_decisao, orientacao_governo, total_sim_fonte,
                             total_nao_fonte, total_abstencao_fonte, total_obstrucao_fonte, fonte_id)
    SELECT uid, id_externo, proposicao_id, casa_id, data_hora, titulo_pauta, descricao, tipo, secreta, aprovada,
           local_deliberacao, nome_comissao, link_ata_reuniao, relator_nome, parecer_relator_numero, parecer_relator_texto,
           link_parecer_relator, resumo_decisao, orientacao_governo, t_sim, t_nao, t_abs, t_obs, v_fonte
    FROM _vot WHERE data_hora >= TIMESTAMPTZ '1995-01-01'
    ON CONFLICT (uid) DO UPDATE SET
        id_externo = EXCLUDED.id_externo, proposicao_id = EXCLUDED.proposicao_id, casa_id = EXCLUDED.casa_id,
        data_hora = EXCLUDED.data_hora, titulo_pauta = EXCLUDED.titulo_pauta, descricao = EXCLUDED.descricao,
        tipo_deliberacao = EXCLUDED.tipo_deliberacao, secreta = EXCLUDED.secreta, aprovada = EXCLUDED.aprovada,
        local_deliberacao = EXCLUDED.local_deliberacao, nome_comissao = EXCLUDED.nome_comissao,
        link_ata = EXCLUDED.link_ata, relator_nome = EXCLUDED.relator_nome, parecer_numero = EXCLUDED.parecer_numero,
        parecer_texto = EXCLUDED.parecer_texto, link_parecer = EXCLUDED.link_parecer,
        resumo_decisao = EXCLUDED.resumo_decisao, orientacao_governo = EXCLUDED.orientacao_governo,
        total_sim_fonte = EXCLUDED.total_sim_fonte, total_nao_fonte = EXCLUDED.total_nao_fonte,
        total_abstencao_fonte = EXCLUDED.total_abstencao_fonte, total_obstrucao_fonte = EXCLUDED.total_obstrucao_fonte;
    GET DIAGNOSTICS v_votacoes = ROW_COUNT;
    DELETE FROM leg.votacao l WHERE l.fonte_id = v_fonte AND NOT EXISTS (SELECT 1 FROM _vot t WHERE t.uid = l.uid);

    DELETE FROM leg.votacao_legado;
    INSERT INTO leg.votacao_legado (legado_id, tabela, votacao_id)
    SELECT t.vp_id, 'votacoes_proposicao', l.id FROM _vot t JOIN leg.votacao l ON l.uid = t.uid WHERE t.vp_id IS NOT NULL
    UNION ALL
    SELECT t.sv_id, 'sessoes_votacao', l.id FROM _vot t JOIN leg.votacao l ON l.uid = t.uid WHERE t.sv_id IS NOT NULL;

    -- ── votos: nominais têm precedência sobre os votos das sessões ──────────────────────────────
    TRUNCATE leg.voto, leg.orientacao;
    INSERT INTO leg.voto (votacao_id, pessoa_id, partido_id, opcao_codigo)
    SELECT DISTINCT ON (x.votacao_id, x.pessoa_id) x.votacao_id, x.pessoa_id, x.partido_id, x.opcao
    FROM (
        SELECT m.votacao_id, pe.id AS pessoa_id, NULL::bigint AS partido_id, vn.voto AS opcao, 1 AS prioridade
        FROM public.votos_nominais vn
        JOIN leg.votacao_legado m ON m.legado_id = vn.votacao_id AND m.tabela = 'votacoes_proposicao'
        JOIN core.pessoa pe ON pe.uid = vn.parlamentar_id
        UNION ALL
        SELECT m.votacao_id, pe.id, pa.id, vp.voto::text, 2
        FROM public.votos_parlamentares vp
        JOIN leg.votacao_legado m ON m.legado_id = vp."sessaoVotacaoId" AND m.tabela = 'sessoes_votacao'
        JOIN core.pessoa pe ON pe.uid = vp."politicoId"
        LEFT JOIN core.partido pa ON pa.uid = vp."partidoId"
    ) x
    WHERE x.opcao IN (SELECT codigo FROM ref.opcao_voto)
    ORDER BY x.votacao_id, x.pessoa_id, x.prioridade;
    GET DIAGNOSTICS v_votos = ROW_COUNT;
    -- partido do voto: quando só o voto nominal existe, usa a filiação vigente na data da votação
    -- (quem não tem nenhuma filiação registrada herda o partido do mandato)
    UPDATE leg.voto v SET partido_id = coalesce(
        (SELECT f.partido_id FROM core.filiacao f JOIN leg.votacao vo ON vo.id = v.votacao_id
          WHERE f.pessoa_id = v.pessoa_id AND f.periodo @> vo.data_hora::date LIMIT 1),
        (SELECT m.partido_id FROM core.mandato m
          WHERE m.pessoa_id = v.pessoa_id AND m.partido_id IS NOT NULL
            AND NOT EXISTS (SELECT 1 FROM core.filiacao x WHERE x.pessoa_id = v.pessoa_id)
          ORDER BY m.inicio DESC LIMIT 1))
    WHERE v.partido_id IS NULL;

    INSERT INTO leg.orientacao (votacao_id, bancada, partido_id, orientacao)
    SELECT m.votacao_id, o.partido_bancada,
           (SELECT p.id FROM core.partido p WHERE p.sigla_normalizada = ref.normalizar_texto(o.partido_bancada)
            UNION SELECT a.partido_id FROM core.partido_alias a WHERE a.sigla_normalizada = ref.normalizar_texto(o.partido_bancada)
            LIMIT 1),
           o.orientacao
    FROM public.orientacoes_partidarias o
    JOIN leg.votacao_legado m ON m.legado_id = o.votacao_id AND m.tabela = 'votacoes_proposicao'
    WHERE o.orientacao IN ('SIM','NAO','ABSTENCAO','OBSTRUCAO','LIBERADO')
    ON CONFLICT (votacao_id, bancada) DO NOTHING;
    GET DIAGNOSTICS v_orient = ROW_COUNT;

    -- ── presença ────────────────────────────────────────────────────────────────────────────────
    TRUNCATE leg.presenca;
    INSERT INTO etl.rejeito (execucao_id, recurso, chave_natural, motivo, payload)
    SELECT v_execucao, 'presenca', r.id::text, 'FORA_DA_JANELA_1995', jsonb_build_object('dataSessao', r."dataSessao")
    FROM public.registros_presenca r WHERE r."dataSessao" < DATE '1995-01-01';
    INSERT INTO leg.presenca (pessoa_id, casa_id, data_sessao, tipo_codigo, mandato_id, justificativa)
    SELECT DISTINCT ON (pe.id, c.id, r."dataSessao") pe.id, c.id, r."dataSessao", r."tipoPresenca"::text, ml.mandato_id, r.justificativa
    FROM public.registros_presenca r
    JOIN core.pessoa pe ON pe.uid = r."politicoId"
    JOIN ref.casa_legislativa c ON c.codigo = r."casaLegislativa"::text
    LEFT JOIN core.mandato_legado ml ON ml.legado_id = r."mandatoId" AND ml.tabela = 'mandatos'
    WHERE r."dataSessao" >= DATE '1995-01-01'
    ORDER BY pe.id, c.id, r."dataSessao", r.id;
    GET DIAGNOSTICS v_pres = ROW_COUNT;

    SELECT count(*) INTO v_rej FROM etl.rejeito WHERE execucao_id = v_execucao;
    UPDATE etl.execucao SET finalizado_em = now(), status = CASE WHEN v_rej > 0 THEN 'COM_ALERTA' ELSE 'OK' END,
        linhas_lidas = (SELECT count(*) FROM public.proposicoes) + (SELECT count(*) FROM public.votos_nominais)
                       + (SELECT count(*) FROM public.votos_parlamentares) + (SELECT count(*) FROM public.registros_presenca),
        linhas_gravadas = v_props + v_autorias + v_votacoes + v_votos + v_orient + v_pres, linhas_rejeitadas = v_rej
    WHERE id = v_execucao;
    RETURN jsonb_build_object('execucao_id', v_execucao, 'proposicoes', v_props, 'autorias', v_autorias,
                              'votacoes', v_votacoes, 'votos', v_votos, 'orientacoes', v_orient, 'presencas', v_pres,
                              'rejeitos', v_rej);
END
$fn$;
"""


def upgrade() -> None:
    op.execute(FUNCAO)
    op.execute("SELECT etl.sincronizar_legado_leg()")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS etl.sincronizar_legado_leg()")
    op.execute(
        "TRUNCATE leg.presenca, leg.orientacao, leg.voto, leg.votacao_legado, leg.votacao, leg.autoria, "
        "leg.proposicao CASCADE"
    )
