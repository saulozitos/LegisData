"""Ponte do legado adota partido do schema novo que já existe com a mesma sigla.

O ETL em lote cria em `core.partido` partidos extintos ou ausentes do legado (catálogo falso). Quando uma carga do ETL
antigo cria depois o mesmo partido no legado (ex.: PHS), o upsert por `uid` colidia com a unicidade da sigla e a ponte
inteira falhava. Agora a ponte troca o `uid` do partido já existente pelo id do legado antes do upsert (o `uid` não é
chave estrangeira de nenhuma tabela).

A função da ponte está copiada por inteiro nesta revisão: migração aplicada é imutável e não pode depender do texto
de outra revisão.

Revision ID: 0020
Revises: 0019
"""

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

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
    -- partido criado antes pelo ETL em lote com a mesma sigla: adota o id do legado em vez de colidir
    UPDATE core.partido c SET uid = p.id
    FROM public.partidos_politicos p
    WHERE c.sigla = p.sigla AND c.uid <> p.id
      AND NOT EXISTS (SELECT 1 FROM public.partidos_politicos x WHERE x.id = c.uid)
      AND NOT EXISTS (SELECT 1 FROM core.partido y WHERE y.uid = p.id);
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


def upgrade() -> None:
    op.execute(PONTE_CORE)


def downgrade() -> None:
    raise NotImplementedError("Migração 0020 não é reversível.")
