-- Histórico de mandatos dos deputados (eventos da API da Câmara): mandato, situações e partido por período.
-- Entradas: _in_historico, _in_legislatura. A pessoa vem do id da Câmara; sem ele não há mandato.
-- ── eventos relevantes, em ordem ────────────────────────────────────────────────────────────
    CREATE TEMP TABLE _ev ON COMMIT DROP AS
    SELECT DISTINCT h."id"::int AS id, h."idLegislatura"::int AS leg, h."dataHora"::timestamp AS ts,
           h."dataHora"::timestamp::date AS d, nullif(h."situacao", '') AS situacao,
           nullif(h."condicaoEleitoral", '') AS cond,
           nullif(btrim(regexp_replace(h."siglaPartido", '\*+$', '')), '') AS sigla_partido,
           nullif(btrim(h."siglaUf"), '') AS uf, h."nomeEleitoral" AS nome, nullif(h."urlFoto", '') AS foto,
           h."descricaoStatus" AS descr,
           CASE WHEN h."descricaoStatus" LIKE 'Entrada -%' THEN 'ENTRADA'
                WHEN h."descricaoStatus" LIKE 'Saída -%' THEN 'SAIDA'
                WHEN h."descricaoStatus" LIKE 'Alteração de partido%' THEN 'PARTIDO' END AS tipo
    FROM _in_historico h
    WHERE h."idLegislatura"::int IN (SELECT "id"::int FROM _in_legislatura);
    DELETE FROM _ev WHERE tipo IS NULL;
    ALTER TABLE _ev ADD COLUMN ord int;
    UPDATE _ev SET ord = CASE tipo WHEN 'SAIDA' THEN 1 WHEN 'ENTRADA' THEN 2 ELSE 3 END;

    CREATE TEMP TABLE _leg ON COMMIT DROP AS
    SELECT "id"::int AS id, "dataInicio"::date AS inicio, "dataFim"::date AS fim FROM _in_legislatura;

    -- ── intervalos de exercício: cada entrada vale até a próxima saída (ou o fim da legislatura) ──
    CREATE TEMP TABLE _seq ON COMMIT DROP AS
    SELECT e.*, lag(tipo) OVER w AS tipo_anterior, lead(tipo) OVER w AS tipo_seguinte
    FROM _ev e WHERE tipo IN ('ENTRADA', 'SAIDA')
    WINDOW w AS (PARTITION BY id, leg ORDER BY ts, ord);
    DELETE FROM _seq WHERE (tipo = 'ENTRADA' AND tipo_anterior = 'ENTRADA') OR (tipo = 'SAIDA' AND coalesce(tipo_anterior, 'SAIDA') = 'SAIDA');

    CREATE TEMP TABLE _int ON COMMIT DROP AS
    SELECT x.id, x.leg, x.d AS inicio,
           coalesce(CASE WHEN x.prox_tipo = 'SAIDA' THEN CASE WHEN x.prox_ts::time >= TIME '23:00' THEN x.prox_d + 1 ELSE x.prox_d END END,
                    l.fim + 1) AS fim_exclusivo,
           x.cond, x.uf, x.nome, x.foto, x.sigla_partido, x.prox_descr
    FROM (SELECT s.*, lead(s.tipo) OVER w AS prox_tipo, lead(s.d) OVER w AS prox_d, lead(s.ts) OVER w AS prox_ts,
                 lead(s.descr) OVER w AS prox_descr
          FROM _seq s WINDOW w AS (PARTITION BY s.id, s.leg ORDER BY s.ts, s.ord)) x
    JOIN _leg l ON l.id = x.leg
    WHERE x.tipo = 'ENTRADA';
    DELETE FROM _int WHERE fim_exclusivo <= inicio;

    -- ── partido do deputado ao longo da legislatura (entrada e trocas de partido) ───────────────
    CREATE TEMP TABLE _par ON COMMIT DROP AS
    SELECT p.id, p.leg, p.sigla_partido,
           daterange(p.d, coalesce(p.prox_d, l.fim + 1), '[)') AS periodo
    FROM (SELECT e.id, e.leg, e.d, e.sigla_partido, lead(e.d) OVER (PARTITION BY e.id, e.leg ORDER BY e.ts, e.ord) AS prox_d
          FROM _ev e WHERE e.tipo IN ('ENTRADA', 'PARTIDO') AND e.sigla_partido IS NOT NULL) p
    JOIN _leg l ON l.id = p.leg
    WHERE p.prox_d IS DISTINCT FROM p.d;

    -- partidos citados que ainda não existem (siglas históricas) entram fora do catálogo
    INSERT INTO core.partido (sigla, nome, catalogo)
    SELECT DISTINCT s.sigla_partido, s.sigla_partido, false FROM _par s
    WHERE NOT EXISTS (SELECT 1 FROM core.partido p WHERE p.sigla_normalizada = ref.normalizar_texto(s.sigla_partido))
      AND NOT EXISTS (SELECT 1 FROM core.partido_alias al WHERE al.sigla_normalizada = ref.normalizar_texto(s.sigla_partido))
    ON CONFLICT DO NOTHING;

    -- ── pessoas: identidade pelo id da fonte, nunca pelo nome ───────────────────────────────────
    INSERT INTO core.midia (tipo, url_origem, fonte_id)
    SELECT DISTINCT 'FOTO_PESSOA', foto, (SELECT id FROM etl.fonte WHERE codigo = 'CAMARA_API') FROM _int WHERE foto IS NOT NULL
    ON CONFLICT (tipo, url_origem) DO NOTHING;
    INSERT INTO core.pessoa (uid, nome_exibicao, foto_midia_id)
    SELECT DISTINCT ON (i.id) md5('camara:' || i.id)::uuid, i.nome,
           (SELECT m.id FROM core.midia m WHERE m.tipo = 'FOTO_PESSOA' AND m.url_origem = i.foto)
    FROM _int i
    WHERE NOT EXISTS (SELECT 1 FROM core.pessoa_identificador x
                       WHERE x.fonte_id = (SELECT id FROM etl.fonte WHERE codigo = 'CAMARA_API') AND x.tipo = 'CAMARA_ID' AND x.valor = i.id::text)
    ORDER BY i.id, i.inicio DESC
    ON CONFLICT (uid) DO NOTHING;
    INSERT INTO core.pessoa_identificador (pessoa_id, fonte_id, tipo, valor)
    SELECT pe.id, (SELECT id FROM etl.fonte WHERE codigo = 'CAMARA_API'), 'CAMARA_ID', x.id::text FROM (SELECT DISTINCT id FROM _int) x
    JOIN core.pessoa pe ON pe.uid = md5('camara:' || x.id)::uuid
    ON CONFLICT DO NOTHING;
    INSERT INTO core.pessoa_nome (pessoa_id, tipo, nome, fonte_id)
    SELECT DISTINCT ON (ident.pessoa_id, ref.normalizar_texto(i.nome)) ident.pessoa_id, 'PARLAMENTAR', i.nome, (SELECT id FROM etl.fonte WHERE codigo = 'CAMARA_API')
    FROM _int i
    JOIN core.pessoa_identificador ident ON ident.fonte_id = (SELECT id FROM etl.fonte WHERE codigo = 'CAMARA_API') AND ident.tipo = 'CAMARA_ID' AND ident.valor = i.id::text
    WHERE nullif(btrim(i.nome), '') IS NOT NULL
    ON CONFLICT DO NOTHING;

    -- ── mandatos (um por deputado e legislatura) ────────────────────────────────────────────────
    INSERT INTO core.eleicao (ano, tipo)
    SELECT DISTINCT extract(year FROM l.inicio)::int - 1, 'GERAL' FROM _leg l ON CONFLICT (ano, tipo) DO NOTHING;

    CREATE TEMP TABLE _man ON COMMIT DROP AS
    SELECT ident.pessoa_id, i.id, i.leg,
           (SELECT e.id FROM core.eleicao e WHERE e.tipo = 'GERAL' AND e.ano = extract(year FROM l.inicio)::int - 1) AS eleicao_id,
           CASE WHEN bool_or(coalesce(i.cond, 'Titular') <> 'Suplente') THEN 'TITULAR' ELSE 'SUPLENTE' END AS condicao,
           min(i.inicio) AS inicio,
           CASE WHEN max(i.fim_exclusivo) > l.fim THEN l.fim ELSE max(i.fim_exclusivo) - 1 END AS fim,
           (array_agg(i.uf ORDER BY i.inicio))[1] AS uf,
           (array_agg(i.sigla_partido ORDER BY i.inicio))[1] AS sigla_partido,
           (array_agg(i.prox_descr ORDER BY i.inicio DESC))[1] AS ultima_saida
    FROM _int i
    JOIN _leg l ON l.id = i.leg
    JOIN core.pessoa_identificador ident ON ident.fonte_id = (SELECT id FROM etl.fonte WHERE codigo = 'CAMARA_API') AND ident.tipo = 'CAMARA_ID' AND ident.valor = i.id::text
    GROUP BY ident.pessoa_id, i.id, i.leg, l.inicio, l.fim;

    INSERT INTO core.mandato (pessoa_id, cargo_id, circunscricao_id, eleicao_id, partido_id, condicao, numero_mandato,
                              inicio, fim, motivo_encerramento, fonte_id)
    SELECT m.pessoa_id, (SELECT id FROM ref.cargo WHERE codigo = 'DEPUTADO_FEDERAL'),
           coalesce((SELECT ci.id FROM ref.circunscricao ci WHERE ci.tipo = 'UF' AND ci.uf = upper(m.uf)),
                    (SELECT ci.id FROM ref.circunscricao ci WHERE ci.tipo = 'BR')),
           m.eleicao_id,
           (SELECT x.id FROM (
                SELECT p.id FROM core.partido p WHERE p.sigla_normalizada = ref.normalizar_texto(m.sigla_partido)
                UNION ALL
                SELECT al.partido_id FROM core.partido_alias al WHERE al.sigla_normalizada = ref.normalizar_texto(m.sigla_partido)
           ) x LIMIT 1),
           m.condicao, 1, m.inicio, m.fim,
           CASE WHEN m.ultima_saida ILIKE '%Término da Legislatura%' THEN 'CONCLUIDO'
                WHEN m.ultima_saida ILIKE '%Renúncia%' THEN 'RENUNCIA'
                WHEN m.ultima_saida ILIKE '%Cassa%' THEN 'CASSACAO'
                WHEN m.ultima_saida ILIKE '%Falecimento%' THEN 'FALECIMENTO' END,
           (SELECT id FROM etl.fonte WHERE codigo = 'CAMARA_API')
    FROM _man m
    ON CONFLICT ON CONSTRAINT uq_mandato_natural DO UPDATE SET
        circunscricao_id = EXCLUDED.circunscricao_id, partido_id = EXCLUDED.partido_id, condicao = EXCLUDED.condicao,
        inicio = EXCLUDED.inicio, fim = EXCLUDED.fim, motivo_encerramento = EXCLUDED.motivo_encerramento,
        fonte_id = EXCLUDED.fonte_id;

    ALTER TABLE _man ADD COLUMN mandato_id bigint;
    UPDATE _man m SET mandato_id = c.id FROM core.mandato c
    WHERE c.pessoa_id = m.pessoa_id AND c.eleicao_id = m.eleicao_id AND c.numero_mandato = 1 AND c.orgao_nome IS NULL
      AND c.cargo_id = (SELECT id FROM ref.cargo WHERE codigo = 'DEPUTADO_FEDERAL');

    -- ── situações: exercício/suplência e as lacunas entre eles (licenças e afastamentos) ─────────
    DELETE FROM core.mandato_situacao WHERE mandato_id IN (SELECT mandato_id FROM _man);
    INSERT INTO core.mandato_situacao (mandato_id, situacao, periodo, fonte_id)
    SELECT m.mandato_id, CASE WHEN coalesce(i.cond, 'Titular') = 'Suplente' THEN 'SUPLENCIA' ELSE 'EXERCICIO' END,
           daterange(i.inicio, i.fim_exclusivo, '[)'), (SELECT id FROM etl.fonte WHERE codigo = 'CAMARA_API')
    FROM _int i JOIN _man m ON m.id = i.id AND m.leg = i.leg;
    INSERT INTO core.mandato_situacao (mandato_id, situacao, periodo, motivo, fonte_id)
    SELECT g.mandato_id, CASE WHEN g.prox_descr ILIKE '%Ministro%' THEN 'AFASTADO_MINISTERIO' ELSE 'LICENCA' END,
           daterange(g.fim_exclusivo, g.prox_inicio, '[)'), g.prox_descr, (SELECT id FROM etl.fonte WHERE codigo = 'CAMARA_API')
    FROM (SELECT m.mandato_id, i.fim_exclusivo, i.prox_descr,
                 lead(i.inicio) OVER (PARTITION BY i.id, i.leg ORDER BY i.inicio) AS prox_inicio
          FROM _int i JOIN _man m ON m.id = i.id AND m.leg = i.leg) g
    WHERE g.prox_inicio IS NOT NULL AND g.prox_inicio > g.fim_exclusivo;

    -- ── partido que ocupa a cadeira em cada dia de exercício ────────────────────────────────────
    DELETE FROM core.mandato_partido WHERE mandato_id IN (SELECT mandato_id FROM _man);
    INSERT INTO core.mandato_partido (mandato_id, partido_id, periodo, fonte_id)
    SELECT m.mandato_id,
           (SELECT x.id FROM (
                SELECT p.id FROM core.partido p WHERE p.sigla_normalizada = ref.normalizar_texto(pp.sigla_partido)
                UNION ALL
                SELECT al.partido_id FROM core.partido_alias al WHERE al.sigla_normalizada = ref.normalizar_texto(pp.sigla_partido)
           ) x LIMIT 1),
           daterange(lower(i_p), upper(i_p), '[)'), (SELECT id FROM etl.fonte WHERE codigo = 'CAMARA_API')
    FROM _par pp
    JOIN _man m ON m.id = pp.id AND m.leg = pp.leg
    JOIN _int i ON i.id = pp.id AND i.leg = pp.leg
    CROSS JOIN LATERAL (SELECT pp.periodo * daterange(i.inicio, i.fim_exclusivo, '[)') AS i_p) z
    WHERE NOT isempty(z.i_p);
