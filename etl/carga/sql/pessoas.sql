-- Pessoas e mandatos de quem as fontes oficiais listam. A pessoa se acha pelo identificador oficial (CAMARA_ID, SENADO_ID,
-- TSE_ID), pela chave curada (presidentes e ministros) ou, quando é a primeira vez que a fonte a cita, pelo NOME CIVIL
-- COMPLETO + DATA DE NASCIMENTO (os dois presentes e iguais): assim quem foi deputado e depois senador é uma pessoa só,
-- com os dois identificadores. Nome sem data de nascimento nunca une ninguém (vira candidata a duplicidade). Idempotente.
-- Entradas (tabelas temporárias da transação): _in_pessoa, _in_mandato, _in_ministro. Saída: _rej (motivo, n).

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

-- primeira vez que a fonte cita o id: se já existe pessoa com o mesmo nome civil e a mesma data de nascimento, é ela
UPDATE _p SET pessoa_id = (
    SELECT pe.id FROM core.pessoa pe JOIN core.pessoa_nome n ON n.pessoa_id = pe.id AND n.tipo = 'CIVIL'
    WHERE n.nome_normalizado = ref.normalizar_texto(_p.nome_civil) AND pe.data_nascimento = _p.data_nascimento
    ORDER BY pe.id LIMIT 1)
WHERE pessoa_id IS NULL AND nullif(btrim(nome_civil), '') IS NOT NULL AND data_nascimento IS NOT NULL;

-- ainda sem pessoa: um uid por chave, para o deputado e o senador da mesma pessoa nascerem juntos
CREATE TEMP TABLE _uid_chave ON COMMIT DROP AS
SELECT d.chave_pessoa, gen_random_uuid() AS uid
FROM (SELECT DISTINCT chave_pessoa FROM _p WHERE pessoa_id IS NULL AND chave_pessoa IS NOT NULL) d;
UPDATE _p SET uid_novo = k.uid FROM _uid_chave k WHERE _p.pessoa_id IS NULL AND _p.chave_pessoa = k.chave_pessoa;
UPDATE _p SET uid_novo = gen_random_uuid() WHERE pessoa_id IS NULL AND uid_novo IS NULL;

INSERT INTO core.pessoa (uid, nome_exibicao, data_nascimento, data_falecimento, sexo, municipio_nascimento, uf_nascimento,
                         foto_midia_id, biografia, email, gabinete_sala, gabinete_telefone)
SELECT DISTINCT ON (p.uid_novo)
       p.uid_novo, p.nome_exibicao, p.data_nascimento, p.data_falecimento, p.sexo, p.municipio_nascimento,
       (SELECT u.sigla FROM ref.uf u WHERE u.sigla = upper(p.uf_nascimento)),
       (SELECT m.id FROM core.midia m WHERE m.tipo = 'FOTO_PESSOA' AND m.url_origem = p.foto_url),
       p.biografia, p.email, p.gabinete_sala, p.gabinete_telefone
FROM _p p WHERE p.pessoa_id IS NULL
ORDER BY p.uid_novo, p.prioridade, p.id_tipo, p.id_valor;
UPDATE _p SET pessoa_id = pe.id FROM core.pessoa pe WHERE _p.pessoa_id IS NULL AND pe.uid = _p.uid_novo;

-- quem já existe: a fonte atual (prioridade 1) vale sobre o que está gravado; a histórica só preenche o que está vazio
UPDATE core.pessoa pe SET
    nome_exibicao = CASE WHEN p.prioridade = 1 THEN coalesce(p.nome_exibicao, pe.nome_exibicao) ELSE pe.nome_exibicao END,
    data_nascimento = CASE WHEN p.prioridade = 1 THEN coalesce(p.data_nascimento, pe.data_nascimento) ELSE coalesce(pe.data_nascimento, p.data_nascimento) END,
    data_falecimento = CASE WHEN p.prioridade = 1 THEN coalesce(p.data_falecimento, pe.data_falecimento) ELSE coalesce(pe.data_falecimento, p.data_falecimento) END,
    sexo = CASE WHEN p.prioridade = 1 THEN coalesce(p.sexo, pe.sexo) ELSE coalesce(pe.sexo, p.sexo) END,
    municipio_nascimento = CASE WHEN p.prioridade = 1 THEN coalesce(p.municipio_nascimento, pe.municipio_nascimento) ELSE coalesce(pe.municipio_nascimento, p.municipio_nascimento) END,
    uf_nascimento = coalesce(pe.uf_nascimento, (SELECT u.sigla FROM ref.uf u WHERE u.sigla = upper(p.uf_nascimento))),
    foto_midia_id = CASE WHEN p.prioridade = 1 THEN coalesce((SELECT m.id FROM core.midia m WHERE m.tipo = 'FOTO_PESSOA' AND m.url_origem = p.foto_url), pe.foto_midia_id)
                         ELSE coalesce(pe.foto_midia_id, (SELECT m.id FROM core.midia m WHERE m.tipo = 'FOTO_PESSOA' AND m.url_origem = p.foto_url)) END,
    biografia = CASE WHEN p.prioridade = 1 THEN coalesce(p.biografia, pe.biografia) ELSE coalesce(pe.biografia, p.biografia) END,
    email = CASE WHEN p.prioridade = 1 THEN coalesce(p.email, pe.email) ELSE coalesce(pe.email, p.email) END,
    gabinete_sala = CASE WHEN p.prioridade = 1 THEN coalesce(p.gabinete_sala, pe.gabinete_sala) ELSE coalesce(pe.gabinete_sala, p.gabinete_sala) END,
    gabinete_telefone = CASE WHEN p.prioridade = 1 THEN coalesce(p.gabinete_telefone, pe.gabinete_telefone) ELSE coalesce(pe.gabinete_telefone, p.gabinete_telefone) END,
    atualizado_em = now()
FROM (SELECT DISTINCT ON (x.pessoa_id) x.* FROM _p x WHERE x.uid_novo IS NULL
      ORDER BY x.pessoa_id, x.prioridade, x.id_tipo, x.id_valor) p
WHERE pe.id = p.pessoa_id;

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
DO $$
DECLARE par record;
BEGIN
    FOR par IN
        SELECT DISTINCT ON (b.pessoa_id) a.pessoa_id AS manter, b.pessoa_id AS apagar
        FROM core.pessoa_identificador a
        JOIN core.pessoa_identificador b ON b.tipo = 'CPF_HMAC' AND b.valor = a.valor AND b.pessoa_id > a.pessoa_id
        WHERE a.tipo = 'CPF_HMAC' AND (a.pessoa_id IN (SELECT pessoa_id FROM _p) OR b.pessoa_id IN (SELECT pessoa_id FROM _p))
        ORDER BY b.pessoa_id, a.pessoa_id
    LOOP
        DELETE FROM core.pessoa_candidata_duplicidade WHERE pessoa_a_id = par.apagar OR pessoa_b_id = par.apagar;
        PERFORM core.unificar_pessoas(par.manter, par.apagar);
    END LOOP;
END $$;

DO $$
DECLARE par record;
BEGIN
    FOR par IN
        SELECT DISTINCT ON (b.id) a.id AS manter, b.id AS apagar
        FROM core.pessoa a
        JOIN core.pessoa_nome na ON na.pessoa_id = a.id AND na.tipo = 'CIVIL'
        JOIN core.pessoa_nome nb ON nb.nome_normalizado = na.nome_normalizado AND nb.tipo = 'CIVIL' AND nb.pessoa_id > a.id
        JOIN core.pessoa b ON b.id = nb.pessoa_id AND b.data_nascimento = a.data_nascimento
        WHERE a.id IN (SELECT pessoa_id FROM _p) OR b.id IN (SELECT pessoa_id FROM _p)
        ORDER BY b.id, a.id
    LOOP
        DELETE FROM core.pessoa_candidata_duplicidade WHERE pessoa_a_id = par.apagar OR pessoa_b_id = par.apagar;
        PERFORM core.unificar_pessoas(par.manter, par.apagar);
    END LOOP;
END $$;

-- ── possíveis duplicados: mesmo nome civil sem data de nascimento para confirmar (revisão humana, nunca se funde) ──
INSERT INTO core.pessoa_candidata_duplicidade (pessoa_a_id, pessoa_b_id, similaridade, motivo)
SELECT DISTINCT least(na.pessoa_id, nb.pessoa_id), greatest(na.pessoa_id, nb.pessoa_id), 1.0, 'NOME_NORMALIZADO_IGUAL'
FROM core.pessoa_nome na JOIN core.pessoa_nome nb
  ON nb.nome_normalizado = na.nome_normalizado AND nb.tipo = na.tipo AND nb.pessoa_id > na.pessoa_id
WHERE na.tipo = 'CIVIL' AND na.pessoa_id IN (SELECT pessoa_id FROM _p)
ON CONFLICT (pessoa_a_id, pessoa_b_id) DO NOTHING;
