-- Proposições dos arquivos da Câmara (API) e do Senado: acrescentam área, eixos, autoria e as proposições do Senado às que o
-- CSV da Câmara já gravou. Sem situação na fonte, a situação é SEM_INFORMACAO (nunca uma situação suposta).
-- Entrada: _in_prop. Saída: _rej.

CREATE TEMP TABLE _pp ON COMMIT DROP AS
SELECT DISTINCT ON (p.casa, p.ext_id) p.* FROM _in_prop p ORDER BY p.casa, p.ext_id, p.linha;

INSERT INTO _rej SELECT 'ID_REPETIDO_NOS_ARQUIVOS', count(*) - (SELECT count(*) FROM _pp) FROM _in_prop
 HAVING count(*) > (SELECT count(*) FROM _pp);
INSERT INTO _rej SELECT motivo, count(*) FROM (
    SELECT CASE WHEN tipo NOT IN (SELECT codigo FROM ref.tipo_proposicao) THEN 'TIPO_FORA_DO_ESCOPO'
                WHEN numero IS NULL OR ano IS NULL OR data_apresentacao IS NULL THEN 'DADO_OBRIGATORIO_AUSENTE'
                WHEN ano < 1995 OR data_apresentacao < DATE '1995-01-01' THEN 'FORA_DA_JANELA_1995' END AS motivo
    FROM _pp) x WHERE motivo IS NOT NULL GROUP BY motivo;
DELETE FROM _pp WHERE tipo NOT IN (SELECT codigo FROM ref.tipo_proposicao)
   OR numero IS NULL OR ano IS NULL OR data_apresentacao IS NULL OR ano < 1995 OR data_apresentacao < DATE '1995-01-01';

-- Câmara: a proposição que já existe (pelo id) e as novas
ALTER TABLE _pp ADD COLUMN prop_id bigint;
UPDATE _pp SET prop_id = lp.id FROM leg.proposicao lp WHERE _pp.casa = 'CAMARA' AND lp.id_camara = _pp.ext_id;
INSERT INTO leg.proposicao (id_camara, tipo_codigo, numero, ano, titulo, ementa, area_tematica, data_apresentacao,
                            status_codigo, url_oficial, reforma_estrutural, iniciativa_executivo, autor_nome, eixo_impacto,
                            eixos_impacto, fonte_id)
SELECT p.ext_id, p.tipo, p.numero, p.ano, coalesce(p.titulo, p.tipo || ' ' || p.numero || '/' || p.ano), p.ementa, p.area,
       p.data_apresentacao, 'SEM_INFORMACAO', p.url_oficial, coalesce(p.reforma, false), coalesce(p.executivo, false),
       p.autor_nome, p.eixo, p.eixos, (SELECT id FROM etl.fonte WHERE codigo = 'CAMARA_API')
FROM _pp p WHERE p.casa = 'CAMARA' AND p.prop_id IS NULL
ON CONFLICT DO NOTHING;
UPDATE _pp SET prop_id = lp.id FROM leg.proposicao lp WHERE _pp.casa = 'CAMARA' AND _pp.prop_id IS NULL AND lp.id_camara = _pp.ext_id;

-- Senado: pelo id da matéria; senão pela numeração única (PL, PEC... a partir de 2019), que identifica a mesma proposição
-- na Câmara; senão é nova
UPDATE _pp SET prop_id = lp.id FROM leg.proposicao lp WHERE _pp.casa = 'SENADO' AND lp.id_senado = _pp.ext_id;
UPDATE _pp SET prop_id = x.id FROM (
    SELECT p.ext_id, min(lp.id) AS id FROM _pp p JOIN leg.proposicao lp
      ON lp.tipo_codigo = p.tipo AND lp.numero = p.numero AND lp.ano = p.ano AND lp.id_senado IS NULL
    WHERE p.casa = 'SENADO' AND p.prop_id IS NULL AND p.ano >= 2019
      -- duas matérias do Senado com a mesma numeração: só a de menor id adota a da Câmara (o resultado não depende da ordem)
      AND p.ext_id = (SELECT min(q.ext_id) FROM _pp q WHERE q.casa = 'SENADO' AND q.tipo = p.tipo AND q.numero = p.numero AND q.ano = p.ano)
    GROUP BY p.ext_id HAVING count(*) = 1) x
WHERE _pp.casa = 'SENADO' AND _pp.ext_id = x.ext_id AND _pp.prop_id IS NULL;
UPDATE leg.proposicao lp SET id_senado = p.ext_id FROM _pp p
 WHERE p.casa = 'SENADO' AND p.prop_id = lp.id AND lp.id_senado IS NULL
   AND NOT EXISTS (SELECT 1 FROM leg.proposicao o WHERE o.id_senado = p.ext_id);
INSERT INTO leg.proposicao (id_senado, tipo_codigo, numero, ano, titulo, ementa, area_tematica, data_apresentacao,
                            status_codigo, url_oficial, reforma_estrutural, iniciativa_executivo, autor_nome, eixo_impacto,
                            eixos_impacto, fonte_id)
SELECT p.ext_id, p.tipo, p.numero, p.ano, coalesce(p.titulo, p.tipo || ' ' || p.numero || '/' || p.ano), p.ementa, p.area,
       p.data_apresentacao, 'SEM_INFORMACAO', p.url_oficial, coalesce(p.reforma, false), coalesce(p.executivo, false),
       p.autor_nome, p.eixo, p.eixos, (SELECT id FROM etl.fonte WHERE codigo = 'SENADO_API')
FROM _pp p WHERE p.casa = 'SENADO' AND p.prop_id IS NULL
ON CONFLICT DO NOTHING;
UPDATE _pp SET prop_id = lp.id FROM leg.proposicao lp WHERE _pp.casa = 'SENADO' AND _pp.prop_id IS NULL AND lp.id_senado = _pp.ext_id;

-- enriquecimento: só o que a fonte do CSV não traz; título, ementa, datas e situação não são tocados
UPDATE leg.proposicao lp SET
    area_tematica = coalesce(p.area, lp.area_tematica), eixo_impacto = coalesce(p.eixo, lp.eixo_impacto),
    eixos_impacto = coalesce(p.eixos, lp.eixos_impacto), url_oficial = coalesce(p.url_oficial, lp.url_oficial),
    reforma_estrutural = coalesce(p.reforma, lp.reforma_estrutural),
    iniciativa_executivo = coalesce(p.executivo, lp.iniciativa_executivo),
    autor_nome = coalesce(lp.autor_nome, p.autor_nome),
    autor_pessoa_id = coalesce(lp.autor_pessoa_id, (SELECT i.pessoa_id FROM core.pessoa_identificador i
                        WHERE i.tipo = 'CAMARA_ID' AND i.valor = p.autor_camara_id::text ORDER BY i.id LIMIT 1)),
    atualizado_em = now()
FROM _pp p WHERE p.prop_id = lp.id;

-- autoria: o que veio dos autores do CSV não é tocado; sem nenhuma autoria, o autor do arquivo vira o principal
INSERT INTO leg.autoria (proposicao_id, pessoa_id, nome_autor, tipo_codigo, ordem, fonte_id)
SELECT p.prop_id, lp.autor_pessoa_id, coalesce(lp.autor_nome, pe.nome_exibicao), 'AUTOR_PRINCIPAL', 1,
       (SELECT id FROM etl.fonte WHERE codigo = CASE WHEN p.casa = 'CAMARA' THEN 'CAMARA_API' ELSE 'SENADO_API' END)
FROM _pp p JOIN leg.proposicao lp ON lp.id = p.prop_id LEFT JOIN core.pessoa pe ON pe.id = lp.autor_pessoa_id
WHERE coalesce(lp.autor_nome, pe.nome_exibicao) IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM leg.autoria a WHERE a.proposicao_id = p.prop_id);
