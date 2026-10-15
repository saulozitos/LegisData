"""Cadeiras de todos os períodos: histórico de mandatos da Câmara (posse, saída, licença, suplência, partido).

- core.mandato_partido: partido que ocupa a cadeira em cada dia de exercício (fonte: histórico de cada deputado).
- stg.camara_historico / stg.camara_legislatura: staging dos eventos e das datas das legislaturas.
- etl.merge_camara_historico(): grava pessoa, mandato (por legislatura), situações (exercício, suplência, licença) e o
  partido por período. Titulares e suplentes entram igualmente: as cadeiras-dia somam quem esteve no exercício.
- etl.sincronizar_legado() (redefinida): não sobrescreve mandatos que o ETL da Câmara já assumiu.
- core.vw_bancada_atual passa a usar o partido da cadeira na data quando ele existe.

Revision ID: 0011
Revises: 0010
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

CSV_HISTORICO = [
    "id", "uri", "nome", "nomeEleitoral", "siglaPartido", "uriPartido", "siglaUf", "idLegislatura", "email", "urlFoto",
    "dataHora", "situacao", "condicaoEleitoral", "descricaoStatus",
]

PONTE_CORE = r"""
CREATE OR REPLACE FUNCTION etl.sincronizar_legado() RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    v_fonte smallint := (SELECT id FROM etl.fonte WHERE codigo = 'LEGADO');
    v_curadoria smallint := (SELECT id FROM etl.fonte WHERE codigo = 'CURADORIA');
    v_camara smallint := (SELECT id FROM etl.fonte WHERE codigo = 'CAMARA_API');
    v_senado smallint := (SELECT id FROM etl.fonte WHERE codigo = 'SENADO_API');
    v_tse smallint := (SELECT id FROM etl.fonte WHERE codigo = 'TSE');
    v_execucao bigint;
    v_pessoas int; v_partidos int; v_filiacoes int; v_mandatos int; v_rejeitos int;
BEGIN
    INSERT INTO etl.execucao (fonte_id, estagio) VALUES (v_fonte, 'LEGADO') RETURNING id INTO v_execucao;

    -- ── mídia (logos e fotos) ───────────────────────────────────────────────────────────────────
    INSERT INTO core.midia (tipo, url_origem, fonte_id)
    SELECT DISTINCT 'LOGO_PARTIDO', "logoUrl", v_fonte FROM public.partidos_politicos WHERE nullif(btrim("logoUrl"), '') IS NOT NULL
    ON CONFLICT (tipo, url_origem) DO NOTHING;
    INSERT INTO core.midia (tipo, url_origem, fonte_id)
    SELECT DISTINCT 'LOGO_PARTIDO', s.logo_url, v_curadoria FROM ref.partido_semente s WHERE s.logo_url IS NOT NULL
    ON CONFLICT (tipo, url_origem) DO NOTHING;
    INSERT INTO core.midia (tipo, url_origem, fonte_id)
    SELECT DISTINCT 'FOTO_PESSOA', "fotoUrl", v_fonte FROM public.politicos WHERE nullif(btrim("fotoUrl"), '') IS NOT NULL
    ON CONFLICT (tipo, url_origem) DO NOTHING;

    -- ── partidos ────────────────────────────────────────────────────────────────────────────────
    INSERT INTO core.partido (uid, sigla, nome, numero_eleitoral, data_fundacao, data_extincao, ideologia_texto, lema)
    SELECT p.id, p.sigla, p."nomeCompleto",
           coalesce(p."numeroEleitoral", (SELECT s.numero_eleitoral FROM ref.partido_semente s
                                           WHERE s.sigla_normalizada = ref.normalizar_texto(p.sigla)
                                             AND NOT EXISTS (SELECT 1 FROM public.partidos_politicos p2
                                                              WHERE p2."numeroEleitoral" = s.numero_eleitoral AND p2.id <> p.id))),
           p."dataFundacao", p."dataExtincao",
           coalesce(p.ideologia, (SELECT s.ideologia FROM ref.partido_semente s WHERE s.sigla_normalizada = ref.normalizar_texto(p.sigla))),
           coalesce(p.lema, (SELECT s.lema FROM ref.partido_semente s WHERE s.sigla_normalizada = ref.normalizar_texto(p.sigla)))
    FROM public.partidos_politicos p
    ON CONFLICT (uid) DO UPDATE SET
        sigla = EXCLUDED.sigla, nome = EXCLUDED.nome, numero_eleitoral = EXCLUDED.numero_eleitoral,
        data_fundacao = EXCLUDED.data_fundacao, data_extincao = EXCLUDED.data_extincao,
        ideologia_texto = EXCLUDED.ideologia_texto, lema = EXCLUDED.lema;

    UPDATE core.partido c SET
        logo_midia_id = coalesce(
            (SELECT m.id FROM core.midia m WHERE m.tipo = 'LOGO_PARTIDO' AND m.url_origem = nullif(btrim(l."logoUrl"), '')),
            c.logo_midia_id,
            (SELECT m.id FROM core.midia m JOIN ref.partido_semente s ON s.logo_url = m.url_origem
              WHERE m.tipo = 'LOGO_PARTIDO' AND s.sigla_normalizada = c.sigla_normalizada)),
        cor_hex = coalesce(c.cor_hex, (SELECT s.cor_hex FROM ref.partido_semente s WHERE s.sigla_normalizada = c.sigla_normalizada))
    FROM public.partidos_politicos l WHERE l.id = c.uid;

    INSERT INTO core.partido_alias (partido_id, sigla_alias, tipo)
    SELECT c.id, a.sigla_alias, 'GRAFIA_FONTE'
    FROM ref.partido_alias_semente a
    JOIN core.partido c ON c.sigla_normalizada = a.sigla_destino_normalizada
    WHERE a.sigla_alias_normalizada <> c.sigla_normalizada
      AND NOT EXISTS (SELECT 1 FROM core.partido x WHERE x.sigla_normalizada = a.sigla_alias_normalizada)
    ON CONFLICT (sigla_normalizada) DO NOTHING;

    DELETE FROM core.partido_sucessao WHERE fonte_id = v_fonte;
    INSERT INTO core.partido_sucessao (partido_origem_id, partido_destino_id, tipo, fonte_id)
    SELECT o.id, d.id, 'SUCESSAO', v_fonte
    FROM public.partidos_politicos l
    JOIN core.partido o ON o.uid = l.id JOIN core.partido d ON d.uid = l."partidoSucessorId"
    WHERE l."partidoSucessorId" IS NOT NULL AND l.id <> l."partidoSucessorId"
    ON CONFLICT DO NOTHING;

    DELETE FROM core.partido_posicao_ideologica WHERE fonte_id = v_fonte;
    INSERT INTO core.partido_posicao_ideologica (partido_id, escala, espectro, fonte_id, observacao)
    SELECT c.id, 'ESPECTRO_5', coalesce(l."espectroPolitico"::text, s.espectro), v_fonte,
           'Valor herdado do schema legado, sem fonte primária registrada'
    FROM public.partidos_politicos l JOIN core.partido c ON c.uid = l.id
    LEFT JOIN ref.partido_semente s ON s.sigla_normalizada = c.sigla_normalizada
    WHERE coalesce(l."espectroPolitico"::text, s.espectro) IS NOT NULL;
    INSERT INTO core.partido_posicao_ideologica (partido_id, escala, valor, fonte_id, observacao)
    SELECT c.id, 'ESCALA_1_10', s.escala_valor, v_curadoria,
           'ESCALA_IDEOLOGICA_PADRAO (iple_service.py), atribuída no código a BLS / Power & Zucco / Tarouco & Madeira'
    FROM ref.partido_semente s JOIN core.partido c ON c.sigla_normalizada = s.sigla_normalizada
    WHERE s.escala_valor IS NOT NULL
    ON CONFLICT (partido_id, escala, fonte_id, ano_referencia) DO UPDATE SET valor = EXCLUDED.valor;
    GET DIAGNOSTICS v_partidos = ROW_COUNT;

    -- ── pessoas ─────────────────────────────────────────────────────────────────────────────────
    INSERT INTO core.pessoa (uid, nome_exibicao, data_nascimento, data_falecimento, sexo, municipio_nascimento,
                             uf_nascimento, foto_midia_id, biografia, email, gabinete_sala, gabinete_telefone,
                             redes_sociais, possui_processos_declarados)
    SELECT p.id, p."nomeEleitoral", p."dataNascimento", p."dataFalecimento", p.genero, p."naturalidadeMunicipio",
           (SELECT u.sigla FROM ref.uf u WHERE u.sigla = upper(p."naturalidadeUf")),
           (SELECT m.id FROM core.midia m WHERE m.tipo = 'FOTO_PESSOA' AND m.url_origem = nullif(btrim(p."fotoUrl"), '')),
           p.biografia, p.email, p."gabineteSala", p."gabineteTelefone", p."redesSociais"::jsonb, p."possuiProcessosDeclarados"
    FROM public.politicos p
    ON CONFLICT (uid) DO UPDATE SET
        nome_exibicao = EXCLUDED.nome_exibicao, data_nascimento = EXCLUDED.data_nascimento,
        data_falecimento = EXCLUDED.data_falecimento, sexo = EXCLUDED.sexo,
        municipio_nascimento = EXCLUDED.municipio_nascimento, uf_nascimento = EXCLUDED.uf_nascimento,
        foto_midia_id = EXCLUDED.foto_midia_id, biografia = EXCLUDED.biografia, email = EXCLUDED.email,
        gabinete_sala = EXCLUDED.gabinete_sala, gabinete_telefone = EXCLUDED.gabinete_telefone,
        redes_sociais = EXCLUDED.redes_sociais, possui_processos_declarados = EXCLUDED.possui_processos_declarados;
    GET DIAGNOSTICS v_pessoas = ROW_COUNT;

    INSERT INTO core.pessoa_nome (pessoa_id, tipo, nome, fonte_id)
    SELECT c.id, 'CIVIL', p."nomeCivil", v_fonte FROM public.politicos p JOIN core.pessoa c ON c.uid = p.id
    WHERE nullif(btrim(p."nomeCivil"), '') IS NOT NULL
    ON CONFLICT (pessoa_id, tipo, nome_normalizado) DO NOTHING;
    INSERT INTO core.pessoa_nome (pessoa_id, tipo, nome, fonte_id)
    SELECT c.id, 'ELEITORAL', p."nomeEleitoral", v_fonte FROM public.politicos p JOIN core.pessoa c ON c.uid = p.id
    WHERE nullif(btrim(p."nomeEleitoral"), '') IS NOT NULL
    ON CONFLICT (pessoa_id, tipo, nome_normalizado) DO NOTHING;

    INSERT INTO core.pessoa_identificador (pessoa_id, fonte_id, tipo, valor)
    SELECT c.id, v_camara, 'CAMARA_ID', p."camaraId"::text FROM public.politicos p JOIN core.pessoa c ON c.uid = p.id
    WHERE p."camaraId" IS NOT NULL ON CONFLICT (fonte_id, tipo, valor) DO NOTHING;
    INSERT INTO core.pessoa_identificador (pessoa_id, fonte_id, tipo, valor)
    SELECT c.id, v_senado, 'SENADO_ID', p."senadoId"::text FROM public.politicos p JOIN core.pessoa c ON c.uid = p.id
    WHERE p."senadoId" IS NOT NULL ON CONFLICT (fonte_id, tipo, valor) DO NOTHING;
    INSERT INTO core.pessoa_identificador (pessoa_id, fonte_id, tipo, valor)
    SELECT c.id, v_tse, 'TSE_ID', p."tseId" FROM public.politicos p JOIN core.pessoa c ON c.uid = p.id
    WHERE nullif(btrim(p."tseId"), '') IS NOT NULL ON CONFLICT (fonte_id, tipo, valor) DO NOTHING;

    -- ── eleições ────────────────────────────────────────────────────────────────────────────────
    INSERT INTO core.eleicao (ano, tipo)
    SELECT DISTINCT "anoEleicao", 'GERAL' FROM public.mandatos ON CONFLICT (ano, tipo) DO NOTHING;

    -- ── filiações: um partido por vez; conflitos viram rejeito explícito ────────────────────────
    DELETE FROM core.filiacao WHERE fonte_id = v_fonte;
    DELETE FROM etl.rejeito WHERE recurso = 'filiacao' AND execucao_id IN (SELECT id FROM etl.execucao WHERE fonte_id = v_fonte);

    CREATE TEMP TABLE _fil ON COMMIT DROP AS
    WITH base AS (
        SELECT f.*, row_number() OVER (
                   PARTITION BY f."politicoId", f."dataFiliacao"
                   ORDER BY (EXISTS (SELECT 1 FROM public.mandatos m
                                      WHERE m."politicoId" = f."politicoId" AND m."partidoId" = f."partidoId")) DESC,
                            f."isAtual" DESC, f."dataFiliacao", f.id) AS rn
        FROM public.filiacoes_partidarias f
    )
    SELECT * FROM base;

    INSERT INTO etl.rejeito (execucao_id, recurso, chave_natural, motivo, payload)
    SELECT v_execucao, 'filiacao', f.id::text, 'FILIACAO_MESMO_INICIO_QUE_OUTRA_DA_MESMA_PESSOA',
           jsonb_build_object('politicoId', f."politicoId", 'partidoId', f."partidoId",
                              'dataFiliacao', f."dataFiliacao", 'dataDesfiliacao', f."dataDesfiliacao")
    FROM _fil f WHERE f.rn > 1;

    INSERT INTO core.filiacao (pessoa_id, partido_id, periodo, fim_inferido, motivo_saida, uf, fonte_id)
    SELECT pe.id, pa.id,
           daterange(k."dataFiliacao", k.fim_incl, '[]'),
           k.inferido,
           CASE WHEN k.inferido THEN NULL ELSE k."motivoDesfiliacao"::text END,
           (SELECT u.sigla FROM ref.uf u WHERE u.sigla = upper(k.uf)),
           v_fonte
    FROM (
        SELECT x.*,
               CASE WHEN x.prox IS NOT NULL AND (x."dataDesfiliacao" IS NULL OR x."dataDesfiliacao" >= x.prox)
                    THEN x.prox - 1 ELSE x."dataDesfiliacao" END AS fim_incl,
               (x.prox IS NOT NULL AND (x."dataDesfiliacao" IS NULL OR x."dataDesfiliacao" >= x.prox)) AS inferido
        FROM (SELECT t.*, lead(t."dataFiliacao") OVER (PARTITION BY t."politicoId" ORDER BY t."dataFiliacao") AS prox
              FROM _fil t WHERE t.rn = 1) x
    ) k
    JOIN core.pessoa pe ON pe.uid = k."politicoId"
    JOIN core.partido pa ON pa.uid = k."partidoId";
    GET DIAGNOSTICS v_filiacoes = ROW_COUNT;
    SELECT count(*) INTO v_rejeitos FROM etl.rejeito WHERE execucao_id = v_execucao;

    -- ── mandatos parlamentares/presidenciais: um por (pessoa, cargo, eleição, nº), não um por partido ──
    CREATE TEMP TABLE _man ON COMMIT DROP AS
    SELECT DISTINCT ON (pe.id, cg.id, e.id, m."numeroMandato")
           m.id AS legado_id, pe.id AS pessoa_id, cg.id AS cargo_id, e.id AS eleicao_id, pa.id AS partido_id, m.*
    FROM public.mandatos m
    JOIN core.pessoa pe ON pe.uid = m."politicoId"
    JOIN ref.cargo cg ON cg.codigo = m.cargo::text
    JOIN core.partido pa ON pa.uid = m."partidoId"
    JOIN core.eleicao e ON e.ano = m."anoEleicao" AND e.tipo = 'GERAL'
    LEFT JOIN core.filiacao f ON f.pessoa_id = pe.id AND f.periodo @> m."dataInicio"
    -- mandatos que o ETL da Câmara (histórico por deputado) já assumiu não são mais sobrescritos pelo legado
    WHERE NOT EXISTS (SELECT 1 FROM core.mandato x
                       WHERE x.pessoa_id = pe.id AND x.cargo_id = cg.id AND x.eleicao_id = e.id
                         AND x.numero_mandato = m."numeroMandato" AND x.orgao_nome IS NULL AND x.fonte_id <> v_fonte)
    ORDER BY pe.id, cg.id, e.id, m."numeroMandato", (f.partido_id = pa.id) DESC NULLS LAST, m.id;

    INSERT INTO core.mandato (pessoa_id, cargo_id, circunscricao_id, eleicao_id, partido_id, condicao, numero_mandato,
                              inicio, fim, motivo_encerramento, votos, percentual_votos, coligacao, fonte_id)
    SELECT t.pessoa_id, t.cargo_id,
           (SELECT ci.id FROM ref.circunscricao ci
             WHERE (t."ufJurisdicao" = 'BR' AND ci.tipo = 'BR') OR (t."ufJurisdicao" <> 'BR' AND ci.tipo = 'UF' AND ci.uf = t."ufJurisdicao")),
           t.eleicao_id, t.partido_id,
           CASE WHEN t.status = 'SUPLENTE_EM_EXERCICIO' THEN 'SUPLENTE' ELSE 'TITULAR' END,
           t."numeroMandato", t."dataInicio", t."dataFim",
           CASE t.status WHEN 'CONCLUIDO' THEN 'CONCLUIDO' WHEN 'RENUNCIA' THEN 'RENUNCIA' WHEN 'IMPEACHMENT' THEN 'IMPEACHMENT'
                         WHEN 'CASSADO' THEN 'CASSACAO' WHEN 'FALECIDO' THEN 'FALECIMENTO' END,
           t."totalVotos", t."percentualVotos", t."coligacaoNome", v_fonte
    FROM _man t
    ON CONFLICT ON CONSTRAINT uq_mandato_natural DO UPDATE SET
        circunscricao_id = EXCLUDED.circunscricao_id, partido_id = EXCLUDED.partido_id, condicao = EXCLUDED.condicao,
        inicio = EXCLUDED.inicio, fim = EXCLUDED.fim, motivo_encerramento = EXCLUDED.motivo_encerramento,
        votos = EXCLUDED.votos, percentual_votos = EXCLUDED.percentual_votos, coligacao = EXCLUDED.coligacao;

    DELETE FROM core.mandato_legado WHERE tabela = 'mandatos';
    INSERT INTO core.mandato_legado (legado_id, tabela, mandato_id)
    SELECT m.id, 'mandatos', c.id
    FROM public.mandatos m
    JOIN core.pessoa pe ON pe.uid = m."politicoId"
    JOIN ref.cargo cg ON cg.codigo = m.cargo::text
    JOIN core.eleicao e ON e.ano = m."anoEleicao" AND e.tipo = 'GERAL'
    JOIN core.mandato c ON c.pessoa_id = pe.id AND c.cargo_id = cg.id AND c.eleicao_id = e.id
                       AND c.numero_mandato = m."numeroMandato" AND c.orgao_nome IS NULL;
    DELETE FROM core.mandato c WHERE c.fonte_id = v_fonte AND c.condicao <> 'NOMEADO'
        AND NOT EXISTS (SELECT 1 FROM core.mandato_legado l WHERE l.mandato_id = c.id);

    -- ── ministros (membros_gabinete) viram mandatos de cargo não eletivo ────────────────────────
    INSERT INTO core.pessoa (uid, nome_exibicao)
    SELECT DISTINCT md5('ministro:' || ref.normalizar_texto(g."nomeOcupante"))::uuid, g."nomeOcupante"
    FROM public.membros_gabinete g WHERE g."politicoId" IS NULL
    ON CONFLICT (uid) DO NOTHING;
    INSERT INTO core.pessoa_nome (pessoa_id, tipo, nome, fonte_id)
    SELECT pe.id, 'HISTORICO', g."nomeOcupante", v_fonte
    FROM public.membros_gabinete g
    JOIN core.pessoa pe ON pe.uid = coalesce(g."politicoId", md5('ministro:' || ref.normalizar_texto(g."nomeOcupante"))::uuid)
    ON CONFLICT (pessoa_id, tipo, nome_normalizado) DO NOTHING;

    INSERT INTO core.mandato (pessoa_id, cargo_id, circunscricao_id, condicao, numero_mandato, inicio, fim, orgao_nome,
                              funcao_destaque, nomeado_por_mandato_id, fonte_id)
    SELECT pe.id, (SELECT id FROM ref.cargo WHERE codigo = 'MINISTRO_DE_ESTADO'),
           (SELECT id FROM ref.circunscricao WHERE tipo = 'BR'), 'NOMEADO',
           row_number() OVER (PARTITION BY pe.id, g."ministerioNome" ORDER BY g."dataPosse")::smallint,
           g."dataPosse", g."dataExoneracao", g."ministerioNome", CASE WHEN g."isMinistroEconomia" THEN 'ECONOMIA' END,
           (SELECT l.mandato_id FROM core.mandato_legado l WHERE l.legado_id = g."mandatoId"), v_fonte
    FROM public.membros_gabinete g
    JOIN core.pessoa pe ON pe.uid = coalesce(g."politicoId", md5('ministro:' || ref.normalizar_texto(g."nomeOcupante"))::uuid)
    ON CONFLICT ON CONSTRAINT uq_mandato_natural DO UPDATE SET
        inicio = EXCLUDED.inicio, fim = EXCLUDED.fim, funcao_destaque = EXCLUDED.funcao_destaque,
        nomeado_por_mandato_id = EXCLUDED.nomeado_por_mandato_id;

    DELETE FROM core.mandato_legado WHERE tabela = 'membros_gabinete';
    INSERT INTO core.mandato_legado (legado_id, tabela, mandato_id)
    SELECT g.id, 'membros_gabinete', c.id
    FROM public.membros_gabinete g
    JOIN core.pessoa pe ON pe.uid = coalesce(g."politicoId", md5('ministro:' || ref.normalizar_texto(g."nomeOcupante"))::uuid)
    JOIN core.mandato c ON c.pessoa_id = pe.id AND c.condicao = 'NOMEADO' AND c.orgao_nome = g."ministerioNome"
                       AND c.inicio = g."dataPosse";
    DELETE FROM core.mandato c WHERE c.fonte_id = v_fonte AND c.condicao = 'NOMEADO'
        AND NOT EXISTS (SELECT 1 FROM core.mandato_legado l WHERE l.mandato_id = c.id);

    -- Ministros sem vínculo no legado podem ser a mesma pessoa de um político: nunca se funde por nome,
    -- vira candidata a duplicidade para revisão humana.
    INSERT INTO core.pessoa_candidata_duplicidade (pessoa_a_id, pessoa_b_id, similaridade, motivo)
    SELECT DISTINCT least(na.pessoa_id, nb.pessoa_id), greatest(na.pessoa_id, nb.pessoa_id), 1.0, 'NOME_NORMALIZADO_IGUAL'
    FROM core.pessoa_nome na
    JOIN core.pessoa_nome nb ON nb.nome_normalizado = na.nome_normalizado AND nb.pessoa_id <> na.pessoa_id
    WHERE EXISTS (SELECT 1 FROM core.mandato m WHERE m.pessoa_id = na.pessoa_id AND m.condicao = 'NOMEADO')
      AND NOT EXISTS (SELECT 1 FROM core.mandato m WHERE m.pessoa_id = na.pessoa_id AND m.condicao <> 'NOMEADO')
    ON CONFLICT (pessoa_a_id, pessoa_b_id) DO NOTHING;

    -- ── situações: mandato menos os períodos em que o titular esteve em ministério ──────────────
    DELETE FROM core.mandato_situacao WHERE fonte_id = v_fonte;
    INSERT INTO core.mandato_situacao (mandato_id, situacao, periodo, motivo, fonte_id)
    SELECT s.id, s.situacao, daterange(lower(s.seg), upper(s.seg), '[)'), s.motivo, v_fonte
    FROM (
        SELECT b.id,
               CASE WHEN b.tipo = 'AFASTADO' THEN 'AFASTADO_MINISTERIO'
                    WHEN b.condicao = 'SUPLENTE' THEN 'SUPLENCIA'
                    WHEN b.licenciado THEN 'LICENCA'
                    ELSE 'EXERCICIO' END AS situacao,
               CASE WHEN b.tipo = 'AFASTADO' THEN 'Licenciado para cargo de Ministro de Estado' END AS motivo,
               unnest(b.mr) AS seg
        FROM (
            SELECT c.id, c.condicao, t.tipo,
                   EXISTS (SELECT 1 FROM core.mandato_legado l JOIN public.mandatos x ON x.id = l.legado_id
                            WHERE l.mandato_id = c.id AND x.status = 'LICENCIADO') AS licenciado,
                   CASE t.tipo
                        WHEN 'EXERCICIO' THEN datemultirange(daterange(c.inicio, c.fim, '[]')) - coalesce(mn.mr, '{}'::datemultirange)
                        ELSE datemultirange(daterange(c.inicio, c.fim, '[]')) * coalesce(mn.mr, '{}'::datemultirange)
                   END AS mr
            FROM core.mandato c
            LEFT JOIN LATERAL (
                SELECT range_agg(daterange(m2.inicio, m2.fim, '[]')) AS mr
                FROM core.mandato m2 WHERE m2.pessoa_id = c.pessoa_id AND m2.condicao = 'NOMEADO'
            ) mn ON true
            CROSS JOIN (VALUES ('EXERCICIO'), ('AFASTADO')) AS t(tipo)
            WHERE c.condicao <> 'NOMEADO' AND c.fonte_id = v_fonte
        ) b
    ) s
    WHERE NOT isempty(s.seg);
    GET DIAGNOSTICS v_mandatos = ROW_COUNT;

    UPDATE etl.execucao SET finalizado_em = now(), status = CASE WHEN v_rejeitos > 0 THEN 'COM_ALERTA' ELSE 'OK' END,
        linhas_lidas = (SELECT count(*) FROM public.politicos) + (SELECT count(*) FROM public.mandatos)
                       + (SELECT count(*) FROM public.filiacoes_partidarias),
        linhas_gravadas = v_pessoas + v_filiacoes + v_mandatos, linhas_rejeitadas = v_rejeitos
    WHERE id = v_execucao;

    RETURN jsonb_build_object('execucao_id', v_execucao, 'pessoas', v_pessoas, 'filiacoes', v_filiacoes,
                              'situacoes', v_mandatos, 'rejeitos', v_rejeitos);
END
$fn$;
"""

MERGE_HISTORICO = r"""
CREATE OR REPLACE FUNCTION etl.merge_camara_historico() RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    v_fonte smallint := (SELECT id FROM etl.fonte WHERE codigo = 'CAMARA_API');
    v_exec bigint;
    v_eventos int; v_pessoas int; v_mandatos int; v_intervalos int; v_partidos int; v_rej int;
BEGIN
    INSERT INTO etl.execucao (fonte_id, estagio) VALUES (v_fonte, 'MERGE') RETURNING id INTO v_exec;
    DELETE FROM etl.rejeito WHERE recurso = 'camara_historico';
    SELECT count(*) INTO v_eventos FROM stg.camara_historico;

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
    FROM stg.camara_historico h
    WHERE h."idLegislatura"::int IN (SELECT "id"::int FROM stg.camara_legislatura);
    DELETE FROM _ev WHERE tipo IS NULL;
    ALTER TABLE _ev ADD COLUMN ord int;
    UPDATE _ev SET ord = CASE tipo WHEN 'SAIDA' THEN 1 WHEN 'ENTRADA' THEN 2 ELSE 3 END;

    CREATE TEMP TABLE _leg ON COMMIT DROP AS
    SELECT "id"::int AS id, "dataInicio"::date AS inicio, "dataFim"::date AS fim FROM stg.camara_legislatura;

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
    GET DIAGNOSTICS v_partidos = ROW_COUNT;

    -- ── pessoas: identidade pelo id da fonte, nunca pelo nome ───────────────────────────────────
    INSERT INTO core.midia (tipo, url_origem, fonte_id)
    SELECT DISTINCT 'FOTO_PESSOA', foto, v_fonte FROM _int WHERE foto IS NOT NULL
    ON CONFLICT (tipo, url_origem) DO NOTHING;
    INSERT INTO core.pessoa (uid, nome_exibicao, foto_midia_id)
    SELECT DISTINCT ON (i.id) md5('camara:' || i.id)::uuid, i.nome,
           (SELECT m.id FROM core.midia m WHERE m.tipo = 'FOTO_PESSOA' AND m.url_origem = i.foto)
    FROM _int i
    WHERE NOT EXISTS (SELECT 1 FROM core.pessoa_identificador x
                       WHERE x.fonte_id = v_fonte AND x.tipo = 'CAMARA_ID' AND x.valor = i.id::text)
    ORDER BY i.id, i.inicio DESC
    ON CONFLICT (uid) DO NOTHING;
    GET DIAGNOSTICS v_pessoas = ROW_COUNT;
    INSERT INTO core.pessoa_identificador (pessoa_id, fonte_id, tipo, valor)
    SELECT pe.id, v_fonte, 'CAMARA_ID', x.id::text FROM (SELECT DISTINCT id FROM _int) x
    JOIN core.pessoa pe ON pe.uid = md5('camara:' || x.id)::uuid
    ON CONFLICT DO NOTHING;
    INSERT INTO core.pessoa_nome (pessoa_id, tipo, nome, fonte_id)
    SELECT DISTINCT ON (ident.pessoa_id, ref.normalizar_texto(i.nome)) ident.pessoa_id, 'PARLAMENTAR', i.nome, v_fonte
    FROM _int i
    JOIN core.pessoa_identificador ident ON ident.fonte_id = v_fonte AND ident.tipo = 'CAMARA_ID' AND ident.valor = i.id::text
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
    JOIN core.pessoa_identificador ident ON ident.fonte_id = v_fonte AND ident.tipo = 'CAMARA_ID' AND ident.valor = i.id::text
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
           v_fonte
    FROM _man m
    ON CONFLICT ON CONSTRAINT uq_mandato_natural DO UPDATE SET
        circunscricao_id = EXCLUDED.circunscricao_id, partido_id = EXCLUDED.partido_id, condicao = EXCLUDED.condicao,
        inicio = EXCLUDED.inicio, fim = EXCLUDED.fim, motivo_encerramento = EXCLUDED.motivo_encerramento,
        fonte_id = EXCLUDED.fonte_id;
    GET DIAGNOSTICS v_mandatos = ROW_COUNT;

    ALTER TABLE _man ADD COLUMN mandato_id bigint;
    UPDATE _man m SET mandato_id = c.id FROM core.mandato c
    WHERE c.pessoa_id = m.pessoa_id AND c.eleicao_id = m.eleicao_id AND c.numero_mandato = 1 AND c.orgao_nome IS NULL
      AND c.cargo_id = (SELECT id FROM ref.cargo WHERE codigo = 'DEPUTADO_FEDERAL');

    -- ── situações: exercício/suplência e as lacunas entre eles (licenças e afastamentos) ─────────
    DELETE FROM core.mandato_situacao WHERE mandato_id IN (SELECT mandato_id FROM _man);
    INSERT INTO core.mandato_situacao (mandato_id, situacao, periodo, fonte_id)
    SELECT m.mandato_id, CASE WHEN coalesce(i.cond, 'Titular') = 'Suplente' THEN 'SUPLENCIA' ELSE 'EXERCICIO' END,
           daterange(i.inicio, i.fim_exclusivo, '[)'), v_fonte
    FROM _int i JOIN _man m ON m.id = i.id AND m.leg = i.leg;
    GET DIAGNOSTICS v_intervalos = ROW_COUNT;
    INSERT INTO core.mandato_situacao (mandato_id, situacao, periodo, motivo, fonte_id)
    SELECT g.mandato_id, CASE WHEN g.prox_descr ILIKE '%Ministro%' THEN 'AFASTADO_MINISTERIO' ELSE 'LICENCA' END,
           daterange(g.fim_exclusivo, g.prox_inicio, '[)'), g.prox_descr, v_fonte
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
           daterange(lower(i_p), upper(i_p), '[)'), v_fonte
    FROM _par pp
    JOIN _man m ON m.id = pp.id AND m.leg = pp.leg
    JOIN _int i ON i.id = pp.id AND i.leg = pp.leg
    CROSS JOIN LATERAL (SELECT pp.periodo * daterange(i.inicio, i.fim_exclusivo, '[)') AS i_p) z
    WHERE NOT isempty(z.i_p);

    SELECT count(*) INTO v_rej FROM etl.rejeito WHERE execucao_id = v_exec;
    INSERT INTO etl.verificacao (execucao_id, nome, passou, detalhe)
    VALUES (v_exec, 'camara_historico_cobertura', v_mandatos > 0,
            jsonb_build_object('eventos', v_eventos, 'mandatos', v_mandatos, 'intervalos_exercicio', v_intervalos,
                               'pessoas_criadas', v_pessoas, 'partidos_criados', v_partidos));
    UPDATE etl.execucao SET finalizado_em = now(), status = 'OK', linhas_lidas = v_eventos,
        linhas_gravadas = v_mandatos + v_intervalos, linhas_rejeitadas = v_rej WHERE id = v_exec;
    RETURN jsonb_build_object('execucao_id', v_exec, 'eventos', v_eventos, 'mandatos', v_mandatos,
                              'intervalos_exercicio', v_intervalos, 'pessoas_criadas', v_pessoas,
                              'partidos_criados', v_partidos);
END
$fn$;
"""


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE core.mandato_partido (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            mandato_id bigint NOT NULL REFERENCES core.mandato(id) ON DELETE CASCADE,
            partido_id bigint NOT NULL REFERENCES core.partido(id),
            periodo daterange NOT NULL CHECK (NOT isempty(periodo) AND NOT lower_inf(periodo)),
            fonte_id smallint REFERENCES etl.fonte(id),
            EXCLUDE USING gist (mandato_id WITH =, periodo WITH &&)
        )
        """
    )
    op.execute("CREATE INDEX ix_mandato_partido_partido ON core.mandato_partido (partido_id)")
    colunas = ", ".join(f'"{c}" text' for c in CSV_HISTORICO)
    op.execute(f"CREATE UNLOGGED TABLE stg.camara_historico ({colunas})")
    op.execute('CREATE UNLOGGED TABLE stg.camara_legislatura ("id" text, "dataInicio" text, "dataFim" text)')
    op.execute(PONTE_CORE)
    op.execute(MERGE_HISTORICO)

    op.execute("DROP VIEW core.vw_bancada_atual")
    op.execute(
        """
        CREATE VIEW core.vw_bancada_atual AS
        SELECT coalesce(mp.partido_id, fa.partido_id, m.partido_id) AS partido_id, m.cargo_id,
               count(DISTINCT m.pessoa_id)::int AS total
        FROM core.mandato m
        JOIN ref.cargo c ON c.id = m.cargo_id
        JOIN core.mandato_situacao ms ON ms.mandato_id = m.id AND ms.periodo @> current_date
                                    AND ms.situacao IN ('EXERCICIO', 'SUPLENCIA')
        LEFT JOIN core.mandato_partido mp ON mp.mandato_id = m.id AND mp.periodo @> current_date
        LEFT JOIN core.filiacao fa ON fa.pessoa_id = m.pessoa_id AND upper_inf(fa.periodo)
        WHERE c.codigo IN ('DEPUTADO_FEDERAL', 'SENADOR')
          AND m.condicao IN ('TITULAR', 'SUPLENTE')
          AND m.motivo_encerramento IS NULL
        GROUP BY coalesce(mp.partido_id, fa.partido_id, m.partido_id), m.cargo_id
        """
    )


def downgrade() -> None:
    raise NotImplementedError("Migração de histórico de mandatos (0011) não é reversível.")
