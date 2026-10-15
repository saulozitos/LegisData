"""Ponte legado -> leg convive com o ETL em lote da Câmara; função de merge dos CSV anuais.

- etl.sincronizar_legado_leg() (redefinida): proposições que o ETL em lote já assumiu adotam o uid legado e deixam de
  ter status/datas sobrescritos; a autoria do legado só continua para o que o lote não cobre e para relatores.
- etl.merge_camara_bulk(): lê stg.camara_proposicao/stg.camara_autor e grava proposição, autoria (pessoa, entidade ou
  partido), pessoas e partidos novos. Situação ou tipo de autor sem mapa viram etl.rejeito.
- Variações de sigla observadas na fonte viram aliases (REPUBLIC, SOLIDARI, S.PART...).

Revision ID: 0010
Revises: 0009
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

ALIASES = {
    "REPUBLIC": "REPUBLICANOS", "SOLIDARI": "SOLIDARIEDADE", "SOLIDARIED": "SOLIDARIEDADE",
    "S.PART": "S.PART.", "S. PART.": "S.PART.",
}

PONTE_LEG = r"""
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

    -- Proposições já carregadas pelo ETL em lote (mesmo id_camara) adotam o uid legado: o contrato público não muda
    UPDATE leg.proposicao l SET uid = p.id
    FROM public.proposicoes p
    WHERE l.id_camara = p."idExternoCamara" AND l.uid <> p.id AND p.ano >= 1995
      AND p."dataApresentacao" >= DATE '1995-01-01' AND NOT EXISTS (SELECT 1 FROM leg.proposicao y WHERE y.uid = p.id);

    -- Campos de enriquecimento (área, eixos, iniciativa, autor resolvido) vêm sempre do legado; os campos que o ETL em
    -- lote assume (tipo, status, datas, ementa) só são atualizados enquanto a proposição ainda pertence ao legado.
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
      AND NOT EXISTS (SELECT 1 FROM leg.proposicao x WHERE x.id_camara = p."idExternoCamara" AND x.uid <> p.id)
    ON CONFLICT (uid) DO UPDATE SET
        id_senado = EXCLUDED.id_senado,
        explicacao_ementa = EXCLUDED.explicacao_ementa, area_tematica = EXCLUDED.area_tematica,
        url_oficial = EXCLUDED.url_oficial, reforma_estrutural = EXCLUDED.reforma_estrutural,
        iniciativa_executivo = EXCLUDED.iniciativa_executivo,
        autor_pessoa_id = coalesce(EXCLUDED.autor_pessoa_id, leg.proposicao.autor_pessoa_id),
        autor_nome = coalesce(leg.proposicao.autor_nome, EXCLUDED.autor_nome),
        eixo_impacto = EXCLUDED.eixo_impacto, eixos_impacto = EXCLUDED.eixos_impacto,
        id_camara = CASE WHEN leg.proposicao.fonte_id = v_fonte THEN EXCLUDED.id_camara ELSE leg.proposicao.id_camara END,
        tipo_codigo = CASE WHEN leg.proposicao.fonte_id = v_fonte THEN EXCLUDED.tipo_codigo ELSE leg.proposicao.tipo_codigo END,
        numero = CASE WHEN leg.proposicao.fonte_id = v_fonte THEN EXCLUDED.numero ELSE leg.proposicao.numero END,
        ano = CASE WHEN leg.proposicao.fonte_id = v_fonte THEN EXCLUDED.ano ELSE leg.proposicao.ano END,
        titulo = CASE WHEN leg.proposicao.fonte_id = v_fonte THEN EXCLUDED.titulo ELSE leg.proposicao.titulo END,
        ementa = CASE WHEN leg.proposicao.fonte_id = v_fonte THEN EXCLUDED.ementa ELSE leg.proposicao.ementa END,
        data_apresentacao = CASE WHEN leg.proposicao.fonte_id = v_fonte THEN EXCLUDED.data_apresentacao ELSE leg.proposicao.data_apresentacao END,
        data_sancao_promulgacao = CASE WHEN leg.proposicao.fonte_id = v_fonte THEN EXCLUDED.data_sancao_promulgacao ELSE leg.proposicao.data_sancao_promulgacao END,
        status_codigo = CASE WHEN leg.proposicao.fonte_id = v_fonte THEN EXCLUDED.status_codigo ELSE leg.proposicao.status_codigo END,
        url_texto_original = CASE WHEN leg.proposicao.fonte_id = v_fonte THEN EXCLUDED.url_texto_original ELSE leg.proposicao.url_texto_original END;
    GET DIAGNOSTICS v_props = ROW_COUNT;
    DELETE FROM leg.proposicao l WHERE l.fonte_id = v_fonte AND NOT EXISTS (SELECT 1 FROM public.proposicoes p WHERE p.id = l.uid);

    -- ── autoria ─────────────────────────────────────────────────────────────────────────────────
    -- Autoria de proposições assumidas pelo ETL em lote vem de lá; do legado só ficam os relatores
    INSERT INTO leg.autoria (proposicao_id, pessoa_id, nome_autor, tipo_codigo, ordem, legado_id, fonte_id)
    SELECT lp.id, pe.id, a."nomeAutor", a."tipoAutoria"::text, a.ordem, a.id, v_fonte
    FROM public.proposicoes_autores a
    JOIN leg.proposicao lp ON lp.uid = a."proposicaoId"
    LEFT JOIN core.pessoa pe ON pe.uid = a."politicoId"
    WHERE lp.fonte_id = v_fonte OR a."tipoAutoria" = 'RELATOR'
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

MERGE_CAMARA = r"""
CREATE OR REPLACE FUNCTION etl.merge_camara_bulk() RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    v_fonte smallint := (SELECT id FROM etl.fonte WHERE codigo = 'CAMARA_CSV');
    v_camara_api smallint := (SELECT id FROM etl.fonte WHERE codigo = 'CAMARA_API');
    v_exec bigint;
    v_no_stg int; v_escopo int; v_props int; v_autorias int; v_rej int; v_fora jsonb; v_pessoas int; v_entidades int;
    v_partidos int;
BEGIN
    INSERT INTO etl.execucao (fonte_id, estagio) VALUES (v_fonte, 'MERGE') RETURNING id INTO v_exec;
    DELETE FROM etl.rejeito WHERE recurso IN ('camara_proposicao', 'camara_autor');

    SELECT count(*) INTO v_no_stg FROM stg.camara_proposicao;
    SELECT coalesce(jsonb_object_agg(tipo, n), '{}'::jsonb) INTO v_fora FROM (
        SELECT "siglaTipo" AS tipo, count(*) AS n FROM stg.camara_proposicao
        WHERE "siglaTipo" NOT IN (SELECT codigo FROM ref.tipo_proposicao) GROUP BY 1) x;

    -- ── proposições em escopo (iniciativas legislativas com peso na metodologia) ─────────────────
    CREATE TEMP TABLE _p ON COMMIT DROP AS
    SELECT DISTINCT ON (s."id") s."id"::int AS id_camara, s."siglaTipo" AS tipo,
           nullif(s."numero", '')::int AS numero, nullif(s."ano", '')::int AS ano,
           nullif(btrim(s."ementa"), '') AS ementa,
           nullif(s."dataApresentacao", '')::timestamp::date AS data_apresentacao,
           nullif(s."urlInteiroTeor", '') AS url_texto,
           coalesce(s."ultimoStatus_descricaoSituacao", '') AS situacao,
           nullif(s."ultimoStatus_dataHora", '')::timestamp AT TIME ZONE 'America/Sao_Paulo' AS data_ultimo_status
    FROM stg.camara_proposicao s
    WHERE s."siglaTipo" IN (SELECT codigo FROM ref.tipo_proposicao)
    ORDER BY s."id";
    SELECT count(*) INTO v_escopo FROM _p;

    CREATE TEMP TABLE _pr ON COMMIT DROP AS
    SELECT p.*, (SELECT m.status_codigo FROM ref.situacao_camara m
                  WHERE m.descricao = p.situacao AND (m.tipo_codigo = p.tipo OR m.tipo_codigo IS NULL)
                  ORDER BY m.tipo_codigo IS NULL LIMIT 1) AS status_codigo
    FROM _p p;

    INSERT INTO etl.rejeito (execucao_id, recurso, chave_natural, motivo, payload)
    SELECT v_exec, 'camara_proposicao', id_camara::text,
           CASE WHEN status_codigo IS NULL THEN 'SITUACAO_SEM_MAPEAMENTO'
                WHEN numero IS NULL OR ano IS NULL OR data_apresentacao IS NULL THEN 'DADO_OBRIGATORIO_AUSENTE'
                ELSE 'FORA_DA_JANELA_1995' END,
           jsonb_build_object('tipo', tipo, 'ano', ano, 'situacao', situacao)
    FROM _pr WHERE status_codigo IS NULL OR numero IS NULL OR ano IS NULL OR data_apresentacao IS NULL
       OR ano < 1995 OR data_apresentacao < DATE '1995-01-01';

    INSERT INTO leg.proposicao (id_camara, tipo_codigo, numero, ano, titulo, ementa, data_apresentacao,
                                data_sancao_promulgacao, status_codigo, url_texto_original, situacao_fonte,
                                data_ultimo_status, fonte_id)
    SELECT id_camara, tipo, numero, ano, tipo || ' ' || numero || '/' || ano, ementa, data_apresentacao,
           CASE WHEN status_codigo IN ('APROVADA_E_SANCIONADA', 'APROVADA_E_PROMULGADA') THEN data_ultimo_status::date END,
           status_codigo, url_texto, situacao, data_ultimo_status, v_fonte
    FROM _pr
    WHERE status_codigo IS NOT NULL AND numero IS NOT NULL AND ano >= 1995 AND data_apresentacao >= DATE '1995-01-01'
    ON CONFLICT (id_camara) DO UPDATE SET
        tipo_codigo = EXCLUDED.tipo_codigo, numero = EXCLUDED.numero, ano = EXCLUDED.ano,
        ementa = EXCLUDED.ementa, data_apresentacao = EXCLUDED.data_apresentacao,
        data_sancao_promulgacao = EXCLUDED.data_sancao_promulgacao, status_codigo = EXCLUDED.status_codigo,
        url_texto_original = EXCLUDED.url_texto_original, situacao_fonte = EXCLUDED.situacao_fonte,
        data_ultimo_status = EXCLUDED.data_ultimo_status, fonte_id = v_fonte;
    GET DIAGNOSTICS v_props = ROW_COUNT;

    -- ── autores ─────────────────────────────────────────────────────────────────────────────────
    CREATE TEMP TABLE _aut ON COMMIT DROP AS
    SELECT lp.id AS proposicao_id, nullif(a."idDeputadoAutor", '')::int AS id_deputado, a."tipoAutor" AS tipo_autor,
           t.categoria, btrim(a."nomeAutor") AS nome,
           nullif(btrim(regexp_replace(a."siglaPartidoAutor", '\*+$', '')), '') AS sigla,
           nullif(btrim(a."siglaUFAutor"), '') AS uf,
           coalesce(nullif(a."ordemAssinatura", '')::int, 1) AS ordem, (a."proponente" = '1') AS proponente
    FROM stg.camara_autor a
    JOIN leg.proposicao lp ON lp.id_camara = a."idProposicao"::int AND lp.fonte_id = v_fonte
    LEFT JOIN ref.tipo_autor_camara t ON t.descricao = a."tipoAutor";

    INSERT INTO etl.rejeito (execucao_id, recurso, chave_natural, motivo, payload)
    SELECT DISTINCT v_exec, 'camara_autor', tipo_autor, 'TIPO_AUTOR_SEM_MAPEAMENTO', jsonb_build_object('tipo_autor', tipo_autor)
    FROM _aut WHERE categoria IS NULL;

    -- siglas sem cadastro oficial viram partidos fora do catálogo (histórico: PPB, PRONA, PTdoB...)
    INSERT INTO core.partido (sigla, nome, catalogo)
    SELECT DISTINCT a.sigla, a.sigla, false FROM _aut a
    WHERE a.sigla IS NOT NULL AND a.categoria IN ('PESSOA_DEPUTADO', 'PESSOA_SENADOR')
      AND NOT EXISTS (SELECT 1 FROM core.partido p WHERE p.sigla_normalizada = ref.normalizar_texto(a.sigla))
      AND NOT EXISTS (SELECT 1 FROM core.partido_alias al WHERE al.sigla_normalizada = ref.normalizar_texto(a.sigla))
    ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS v_partidos = ROW_COUNT;

    -- deputados ainda desconhecidos: identidade pela fonte (id da Câmara), nunca por nome
    INSERT INTO core.pessoa (uid, nome_exibicao)
    SELECT DISTINCT ON (a.id_deputado) md5('camara:' || a.id_deputado)::uuid, a.nome
    FROM _aut a
    WHERE a.id_deputado IS NOT NULL AND a.nome <> ''
      AND NOT EXISTS (SELECT 1 FROM core.pessoa_identificador i
                       WHERE i.fonte_id = v_camara_api AND i.tipo = 'CAMARA_ID' AND i.valor = a.id_deputado::text)
    ORDER BY a.id_deputado, a.ordem
    ON CONFLICT (uid) DO NOTHING;
    GET DIAGNOSTICS v_pessoas = ROW_COUNT;
    INSERT INTO core.pessoa_identificador (pessoa_id, fonte_id, tipo, valor)
    SELECT pe.id, v_camara_api, 'CAMARA_ID', x.id_deputado::text
    FROM (SELECT DISTINCT id_deputado FROM _aut WHERE id_deputado IS NOT NULL) x
    JOIN core.pessoa pe ON pe.uid = md5('camara:' || x.id_deputado)::uuid
    ON CONFLICT DO NOTHING;
    INSERT INTO core.pessoa_nome (pessoa_id, tipo, nome, fonte_id)
    SELECT DISTINCT ON (pe.id) pe.id, 'PARLAMENTAR', a.nome, v_fonte
    FROM _aut a JOIN core.pessoa pe ON pe.uid = md5('camara:' || a.id_deputado)::uuid
    WHERE a.id_deputado IS NOT NULL AND a.nome <> ''
    ON CONFLICT DO NOTHING;

    -- autores que não são pessoas (Executivo, comissões, Mesa, lideranças...) passam a ser entidades
    INSERT INTO core.entidade (categoria, nome)
    SELECT DISTINCT categoria, nome FROM _aut
    WHERE categoria NOT IN ('PESSOA_DEPUTADO', 'PESSOA_SENADOR') AND nome <> ''
    ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS v_entidades = ROW_COUNT;

    -- a autoria das proposições carregadas é refeita (relatores vindos do legado são preservados)
    DELETE FROM leg.autoria WHERE proposicao_id IN (SELECT DISTINCT proposicao_id FROM _aut)
        AND (legado_id IS NULL OR tipo_codigo <> 'RELATOR');
    INSERT INTO leg.autoria (proposicao_id, pessoa_id, entidade_id, partido_id, uf, nome_autor, tipo_codigo, ordem,
                             proponente, tipo_autor_fonte, fonte_id)
    SELECT DISTINCT ON (a.proposicao_id, a.ordem, a.nome)
           a.proposicao_id,
           CASE WHEN a.categoria = 'PESSOA_DEPUTADO' THEN
                (SELECT i.pessoa_id FROM core.pessoa_identificador i
                  WHERE i.fonte_id = v_camara_api AND i.tipo = 'CAMARA_ID' AND i.valor = a.id_deputado::text) END,
           CASE WHEN a.categoria NOT IN ('PESSOA_DEPUTADO', 'PESSOA_SENADOR') THEN
                (SELECT e.id FROM core.entidade e
                  WHERE e.categoria = a.categoria AND e.nome_normalizado = ref.normalizar_texto(a.nome)) END,
           CASE WHEN a.categoria IN ('PESSOA_DEPUTADO', 'PESSOA_SENADOR') AND a.sigla IS NOT NULL THEN
                (SELECT x.id FROM (
                    SELECT p.id FROM core.partido p WHERE p.sigla_normalizada = ref.normalizar_texto(a.sigla)
                    UNION ALL
                    SELECT al.partido_id FROM core.partido_alias al WHERE al.sigla_normalizada = ref.normalizar_texto(a.sigla)
                 ) x LIMIT 1) END,
           (SELECT u.sigla FROM ref.uf u WHERE u.sigla = upper(a.uf)),
           coalesce(nullif(a.nome, ''), a.tipo_autor),
           CASE WHEN a.categoria IN ('PESSOA_DEPUTADO', 'PESSOA_SENADOR')
                THEN CASE WHEN a.ordem = 1 THEN 'AUTOR_PRINCIPAL' ELSE 'COAUTOR' END ELSE 'INSTITUCIONAL' END,
           a.ordem, a.proponente, a.tipo_autor, v_fonte
    FROM _aut a WHERE a.categoria IS NOT NULL
    ORDER BY a.proposicao_id, a.ordem, a.nome;
    GET DIAGNOSTICS v_autorias = ROW_COUNT;

    UPDATE leg.proposicao p SET autor_nome = x.nome_autor, autor_pessoa_id = coalesce(x.pessoa_id, p.autor_pessoa_id)
    FROM (SELECT DISTINCT ON (a.proposicao_id) a.proposicao_id, a.nome_autor, a.pessoa_id
          FROM leg.autoria a WHERE a.proposicao_id IN (SELECT DISTINCT proposicao_id FROM _aut)
            AND a.tipo_codigo IN ('AUTOR_PRINCIPAL', 'INSTITUCIONAL') ORDER BY a.proposicao_id, a.ordem) x
    WHERE x.proposicao_id = p.id AND p.fonte_id = v_fonte;

    SELECT count(*) INTO v_rej FROM etl.rejeito WHERE execucao_id = v_exec;
    INSERT INTO etl.verificacao (execucao_id, nome, passou, detalhe)
    VALUES (v_exec, 'camara_bulk_cobertura', v_rej = 0,
            jsonb_build_object('proposicoes_no_staging', v_no_stg, 'proposicoes_em_escopo', v_escopo,
                               'proposicoes_gravadas', v_props, 'autorias_gravadas', v_autorias,
                               'pessoas_criadas', v_pessoas, 'entidades_criadas', v_entidades,
                               'partidos_criados', v_partidos, 'rejeitos', v_rej, 'fora_de_escopo_por_tipo', v_fora));
    UPDATE etl.execucao SET finalizado_em = now(), status = CASE WHEN v_rej > 0 THEN 'COM_ALERTA' ELSE 'OK' END,
        linhas_lidas = v_no_stg, linhas_gravadas = v_props + v_autorias, linhas_rejeitadas = v_rej WHERE id = v_exec;
    RETURN jsonb_build_object('execucao_id', v_exec, 'proposicoes_em_escopo', v_escopo, 'proposicoes', v_props,
                              'autorias', v_autorias, 'pessoas_criadas', v_pessoas, 'entidades_criadas', v_entidades,
                              'partidos_criados', v_partidos, 'rejeitos', v_rej);
END
$fn$;
"""


def upgrade() -> None:
    bind = op.get_bind()
    for alias, destino in ALIASES.items():
        bind.exec_driver_sql(
            "INSERT INTO ref.partido_alias_semente VALUES (ref.normalizar_texto(%s), %s, ref.normalizar_texto(%s)) "
            "ON CONFLICT DO NOTHING",
            (alias, alias, destino),
        )
    op.execute(PONTE_LEG)
    op.execute(MERGE_CAMARA)


def downgrade() -> None:
    raise NotImplementedError("Migração de cobertura (0010) não é reversível.")
