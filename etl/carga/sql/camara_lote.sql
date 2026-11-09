-- Proposições e autores dos CSV anuais da Câmara. Entradas: _in_camara_proposicao, _in_camara_autor. Saída: _rej.
-- ── proposições em escopo (iniciativas legislativas com peso na metodologia) ─────────────────
    INSERT INTO _rej SELECT 'TIPO_FORA_DO_ESCOPO', count(*) FROM _in_camara_proposicao
     WHERE "siglaTipo" NOT IN (SELECT codigo FROM ref.tipo_proposicao) HAVING count(*) > 0;
    INSERT INTO _rej SELECT 'ID_REPETIDO_NOS_ARQUIVOS', count(*) - count(DISTINCT "id") FROM _in_camara_proposicao
     WHERE "siglaTipo" IN (SELECT codigo FROM ref.tipo_proposicao) HAVING count(*) - count(DISTINCT "id") > 0;
    CREATE TEMP TABLE _p ON COMMIT DROP AS
    SELECT DISTINCT ON (s."id") s."id"::int AS id_camara, s."siglaTipo" AS tipo,
           nullif(s."numero", '')::int AS numero, nullif(s."ano", '')::int AS ano,
           nullif(btrim(s."ementa"), '') AS ementa,
           nullif(s."dataApresentacao", '')::timestamp::date AS data_apresentacao,
           nullif(s."urlInteiroTeor", '') AS url_texto,
           coalesce(s."ultimoStatus_descricaoSituacao", '') AS situacao,
           nullif(s."ultimoStatus_dataHora", '')::timestamp AT TIME ZONE 'America/Sao_Paulo' AS data_ultimo_status
    FROM _in_camara_proposicao s
    WHERE s."siglaTipo" IN (SELECT codigo FROM ref.tipo_proposicao)
    ORDER BY s."id";

    CREATE TEMP TABLE _pr ON COMMIT DROP AS
    SELECT p.*, (SELECT m.status_codigo FROM ref.situacao_camara m
                  WHERE m.descricao = p.situacao AND (m.tipo_codigo = p.tipo OR m.tipo_codigo IS NULL)
                  ORDER BY m.tipo_codigo IS NULL LIMIT 1) AS status_codigo
    FROM _p p;

    -- cada rejeição de negócio fica rastreável pelo id da Câmara (o fora-de-escopo, por ser milhões, só entra na contagem)
    INSERT INTO etl.rejeito (execucao_id, recurso, chave_natural, motivo, payload)
    SELECT (SELECT execucao_id FROM _ctx), 'camara_proposicao', id_camara::text,
           CASE WHEN status_codigo IS NULL THEN 'SITUACAO_SEM_MAPEAMENTO'
                WHEN numero IS NULL OR ano IS NULL OR data_apresentacao IS NULL THEN 'DADO_OBRIGATORIO_AUSENTE'
                ELSE 'FORA_DA_JANELA_1995' END,
           jsonb_build_object('tipo', tipo, 'ano', ano, 'situacao', situacao)
    FROM _pr WHERE status_codigo IS NULL OR numero IS NULL OR ano IS NULL OR data_apresentacao IS NULL
       OR ano < 1995 OR data_apresentacao < DATE '1995-01-01';
    INSERT INTO _rej
    SELECT CASE WHEN status_codigo IS NULL THEN 'SITUACAO_SEM_MAPEAMENTO'
                WHEN numero IS NULL OR ano IS NULL OR data_apresentacao IS NULL THEN 'DADO_OBRIGATORIO_AUSENTE'
                ELSE 'FORA_DA_JANELA_1995' END, count(*)
    FROM _pr WHERE status_codigo IS NULL OR numero IS NULL OR ano IS NULL OR data_apresentacao IS NULL
       OR ano < 1995 OR data_apresentacao < DATE '1995-01-01' GROUP BY 1;

    INSERT INTO leg.proposicao (id_camara, tipo_codigo, numero, ano, titulo, ementa, data_apresentacao,
                                data_sancao_promulgacao, status_codigo, url_texto_original, situacao_fonte,
                                data_ultimo_status, fonte_id)
    SELECT id_camara, tipo, numero, ano, tipo || ' ' || numero || '/' || ano, ementa, data_apresentacao,
           CASE WHEN status_codigo IN ('APROVADA_E_SANCIONADA', 'APROVADA_E_PROMULGADA') THEN data_ultimo_status::date END,
           status_codigo, url_texto, situacao, data_ultimo_status, (SELECT id FROM etl.fonte WHERE codigo = 'CAMARA_CSV')
    FROM _pr
    WHERE status_codigo IS NOT NULL AND numero IS NOT NULL AND ano >= 1995 AND data_apresentacao >= DATE '1995-01-01'
    ON CONFLICT (id_camara) DO UPDATE SET
        tipo_codigo = EXCLUDED.tipo_codigo, numero = EXCLUDED.numero, ano = EXCLUDED.ano,
        ementa = EXCLUDED.ementa, data_apresentacao = EXCLUDED.data_apresentacao,
        data_sancao_promulgacao = EXCLUDED.data_sancao_promulgacao, status_codigo = EXCLUDED.status_codigo,
        url_texto_original = EXCLUDED.url_texto_original, situacao_fonte = EXCLUDED.situacao_fonte,
        data_ultimo_status = EXCLUDED.data_ultimo_status, fonte_id = (SELECT id FROM etl.fonte WHERE codigo = 'CAMARA_CSV');

    -- ── autores ─────────────────────────────────────────────────────────────────────────────────
    CREATE TEMP TABLE _aut ON COMMIT DROP AS
    SELECT lp.id AS proposicao_id, nullif(a."idDeputadoAutor", '')::int AS id_deputado, a."tipoAutor" AS tipo_autor,
           t.categoria, btrim(a."nomeAutor") AS nome,
           nullif(btrim(regexp_replace(a."siglaPartidoAutor", '\*+$', '')), '') AS sigla,
           nullif(btrim(a."siglaUFAutor"), '') AS uf,
           coalesce(nullif(a."ordemAssinatura", '')::int, 1) AS ordem, (a."proponente" = '1') AS proponente
    FROM _in_camara_autor a
    JOIN leg.proposicao lp ON lp.id_camara = a."idProposicao"::int AND lp.fonte_id = (SELECT id FROM etl.fonte WHERE codigo = 'CAMARA_CSV')
    LEFT JOIN ref.tipo_autor_camara t ON t.descricao = a."tipoAutor";

    INSERT INTO etl.rejeito (execucao_id, recurso, chave_natural, motivo, payload)
    SELECT DISTINCT (SELECT execucao_id FROM _ctx), 'camara_autor', tipo_autor, 'TIPO_AUTOR_SEM_MAPEAMENTO', jsonb_build_object('tipo_autor', tipo_autor)
    FROM _aut WHERE categoria IS NULL;
    INSERT INTO _rej SELECT 'TIPO_AUTOR_SEM_MAPEAMENTO', count(*) FROM _aut WHERE categoria IS NULL HAVING count(*) > 0;

    -- siglas sem cadastro oficial viram partidos fora do catálogo (histórico: PPB, PRONA, PTdoB...)
    INSERT INTO core.partido (sigla, nome, catalogo)
    SELECT DISTINCT a.sigla, a.sigla, false FROM _aut a
    WHERE a.sigla IS NOT NULL AND a.categoria IN ('PESSOA_DEPUTADO', 'PESSOA_SENADOR')
      AND NOT EXISTS (SELECT 1 FROM core.partido p WHERE p.sigla_normalizada = ref.normalizar_texto(a.sigla))
      AND NOT EXISTS (SELECT 1 FROM core.partido_alias al WHERE al.sigla_normalizada = ref.normalizar_texto(a.sigla))
    ON CONFLICT DO NOTHING;

    -- deputados ainda desconhecidos: identidade pela fonte (id da Câmara), nunca por nome
    INSERT INTO core.pessoa (uid, nome_exibicao)
    SELECT DISTINCT ON (a.id_deputado) md5('camara:' || a.id_deputado)::uuid, a.nome
    FROM _aut a
    WHERE a.id_deputado IS NOT NULL AND a.nome <> ''
      AND NOT EXISTS (SELECT 1 FROM core.pessoa_identificador i
                       WHERE i.fonte_id = (SELECT id FROM etl.fonte WHERE codigo = 'CAMARA_API') AND i.tipo = 'CAMARA_ID' AND i.valor = a.id_deputado::text)
    ORDER BY a.id_deputado, a.ordem
    ON CONFLICT (uid) DO NOTHING;
    INSERT INTO core.pessoa_identificador (pessoa_id, fonte_id, tipo, valor)
    SELECT pe.id, (SELECT id FROM etl.fonte WHERE codigo = 'CAMARA_API'), 'CAMARA_ID', x.id_deputado::text
    FROM (SELECT DISTINCT id_deputado FROM _aut WHERE id_deputado IS NOT NULL) x
    JOIN core.pessoa pe ON pe.uid = md5('camara:' || x.id_deputado)::uuid
    ON CONFLICT DO NOTHING;
    INSERT INTO core.pessoa_nome (pessoa_id, tipo, nome, fonte_id)
    SELECT DISTINCT ON (pe.id) pe.id, 'PARLAMENTAR', a.nome, (SELECT id FROM etl.fonte WHERE codigo = 'CAMARA_CSV')
    FROM _aut a JOIN core.pessoa pe ON pe.uid = md5('camara:' || a.id_deputado)::uuid
    WHERE a.id_deputado IS NOT NULL AND a.nome <> ''
    ON CONFLICT DO NOTHING;

    -- autores que não são pessoas (Executivo, comissões, Mesa, lideranças...) passam a ser entidades
    INSERT INTO core.entidade (categoria, nome)
    SELECT DISTINCT categoria, nome FROM _aut
    WHERE categoria NOT IN ('PESSOA_DEPUTADO', 'PESSOA_SENADOR') AND nome <> ''
    ON CONFLICT DO NOTHING;

    -- a autoria das proposições carregadas é refeita a cada carga (apaga e regrava as da proposição)
    DELETE FROM leg.autoria WHERE proposicao_id IN (SELECT DISTINCT proposicao_id FROM _aut);
    INSERT INTO leg.autoria (proposicao_id, pessoa_id, entidade_id, partido_id, uf, nome_autor, tipo_codigo, ordem,
                             proponente, tipo_autor_fonte, fonte_id)
    SELECT DISTINCT ON (a.proposicao_id, a.ordem, a.nome)
           a.proposicao_id,
           CASE WHEN a.categoria = 'PESSOA_DEPUTADO' THEN
                (SELECT i.pessoa_id FROM core.pessoa_identificador i
                  WHERE i.fonte_id = (SELECT id FROM etl.fonte WHERE codigo = 'CAMARA_API') AND i.tipo = 'CAMARA_ID' AND i.valor = a.id_deputado::text) END,
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
           a.ordem, a.proponente, a.tipo_autor, (SELECT id FROM etl.fonte WHERE codigo = 'CAMARA_CSV')
    FROM _aut a WHERE a.categoria IS NOT NULL
    ORDER BY a.proposicao_id, a.ordem, a.nome;

    UPDATE leg.proposicao p SET autor_nome = x.nome_autor, autor_pessoa_id = coalesce(x.pessoa_id, p.autor_pessoa_id)
    FROM (SELECT DISTINCT ON (a.proposicao_id) a.proposicao_id, a.nome_autor, a.pessoa_id
          FROM leg.autoria a WHERE a.proposicao_id IN (SELECT DISTINCT proposicao_id FROM _aut)
            AND a.tipo_codigo IN ('AUTOR_PRINCIPAL', 'INSTITUCIONAL') ORDER BY a.proposicao_id, a.ordem) x
    WHERE x.proposicao_id = p.id AND p.fonte_id = (SELECT id FROM etl.fonte WHERE codigo = 'CAMARA_CSV');
