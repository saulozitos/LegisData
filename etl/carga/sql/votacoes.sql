-- Votações de plenário (arquivos de 2023 e anuais): sessão, votos nominais e orientações de bancada. A sessão se liga à
-- proposição pelo id da casa (ou pela numeração exata do Senado); quando o arquivo traz os dados da proposição e ela não
-- existe, ela é criada. O parlamentar vem do id oficial da casa; sem ele o voto é rejeitado.
-- Entradas: _in_sessao, _in_voto, _in_orientacao. Saída: _rej.

CREATE TEMP TABLE _s ON COMMIT DROP AS
SELECT DISTINCT ON (s.id_externo) s.*, (s.data_hora::timestamp AT TIME ZONE 'America/Sao_Paulo') AS ts, NULL::bigint AS prop_id,
       NULL::bigint AS votacao_id
FROM _in_sessao s ORDER BY s.id_externo, s.linha;

INSERT INTO _rej SELECT 'SESSAO_REPETIDA_NOS_ARQUIVOS', count(*) - (SELECT count(*) FROM _s) FROM _in_sessao
 HAVING count(*) > (SELECT count(*) FROM _s);

-- proposição existente
UPDATE _s SET prop_id = lp.id FROM leg.proposicao lp WHERE _s.casa = 'CAMARA' AND _s.prop_camara_id IS NOT NULL AND lp.id_camara = _s.prop_camara_id;
UPDATE _s SET prop_id = lp.id FROM leg.proposicao lp WHERE _s.casa = 'SENADO' AND _s.prop_senado_id IS NOT NULL AND lp.id_senado = _s.prop_senado_id;
-- Senado sem id da matéria no arquivo: pela numeração exata (tipo, número, ano), só quando é uma proposição só
UPDATE _s SET prop_id = x.id FROM (
    SELECT s.id_externo, min(lp.id) AS id FROM _s s JOIN leg.proposicao lp
      ON lp.tipo_codigo = s.prop_tipo AND lp.numero = s.prop_numero AND lp.ano = s.prop_ano
    WHERE s.casa = 'SENADO' AND s.prop_id IS NULL GROUP BY s.id_externo HAVING count(*) = 1) x
WHERE _s.id_externo = x.id_externo AND _s.prop_id IS NULL;

-- proposição que o arquivo descreve por inteiro e o banco ainda não tem
WITH novas AS (
    SELECT DISTINCT ON (s.casa, coalesce(s.prop_camara_id, s.prop_senado_id)) s.*
    FROM _s s
    WHERE s.prop_id IS NULL AND coalesce(s.prop_camara_id, s.prop_senado_id) IS NOT NULL
      AND s.prop_tipo IN (SELECT codigo FROM ref.tipo_proposicao) AND s.prop_numero IS NOT NULL
      AND s.prop_ano >= 1995 AND s.prop_data_apresentacao >= DATE '1995-01-01'
    ORDER BY s.casa, coalesce(s.prop_camara_id, s.prop_senado_id), s.linha)
INSERT INTO leg.proposicao (id_camara, id_senado, tipo_codigo, numero, ano, titulo, ementa, data_apresentacao, status_codigo,
                            url_oficial, url_texto_original, eixo_impacto, eixos_impacto, fonte_id)
SELECT n.prop_camara_id, n.prop_senado_id, n.prop_tipo, n.prop_numero, n.prop_ano,
       coalesce(n.prop_titulo, n.prop_tipo || ' ' || n.prop_numero || '/' || n.prop_ano), n.prop_ementa,
       n.prop_data_apresentacao,
       coalesce((SELECT codigo FROM ref.status_tramitacao WHERE codigo = n.prop_status), 'SEM_INFORMACAO'), n.prop_url, n.prop_url_texto, n.prop_eixo, n.prop_eixos,
       (SELECT id FROM etl.fonte WHERE codigo = CASE WHEN n.casa = 'CAMARA' THEN 'CAMARA_API' ELSE 'SENADO_API' END)
FROM novas n
ON CONFLICT DO NOTHING;
UPDATE _s SET prop_id = lp.id FROM leg.proposicao lp
 WHERE _s.prop_id IS NULL AND ((_s.casa = 'CAMARA' AND lp.id_camara = _s.prop_camara_id)
                            OR (_s.casa = 'SENADO' AND lp.id_senado = _s.prop_senado_id));

-- rejeições da sessão
ALTER TABLE _s ADD COLUMN rej text;
UPDATE _s SET rej = CASE
    WHEN ts IS NULL THEN 'SESSAO_SEM_DATA'
    WHEN ts < TIMESTAMPTZ '1995-01-01' THEN 'FORA_DA_JANELA_1995'
    WHEN prop_id IS NULL THEN 'SEM_PROPOSICAO' END;
INSERT INTO _rej SELECT rej, count(*) FROM _s WHERE rej IS NOT NULL GROUP BY rej;

-- sessão
INSERT INTO leg.votacao (id_externo, proposicao_id, casa_id, data_hora, titulo_pauta, descricao, tipo_deliberacao, secreta,
                         aprovada, orientacao_governo, total_sim_fonte, total_nao_fonte, total_abstencao_fonte,
                         total_obstrucao_fonte, fonte_id)
SELECT s.id_externo, s.prop_id,
       (SELECT c.id FROM ref.casa_legislativa c WHERE c.codigo = CASE WHEN s.casa = 'CAMARA' THEN 'CAMARA_DOS_DEPUTADOS' ELSE 'SENADO_FEDERAL' END),
       s.ts, s.titulo_pauta, s.descricao, CASE WHEN coalesce(s.secreta, false) THEN 'SECRETA' ELSE 'NOMINAL' END,
       coalesce(s.secreta, false), s.aprovada,
       s.orientacao_governo, s.t_sim, s.t_nao, s.t_abs, s.t_obs,
       (SELECT id FROM etl.fonte WHERE codigo = CASE WHEN s.casa = 'CAMARA' THEN 'CAMARA_API' ELSE 'SENADO_API' END)
FROM _s s WHERE s.rej IS NULL
ON CONFLICT (id_externo) DO UPDATE SET
    proposicao_id = EXCLUDED.proposicao_id, data_hora = EXCLUDED.data_hora,
    titulo_pauta = coalesce(EXCLUDED.titulo_pauta, leg.votacao.titulo_pauta),
    descricao = coalesce(EXCLUDED.descricao, leg.votacao.descricao), tipo_deliberacao = EXCLUDED.tipo_deliberacao,
    secreta = EXCLUDED.secreta, aprovada = coalesce(EXCLUDED.aprovada, leg.votacao.aprovada),
    orientacao_governo = coalesce(EXCLUDED.orientacao_governo, leg.votacao.orientacao_governo),
    total_sim_fonte = coalesce(EXCLUDED.total_sim_fonte, leg.votacao.total_sim_fonte),
    total_nao_fonte = coalesce(EXCLUDED.total_nao_fonte, leg.votacao.total_nao_fonte),
    total_abstencao_fonte = coalesce(EXCLUDED.total_abstencao_fonte, leg.votacao.total_abstencao_fonte),
    total_obstrucao_fonte = coalesce(EXCLUDED.total_obstrucao_fonte, leg.votacao.total_obstrucao_fonte);
UPDATE _s SET votacao_id = v.id FROM leg.votacao v WHERE v.id_externo = _s.id_externo AND _s.rej IS NULL;

-- votos
CREATE TEMP TABLE _partido ON COMMIT DROP AS
SELECT DISTINCT ON (k) k, id FROM (
    SELECT sigla_normalizada AS k, id, 0 AS o FROM core.partido
    UNION ALL SELECT sigla_normalizada, partido_id, 1 FROM core.partido_alias) x ORDER BY k, o, id;

CREATE TEMP TABLE _v ON COMMIT DROP AS
SELECT DISTINCT ON (s.votacao_id, i.pessoa_id) s.votacao_id, i.pessoa_id, v.opcao,
       (SELECT pt.id FROM _partido pt WHERE pt.k = ref.normalizar_texto(v.partido)) AS partido_id
FROM _in_voto v
JOIN _s s ON s.id_externo = v.id_externo AND s.rej IS NULL
JOIN core.pessoa_identificador i ON i.tipo = CASE WHEN v.casa = 'CAMARA' THEN 'CAMARA_ID' ELSE 'SENADO_ID' END
                                AND i.valor = v.parlamentar_ext_id::text
WHERE v.opcao IN (SELECT codigo FROM ref.opcao_voto)
ORDER BY s.votacao_id, i.pessoa_id, v.linha;

INSERT INTO _rej SELECT 'VOTO_COM_OPCAO_INVALIDA', count(*) FROM _in_voto WHERE opcao IS NULL OR opcao NOT IN (SELECT codigo FROM ref.opcao_voto)
 HAVING count(*) > 0;
INSERT INTO _rej SELECT 'VOTO_SEM_SESSAO_OU_PARLAMENTAR', count(*) - (SELECT count(*) FROM _v)
  - (SELECT count(*) FROM _in_voto WHERE opcao IS NULL OR opcao NOT IN (SELECT codigo FROM ref.opcao_voto))
  FROM _in_voto HAVING count(*) - (SELECT count(*) FROM _v)
  - (SELECT count(*) FROM _in_voto WHERE opcao IS NULL OR opcao NOT IN (SELECT codigo FROM ref.opcao_voto)) > 0;

ANALYZE _v;

-- sem partido no arquivo: o da filiação vigente na data da votação; sem filiação nenhuma, o do mandato
UPDATE _v v SET partido_id = coalesce(
    (SELECT f.partido_id FROM core.filiacao f JOIN leg.votacao vo ON vo.id = v.votacao_id
      WHERE f.pessoa_id = v.pessoa_id AND f.periodo @> vo.data_hora::date LIMIT 1),
    (SELECT m.partido_id FROM core.mandato m
      WHERE m.pessoa_id = v.pessoa_id AND m.partido_id IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM core.filiacao x WHERE x.pessoa_id = v.pessoa_id)
      ORDER BY m.inicio DESC LIMIT 1))
WHERE v.partido_id IS NULL;

INSERT INTO leg.voto (votacao_id, pessoa_id, partido_id, opcao_codigo)
SELECT votacao_id, pessoa_id, partido_id, opcao FROM _v
ON CONFLICT (votacao_id, pessoa_id) DO UPDATE SET partido_id = coalesce(EXCLUDED.partido_id, leg.voto.partido_id),
    opcao_codigo = EXCLUDED.opcao_codigo;

-- orientações de bancada
INSERT INTO leg.orientacao (votacao_id, bancada, partido_id, orientacao)
SELECT DISTINCT ON (s.votacao_id, o.bancada) s.votacao_id, o.bancada,
       (SELECT pt.id FROM _partido pt WHERE pt.k = ref.normalizar_texto(o.bancada)), o.orientacao
FROM _in_orientacao o JOIN _s s ON s.id_externo = o.id_externo AND s.rej IS NULL
WHERE o.orientacao IN ('SIM', 'NAO', 'ABSTENCAO', 'OBSTRUCAO', 'LIBERADO') AND nullif(btrim(o.bancada), '') IS NOT NULL
ORDER BY s.votacao_id, o.bancada
ON CONFLICT (votacao_id, bancada) DO UPDATE SET orientacao = EXCLUDED.orientacao, partido_id = EXCLUDED.partido_id;
