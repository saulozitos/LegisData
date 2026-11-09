-- Pessoas e mandatos de quem as fontes oficiais listam. A pessoa se acha pelo identificador oficial (CAMARA_ID, SENADO_ID,
-- TSE_ID), pela chave curada (presidentes e ministros) ou, quando é a primeira vez que a fonte a cita, pelo NOME CIVIL
-- COMPLETO + DATA DE NASCIMENTO (os dois presentes e iguais): assim quem foi deputado e depois senador é uma pessoa só,
-- com os dois identificadores. O mesmo CPF (HMAC) em dois cadastros também é a mesma pessoa; CPF diferente nunca une.
-- Nome sem data de nascimento nunca une ninguém (vira candidata a duplicidade). Idempotente.
-- Entradas (tabelas temporárias da transação): _in_pessoa, _in_mandato, _in_ministro, _in_filiacao_senador, _in_cpf (HMAC
-- por id oficial; nunca o CPF). Saída: _rej (motivo, n).

UPDATE _in_pessoa SET id_valor = ref.normalizar_texto(id_valor) WHERE id_tipo = 'CURADORIA_ID';
UPDATE _in_mandato SET id_valor = ref.normalizar_texto(id_valor) WHERE id_tipo = 'CURADORIA_ID';
UPDATE _in_cpf SET id_valor = ref.normalizar_texto(id_valor) WHERE id_tipo = 'CURADORIA_ID';

-- ── fotos ────────────────────────────────────────────────────────────────────────────────────────────────────────
INSERT INTO core.midia (tipo, url_origem, fonte_id)
SELECT DISTINCT ON (p.foto_url) 'FOTO_PESSOA', p.foto_url, f.id
FROM _in_pessoa p JOIN etl.fonte f ON f.codigo = p.fonte
WHERE nullif(btrim(p.foto_url), '') IS NOT NULL
ORDER BY p.foto_url, p.prioridade DESC
ON CONFLICT (tipo, url_origem) DO NOTHING;

-- ── pessoas ──────────────────────────────────────────────────────────────────────────────────────────────────────
CREATE TEMP TABLE _p ON COMMIT DROP AS
SELECT p.*,
       CASE WHEN p.cpf_hmac IS NOT NULL THEN 'cpf:' || p.cpf_hmac
            WHEN nullif(btrim(p.nome_civil), '') IS NOT NULL AND p.data_nascimento IS NOT NULL
            THEN ref.normalizar_texto(p.nome_civil) || '|' || p.data_nascimento::text END AS chave_pessoa,
       NULL::uuid AS uid_novo,
       (SELECT i.pessoa_id FROM core.pessoa_identificador i WHERE i.tipo = p.id_tipo AND i.valor = p.id_valor
         ORDER BY i.id LIMIT 1) AS pessoa_id
FROM (SELECT q.*, (SELECT c.cpf_hmac FROM _in_cpf c WHERE c.id_tipo = q.id_tipo AND c.id_valor = q.id_valor LIMIT 1) AS cpf_hmac,
             (SELECT c.origem FROM _in_cpf c WHERE c.id_tipo = q.id_tipo AND c.id_valor = q.id_valor LIMIT 1) AS cpf_origem
      FROM _in_pessoa q) p;

-- mesmo CPF (HMAC) já gravado em outra fonte: é a mesma pessoa, mesmo que o nome seja outro
UPDATE _p SET pessoa_id = (
    SELECT i.pessoa_id FROM core.pessoa_identificador i WHERE i.tipo = 'CPF_HMAC' AND i.valor = _p.cpf_hmac
    ORDER BY i.pessoa_id LIMIT 1)
WHERE pessoa_id IS NULL AND cpf_hmac IS NOT NULL;

-- primeira vez que a fonte cita o id: se já existe pessoa com o mesmo nome civil e a mesma data de nascimento, é ela.
-- CPF diferente prova que são pessoas diferentes: quem já tem CPF_HMAC e nenhum igual ao do registro não é candidata
UPDATE _p SET pessoa_id = (
    SELECT pe.id FROM core.pessoa pe JOIN core.pessoa_nome n ON n.pessoa_id = pe.id AND n.tipo = 'CIVIL'
    WHERE n.nome_normalizado = ref.normalizar_texto(_p.nome_civil) AND pe.data_nascimento = _p.data_nascimento
      AND (_p.cpf_hmac IS NULL
           OR NOT EXISTS (SELECT 1 FROM core.pessoa_identificador h WHERE h.pessoa_id = pe.id AND h.tipo = 'CPF_HMAC')
           OR EXISTS (SELECT 1 FROM core.pessoa_identificador h
                       WHERE h.pessoa_id = pe.id AND h.tipo = 'CPF_HMAC' AND h.valor = _p.cpf_hmac))
    ORDER BY pe.id LIMIT 1)
WHERE pessoa_id IS NULL AND nullif(btrim(nome_civil), '') IS NOT NULL AND data_nascimento IS NOT NULL;

-- ainda sem pessoa: um uid por chave, para o deputado e o senador da mesma pessoa nascerem juntos
CREATE TEMP TABLE _uid_chave ON COMMIT DROP AS
SELECT d.chave_pessoa, gen_random_uuid() AS uid
FROM (SELECT DISTINCT chave_pessoa FROM _p WHERE pessoa_id IS NULL AND chave_pessoa IS NOT NULL) d;
UPDATE _p SET uid_novo = k.uid FROM _uid_chave k WHERE _p.pessoa_id IS NULL AND _p.chave_pessoa = k.chave_pessoa;
UPDATE _p SET uid_novo = gen_random_uuid() WHERE pessoa_id IS NULL AND uid_novo IS NULL;

-- um valor por coluna e por pessoa: a fonte atual (prioridade 1) primeiro, a histórica só onde a atual nada diz. Vale para a
-- pessoa nova e para a que já existe, e não depende de qual dos ids dela aparece primeiro (deputado que virou senador).
CREATE TEMP TABLE _pg ON COMMIT DROP AS
SELECT p.uid_novo, p.pessoa_id,
       (array_agg(p.nome_exibicao ORDER BY p.id_tipo, p.id_valor) FILTER (WHERE p.nome_exibicao IS NOT NULL AND p.prioridade = 1))[1] AS a_nome_exibicao,
       (array_agg(p.nome_exibicao ORDER BY p.id_tipo, p.id_valor) FILTER (WHERE p.nome_exibicao IS NOT NULL AND p.prioridade <> 1))[1] AS h_nome_exibicao,
       (array_agg(p.data_nascimento ORDER BY p.id_tipo, p.id_valor) FILTER (WHERE p.data_nascimento IS NOT NULL AND p.prioridade = 1))[1] AS a_data_nascimento,
       (array_agg(p.data_nascimento ORDER BY p.id_tipo, p.id_valor) FILTER (WHERE p.data_nascimento IS NOT NULL AND p.prioridade <> 1))[1] AS h_data_nascimento,
       (array_agg(p.data_falecimento ORDER BY p.id_tipo, p.id_valor) FILTER (WHERE p.data_falecimento IS NOT NULL AND p.prioridade = 1))[1] AS a_data_falecimento,
       (array_agg(p.data_falecimento ORDER BY p.id_tipo, p.id_valor) FILTER (WHERE p.data_falecimento IS NOT NULL AND p.prioridade <> 1))[1] AS h_data_falecimento,
       (array_agg(p.sexo ORDER BY p.id_tipo, p.id_valor) FILTER (WHERE p.sexo IS NOT NULL AND p.prioridade = 1))[1] AS a_sexo,
       (array_agg(p.sexo ORDER BY p.id_tipo, p.id_valor) FILTER (WHERE p.sexo IS NOT NULL AND p.prioridade <> 1))[1] AS h_sexo,
       (array_agg(p.municipio_nascimento ORDER BY p.id_tipo, p.id_valor) FILTER (WHERE p.municipio_nascimento IS NOT NULL AND p.prioridade = 1))[1] AS a_municipio_nascimento,
       (array_agg(p.municipio_nascimento ORDER BY p.id_tipo, p.id_valor) FILTER (WHERE p.municipio_nascimento IS NOT NULL AND p.prioridade <> 1))[1] AS h_municipio_nascimento,
       (array_agg(p.uf_nascimento ORDER BY p.id_tipo, p.id_valor) FILTER (WHERE p.uf_nascimento IS NOT NULL AND p.prioridade = 1))[1] AS a_uf_nascimento,
       (array_agg(p.uf_nascimento ORDER BY p.id_tipo, p.id_valor) FILTER (WHERE p.uf_nascimento IS NOT NULL AND p.prioridade <> 1))[1] AS h_uf_nascimento,
       (array_agg(p.foto_url ORDER BY p.id_tipo, p.id_valor) FILTER (WHERE p.foto_url IS NOT NULL AND p.prioridade = 1))[1] AS a_foto_url,
       (array_agg(p.foto_url ORDER BY p.id_tipo, p.id_valor) FILTER (WHERE p.foto_url IS NOT NULL AND p.prioridade <> 1))[1] AS h_foto_url,
       (array_agg(p.biografia ORDER BY p.id_tipo, p.id_valor) FILTER (WHERE p.biografia IS NOT NULL AND p.prioridade = 1))[1] AS a_biografia,
       (array_agg(p.biografia ORDER BY p.id_tipo, p.id_valor) FILTER (WHERE p.biografia IS NOT NULL AND p.prioridade <> 1))[1] AS h_biografia,
       (array_agg(p.email ORDER BY p.id_tipo, p.id_valor) FILTER (WHERE p.email IS NOT NULL AND p.prioridade = 1))[1] AS a_email,
       (array_agg(p.email ORDER BY p.id_tipo, p.id_valor) FILTER (WHERE p.email IS NOT NULL AND p.prioridade <> 1))[1] AS h_email,
       (array_agg(p.gabinete_sala ORDER BY p.id_tipo, p.id_valor) FILTER (WHERE p.gabinete_sala IS NOT NULL AND p.prioridade = 1))[1] AS a_gabinete_sala,
       (array_agg(p.gabinete_sala ORDER BY p.id_tipo, p.id_valor) FILTER (WHERE p.gabinete_sala IS NOT NULL AND p.prioridade <> 1))[1] AS h_gabinete_sala,
       (array_agg(p.gabinete_telefone ORDER BY p.id_tipo, p.id_valor) FILTER (WHERE p.gabinete_telefone IS NOT NULL AND p.prioridade = 1))[1] AS a_gabinete_telefone,
       (array_agg(p.gabinete_telefone ORDER BY p.id_tipo, p.id_valor) FILTER (WHERE p.gabinete_telefone IS NOT NULL AND p.prioridade <> 1))[1] AS h_gabinete_telefone
FROM _p p GROUP BY p.uid_novo, p.pessoa_id;

INSERT INTO core.pessoa (uid, nome_exibicao, data_nascimento, data_falecimento, sexo, municipio_nascimento, uf_nascimento,
                         foto_midia_id, biografia, email, gabinete_sala, gabinete_telefone)
SELECT g.uid_novo, coalesce(g.a_nome_exibicao, g.h_nome_exibicao), coalesce(g.a_data_nascimento, g.h_data_nascimento),
       coalesce(g.a_data_falecimento, g.h_data_falecimento), coalesce(g.a_sexo, g.h_sexo),
       coalesce(g.a_municipio_nascimento, g.h_municipio_nascimento),
       (SELECT u.sigla FROM ref.uf u WHERE u.sigla = upper(coalesce(g.a_uf_nascimento, g.h_uf_nascimento))),
       (SELECT m.id FROM core.midia m WHERE m.tipo = 'FOTO_PESSOA' AND m.url_origem = coalesce(g.a_foto_url, g.h_foto_url)),
       coalesce(g.a_biografia, g.h_biografia), coalesce(g.a_email, g.h_email),
       coalesce(g.a_gabinete_sala, g.h_gabinete_sala), coalesce(g.a_gabinete_telefone, g.h_gabinete_telefone)
FROM _pg g WHERE g.pessoa_id IS NULL;
UPDATE _p SET pessoa_id = pe.id FROM core.pessoa pe WHERE _p.pessoa_id IS NULL AND pe.uid = _p.uid_novo;

-- quem já existe: a fonte atual vale sobre o que está gravado; a histórica só preenche o que está vazio
UPDATE core.pessoa pe SET
    nome_exibicao = coalesce(g.a_nome_exibicao, pe.nome_exibicao),
    data_nascimento = coalesce(g.a_data_nascimento, pe.data_nascimento, g.h_data_nascimento),
    data_falecimento = coalesce(g.a_data_falecimento, pe.data_falecimento, g.h_data_falecimento),
    sexo = coalesce(g.a_sexo, pe.sexo, g.h_sexo),
    municipio_nascimento = coalesce(g.a_municipio_nascimento, pe.municipio_nascimento, g.h_municipio_nascimento),
    uf_nascimento = coalesce(pe.uf_nascimento,
                             (SELECT u.sigla FROM ref.uf u WHERE u.sigla = upper(coalesce(g.a_uf_nascimento, g.h_uf_nascimento)))),
    foto_midia_id = coalesce((SELECT m.id FROM core.midia m WHERE m.tipo = 'FOTO_PESSOA' AND m.url_origem = g.a_foto_url),
                             pe.foto_midia_id,
                             (SELECT m.id FROM core.midia m WHERE m.tipo = 'FOTO_PESSOA' AND m.url_origem = g.h_foto_url)),
    biografia = coalesce(g.a_biografia, pe.biografia, g.h_biografia),
    email = coalesce(g.a_email, pe.email, g.h_email),
    gabinete_sala = coalesce(g.a_gabinete_sala, pe.gabinete_sala, g.h_gabinete_sala),
    gabinete_telefone = coalesce(g.a_gabinete_telefone, pe.gabinete_telefone, g.h_gabinete_telefone),
    atualizado_em = now()
FROM _pg g
WHERE g.uid_novo IS NULL AND pe.id = g.pessoa_id;

INSERT INTO core.pessoa_identificador (pessoa_id, fonte_id, tipo, valor)
SELECT p.pessoa_id, f.id, p.id_tipo, p.id_valor FROM _p p JOIN etl.fonte f ON f.codigo = p.fonte
ON CONFLICT (fonte_id, tipo, valor) DO NOTHING;

INSERT INTO core.pessoa_identificador (pessoa_id, fonte_id, tipo, valor)
SELECT p.pessoa_id, f.id, 'CPF_HMAC', p.cpf_hmac FROM _p p JOIN etl.fonte f ON f.codigo = p.cpf_origem
WHERE p.cpf_hmac IS NOT NULL
ON CONFLICT (fonte_id, tipo, valor) DO NOTHING;

INSERT INTO core.pessoa_nome (pessoa_id, tipo, nome, fonte_id)
SELECT DISTINCT ON (p.pessoa_id, ref.normalizar_texto(p.nome_civil)) p.pessoa_id, 'CIVIL', p.nome_civil, f.id
FROM _p p JOIN etl.fonte f ON f.codigo = p.fonte WHERE nullif(btrim(p.nome_civil), '') IS NOT NULL
ORDER BY p.pessoa_id, ref.normalizar_texto(p.nome_civil)
ON CONFLICT (pessoa_id, tipo, nome_normalizado) DO NOTHING;
INSERT INTO core.pessoa_nome (pessoa_id, tipo, nome, fonte_id)
SELECT DISTINCT ON (p.pessoa_id, ref.normalizar_texto(p.nome_exibicao)) p.pessoa_id, 'ELEITORAL', p.nome_exibicao, f.id
FROM _p p JOIN etl.fonte f ON f.codigo = p.fonte WHERE nullif(btrim(p.nome_exibicao), '') IS NOT NULL
ORDER BY p.pessoa_id, ref.normalizar_texto(p.nome_exibicao)
ON CONFLICT (pessoa_id, tipo, nome_normalizado) DO NOTHING;

-- ── mandatos ─────────────────────────────────────────────────────────────────────────────────────────────────────
INSERT INTO core.eleicao (ano, tipo) SELECT DISTINCT ano_eleicao, 'GERAL' FROM _in_mandato WHERE ano_eleicao IS NOT NULL
ON CONFLICT (ano, tipo) DO NOTHING;

CREATE TEMP TABLE _partido ON COMMIT DROP AS
SELECT DISTINCT ON (k) k, id FROM (
    SELECT sigla_normalizada AS k, id, 0 AS o FROM core.partido
    UNION ALL SELECT sigla_normalizada, partido_id, 1 FROM core.partido_alias) x ORDER BY k, o, id;

CREATE TEMP TABLE _m ON COMMIT DROP AS
SELECT m.*, p.pessoa_id, cg.id AS cargo_id, e.id AS eleicao_id,
       (SELECT pt.id FROM _partido pt WHERE pt.k = ref.normalizar_texto(m.partido_sigla)) AS partido_id,
       CASE WHEN m.cargo = 'PRESIDENTE' THEN (SELECT ci.id FROM ref.circunscricao ci WHERE ci.tipo = 'BR')
            ELSE (SELECT ci.id FROM ref.circunscricao ci WHERE ci.tipo = 'UF' AND ci.uf = upper(m.uf)) END AS circunscricao_id
FROM _in_mandato m
LEFT JOIN _p p ON p.id_tipo = m.id_tipo AND p.id_valor = m.id_valor
LEFT JOIN ref.cargo cg ON cg.codigo = m.cargo
LEFT JOIN core.eleicao e ON e.ano = m.ano_eleicao AND e.tipo = 'GERAL';

INSERT INTO _rej SELECT motivo, count(*) FROM (
    SELECT CASE WHEN pessoa_id IS NULL THEN 'MANDATO_SEM_PESSOA'
                WHEN cargo_id IS NULL THEN 'CARGO_DESCONHECIDO'
                WHEN circunscricao_id IS NULL THEN 'MANDATO_SEM_UF' END AS motivo FROM _m) x
WHERE motivo IS NOT NULL GROUP BY motivo;
DELETE FROM _m WHERE pessoa_id IS NULL OR cargo_id IS NULL OR circunscricao_id IS NULL;

CREATE TEMP TABLE _toca (id bigint PRIMARY KEY) ON COMMIT DROP;

-- mandatos que esta carga refaz (senadores, presidentes, ex-parlamentares)
WITH gravado AS (
    INSERT INTO core.mandato (pessoa_id, cargo_id, circunscricao_id, eleicao_id, partido_id, condicao, numero_mandato,
                              inicio, fim, motivo_encerramento, fonte_id)
    SELECT m.pessoa_id, m.cargo_id, m.circunscricao_id, m.eleicao_id, m.partido_id, m.condicao, m.numero_mandato,
           m.inicio, m.fim, m.motivo_encerramento, f.id
    FROM _m m JOIN etl.fonte f ON f.codigo = m.fonte WHERE m.sobrescreve
    ON CONFLICT ON CONSTRAINT uq_mandato_natural DO UPDATE SET
        circunscricao_id = EXCLUDED.circunscricao_id, partido_id = coalesce(EXCLUDED.partido_id, core.mandato.partido_id),
        condicao = EXCLUDED.condicao, inicio = EXCLUDED.inicio, fim = EXCLUDED.fim,
        motivo_encerramento = EXCLUDED.motivo_encerramento, atualizado_em = now()
    RETURNING id)
INSERT INTO _toca SELECT id FROM gravado ON CONFLICT DO NOTHING;

-- mandato presidencial: o slug (id_referencia do arquivo curado) e o rótulo; a economia, o território e a composição ligam por ele
INSERT INTO core.mandato_presidencial (mandato_id, slug, rotulo)
SELECT mm.id, m.ref_mandato, m.rotulo
FROM _m m JOIN core.mandato mm ON mm.pessoa_id = m.pessoa_id AND mm.cargo_id = m.cargo_id
 AND mm.eleicao_id IS NOT DISTINCT FROM m.eleicao_id AND mm.numero_mandato = m.numero_mandato AND mm.orgao_nome IS NULL
WHERE m.cargo = 'PRESIDENTE' AND m.ref_mandato IS NOT NULL
ON CONFLICT (mandato_id) DO UPDATE SET slug = EXCLUDED.slug,
    rotulo = coalesce(EXCLUDED.rotulo, core.mandato_presidencial.rotulo);

-- mandatos de deputado: o histórico por deputado (eventos da Câmara) traz datas e situações mais exatas; aqui só entram
-- os que ainda não existem, e nunca se sobrescreve o que ele gravou
WITH gravado AS (
    INSERT INTO core.mandato (pessoa_id, cargo_id, circunscricao_id, eleicao_id, partido_id, condicao, numero_mandato,
                              inicio, fim, motivo_encerramento, fonte_id)
    SELECT m.pessoa_id, m.cargo_id, m.circunscricao_id, m.eleicao_id, m.partido_id, m.condicao, m.numero_mandato,
           m.inicio, m.fim, m.motivo_encerramento, f.id
    FROM _m m JOIN etl.fonte f ON f.codigo = m.fonte WHERE NOT m.sobrescreve
    ON CONFLICT ON CONSTRAINT uq_mandato_natural DO NOTHING
    RETURNING id)
INSERT INTO _toca SELECT id FROM gravado ON CONFLICT DO NOTHING;

-- ── partido do senador ao longo do mandato: as filiações do Senado (`/senador/{codigo}/filiacoes`) cortadas pelo mandato ──
-- O partido da lista do mandato é o atual (ou o da última legislatura), não vale para o mandato inteiro; o período exato
-- vem daqui, e `filiacoes.sql` só usa o partido do mandato quando não há período. Períodos que se tocam terminam na véspera do
-- seguinte (o Senado às vezes repete o dia da troca). Sem filiação conhecida o período fica sem partido (desconhecido).
CREATE TEMP TABLE _fs ON COMMIT DROP AS
SELECT y.pessoa_id, y.partido_id, daterange(y.inicio, y.fim_exclusivo, '[)') AS periodo
FROM (SELECT x.pessoa_id, x.partido_id, x.inicio, least(x.fim + 1, x.prox) AS fim_exclusivo
      FROM (SELECT i.pessoa_id, (SELECT pt.id FROM _partido pt WHERE pt.k = ref.normalizar_texto(f.partido_sigla)) AS partido_id,
                   f.inicio, f.fim, lead(f.inicio) OVER (PARTITION BY i.pessoa_id ORDER BY f.inicio, f.fim NULLS LAST) AS prox
            FROM _in_filiacao_senador f
            JOIN core.pessoa_identificador i ON i.tipo = 'SENADO_ID' AND i.valor = f.id_valor) x) y
WHERE y.partido_id IS NOT NULL AND (y.fim_exclusivo IS NULL OR y.fim_exclusivo > y.inicio);

DELETE FROM core.mandato_partido mp USING core.mandato m
WHERE mp.mandato_id = m.id AND m.cargo_id = (SELECT id FROM ref.cargo WHERE codigo = 'SENADOR')
  AND m.pessoa_id IN (SELECT pessoa_id FROM _fs);
INSERT INTO core.mandato_partido (mandato_id, partido_id, periodo, fonte_id)
SELECT m.id, f.partido_id, x.corte, (SELECT id FROM etl.fonte WHERE codigo = 'SENADO_API')
FROM _fs f
JOIN core.mandato m ON m.pessoa_id = f.pessoa_id AND m.cargo_id = (SELECT id FROM ref.cargo WHERE codigo = 'SENADOR')
CROSS JOIN LATERAL (SELECT f.periodo * daterange(m.inicio, m.fim, '[]') AS corte) x
WHERE NOT isempty(x.corte);

-- ── ministros: pessoa curada, mandato NOMEADO, ligado ao mandato do presidente que o nomeou ─────────────────────────
CREATE TEMP TABLE _min ON COMMIT DROP AS
SELECT g.*, ref.normalizar_texto('ministro:' || g.nome) AS chave,
       (SELECT mm.id FROM core.mandato mm JOIN _m x ON x.pessoa_id = mm.pessoa_id AND x.cargo_id = mm.cargo_id
         AND x.eleicao_id IS NOT DISTINCT FROM mm.eleicao_id AND x.numero_mandato = mm.numero_mandato
         WHERE x.ref_mandato = g.ref_mandato AND mm.orgao_nome IS NULL LIMIT 1) AS nomeado_por
FROM _in_ministro g;

-- uma pessoa por chave curada (o mesmo ministro pode servir a mais de um presidente)
CREATE TEMP TABLE _minp ON COMMIT DROP AS
SELECT g.chave, min(g.nome) AS nome, gen_random_uuid() AS uid_novo FROM _min g GROUP BY g.chave;
INSERT INTO core.pessoa (uid, nome_exibicao)
SELECT m.uid_novo, m.nome FROM _minp m
WHERE NOT EXISTS (SELECT 1 FROM core.pessoa_identificador i WHERE i.tipo = 'CURADORIA_ID' AND i.valor = m.chave);
INSERT INTO core.pessoa_identificador (pessoa_id, fonte_id, tipo, valor)
SELECT pe.id, (SELECT id FROM etl.fonte WHERE codigo = 'CURADORIA'), 'CURADORIA_ID', m.chave
FROM _minp m JOIN core.pessoa pe ON pe.uid = m.uid_novo
ON CONFLICT (fonte_id, tipo, valor) DO NOTHING;
INSERT INTO core.pessoa_nome (pessoa_id, tipo, nome, fonte_id)
SELECT DISTINCT ON (i.pessoa_id) i.pessoa_id, 'HISTORICO', g.nome, i.fonte_id
FROM _min g JOIN core.pessoa_identificador i ON i.tipo = 'CURADORIA_ID' AND i.valor = g.chave
ON CONFLICT (pessoa_id, tipo, nome_normalizado) DO NOTHING;

WITH gravado AS (
    INSERT INTO core.mandato (pessoa_id, cargo_id, circunscricao_id, condicao, numero_mandato, inicio, fim, orgao_nome,
                              funcao_destaque, nomeado_por_mandato_id, fonte_id)
    SELECT i.pessoa_id, (SELECT id FROM ref.cargo WHERE codigo = 'MINISTRO_DE_ESTADO'),
           (SELECT id FROM ref.circunscricao WHERE tipo = 'BR'), 'NOMEADO',
           (row_number() OVER (PARTITION BY i.pessoa_id, g.orgao ORDER BY g.inicio))::smallint,
           g.inicio, g.fim, g.orgao, CASE WHEN g.economia THEN 'ECONOMIA' END, g.nomeado_por,
           (SELECT id FROM etl.fonte WHERE codigo = 'CURADORIA')
    FROM _min g JOIN core.pessoa_identificador i ON i.tipo = 'CURADORIA_ID' AND i.valor = g.chave
    ON CONFLICT ON CONSTRAINT uq_mandato_natural DO UPDATE SET
        inicio = EXCLUDED.inicio, fim = EXCLUDED.fim, funcao_destaque = EXCLUDED.funcao_destaque,
        nomeado_por_mandato_id = EXCLUDED.nomeado_por_mandato_id, atualizado_em = now()
    RETURNING id)
INSERT INTO _toca SELECT id FROM gravado ON CONFLICT DO NOTHING;

-- ── situações do mandato: exercício menos os períodos em que o titular esteve em ministério ──────────────────────────
-- (suplente: SUPLENCIA; ministério: AFASTADO_MINISTERIO). O histórico da Câmara refaz as dos deputados que ele cobre.
INSERT INTO _toca SELECT c.id FROM core.mandato c
WHERE c.condicao = 'NOMEADO' AND EXISTS (SELECT 1 FROM _toca t WHERE t.id = c.id) ON CONFLICT DO NOTHING;
INSERT INTO _toca SELECT c.id FROM core.mandato c
WHERE c.condicao <> 'NOMEADO' AND c.pessoa_id IN (SELECT m2.pessoa_id FROM core.mandato m2 JOIN _toca t ON t.id = m2.id WHERE m2.condicao = 'NOMEADO')
ON CONFLICT DO NOTHING;

DELETE FROM core.mandato_situacao s USING _toca t WHERE s.mandato_id = t.id;
INSERT INTO core.mandato_situacao (mandato_id, situacao, periodo, motivo, fonte_id)
SELECT s.id, s.situacao, daterange(lower(s.seg), upper(s.seg), '[)'), s.motivo, s.fonte_id
FROM (
    SELECT b.id, b.fonte_id,
           CASE WHEN b.tipo = 'AFASTADO' THEN 'AFASTADO_MINISTERIO' WHEN b.condicao = 'SUPLENTE' THEN 'SUPLENCIA'
                ELSE 'EXERCICIO' END AS situacao,
           CASE WHEN b.tipo = 'AFASTADO' THEN 'Licenciado para cargo de Ministro de Estado' END AS motivo,
           unnest(b.mr) AS seg
    FROM (
        SELECT c.id, c.condicao, c.fonte_id, t.tipo,
               CASE t.tipo
                    WHEN 'EXERCICIO' THEN datemultirange(daterange(c.inicio, c.fim, '[]')) - coalesce(mn.mr, '{}'::datemultirange)
                    ELSE datemultirange(daterange(c.inicio, c.fim, '[]')) * coalesce(mn.mr, '{}'::datemultirange)
               END AS mr
        FROM core.mandato c JOIN _toca k ON k.id = c.id
        LEFT JOIN LATERAL (
            SELECT range_agg(daterange(m2.inicio, m2.fim, '[]')) AS mr
            FROM core.mandato m2 WHERE m2.pessoa_id = c.pessoa_id AND m2.condicao = 'NOMEADO') mn ON true
        CROSS JOIN (VALUES ('EXERCICIO'), ('AFASTADO')) AS t(tipo)
        WHERE c.condicao <> 'NOMEADO'
    ) b
) s
WHERE NOT isempty(s.seg);

-- ── mesma pessoa gravada com dois cadastros: o mesmo CPF (HMAC) ou, sem CPF, o mesmo nome civil + nascimento (fica a de menor id) ──
-- O mesmo HMAC vale mesmo que um dos cadastros ainda não o tenha como identificador (o identificador é único por fonte: quem
-- já o tem de outra pessoa da mesma fonte não o recebe acima). Nome civil + nascimento só funde quando o CPF não prova o
-- contrário: dois cadastros com CPF_HMAC diferentes são pessoas diferentes, por mais que o nome e o nascimento coincidam.
-- Cada fusão recomeça a busca (uma fusão muda os pares que sobram) e leva o `_p.pessoa_id` da pessoa apagada para a que ficou.
DO $$
DECLARE par record;
BEGIN
    LOOP
        SELECT x.manter, x.apagar INTO par FROM (
            SELECT a.pessoa_id AS manter, b.pessoa_id AS apagar
            FROM core.pessoa_identificador a
            JOIN core.pessoa_identificador b ON b.tipo = 'CPF_HMAC' AND b.valor = a.valor AND b.pessoa_id > a.pessoa_id
            WHERE a.tipo = 'CPF_HMAC' AND (a.pessoa_id IN (SELECT pessoa_id FROM _p) OR b.pessoa_id IN (SELECT pessoa_id FROM _p))
            UNION
            SELECT least(p.pessoa_id, h.pessoa_id), greatest(p.pessoa_id, h.pessoa_id)
            FROM _p p JOIN core.pessoa_identificador h ON h.tipo = 'CPF_HMAC' AND h.valor = p.cpf_hmac AND h.pessoa_id <> p.pessoa_id
            WHERE p.cpf_hmac IS NOT NULL AND p.pessoa_id IS NOT NULL
        ) x ORDER BY x.apagar, x.manter LIMIT 1;
        EXIT WHEN NOT FOUND;
        DELETE FROM core.pessoa_candidata_duplicidade WHERE pessoa_a_id = par.apagar OR pessoa_b_id = par.apagar;
        PERFORM core.unificar_pessoas(par.manter, par.apagar);
        UPDATE _p SET pessoa_id = par.manter WHERE pessoa_id = par.apagar;
    END LOOP;
END $$;

DO $$
DECLARE par record;
BEGIN
    LOOP
        SELECT a.id AS manter, b.id AS apagar INTO par
        FROM core.pessoa a
        JOIN core.pessoa_nome na ON na.pessoa_id = a.id AND na.tipo = 'CIVIL'
        JOIN core.pessoa_nome nb ON nb.nome_normalizado = na.nome_normalizado AND nb.tipo = 'CIVIL' AND nb.pessoa_id > a.id
        JOIN core.pessoa b ON b.id = nb.pessoa_id AND b.data_nascimento = a.data_nascimento
        WHERE (a.id IN (SELECT pessoa_id FROM _p) OR b.id IN (SELECT pessoa_id FROM _p))
          AND NOT (EXISTS (SELECT 1 FROM core.pessoa_identificador ha WHERE ha.pessoa_id = a.id AND ha.tipo = 'CPF_HMAC')
                   AND EXISTS (SELECT 1 FROM core.pessoa_identificador hb WHERE hb.pessoa_id = b.id AND hb.tipo = 'CPF_HMAC')
                   AND NOT EXISTS (SELECT 1 FROM core.pessoa_identificador ha JOIN core.pessoa_identificador hb
                                      ON hb.tipo = 'CPF_HMAC' AND hb.valor = ha.valor AND hb.pessoa_id = b.id
                                    WHERE ha.pessoa_id = a.id AND ha.tipo = 'CPF_HMAC'))
        ORDER BY b.id, a.id LIMIT 1;
        EXIT WHEN NOT FOUND;
        DELETE FROM core.pessoa_candidata_duplicidade WHERE pessoa_a_id = par.apagar OR pessoa_b_id = par.apagar;
        PERFORM core.unificar_pessoas(par.manter, par.apagar);
        UPDATE _p SET pessoa_id = par.manter WHERE pessoa_id = par.apagar;
    END LOOP;
END $$;

-- ── possíveis duplicados: mesmo nome civil que a data de nascimento não confirma (revisão humana, nunca se funde) ──
-- Entram o par sem data de um dos lados e o par com datas diferentes (a mesma pessoa pode vir com a data errada em uma
-- fonte). Não entra o par que o CPF prova serem pessoas diferentes (CPF_HMAC diferentes nos dois lados).
INSERT INTO core.pessoa_candidata_duplicidade (pessoa_a_id, pessoa_b_id, similaridade, motivo)
SELECT DISTINCT least(na.pessoa_id, nb.pessoa_id), greatest(na.pessoa_id, nb.pessoa_id), 1.0, 'NOME_NORMALIZADO_IGUAL'
FROM core.pessoa_nome na JOIN core.pessoa_nome nb
  ON nb.nome_normalizado = na.nome_normalizado AND nb.tipo = na.tipo AND nb.pessoa_id > na.pessoa_id
WHERE na.tipo = 'CIVIL' AND na.pessoa_id IN (SELECT pessoa_id FROM _p)
  AND NOT (EXISTS (SELECT 1 FROM core.pessoa_identificador ha WHERE ha.pessoa_id = na.pessoa_id AND ha.tipo = 'CPF_HMAC')
           AND EXISTS (SELECT 1 FROM core.pessoa_identificador hb WHERE hb.pessoa_id = nb.pessoa_id AND hb.tipo = 'CPF_HMAC')
           AND NOT EXISTS (SELECT 1 FROM core.pessoa_identificador ha JOIN core.pessoa_identificador hb
                              ON hb.tipo = 'CPF_HMAC' AND hb.valor = ha.valor AND hb.pessoa_id = nb.pessoa_id
                            WHERE ha.pessoa_id = na.pessoa_id AND ha.tipo = 'CPF_HMAC'))
ON CONFLICT (pessoa_a_id, pessoa_b_id) DO NOTHING;
