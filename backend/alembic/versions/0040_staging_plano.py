"""Staging plano e fusão sobre tabelas de trabalho: o ETL deixa de gravar o cadastro relacional em `stg`.

Até aqui o ETL resolvia em Python a que pessoa, partido, mandato e proposição cada registro dos arquivos se refere e gravava o
resultado em tabelas relacionais de `stg` (`stg.politicos`, `stg.mandatos`...), que as funções `etl.merge_*` projetavam em
`core` e `leg`. Esta revisão inverte isso, como o plano da Fase 7 pedia:

- **Tabelas planas por arquivo** (`stg.curadoria_*`, `stg.camara_deputado`, `stg.senado_senador`, `stg.tse_filiacao`,
  `stg.camara_proposicao_api`, `stg.senado_proposicao_api`, `stg.*_sessao_plenario`, `stg.*_voto_plenario`,
  `stg.historico_*`): sem chave estrangeira, uma linha por registro do arquivo, com a execução que a carregou. O Python só
  lê o arquivo e copia (`COPY`); nada de consulta ao banco nem de decisão sobre identidade.
- **Resolução em SQL**: `etl.preparar_staging()` monta, na transação da fusão, tabelas temporárias de trabalho (`w_politicos`,
  `w_partidos`, `w_filiacoes`, `w_mandatos`, `w_gabinete`, `w_proposicoes`, `w_sessoes`, `w_votos`) com as mesmas colunas das
  relacionais antigas. A identidade vem de `core`/`leg`: a pessoa é achada pelo identificador oficial (Câmara, Senado) antes
  de criar uma nova, e o `uid` público que já existe nunca muda. `etl.semear_cadastro()` reconstrói em `w_*` o que a fusão já
  gravou (a fusão é função determinística do staging; aqui se faz o caminho inverso), e as funções `preparar_*` aplicam por
  cima o que os arquivos trazem, com as regras que eram do carregador em Python (id oficial, depois nome único; filiação sem
  proveniência é rejeitada; proposição por id da casa; autor por id, nome exato, nome normalizado ou conjunto de palavras,
  sempre só quando único; homônimo nunca se atribui por palpite).
- **`etl.merge_cadastro` e `etl.merge_legislativo`** passam a ler as tabelas de trabalho. Como nas revisões 0036 e 0038, o
  texto de cada função é lido do catálogo e só as origens mudam, então a lógica não muda.
- **As oito tabelas relacionais saem**: `stg.politicos`, `stg.partidos_politicos`, `stg.filiacoes_partidarias`,
  `stg.mandatos`, `stg.membros_gabinete`, `stg.proposicoes`, `stg.sessoes_votacao` e `stg.votos_parlamentares`. As cinco que
  nenhuma carga escreve mais (`stg.proposicoes_autores`, `stg.registros_presenca`, `stg.votacoes_proposicao`,
  `stg.votos_nominais`, `stg.orientacoes_partidarias`) ficam **congeladas**, sem as chaves estrangeiras para as que caíram:
  a fusão ainda as lê, e apagá-las perderia dado de origem que nenhum arquivo atual reproduz (presença e votos do legado).

O rebaixamento recria as oito tabelas relacionais **vazias** (com as chaves estrangeiras, e as das congeladas como `NOT VALID`),
devolve às funções de fusão as origens `stg.*` e remove as tabelas planas e as funções novas. Não restaura as linhas: elas eram
derivadas e `core`/`leg` guardam tudo o que tinham (o deploy tira um `pg_dump` antes, e o ETL recarrega o staging).

Revision ID: 0040
Revises: 0039
"""

import re

from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None

TABELAS_QUE_CAEM = (
    "votos_parlamentares",
    "sessoes_votacao",
    "membros_gabinete",
    "mandatos",
    "filiacoes_partidarias",
    "proposicoes",
    "politicos",
    "partidos_politicos",
)
TRABALHO = {
    "partidos_politicos": "w_partidos",
    "politicos": "w_politicos",
    "filiacoes_partidarias": "w_filiacoes",
    "mandatos": "w_mandatos",
    "membros_gabinete": "w_gabinete",
    "proposicoes": "w_proposicoes",
    "sessoes_votacao": "w_sessoes",
    "votos_parlamentares": "w_votos",
}
_ORIGEM_RE = re.compile(r"\bstg\.(%s)\b" % "|".join(TRABALHO))
FUNCOES_DE_FUSAO = ("merge_cadastro", "merge_legislativo")
DESEMPATE = "ORDER BY (EXISTS (SELECT 1 FROM w_mandatos m"
DESEMPATE_COM_SOBREVIVENTE = 'ORDER BY f."sobrevivente" DESC, (EXISTS (SELECT 1 FROM w_mandatos m'

TABELAS_PLANAS = r"""
-- Tabelas planas do cadastro (uma por arquivo de entrada). Sem chave estrangeira e sem regra de negócio:
-- só o que o arquivo traz, uma linha por registro, com a execução que o carregou.
CREATE TABLE IF NOT EXISTS stg.curadoria_partido (
    execucao_id bigint, linha int, sigla text, nome text, espectro text, ideologia text, lema text, numero int, logo_url text);
CREATE TABLE IF NOT EXISTS stg.curadoria_presidente (
    execucao_id bigint, linha int, id_referencia text, nome_civil text, nome_eleitoral text, data_nascimento date,
    data_falecimento date, genero text, naturalidade_municipio text, naturalidade_uf text, foto_url text,
    partido_sigla text, mandato_numero int, ano_eleicao int, data_inicio date, data_fim date, status_mandato text,
    biografia text);
CREATE TABLE IF NOT EXISTS stg.curadoria_ministro_fazenda (
    execucao_id bigint, linha int, id_referencia text, nome text, inicio date, fim date);
CREATE TABLE IF NOT EXISTS stg.camara_deputado (
    execucao_id bigint, linha int, camara_id int, nome_eleitoral text, nome_civil text, partido_sigla text, uf text,
    foto_url text, id_legislatura int, sexo text, data_nascimento date, uf_nascimento text, municipio_nascimento text,
    email text, gabinete_sala text, gabinete_telefone text, biografia text);
CREATE TABLE IF NOT EXISTS stg.senado_senador (
    execucao_id bigint, linha int, senado_id int, nome_civil text, nome_eleitoral text, partido_sigla text, uf text,
    foto_url text, email text, gabinete_sala text, gabinete_telefone text, mandato_inicio date, mandato_fim date,
    ano_eleicao int, datas_informadas boolean, biografia text);
CREATE TABLE IF NOT EXISTS stg.tse_filiacao (
    execucao_id bigint, linha int, politico_nome text, camara_id int, senado_id int, uf text, partido_sigla text,
    data_filiacao date, data_desfiliacao date, motivo_desfiliacao text, is_atual boolean, fonte text, sintetico boolean);
CREATE TABLE IF NOT EXISTS stg.curadoria_partido_conhecido (
    execucao_id bigint, linha int, sigla_maiuscula text, nome text, espectro text);
CREATE TABLE IF NOT EXISTS stg.camara_proposicao_api (
    execucao_id bigint, linha int, camara_id int, tipo text, numero int, ano int, titulo text, ementa text,
    area_tematica text, data_apresentacao date, reforma_estrutural boolean, iniciativa_executivo boolean,
    autor_nome text, autor_camara_id int, url_oficial text, eixo text, eixos text);
CREATE TABLE IF NOT EXISTS stg.senado_proposicao_api (
    execucao_id bigint, linha int, senado_id int, tipo text, numero int, ano int, titulo text, ementa text,
    area_tematica text, data_apresentacao date, autor_nome text, autor_senado_id int, url_oficial text, eixo text,
    eixos text);
-- Votações do plenário (arquivos sessoes_votacao_*.json e votos_nominais_*.json)
CREATE TABLE IF NOT EXISTS stg.camara_sessao_plenario (
    execucao_id bigint, linha int, sessao_externa_id text, proposicao_camara_id int, data_hora timestamptz,
    titulo_pauta text, descricao text, aprovada boolean, total_sim int, total_nao int, total_abstencao int, total_obstrucao int);
CREATE TABLE IF NOT EXISTS stg.camara_voto_plenario (
    execucao_id bigint, linha int, sessao_externa_id text, deputado_camara_id int, partido_sigla text, voto text);
CREATE TABLE IF NOT EXISTS stg.senado_sessao_plenario (
    execucao_id bigint, linha int, sessao_externa_id text, materia_sigla text, materia_numero int, materia_ano int,
    data_hora timestamptz, titulo_pauta text, descricao text, aprovada boolean, total_sim int, total_nao int,
    total_abstencao int, total_obstrucao int);
CREATE TABLE IF NOT EXISTS stg.senado_voto_plenario (
    execucao_id bigint, linha int, sessao_externa_id text, senador_id int, partido_sigla text, voto text);
-- Parlamentares, sessões e votos dos arquivos anuais votacoes/{camara,senado}_AAAA.json.gz e dos ex-parlamentares
CREATE TABLE IF NOT EXISTS stg.historico_parlamentar (
    execucao_id bigint, linha int, origem text, casa text, ext_id int, nome text, nome_civil text, partido text, uf text,
    foto_url text, biografia text, legislaturas jsonb, mandatos jsonb);
CREATE TABLE IF NOT EXISTS stg.historico_partido (execucao_id bigint, linha int, sigla text);
CREATE TABLE IF NOT EXISTS stg.historico_sessao (
    execucao_id bigint, linha int, casa text, ext_id text, data_hora timestamptz, titulo_pauta text, descricao text,
    aprovada boolean, secreta boolean, orientacao_governo text, total_sim int, total_nao int, total_abstencao int,
    total_obstrucao int, prop_valida boolean, prop_camara_id int, prop_senado_id int, prop_tipo text, prop_numero int,
    prop_ano int, prop_titulo text, prop_ementa text, prop_data date, prop_url_inteiro_teor text, prop_status text,
    prop_autor_nome text, prop_autor_camara_id int, prop_eixo text, prop_eixos text, prop_area text, prop_url_oficial text);
-- CUMULATIVA: um voto por (casa, sessão, parlamentar), o primeiro que chegou. `leg.voto` é refeito inteiro a cada fusão, então
-- um arquivo que sumiu não pode apagar votos que já entraram (como o staging relacional, que acumulava com ON CONFLICT).
CREATE TABLE IF NOT EXISTS stg.historico_voto (
    execucao_id bigint, linha int, casa text NOT NULL, sessao_ext_id text NOT NULL, parlamentar_ext_id int NOT NULL,
    opcao text NOT NULL, partido text);
CREATE UNIQUE INDEX IF NOT EXISTS ux_historico_voto ON stg.historico_voto (casa, sessao_ext_id, parlamentar_ext_id);
"""

FUNCOES_TRABALHO = r"""
CREATE OR REPLACE FUNCTION etl.criar_trabalho() RETURNS void LANGUAGE plpgsql AS $fn$
BEGIN
    CREATE TEMP TABLE IF NOT EXISTS w_partidos (
        "id" uuid NOT NULL, "sigla" varchar(20) NOT NULL, "nomeCompleto" varchar(255) NOT NULL, "numeroEleitoral" integer,
        "dataFundacao" date, "dataExtincao" date, "partidoSucessorId" uuid, "logoUrl" text,
        "created_at" timestamptz NOT NULL DEFAULT now(), "updated_at" timestamptz NOT NULL DEFAULT now(),
        "espectroPolitico" espectropoliticoenum, "ideologia" varchar(255), "lema" varchar(255)) ON COMMIT DROP;
    CREATE TEMP TABLE IF NOT EXISTS w_politicos (
        "id" uuid NOT NULL, "nomeCivil" varchar(255) NOT NULL, "nomeEleitoral" varchar(150) NOT NULL, "tseId" varchar(50),
        "camaraId" integer, "senadoId" integer, "dataNascimento" date, "dataFalecimento" date, "genero" varchar(20),
        "naturalidadeMunicipio" varchar(100), "naturalidadeUf" varchar(2), "fotoUrl" text, "biografia" text,
        "redesSociais" json, "created_at" timestamptz NOT NULL DEFAULT now(), "updated_at" timestamptz NOT NULL DEFAULT now(),
        "email" varchar(255), "gabineteSala" varchar(100), "gabineteTelefone" varchar(50),
        "possuiProcessosDeclarados" boolean NOT NULL DEFAULT false) ON COMMIT DROP;
    CREATE TEMP TABLE IF NOT EXISTS w_filiacoes (
        "id" uuid NOT NULL, "politicoId" uuid NOT NULL, "partidoId" uuid NOT NULL, "dataFiliacao" date NOT NULL,
        "dataDesfiliacao" date, "isAtual" boolean NOT NULL, "motivoDesfiliacao" motivodesfiliacaoenum, "uf" varchar(2),
        "created_at" date NOT NULL,
        -- a que já está em core.filiacao: no empate de início de filiação, quem já ficou continua
        "sobrevivente" boolean NOT NULL DEFAULT false) ON COMMIT DROP;
    CREATE TEMP TABLE IF NOT EXISTS w_mandatos (
        "id" uuid NOT NULL, "politicoId" uuid NOT NULL, "partidoId" uuid NOT NULL, "cargo" cargopoliticoenum NOT NULL,
        "esfera" tipoesferaenum NOT NULL, "ufJurisdicao" varchar(2) NOT NULL, "anoEleicao" integer NOT NULL,
        "numeroMandato" integer NOT NULL, "dataInicio" date NOT NULL, "dataFim" date, "status" statusmandatoenum NOT NULL,
        "coligacaoNome" varchar(255), "totalVotos" integer, "percentualVotos" numeric(5,2),
        "created_at" timestamptz NOT NULL DEFAULT now(), "updated_at" timestamptz NOT NULL DEFAULT now()) ON COMMIT DROP;
    CREATE TEMP TABLE IF NOT EXISTS w_gabinete (
        "id" uuid NOT NULL, "mandatoId" uuid NOT NULL, "politicoId" uuid, "nomeOcupante" varchar(255) NOT NULL,
        "ministerioNome" varchar(200) NOT NULL, "dataPosse" date NOT NULL, "dataExoneracao" date,
        "isMinistroEconomia" boolean NOT NULL) ON COMMIT DROP;
    CREATE TEMP TABLE IF NOT EXISTS w_proposicoes (
        "id" uuid NOT NULL, "idExternoCamara" integer, "idExternoSenado" integer, "tipo" tipoproposicaoenum NOT NULL,
        "numero" integer NOT NULL, "ano" integer NOT NULL, "titulo" varchar(255) NOT NULL, "ementa" text NOT NULL,
        "explicacaoEmenta" text, "areaTematica" varchar(100), "dataApresentacao" date NOT NULL,
        "dataSancaoPromulgacao" date, "statusTramitacao" statustramitacaoenum NOT NULL, "urlTextoOriginal" text,
        "isReformaEstrutural" boolean NOT NULL, "autorPoliticoId" uuid, "iniciativaPoderExecutivo" boolean NOT NULL,
        "created_at" timestamptz NOT NULL DEFAULT now(), "updated_at" timestamptz NOT NULL DEFAULT now(),
        "autorNome" text, "eixoImpacto" varchar(100), "eixosImpacto" varchar(255), "urlOficial" text) ON COMMIT DROP;
    CREATE TEMP TABLE IF NOT EXISTS w_sessoes (
        "id" uuid NOT NULL, "idExterno" varchar(100), "proposicaoId" uuid NOT NULL, "casaLegislativa" casalegislativaenum NOT NULL,
        "dataHoraVotacao" timestamptz NOT NULL, "tituloPauta" varchar(255) NOT NULL, "descricaoDetalhada" text,
        "isVotacaoSecreta" boolean NOT NULL, "aprovada" boolean NOT NULL, "totalSim" integer NOT NULL, "totalNao" integer NOT NULL,
        "totalAbstencao" integer NOT NULL, "totalObstrucao" integer NOT NULL, "created_at" timestamptz NOT NULL DEFAULT now(),
        "orientacaoGoverno" varchar(20), "orientacoesBancadas" text) ON COMMIT DROP;
    CREATE TEMP TABLE IF NOT EXISTS w_votos (
        "id" uuid NOT NULL, "sessaoVotacaoId" uuid NOT NULL, "politicoId" uuid NOT NULL, "partidoId" uuid,
        "voto" votoopcaoenum NOT NULL, "created_at" timestamptz NOT NULL DEFAULT now(),
        UNIQUE ("sessaoVotacaoId", "politicoId")) ON COMMIT DROP;
    CREATE INDEX IF NOT EXISTS w_politicos_cam ON w_politicos ("camaraId");
    CREATE INDEX IF NOT EXISTS w_politicos_sen ON w_politicos ("senadoId");
    CREATE INDEX IF NOT EXISTS w_sessoes_ext ON w_sessoes ("idExterno");
    CREATE INDEX IF NOT EXISTS w_prop_cam ON w_proposicoes ("idExternoCamara");
    CREATE INDEX IF NOT EXISTS w_prop_sen ON w_proposicoes ("idExternoSenado");
    CREATE INDEX IF NOT EXISTS w_prop_chave ON w_proposicoes (tipo, numero, ano);
    TRUNCATE w_partidos, w_politicos, w_filiacoes, w_mandatos, w_gabinete, w_proposicoes, w_sessoes, w_votos;
END
$fn$;
"""

FUNCOES_SEMENTE = r"""
-- Semente: reconstrói em w_* o que o staging relacional guardava, a partir do que a fusão já gravou em core/leg.
-- (A fusão é uma função determinística do staging; aqui se faz o caminho inverso, sem tabela relacional persistente.)
CREATE OR REPLACE FUNCTION etl.semear_cadastro() RETURNS void LANGUAGE plpgsql AS $fn$
DECLARE v_legado smallint := (SELECT id FROM etl.fonte WHERE codigo = 'LEGADO');
BEGIN
    -- partidos
    INSERT INTO w_partidos (id, sigla, "nomeCompleto", "numeroEleitoral", "dataFundacao", "dataExtincao", "logoUrl",
                            "espectroPolitico", ideologia, lema)
    SELECT c.uid, c.sigla, c.nome, c.numero_eleitoral, c.data_fundacao, c.data_extincao,
           (SELECT m.url_origem FROM core.midia m WHERE m.id = c.logo_midia_id),
           (SELECT pi.espectro::espectropoliticoenum FROM core.partido_posicao_ideologica pi
             WHERE pi.partido_id = c.id AND pi.escala = 'ESPECTRO_5' AND pi.fonte_id = v_legado LIMIT 1),
           c.ideologia_texto, c.lema
    FROM core.partido c;

    -- políticos: as pessoas que o cadastro do legado conhece (nome civil gravado por ele)
    INSERT INTO w_politicos (id, "nomeCivil", "nomeEleitoral", "tseId", "camaraId", "senadoId", "dataNascimento",
                             "dataFalecimento", genero, "naturalidadeMunicipio", "naturalidadeUf", "fotoUrl", biografia,
                             "redesSociais", email, "gabineteSala", "gabineteTelefone", "possuiProcessosDeclarados")
    SELECT pe.uid,
           (SELECT n.nome FROM core.pessoa_nome n WHERE n.pessoa_id = pe.id AND n.tipo = 'CIVIL' AND n.fonte_id = v_legado
             ORDER BY n.id LIMIT 1),
           pe.nome_exibicao,
           (SELECT i.valor FROM core.pessoa_identificador i WHERE i.pessoa_id = pe.id AND i.tipo = 'TSE_ID' LIMIT 1),
           (SELECT i.valor::int FROM core.pessoa_identificador i WHERE i.pessoa_id = pe.id AND i.tipo = 'CAMARA_ID' ORDER BY i.id LIMIT 1),
           (SELECT i.valor::int FROM core.pessoa_identificador i WHERE i.pessoa_id = pe.id AND i.tipo = 'SENADO_ID' ORDER BY i.id LIMIT 1),
           pe.data_nascimento, pe.data_falecimento, pe.sexo, pe.municipio_nascimento, pe.uf_nascimento,
           (SELECT m.url_origem FROM core.midia m WHERE m.id = pe.foto_midia_id), pe.biografia,
           pe.redes_sociais::json, pe.email, pe.gabinete_sala, pe.gabinete_telefone, pe.possui_processos_declarados
    FROM core.pessoa pe
    WHERE EXISTS (SELECT 1 FROM core.pessoa_nome n WHERE n.pessoa_id = pe.id AND n.tipo = 'CIVIL' AND n.fonte_id = v_legado);

    -- filiações do legado
    INSERT INTO w_filiacoes (id, "politicoId", "partidoId", "dataFiliacao", "dataDesfiliacao", "isAtual",
                             "motivoDesfiliacao", uf, created_at, sobrevivente)
    SELECT gen_random_uuid(), pe.uid, pa.uid, lower(f.periodo),
           CASE WHEN f.fim_inferido OR upper_inf(f.periodo) THEN NULL ELSE upper(f.periodo) - 1 END,
           upper_inf(f.periodo),
           CASE WHEN f.fim_inferido THEN NULL ELSE f.motivo_saida::motivodesfiliacaoenum END, f.uf, CURRENT_DATE, true
    FROM core.filiacao f JOIN core.pessoa pe ON pe.id = f.pessoa_id JOIN core.partido pa ON pa.id = f.partido_id
    WHERE f.fonte_id = v_legado;
    -- as que a fusão rejeitou (mesmo início que outra da pessoa) só existem em etl.rejeito: voltam para o desempate
    INSERT INTO w_filiacoes (id, "politicoId", "partidoId", "dataFiliacao", "dataDesfiliacao", "isAtual", created_at)
    SELECT r.chave_natural::uuid, (r.payload->>'politicoId')::uuid, (r.payload->>'partidoId')::uuid,
           (r.payload->>'dataFiliacao')::date, (r.payload->>'dataDesfiliacao')::date, false, CURRENT_DATE
    FROM etl.rejeito r JOIN etl.execucao x ON x.id = r.execucao_id
    WHERE r.recurso = 'filiacao' AND x.fonte_id = v_legado
      AND r.motivo = 'FILIACAO_MESMO_INICIO_QUE_OUTRA_DA_MESMA_PESSOA';

    -- mandatos do legado (id = o legado_id que a fusão gravou em core.mandato_legado)
    INSERT INTO w_mandatos (id, "politicoId", "partidoId", cargo, esfera, "ufJurisdicao", "anoEleicao", "numeroMandato",
                            "dataInicio", "dataFim", status, "coligacaoNome", "totalVotos", "percentualVotos")
    SELECT ml.legado_id, pe.uid, pa.uid, cg.codigo::cargopoliticoenum, 'FEDERAL'::tipoesferaenum,
           CASE WHEN ci.tipo = 'BR' THEN 'BR' ELSE ci.uf END, e.ano, m.numero_mandato, m.inicio, m.fim,
           CASE WHEN EXISTS (SELECT 1 FROM core.mandato_situacao s WHERE s.mandato_id = m.id AND s.situacao = 'LICENCA')
                     THEN 'LICENCIADO'
                WHEN m.condicao = 'SUPLENTE' THEN 'SUPLENTE_EM_EXERCICIO'
                WHEN m.motivo_encerramento IS NULL THEN 'TITULAR_ATIVO'
                ELSE CASE m.motivo_encerramento WHEN 'CASSACAO' THEN 'CASSADO' WHEN 'FALECIMENTO' THEN 'FALECIDO'
                          ELSE m.motivo_encerramento END
           END::statusmandatoenum,
           m.coligacao, m.votos, m.percentual_votos
    FROM core.mandato_legado ml
    JOIN core.mandato m ON m.id = ml.mandato_id
    JOIN core.pessoa pe ON pe.id = m.pessoa_id
    JOIN core.partido pa ON pa.id = m.partido_id
    JOIN ref.cargo cg ON cg.id = m.cargo_id
    JOIN ref.circunscricao ci ON ci.id = m.circunscricao_id
    JOIN core.eleicao e ON e.id = m.eleicao_id
    WHERE ml.tabela = 'mandatos';

    -- gabinete
    INSERT INTO w_gabinete (id, "mandatoId", "politicoId", "nomeOcupante", "ministerioNome", "dataPosse", "dataExoneracao",
                            "isMinistroEconomia")
    SELECT ml.legado_id, pml.legado_id,
           CASE WHEN pe.uid = md5('ministro:' || ref.normalizar_texto(
                    coalesce((SELECT n.nome FROM core.pessoa_nome n WHERE n.pessoa_id = pe.id AND n.tipo = 'HISTORICO'
                               ORDER BY n.id LIMIT 1), pe.nome_exibicao)))::uuid THEN NULL ELSE pe.uid END,
           coalesce((SELECT n.nome FROM core.pessoa_nome n WHERE n.pessoa_id = pe.id AND n.tipo = 'HISTORICO'
                      ORDER BY n.id LIMIT 1), pe.nome_exibicao),
           m.orgao_nome, m.inicio, m.fim, coalesce(m.funcao_destaque = 'ECONOMIA', false)
    FROM core.mandato_legado ml
    JOIN core.mandato m ON m.id = ml.mandato_id
    JOIN core.pessoa pe ON pe.id = m.pessoa_id
    JOIN core.mandato_legado pml ON pml.mandato_id = m.nomeado_por_mandato_id AND pml.tabela = 'mandatos'
    WHERE ml.tabela = 'membros_gabinete' AND m.fonte_id = v_legado;

    -- proposições do legado (uid = id do staging)
    INSERT INTO w_proposicoes (id, "idExternoCamara", "idExternoSenado", tipo, numero, ano, titulo, ementa, "explicacaoEmenta",
                               "areaTematica", "dataApresentacao", "dataSancaoPromulgacao", "statusTramitacao",
                               "urlTextoOriginal", "isReformaEstrutural", "autorPoliticoId", "iniciativaPoderExecutivo",
                               "autorNome", "eixoImpacto", "eixosImpacto", "urlOficial")
    SELECT l.uid, l.id_camara, l.id_senado, l.tipo_codigo::tipoproposicaoenum, l.numero, l.ano, l.titulo,
           coalesce(l.ementa, ''), l.explicacao_ementa, l.area_tematica, l.data_apresentacao, l.data_sancao_promulgacao,
           l.status_codigo::statustramitacaoenum, l.url_texto_original, l.reforma_estrutural,
           (SELECT pe.uid FROM core.pessoa pe WHERE pe.id = l.autor_pessoa_id), l.iniciativa_executivo,
           l.autor_nome, l.eixo_impacto, l.eixos_impacto, l.url_oficial
    FROM leg.proposicao l WHERE l.fonte_id = v_legado;

    -- sessões de votação (id = legado_id que a fusão gravou em leg.votacao_legado)
    INSERT INTO w_sessoes (id, "idExterno", "proposicaoId", "casaLegislativa", "dataHoraVotacao", "tituloPauta",
                           "descricaoDetalhada", "isVotacaoSecreta", aprovada, "totalSim", "totalNao", "totalAbstencao",
                           "totalObstrucao", "orientacaoGoverno")
    SELECT vl.legado_id, v.id_externo, lp.uid, cl.codigo::casalegislativaenum, v.data_hora, coalesce(v.titulo_pauta, ''),
           v.descricao, v.secreta, v.aprovada, coalesce(v.total_sim_fonte, 0), coalesce(v.total_nao_fonte, 0),
           coalesce(v.total_abstencao_fonte, 0), coalesce(v.total_obstrucao_fonte, 0), v.orientacao_governo
    FROM leg.votacao_legado vl
    JOIN leg.votacao v ON v.id = vl.votacao_id
    JOIN leg.proposicao lp ON lp.id = v.proposicao_id
    LEFT JOIN ref.casa_legislativa cl ON cl.id = v.casa_id
    WHERE vl.tabela = 'sessoes_votacao';
END
$fn$;
"""

FUNCOES_CADASTRO = r"""
CREATE OR REPLACE FUNCTION etl.nome_tokens(t text) RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $fn$
    SELECT btrim(regexp_replace(
        regexp_replace(
            regexp_replace(
                regexp_replace(
                    regexp_replace(lower(public.unaccent('public.unaccent'::regdictionary, coalesce(t, ''))), '\(.*?\)', ' ', 'g'),
                    '\[.*?\]', ' ', 'g'),
                '\y(senador|senadora|deputado|deputada|federal|estadual|dr|dra|doutor|doutora|professor|professora|prof|pastor|pastora|bispo|delegado|delegada|coronel|capitao|sargento|padre)\y',
                ' ', 'g'),
            '[^a-z0-9\s]', ' ', 'g'),
        '\s+', ' ', 'g'))
$fn$;

-- id do partido pela sigla: exata, depois sem distinguir caixa; sigla vazia é "Sem Partido"
CREATE OR REPLACE FUNCTION etl.partido_id(p_sigla text) RETURNS uuid LANGUAGE plpgsql STABLE AS $fn$
DECLARE s text := btrim(coalesce(p_sigla, '')); r uuid;
BEGIN
    IF s = '' THEN s := 'S.PART.'; END IF;
    SELECT id INTO r FROM w_partidos WHERE sigla = s ORDER BY created_at, id LIMIT 1;
    IF r IS NULL THEN SELECT id INTO r FROM w_partidos WHERE upper(sigla) = upper(s) ORDER BY created_at, id LIMIT 1; END IF;
    IF r IS NULL THEN SELECT uid INTO r FROM core.partido WHERE sigla = s ORDER BY id LIMIT 1; END IF;
    IF r IS NULL THEN SELECT uid INTO r FROM core.partido WHERE upper(sigla) = upper(s) ORDER BY id LIMIT 1; END IF;
    RETURN r;
END
$fn$;

-- partido da sigla, criado em w_partidos se ainda não existe em lugar nenhum (nome e espectro curados quando conhecidos)
CREATE OR REPLACE FUNCTION etl.garantir_partido(p_sigla text) RETURNS uuid LANGUAGE plpgsql AS $fn$
DECLARE r uuid := etl.partido_id(p_sigla); k record;
BEGIN
    IF r IS NOT NULL OR nullif(btrim(coalesce(p_sigla, '')), '') IS NULL THEN RETURN r; END IF;
    SELECT * INTO k FROM stg.curadoria_partido_conhecido WHERE sigla_maiuscula = upper(btrim(p_sigla));
    INSERT INTO w_partidos (id, sigla, "nomeCompleto", "espectroPolitico")
    VALUES (gen_random_uuid(), btrim(p_sigla), coalesce(k.nome, 'Partido ' || btrim(p_sigla)), k.espectro::espectropoliticoenum)
    RETURNING id INTO r;
    RETURN r;
END
$fn$;

CREATE OR REPLACE FUNCTION etl.preparar_cadastro(p_sintetico boolean DEFAULT false, p_nao_verificado boolean DEFAULT false)
RETURNS jsonb LANGUAGE plpgsql AS $fn$
DECLARE
    r record; v_id uuid; v_mand uuid; v_partido uuid;
    c_sint int := 0; c_prov int := 0; c_naocad int := 0; c_sempart int := 0; c_fil_nova int := 0;
    c_dep_nao int := 0; c_sen_nao int := 0;
    v_inicio date; v_fim date;
BEGIN
    PERFORM etl.criar_trabalho();
    PERFORM etl.semear_cadastro();

    -- ── partidos: só os que a carga cura (os demais de core.partido são achados por etl.partido_id, sem serem regravados) ───────────────────
    DELETE FROM w_partidos w
     WHERE NOT EXISTS (SELECT 1 FROM stg.curadoria_partido k WHERE upper(k.sigla) = upper(w.sigla))
       AND NOT EXISTS (SELECT 1 FROM core.partido_posicao_ideologica pi JOIN core.partido cp ON cp.id = pi.partido_id
                        WHERE cp.uid = w.id AND pi.fonte_id = (SELECT id FROM etl.fonte WHERE codigo = 'LEGADO'));
    DROP TABLE IF EXISTS _p, _nome_unico, _f;
    CREATE TEMP TABLE _p ON COMMIT DROP AS SELECT * FROM stg.curadoria_partido ORDER BY linha;
    UPDATE _p SET numero = NULL
     WHERE numero IS NOT NULL
       AND (EXISTS (SELECT 1 FROM w_partidos o WHERE o."numeroEleitoral" = _p.numero AND upper(o.sigla) <> upper(_p.sigla))
            OR EXISTS (SELECT 1 FROM core.partido o WHERE o.numero_eleitoral = _p.numero AND upper(o.sigla) <> upper(_p.sigla)));
    UPDATE w_partidos s SET
        "espectroPolitico" = coalesce(p.espectro::espectropoliticoenum, s."espectroPolitico"),
        ideologia = coalesce(p.ideologia, s.ideologia), lema = coalesce(p.lema, s.lema),
        "logoUrl" = coalesce(p.logo_url, s."logoUrl"), "numeroEleitoral" = coalesce(p.numero, s."numeroEleitoral"),
        updated_at = now()
      FROM _p p
     WHERE upper(s.sigla) = upper(p.sigla)
       AND (coalesce(p.espectro::espectropoliticoenum, s."espectroPolitico"), coalesce(p.ideologia, s.ideologia),
            coalesce(p.lema, s.lema), coalesce(p.logo_url, s."logoUrl"), coalesce(p.numero, s."numeroEleitoral"))
           IS DISTINCT FROM (s."espectroPolitico", s.ideologia, s.lema, s."logoUrl", s."numeroEleitoral");
    INSERT INTO w_partidos (id, sigla, "nomeCompleto", "espectroPolitico", ideologia, lema, "numeroEleitoral", "logoUrl")
    SELECT gen_random_uuid(), p.sigla, p.nome, p.espectro::espectropoliticoenum, p.ideologia, p.lema, p.numero, p.logo_url
      FROM _p p
     WHERE NOT EXISTS (SELECT 1 FROM w_partidos s WHERE upper(s.sigla) = upper(p.sigla));

    -- ── políticos: presidentes (sequencial: o segundo mandato do mesmo nome acha o primeiro) ─────────────────────────
    FOR r IN SELECT * FROM stg.curadoria_presidente ORDER BY linha LOOP
        IF NOT EXISTS (SELECT 1 FROM w_politicos x WHERE x."nomeCivil" = r.nome_civil OR x."nomeEleitoral" = r.nome_eleitoral) THEN
            INSERT INTO w_politicos (id, "nomeCivil", "nomeEleitoral", "dataNascimento", "dataFalecimento", genero,
                                     "naturalidadeMunicipio", "naturalidadeUf", "fotoUrl", biografia)
            VALUES (gen_random_uuid(), r.nome_civil, r.nome_eleitoral, r.data_nascimento, r.data_falecimento, r.genero,
                    r.naturalidade_municipio, r.naturalidade_uf, r.foto_url, r.biografia);
        END IF;
    END LOOP;

    -- deputados já cadastrados em core com o id oficial, mas fora da semente (cadastro de outra carga): entram pela identidade
    INSERT INTO w_politicos (id, "nomeCivil", "nomeEleitoral", "camaraId", "dataNascimento", "dataFalecimento", genero,
                             "naturalidadeMunicipio", "naturalidadeUf", "fotoUrl", biografia, "redesSociais", email,
                             "gabineteSala", "gabineteTelefone", "possuiProcessosDeclarados")
    SELECT pe.uid, coalesce((SELECT n.nome FROM core.pessoa_nome n WHERE n.pessoa_id = pe.id AND n.tipo = 'CIVIL' ORDER BY n.id LIMIT 1), pe.nome_exibicao),
           pe.nome_exibicao, i.valor::int, pe.data_nascimento, pe.data_falecimento, pe.sexo, pe.municipio_nascimento,
           pe.uf_nascimento, (SELECT m.url_origem FROM core.midia m WHERE m.id = pe.foto_midia_id), pe.biografia,
           pe.redes_sociais::json, pe.email, pe.gabinete_sala, pe.gabinete_telefone, pe.possui_processos_declarados
      FROM stg.camara_deputado d
      JOIN core.pessoa_identificador i ON i.tipo = 'CAMARA_ID' AND i.valor = d.camara_id::text
      JOIN core.pessoa pe ON pe.id = i.pessoa_id
     WHERE NOT EXISTS (SELECT 1 FROM w_politicos w WHERE w."camaraId" = d.camara_id)
       AND NOT EXISTS (SELECT 1 FROM w_politicos w WHERE w.id = pe.uid);
    INSERT INTO w_politicos (id, "nomeCivil", "nomeEleitoral", "senadoId", "dataNascimento", "dataFalecimento", genero,
                             "naturalidadeMunicipio", "naturalidadeUf", "fotoUrl", biografia, "redesSociais", email,
                             "gabineteSala", "gabineteTelefone", "possuiProcessosDeclarados")
    SELECT pe.uid, coalesce((SELECT n.nome FROM core.pessoa_nome n WHERE n.pessoa_id = pe.id AND n.tipo = 'CIVIL' ORDER BY n.id LIMIT 1), pe.nome_exibicao),
           pe.nome_exibicao, i.valor::int, pe.data_nascimento, pe.data_falecimento, pe.sexo, pe.municipio_nascimento,
           pe.uf_nascimento, (SELECT m.url_origem FROM core.midia m WHERE m.id = pe.foto_midia_id), pe.biografia,
           pe.redes_sociais::json, pe.email, pe.gabinete_sala, pe.gabinete_telefone, pe.possui_processos_declarados
      FROM stg.senado_senador s
      JOIN core.pessoa_identificador i ON i.tipo = 'SENADO_ID' AND i.valor = s.senado_id::text
      JOIN core.pessoa pe ON pe.id = i.pessoa_id
     WHERE NOT EXISTS (SELECT 1 FROM w_politicos w WHERE w."senadoId" = s.senado_id)
       AND NOT EXISTS (SELECT 1 FROM w_politicos w WHERE w.id = pe.uid);

    -- deputados já conhecidos: limpa contato sintético de versões antigas e completa só o que está vazio
    UPDATE w_politicos p SET
        "gabineteTelefone" = CASE
            WHEN p."gabineteSala" ~ '^(Anexo IV, Gabinete \d+|Ala Filinto Müller, Gabinete \d{2})$'
                 AND p."gabineteTelefone" ~ '^\(61\) (3215-5\d{3}|3303-\d{4})$' THEN NULL ELSE p."gabineteTelefone" END
      FROM stg.camara_deputado d WHERE p."camaraId" = d.camara_id;
    UPDATE w_politicos p SET
        email = CASE WHEN p.email ~ '^(dep|sen)\.\d+@(camara|senado)\.leg\.br$' THEN NULL ELSE p.email END,
        "gabineteSala" = CASE WHEN p."gabineteSala" ~ '^(Anexo IV, Gabinete \d+|Ala Filinto Müller, Gabinete \d{2})$' THEN NULL ELSE p."gabineteSala" END
      FROM stg.camara_deputado d WHERE p."camaraId" = d.camara_id;
    UPDATE w_politicos p SET
        email = CASE WHEN nullif(p.email, '') IS NULL AND nullif(d.email, '') IS NOT NULL THEN d.email ELSE p.email END,
        "gabineteSala" = CASE WHEN nullif(p."gabineteSala", '') IS NULL AND nullif(d.gabinete_sala, '') IS NOT NULL THEN d.gabinete_sala ELSE p."gabineteSala" END,
        "gabineteTelefone" = CASE WHEN nullif(p."gabineteTelefone", '') IS NULL AND nullif(d.gabinete_telefone, '') IS NOT NULL THEN d.gabinete_telefone ELSE p."gabineteTelefone" END,
        "naturalidadeUf" = CASE WHEN nullif(p."naturalidadeUf", '') IS NULL AND nullif(d.uf_nascimento, '') IS NOT NULL THEN d.uf_nascimento ELSE p."naturalidadeUf" END,
        "naturalidadeMunicipio" = CASE WHEN nullif(p."naturalidadeMunicipio", '') IS NULL AND nullif(d.municipio_nascimento, '') IS NOT NULL THEN d.municipio_nascimento ELSE p."naturalidadeMunicipio" END,
        genero = CASE WHEN nullif(p.genero, '') IS NULL AND nullif(d.sexo, '') IS NOT NULL THEN d.sexo ELSE p.genero END,
        "dataNascimento" = CASE WHEN p."dataNascimento" IS NULL AND d.data_nascimento IS NOT NULL THEN d.data_nascimento ELSE p."dataNascimento" END,
        updated_at = now()
      FROM stg.camara_deputado d WHERE p."camaraId" = d.camara_id;
    INSERT INTO w_politicos (id, "nomeCivil", "nomeEleitoral", "camaraId", "fotoUrl", "dataNascimento", genero,
                             "naturalidadeUf", "naturalidadeMunicipio", email, "gabineteSala", "gabineteTelefone", biografia)
    SELECT gen_random_uuid(), coalesce(nullif(d.nome_civil, ''), d.nome_eleitoral), d.nome_eleitoral, d.camara_id, d.foto_url,
           d.data_nascimento, d.sexo, d.uf_nascimento, d.municipio_nascimento, d.email, d.gabinete_sala,
           d.gabinete_telefone, d.biografia
      FROM stg.camara_deputado d
     WHERE NOT EXISTS (SELECT 1 FROM w_politicos w WHERE w."camaraId" = d.camara_id) ORDER BY d.linha;

    -- senadores
    UPDATE w_politicos p SET
        email = CASE WHEN p.email ~ '^(dep|sen)\.\d+@(camara|senado)\.leg\.br$' THEN NULL ELSE p.email END,
        "gabineteSala" = CASE WHEN p."gabineteSala" ~ '^(Anexo IV, Gabinete \d+|Ala Filinto Müller, Gabinete \d{2})$' THEN NULL ELSE p."gabineteSala" END,
        "gabineteTelefone" = CASE
            WHEN p."gabineteSala" ~ '^(Anexo IV, Gabinete \d+|Ala Filinto Müller, Gabinete \d{2})$'
                 AND p."gabineteTelefone" ~ '^\(61\) (3215-5\d{3}|3303-\d{4})$' THEN NULL ELSE p."gabineteTelefone" END
      FROM stg.senado_senador s WHERE p."senadoId" = s.senado_id;
    UPDATE w_politicos p SET
        email = CASE WHEN nullif(p.email, '') IS NULL AND nullif(s.email, '') IS NOT NULL THEN s.email ELSE p.email END,
        updated_at = now()
      FROM stg.senado_senador s WHERE p."senadoId" = s.senado_id;
    INSERT INTO w_politicos (id, "nomeCivil", "nomeEleitoral", "senadoId", "fotoUrl", email, "gabineteSala",
                             "gabineteTelefone", biografia)
    SELECT gen_random_uuid(), coalesce(nullif(s.nome_civil, ''), s.nome_eleitoral), s.nome_eleitoral, s.senado_id,
           s.foto_url, s.email, s.gabinete_sala, s.gabinete_telefone, s.biografia
      FROM stg.senado_senador s
     WHERE NOT EXISTS (SELECT 1 FROM w_politicos w WHERE w."senadoId" = s.senado_id) ORDER BY s.linha;


    -- ── filiações ─────────────────────────────────────────────────────────────────────────────────────────────────
    CREATE TEMP TABLE _nome_unico ON COMMIT DROP AS
    SELECT etl.nome_tokens("nomeEleitoral") AS k, (array_agg(id))[1] AS id
      FROM w_politicos WHERE nullif("nomeEleitoral", '') IS NOT NULL AND etl.nome_tokens("nomeEleitoral") <> ''
     GROUP BY 1 HAVING count(DISTINCT id) = 1;
    CREATE TEMP TABLE _f ON COMMIT DROP AS
    SELECT t.*,
           CASE WHEN t.sintetico AND NOT p_sintetico THEN 'SINTETICO'
                WHEN nullif(t.fonte, '') IS NULL AND NOT p_nao_verificado THEN 'SEM_PROVENIENCIA' END AS rej,
           coalesce((SELECT id FROM w_politicos x WHERE x."camaraId" = t.camara_id LIMIT 1),
                    (SELECT id FROM w_politicos x WHERE x."senadoId" = t.senado_id LIMIT 1),
                    (SELECT u.id FROM _nome_unico u WHERE u.k = etl.nome_tokens(t.politico_nome))) AS pol,
           NULL::uuid AS partido
      FROM stg.tse_filiacao t;
    SELECT count(*) FILTER (WHERE rej = 'SINTETICO'), count(*) FILTER (WHERE rej = 'SEM_PROVENIENCIA'),
           count(*) FILTER (WHERE rej IS NULL AND pol IS NULL)
      INTO c_sint, c_prov, c_naocad FROM _f;
    -- os partidos citados só em filiações aceitas são criados antes (um por sigla, na grafia da primeira citação)
    FOR r IN SELECT DISTINCT ON (upper(btrim(partido_sigla))) partido_sigla FROM _f
              WHERE rej IS NULL AND pol IS NOT NULL AND nullif(btrim(coalesce(partido_sigla, '')), '') IS NOT NULL
              ORDER BY upper(btrim(partido_sigla)), linha LOOP
        PERFORM etl.garantir_partido(r.partido_sigla);
    END LOOP;
    UPDATE _f SET partido = etl.partido_id(partido_sigla) WHERE rej IS NULL AND pol IS NOT NULL;
    SELECT count(*) INTO c_sempart FROM _f WHERE rej IS NULL AND pol IS NOT NULL AND partido IS NULL;
    INSERT INTO w_filiacoes (id, "politicoId", "partidoId", "dataFiliacao", "dataDesfiliacao", "isAtual",
                             "motivoDesfiliacao", uf, created_at)
    SELECT gen_random_uuid(), x.pol, x.partido, x.dt, x.data_desfiliacao, x.is_atual, x.motivo::motivodesfiliacaoenum, x.uf,
           CURRENT_DATE
      FROM (SELECT DISTINCT ON (f.pol, f.partido, coalesce(f.data_filiacao, DATE '2023-02-01')) f.*,
                   coalesce(f.data_filiacao, DATE '2023-02-01') AS dt, f.motivo_desfiliacao AS motivo
              FROM _f f WHERE f.rej IS NULL AND f.pol IS NOT NULL AND f.partido IS NOT NULL
             ORDER BY f.pol, f.partido, coalesce(f.data_filiacao, DATE '2023-02-01'), f.linha) x
     WHERE NOT EXISTS (SELECT 1 FROM w_filiacoes e WHERE e."politicoId" = x.pol AND e."partidoId" = x.partido AND e."dataFiliacao" = x.dt);
    GET DIAGNOSTICS c_fil_nova = ROW_COUNT;

    -- ── mandatos presidenciais e ministros da Fazenda ──────────────────────────────────────────────────────────────
    FOR r IN SELECT * FROM stg.curadoria_presidente ORDER BY linha LOOP
        v_id := (SELECT x.id FROM w_politicos x WHERE x."nomeCivil" = r.nome_civil OR x."nomeEleitoral" = r.nome_eleitoral
                  ORDER BY x.created_at, x.id LIMIT 1);
        v_partido := coalesce(etl.partido_id(r.partido_sigla), etl.partido_id('MDB'));
        v_mand := (SELECT m.id FROM w_mandatos m WHERE m."politicoId" = v_id AND m."anoEleicao" = r.ano_eleicao
                      AND m."numeroMandato" = r.mandato_numero LIMIT 1);
        IF v_mand IS NULL THEN
            v_mand := gen_random_uuid();
            INSERT INTO w_mandatos (id, "politicoId", "partidoId", cargo, esfera, "ufJurisdicao", "anoEleicao",
                                    "numeroMandato", "dataInicio", "dataFim", status)
            VALUES (v_mand, v_id, v_partido, 'PRESIDENTE', 'FEDERAL', 'BR', r.ano_eleicao, r.mandato_numero, r.data_inicio,
                    r.data_fim, CASE WHEN r.status_mandato IN ('IMPEACHMENT', 'TITULAR_ATIVO') THEN r.status_mandato
                                     ELSE 'CONCLUIDO' END::statusmandatoenum);
        END IF;
        INSERT INTO w_gabinete (id, "mandatoId", "nomeOcupante", "ministerioNome", "dataPosse", "dataExoneracao",
                                "isMinistroEconomia")
        SELECT gen_random_uuid(), v_mand, g.nome, 'Ministério da Fazenda', g.inicio, g.fim, true
          FROM stg.curadoria_ministro_fazenda g
         WHERE g.id_referencia = r.id_referencia
           AND NOT EXISTS (SELECT 1 FROM w_gabinete e WHERE e."mandatoId" = v_mand AND e."nomeOcupante" = g.nome
                              AND e."dataPosse" = g.inicio);
    END LOOP;

    -- deputados: o mandato segue a legislatura informada (57ª => eleição 2022, 2023-02-01 a 2027-01-31)
    INSERT INTO w_mandatos (id, "politicoId", "partidoId", cargo, esfera, "ufJurisdicao", "anoEleicao", "numeroMandato",
                            "dataInicio", "dataFim", status)
    SELECT gen_random_uuid(), p.id, coalesce(etl.partido_id(d.partido_sigla), etl.partido_id('S.PART.')),
           'DEPUTADO_FEDERAL', 'FEDERAL', coalesce(nullif(d.uf, ''), 'DF'), l.inicio_ano - 1, 1,
           make_date(l.inicio_ano, 2, 1), make_date(l.inicio_ano + 4, 1, 31), 'TITULAR_ATIVO'
      FROM stg.camara_deputado d
      JOIN w_politicos p ON p."camaraId" = d.camara_id
      CROSS JOIN LATERAL (SELECT 2023 + 4 * (coalesce(d.id_legislatura, 57) - 57) AS inicio_ano) l
     WHERE NOT EXISTS (SELECT 1 FROM w_mandatos m WHERE m."politicoId" = p.id AND m."anoEleicao" = l.inicio_ano - 1
                          AND m.cargo = 'DEPUTADO_FEDERAL')
     ORDER BY d.linha;

    -- senadores: as datas vêm da fonte; sem mandato de senador cria, com mandato só corrige quando a fonte informa
    INSERT INTO w_mandatos (id, "politicoId", "partidoId", cargo, esfera, "ufJurisdicao", "anoEleicao", "numeroMandato",
                            "dataInicio", "dataFim", status)
    SELECT gen_random_uuid(), p.id, coalesce(etl.partido_id(s.partido_sigla), etl.partido_id('S.PART.')), 'SENADOR',
           'FEDERAL', coalesce(nullif(s.uf, ''), 'DF'), s.ano_eleicao, 1, s.mandato_inicio, s.mandato_fim, 'TITULAR_ATIVO'
      FROM stg.senado_senador s
      JOIN w_politicos p ON p."senadoId" = s.senado_id
     WHERE NOT EXISTS (SELECT 1 FROM w_mandatos m WHERE m."politicoId" = p.id AND m.cargo = 'SENADOR')
     ORDER BY s.linha;
    UPDATE w_mandatos m SET "dataInicio" = s.mandato_inicio, "dataFim" = s.mandato_fim, "anoEleicao" = s.ano_eleicao,
                            updated_at = now()
      FROM stg.senado_senador s JOIN w_politicos p ON p."senadoId" = s.senado_id
     WHERE s.datas_informadas AND m."politicoId" = p.id AND m.cargo = 'SENADOR'
       AND m.id = (SELECT m2.id FROM w_mandatos m2 WHERE m2."politicoId" = p.id AND m2.cargo = 'SENADOR'
                    ORDER BY m2."dataInicio" DESC, m2.id LIMIT 1)
       AND (m."dataInicio", m."dataFim", m."anoEleicao") IS DISTINCT FROM (s.mandato_inicio, s.mandato_fim, s.ano_eleicao);

    RETURN jsonb_build_object('filiacoes_novas', c_fil_nova, 'rejeitos', jsonb_build_object(
            'SINTETICO', c_sint, 'SEM_PROVENIENCIA', c_prov, 'NAO_CADASTRADO', c_naocad, 'SEM_PARTIDO', c_sempart));
END
$fn$;
"""

FUNCOES_PROPOSICOES = r"""
-- pessoa do autor: id oficial, depois nome (exato, normalizado, conjunto de palavras), sempre só quando é único
CREATE OR REPLACE FUNCTION etl.autor_pessoa(p_nome text, p_camara int, p_senado int) RETURNS uuid LANGUAGE plpgsql STABLE AS $fn$
DECLARE r uuid; v_nome text := btrim(coalesce(p_nome, '')); v_primeiro text; v_norm text; v_toks text;
BEGIN
    IF p_camara IS NOT NULL AND p_camara <> 0 THEN
        SELECT id INTO r FROM w_politicos WHERE "camaraId" = p_camara LIMIT 1;
        IF r IS NOT NULL THEN RETURN r; END IF;
    END IF;
    IF p_senado IS NOT NULL AND p_senado <> 0 THEN
        SELECT id INTO r FROM w_politicos WHERE "senadoId" = p_senado LIMIT 1;
        IF r IS NOT NULL THEN RETURN r; END IF;
    END IF;
    IF nullif(p_nome, '') IS NULL THEN RETURN NULL; END IF;
    v_primeiro := btrim(split_part(regexp_replace(p_nome, ';', ',', 'g'), ',', 1));
    SELECT id INTO r FROM _a_exato WHERE k = v_nome;
    IF r IS NOT NULL THEN RETURN r; END IF;
    SELECT id INTO r FROM _a_exato WHERE k = v_primeiro;
    IF r IS NOT NULL THEN RETURN r; END IF;
    v_norm := etl.nome_tokens(v_primeiro);
    IF v_norm = '' OR v_norm IN ('poder executivo', 'comissao parlamentares', 'comissao', 'mesa diretora', 'senado federal') THEN
        RETURN NULL;
    END IF;
    SELECT id INTO r FROM _a_norm WHERE k = v_norm;
    IF r IS NOT NULL THEN RETURN r; END IF;
    v_toks := etl.nome_conjunto(v_norm);
    IF array_length(string_to_array(v_toks, ' '), 1) >= 2 THEN
        SELECT id INTO r FROM _a_tokens WHERE k = v_toks;
    END IF;
    RETURN r;
END
$fn$;

-- palavras distintas do nome já normalizado, em ordem: dois nomes com as mesmas palavras dão o mesmo texto
CREATE OR REPLACE FUNCTION etl.nome_conjunto(p_norm text) RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $fn$
    SELECT coalesce(string_agg(t, ' ' ORDER BY t), '') FROM (SELECT DISTINCT unnest(string_to_array(p_norm, ' ')) AS t) x WHERE t <> ''
$fn$;

CREATE OR REPLACE FUNCTION etl.preparar_proposicoes() RETURNS jsonb LANGUAGE plpgsql AS $fn$
DECLARE v_legado smallint := (SELECT id FROM etl.fonte WHERE codigo = 'LEGADO'); c_novas int := 0; v_n int;
BEGIN
    -- proposições de outras cargas (mesmo id da casa) entram pela identidade, com o uid que já têm
    INSERT INTO w_proposicoes (id, "idExternoCamara", "idExternoSenado", tipo, numero, ano, titulo, ementa, "explicacaoEmenta",
                               "areaTematica", "dataApresentacao", "dataSancaoPromulgacao", "statusTramitacao",
                               "urlTextoOriginal", "isReformaEstrutural", "autorPoliticoId", "iniciativaPoderExecutivo",
                               "autorNome", "eixoImpacto", "eixosImpacto", "urlOficial")
    -- tipo e situação fora do enum do staging só existem em proposições de outras cargas, que a fusão não regrava
    SELECT l.uid, l.id_camara, l.id_senado,
           (CASE WHEN l.tipo_codigo = ANY (enum_range(NULL::tipoproposicaoenum)::text[]) THEN l.tipo_codigo ELSE 'PL' END)::tipoproposicaoenum,
           l.numero, l.ano, l.titulo, coalesce(l.ementa, ''),
           l.explicacao_ementa, l.area_tematica, l.data_apresentacao, l.data_sancao_promulgacao,
           (CASE WHEN l.status_codigo = ANY (enum_range(NULL::statustramitacaoenum)::text[]) THEN l.status_codigo ELSE 'EM_TRAMITACAO' END)::statustramitacaoenum,
           l.url_texto_original, l.reforma_estrutural,
           (SELECT pe.uid FROM core.pessoa pe WHERE pe.id = l.autor_pessoa_id), l.iniciativa_executivo, l.autor_nome,
           l.eixo_impacto, l.eixos_impacto, l.url_oficial
      FROM leg.proposicao l
     WHERE (l.id_camara IN (SELECT camara_id FROM stg.camara_proposicao_api)
            OR l.id_senado IN (SELECT senado_id FROM stg.senado_proposicao_api))
       AND NOT EXISTS (SELECT 1 FROM w_proposicoes w WHERE w.id = l.uid);

    -- índices de nome para o autor (sobre os políticos já preparados)
    DROP TABLE IF EXISTS _a_nomes, _a_exato, _a_norm, _a_tokens;
    CREATE TEMP TABLE _a_nomes ON COMMIT DROP AS
    SELECT id, btrim(n) AS nome FROM w_politicos, LATERAL (VALUES ("nomeEleitoral"), ("nomeCivil")) v(n) WHERE nullif(n, '') IS NOT NULL;
    CREATE TEMP TABLE _a_exato ON COMMIT DROP AS
    SELECT nome AS k, (array_agg(id))[1] AS id FROM _a_nomes GROUP BY nome HAVING count(DISTINCT id) = 1;
    CREATE TEMP TABLE _a_norm ON COMMIT DROP AS
    SELECT etl.nome_tokens(nome) AS k, (array_agg(id))[1] AS id FROM _a_nomes
     WHERE etl.nome_tokens(nome) <> '' GROUP BY 1 HAVING count(DISTINCT id) = 1;
    CREATE TEMP TABLE _a_tokens ON COMMIT DROP AS
    SELECT etl.nome_conjunto(etl.nome_tokens(nome)) AS k, (array_agg(id))[1] AS id FROM _a_nomes
     WHERE array_length(string_to_array(etl.nome_conjunto(etl.nome_tokens(nome)), ' '), 1) >= 2
     GROUP BY 1 HAVING count(DISTINCT id) = 1;

    -- Câmara: o que já existe recebe o enriquecimento; o novo é criado
    UPDATE w_proposicoes w SET
        "eixoImpacto" = f.eixo, "eixosImpacto" = f.eixos,
        "areaTematica" = CASE WHEN nullif(f.area_tematica, '') IS NOT NULL THEN f.area_tematica ELSE w."areaTematica" END,
        "urlOficial" = CASE WHEN nullif(w."urlOficial", '') IS NULL OR w."urlOficial" NOT LIKE '%camara.leg.br%' THEN f.url_oficial ELSE w."urlOficial" END,
        "autorNome" = CASE WHEN nullif(f.autor_nome, '') IS NOT NULL THEN f.autor_nome ELSE w."autorNome" END,
        "autorPoliticoId" = CASE WHEN nullif(f.autor_nome, '') IS NOT NULL THEN etl.autor_pessoa(f.autor_nome, f.autor_camara_id, NULL) ELSE w."autorPoliticoId" END,
        updated_at = now()
      FROM stg.camara_proposicao_api f WHERE w."idExternoCamara" = f.camara_id;
    INSERT INTO w_proposicoes (id, "idExternoCamara", tipo, numero, ano, titulo, ementa, "areaTematica", "dataApresentacao",
                               "statusTramitacao", "isReformaEstrutural", "iniciativaPoderExecutivo", "eixoImpacto",
                               "eixosImpacto", "autorNome", "autorPoliticoId", "urlOficial")
    SELECT gen_random_uuid(), f.camara_id, f.tipo::tipoproposicaoenum, f.numero, f.ano, f.titulo, f.ementa, f.area_tematica,
           coalesce(f.data_apresentacao, make_date(f.ano, 1, 1)), 'EM_TRAMITACAO', f.reforma_estrutural,
           f.iniciativa_executivo, f.eixo, f.eixos, f.autor_nome, etl.autor_pessoa(f.autor_nome, f.autor_camara_id, NULL),
           f.url_oficial
      FROM stg.camara_proposicao_api f
     WHERE NOT EXISTS (SELECT 1 FROM w_proposicoes w WHERE w."idExternoCamara" = f.camara_id) ORDER BY f.linha;
    GET DIAGNOSTICS c_novas = ROW_COUNT;

    -- Senado: identificado só por idExternoSenado
    UPDATE w_proposicoes w SET
        "eixoImpacto" = f.eixo, "eixosImpacto" = f.eixos,
        "areaTematica" = CASE WHEN nullif(f.area_tematica, '') IS NOT NULL THEN f.area_tematica ELSE w."areaTematica" END,
        "urlOficial" = CASE WHEN nullif(w."urlOficial", '') IS NULL THEN f.url_oficial ELSE w."urlOficial" END,
        "autorNome" = CASE WHEN nullif(f.autor_nome, '') IS NOT NULL THEN f.autor_nome ELSE w."autorNome" END,
        "autorPoliticoId" = CASE WHEN nullif(f.autor_nome, '') IS NOT NULL THEN etl.autor_pessoa(f.autor_nome, NULL, f.autor_senado_id) ELSE w."autorPoliticoId" END,
        updated_at = now()
      FROM stg.senado_proposicao_api f WHERE w."idExternoSenado" = f.senado_id;
    INSERT INTO w_proposicoes (id, "idExternoSenado", tipo, numero, ano, titulo, ementa, "areaTematica", "dataApresentacao",
                               "statusTramitacao", "isReformaEstrutural", "iniciativaPoderExecutivo", "eixoImpacto",
                               "eixosImpacto", "autorNome", "autorPoliticoId", "urlOficial")
    SELECT gen_random_uuid(), f.senado_id, f.tipo::tipoproposicaoenum, f.numero, f.ano, f.titulo, f.ementa, f.area_tematica,
           coalesce(f.data_apresentacao, make_date(f.ano, 1, 1)), 'EM_TRAMITACAO', false, false, f.eixo, f.eixos, f.autor_nome,
           etl.autor_pessoa(f.autor_nome, NULL, f.autor_senado_id), f.url_oficial
      FROM stg.senado_proposicao_api f
     WHERE NOT EXISTS (SELECT 1 FROM w_proposicoes w WHERE w."idExternoSenado" = f.senado_id) ORDER BY f.linha;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    c_novas := c_novas + v_n;

    -- completa a URL oficial que faltar (sem inventar eixo nem área)
    UPDATE w_proposicoes SET "urlOficial" = CASE
            WHEN "idExternoCamara" IS NOT NULL THEN 'https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao=' || "idExternoCamara"
            ELSE 'https://www25.senado.leg.br/web/atividade/materias/-/materia/' || "idExternoSenado" END
     WHERE nullif("urlOficial", '') IS NULL AND ("idExternoCamara" IS NOT NULL OR "idExternoSenado" IS NOT NULL);
    RETURN jsonb_build_object('proposicoes_novas', c_novas);
END
$fn$;
"""

FUNCOES_VOTACOES = r"""
CREATE OR REPLACE FUNCTION etl.legislatura_inicio(p_leg int) RETURNS date LANGUAGE sql IMMUTABLE AS $fn$
    SELECT make_date(2023 + 4 * (p_leg - 57), 2, 1)
$fn$;

-- proposição pelo id da casa: a do trabalho ou, se for de outra carga, a de leg (importada com o uid que já tem)
CREATE OR REPLACE FUNCTION etl.achar_proposicao(p_casa text, p_ext int) RETURNS uuid LANGUAGE plpgsql AS $fn$
DECLARE r uuid;
BEGIN
    IF p_ext IS NULL THEN RETURN NULL; END IF;
    IF p_casa = 'CAMARA' THEN SELECT id INTO r FROM w_proposicoes WHERE "idExternoCamara" = p_ext;
    ELSE SELECT id INTO r FROM w_proposicoes WHERE "idExternoSenado" = p_ext; END IF;
    IF r IS NOT NULL THEN RETURN r; END IF;
    INSERT INTO w_proposicoes (id, "idExternoCamara", "idExternoSenado", tipo, numero, ano, titulo, ementa, "explicacaoEmenta",
                               "areaTematica", "dataApresentacao", "dataSancaoPromulgacao", "statusTramitacao",
                               "urlTextoOriginal", "isReformaEstrutural", "autorPoliticoId", "iniciativaPoderExecutivo",
                               "autorNome", "eixoImpacto", "eixosImpacto", "urlOficial")
    SELECT l.uid, l.id_camara, l.id_senado,
           (CASE WHEN l.tipo_codigo = ANY (enum_range(NULL::tipoproposicaoenum)::text[]) THEN l.tipo_codigo ELSE 'PL' END)::tipoproposicaoenum,
           l.numero, l.ano, l.titulo, coalesce(l.ementa, ''), l.explicacao_ementa, l.area_tematica, l.data_apresentacao,
           l.data_sancao_promulgacao,
           (CASE WHEN l.status_codigo = ANY (enum_range(NULL::statustramitacaoenum)::text[]) THEN l.status_codigo ELSE 'EM_TRAMITACAO' END)::statustramitacaoenum,
           l.url_texto_original, l.reforma_estrutural, (SELECT pe.uid FROM core.pessoa pe WHERE pe.id = l.autor_pessoa_id),
           l.iniciativa_executivo, l.autor_nome, l.eixo_impacto, l.eixos_impacto, l.url_oficial
      FROM leg.proposicao l
     WHERE ((p_casa = 'CAMARA' AND l.id_camara = p_ext) OR (p_casa <> 'CAMARA' AND l.id_senado = p_ext))
       AND NOT EXISTS (SELECT 1 FROM w_proposicoes w WHERE w.id = l.uid)
     LIMIT 1
    RETURNING id INTO r;
    RETURN r;
END
$fn$;

-- cria o político (ou vincula o id da casa a um de mesmo nome único que ainda não o tinha) e garante os mandatos do arquivo
CREATE OR REPLACE FUNCTION etl.garantir_historicos(p_origem text) RETURNS jsonb LANGUAGE plpgsql AS $fn$
DECLARE
    r record; m jsonb; v_pol uuid; v_cand uuid; v_leg int; v_ini date; v_fim date; v_part uuid; v_chave int;
    c_criados int := 0; c_vinculados int := 0; c_mandatos int := 0; c_sem_partido int := 0; v_sup boolean;
BEGIN
    -- nomes únicos (civil e eleitoral) entre quem ainda não tem o id da casa: a foto do início da chamada
    DROP TABLE IF EXISTS _h_nome_cam; DROP TABLE IF EXISTS _h_nome_sen;
    CREATE TEMP TABLE _h_nome_cam ON COMMIT DROP AS
    SELECT etl.nome_tokens(n) AS k, (array_agg(id))[1] AS id FROM w_politicos, LATERAL (VALUES ("nomeEleitoral"), ("nomeCivil")) v(n)
     WHERE "camaraId" IS NULL AND nullif(n, '') IS NOT NULL AND etl.nome_tokens(n) <> '' GROUP BY 1 HAVING count(DISTINCT id) = 1;
    CREATE TEMP TABLE _h_nome_sen ON COMMIT DROP AS
    SELECT etl.nome_tokens(n) AS k, (array_agg(id))[1] AS id FROM w_politicos, LATERAL (VALUES ("nomeEleitoral"), ("nomeCivil")) v(n)
     WHERE "senadoId" IS NULL AND nullif(n, '') IS NOT NULL AND etl.nome_tokens(n) <> '' GROUP BY 1 HAVING count(DISTINCT id) = 1;

    FOR r IN SELECT * FROM stg.historico_parlamentar WHERE origem = p_origem ORDER BY casa DESC, linha LOOP
        IF r.casa = 'CAMARA' THEN
            SELECT id INTO v_pol FROM w_politicos WHERE "camaraId" = r.ext_id;
            IF v_pol IS NULL THEN
                IF nullif(r.nome, '') IS NULL THEN CONTINUE; END IF;
                SELECT n.id INTO v_cand FROM _h_nome_cam n WHERE n.k = etl.nome_tokens(r.nome);
                IF v_cand IS NOT NULL AND EXISTS (SELECT 1 FROM w_politicos WHERE id = v_cand AND "camaraId" IS NULL) THEN
                    UPDATE w_politicos SET "camaraId" = r.ext_id, updated_at = now() WHERE id = v_cand;
                    v_pol := v_cand; c_vinculados := c_vinculados + 1;
                ELSE
                    v_pol := gen_random_uuid();
                    INSERT INTO w_politicos (id, "nomeCivil", "nomeEleitoral", "camaraId", "fotoUrl", biografia)
                    VALUES (v_pol, coalesce(nullif(r.nome_civil, ''), r.nome), r.nome, r.ext_id, r.foto_url, r.biografia);
                    c_criados := c_criados + 1;
                END IF;
            END IF;
            FOR v_leg IN SELECT jsonb_array_elements_text(coalesce(r.legislaturas, '[]'::jsonb))::int LOOP
                v_ini := etl.legislatura_inicio(v_leg); v_fim := make_date(extract(year FROM v_ini)::int + 4, 1, 31);
                IF EXISTS (SELECT 1 FROM w_mandatos WHERE "politicoId" = v_pol AND cargo = 'DEPUTADO_FEDERAL'
                              AND "anoEleicao" = extract(year FROM v_ini)::int - 1) THEN CONTINUE; END IF;
                v_part := coalesce(etl.garantir_partido(nullif(btrim(coalesce(r.partido, '')), '')), etl.garantir_partido('S.PART.'));
                IF v_part IS NULL THEN c_sem_partido := c_sem_partido + 1; CONTINUE; END IF;
                INSERT INTO w_mandatos (id, "politicoId", "partidoId", cargo, esfera, "ufJurisdicao", "anoEleicao",
                                        "numeroMandato", "dataInicio", "dataFim", status)
                VALUES (gen_random_uuid(), v_pol, v_part, 'DEPUTADO_FEDERAL', 'FEDERAL', left(coalesce(nullif(r.uf, ''), 'DF'), 2),
                        extract(year FROM v_ini)::int - 1, 1, v_ini, v_fim,
                        CASE WHEN v_fim < CURRENT_DATE THEN 'CONCLUIDO' ELSE 'TITULAR_ATIVO' END::statusmandatoenum);
                c_mandatos := c_mandatos + 1;
            END LOOP;
        ELSE
            SELECT id INTO v_pol FROM w_politicos WHERE "senadoId" = r.ext_id;
            IF v_pol IS NULL THEN
                IF nullif(r.nome, '') IS NULL THEN CONTINUE; END IF;
                SELECT n.id INTO v_cand FROM _h_nome_sen n WHERE n.k = etl.nome_tokens(r.nome);
                IF v_cand IS NOT NULL AND EXISTS (SELECT 1 FROM w_politicos WHERE id = v_cand AND "senadoId" IS NULL) THEN
                    UPDATE w_politicos SET "senadoId" = r.ext_id, updated_at = now() WHERE id = v_cand;
                    v_pol := v_cand; c_vinculados := c_vinculados + 1;
                ELSE
                    v_pol := gen_random_uuid();
                    INSERT INTO w_politicos (id, "nomeCivil", "nomeEleitoral", "senadoId", "fotoUrl", biografia)
                    VALUES (v_pol, coalesce(nullif(r.nome_civil, ''), r.nome), r.nome, r.ext_id, r.foto_url, r.biografia);
                    c_criados := c_criados + 1;
                END IF;
            END IF;
            FOR m IN SELECT jsonb_array_elements(coalesce(r.mandatos, '[]'::jsonb)) LOOP
                v_ini := nullif(m->>'inicio', '')::date; v_fim := nullif(m->>'fim', '')::date;
                IF v_ini IS NULL THEN CONTINUE; END IF;
                v_chave := extract(year FROM v_ini)::int - 1;
                IF EXISTS (SELECT 1 FROM w_mandatos WHERE "politicoId" = v_pol AND cargo = 'SENADOR'
                              AND abs("anoEleicao" - v_chave) <= 4) THEN CONTINUE; END IF;
                v_part := coalesce(etl.garantir_partido(nullif(btrim(coalesce(r.partido, '')), '')), etl.garantir_partido('S.PART.'));
                IF v_part IS NULL THEN c_sem_partido := c_sem_partido + 1; CONTINUE; END IF;
                v_sup := lower(coalesce(m->>'participacao', '')) LIKE '%suplente%';
                INSERT INTO w_mandatos (id, "politicoId", "partidoId", cargo, esfera, "ufJurisdicao", "anoEleicao",
                                        "numeroMandato", "dataInicio", "dataFim", status)
                VALUES (gen_random_uuid(), v_pol, v_part, 'SENADOR', 'FEDERAL', left(coalesce(nullif(m->>'uf', ''), 'DF'), 2),
                        v_chave, 1, v_ini, v_fim,
                        CASE WHEN v_sup THEN 'SUPLENTE_EM_EXERCICIO'
                             WHEN v_fim < CURRENT_DATE THEN 'CONCLUIDO' ELSE 'TITULAR_ATIVO' END::statusmandatoenum);
                c_mandatos := c_mandatos + 1;
            END LOOP;
        END IF;
    END LOOP;
    RETURN jsonb_build_object('politicos_criados', c_criados, 'politicos_vinculados', c_vinculados, 'mandatos_criados', c_mandatos);
END
$fn$;
"""

FUNCOES_SESSOES = r"""
-- criar_trabalho passa a exigir um voto por (sessão, político): o primeiro que chega fica
-- (ver 10_trabalho.sql: w_votos tem UNIQUE ("sessaoVotacaoId", "politicoId"))

CREATE OR REPLACE FUNCTION etl.preparar_votacoes_plenario() RETURNS jsonb LANGUAGE plpgsql AS $fn$
DECLARE
    s record; v_prop uuid; v_sess uuid; v_casa casalegislativaenum; c_desc int := 0;
    t_sim int; t_nao int; t_abs int; t_obs int; v_tem boolean;
BEGIN
    -- Câmara
    FOR s IN SELECT * FROM stg.camara_sessao_plenario ORDER BY linha LOOP
        v_prop := etl.achar_proposicao('CAMARA', s.proposicao_camara_id);
        IF v_prop IS NULL THEN c_desc := c_desc + 1; CONTINUE; END IF;
        IF s.data_hora IS NULL THEN CONTINUE; END IF;
        SELECT count(*) > 0, count(*) FILTER (WHERE voto = 'SIM'), count(*) FILTER (WHERE voto = 'NAO'),
               count(*) FILTER (WHERE voto = 'ABSTENCAO'), count(*) FILTER (WHERE voto = 'OBSTRUCAO')
          INTO v_tem, t_sim, t_nao, t_abs, t_obs
          FROM stg.camara_voto_plenario WHERE sessao_externa_id = s.sessao_externa_id;
        IF NOT v_tem THEN t_sim := s.total_sim; t_nao := s.total_nao; t_abs := s.total_abstencao; t_obs := s.total_obstrucao; END IF;
        SELECT id, "casaLegislativa" INTO v_sess, v_casa FROM w_sessoes WHERE "idExterno" = s.sessao_externa_id;
        IF v_sess IS NOT NULL AND v_casa <> 'CAMARA_DOS_DEPUTADOS' THEN CONTINUE; END IF;
        IF v_sess IS NULL THEN
            v_sess := gen_random_uuid();
            INSERT INTO w_sessoes (id, "idExterno", "proposicaoId", "casaLegislativa", "dataHoraVotacao", "tituloPauta",
                                   "descricaoDetalhada", "isVotacaoSecreta", aprovada, "totalSim", "totalNao", "totalAbstencao",
                                   "totalObstrucao")
            VALUES (v_sess, s.sessao_externa_id, v_prop, 'CAMARA_DOS_DEPUTADOS', s.data_hora, left(s.titulo_pauta, 255),
                    s.descricao, false, coalesce(s.aprovada, false), t_sim, t_nao, t_abs, t_obs);
        ELSE
            UPDATE w_sessoes SET "totalSim" = t_sim, "totalNao" = t_nao, "totalAbstencao" = t_abs, "totalObstrucao" = t_obs
             WHERE id = v_sess;
        END IF;
    END LOOP;
    -- Senado: a proposição sai de (tipo, número, ano) exatos; sem correspondência única a sessão é descartada
    FOR s IN SELECT * FROM stg.senado_sessao_plenario ORDER BY linha LOOP
        v_prop := NULL;
        IF nullif(s.materia_sigla, '') IS NOT NULL AND s.materia_numero IS NOT NULL AND s.materia_ano IS NOT NULL
           AND upper(s.materia_sigla) = ANY (enum_range(NULL::tipoproposicaoenum)::text[]) THEN
            IF (SELECT count(*) FROM w_proposicoes WHERE tipo::text = upper(s.materia_sigla) AND numero = s.materia_numero
                   AND ano = s.materia_ano) = 1 THEN
                SELECT id INTO v_prop FROM w_proposicoes WHERE tipo::text = upper(s.materia_sigla) AND numero = s.materia_numero
                   AND ano = s.materia_ano;
            ELSIF (SELECT count(*) FROM w_proposicoes WHERE tipo::text = upper(s.materia_sigla) AND numero = s.materia_numero
                      AND ano = s.materia_ano AND "idExternoCamara" IS NOT NULL) = 1 THEN
                SELECT id INTO v_prop FROM w_proposicoes WHERE tipo::text = upper(s.materia_sigla) AND numero = s.materia_numero
                   AND ano = s.materia_ano AND "idExternoCamara" IS NOT NULL;
            END IF;
        END IF;
        IF v_prop IS NULL THEN c_desc := c_desc + 1; CONTINUE; END IF;
        IF s.data_hora IS NULL THEN CONTINUE; END IF;
        SELECT count(*) > 0, count(*) FILTER (WHERE voto = 'SIM'), count(*) FILTER (WHERE voto = 'NAO'),
               count(*) FILTER (WHERE voto = 'ABSTENCAO'), count(*) FILTER (WHERE voto = 'OBSTRUCAO')
          INTO v_tem, t_sim, t_nao, t_abs, t_obs
          FROM stg.senado_voto_plenario WHERE sessao_externa_id = s.sessao_externa_id;
        IF NOT v_tem THEN t_sim := s.total_sim; t_nao := s.total_nao; t_abs := s.total_abstencao; t_obs := s.total_obstrucao; END IF;
        SELECT id, "casaLegislativa" INTO v_sess, v_casa FROM w_sessoes WHERE "idExterno" = s.sessao_externa_id;
        IF v_sess IS NOT NULL AND v_casa <> 'SENADO_FEDERAL' THEN CONTINUE; END IF;
        IF v_sess IS NULL THEN
            v_sess := gen_random_uuid();
            INSERT INTO w_sessoes (id, "idExterno", "proposicaoId", "casaLegislativa", "dataHoraVotacao", "tituloPauta",
                                   "descricaoDetalhada", "isVotacaoSecreta", aprovada, "totalSim", "totalNao", "totalAbstencao",
                                   "totalObstrucao")
            VALUES (v_sess, s.sessao_externa_id, v_prop, 'SENADO_FEDERAL', s.data_hora, left(s.titulo_pauta, 255),
                    s.descricao, false, coalesce(s.aprovada, false), t_sim, t_nao, t_abs, t_obs);
        ELSE
            UPDATE w_sessoes SET "totalSim" = t_sim, "totalNao" = t_nao, "totalAbstencao" = t_abs, "totalObstrucao" = t_obs
             WHERE id = v_sess;
        END IF;
    END LOOP;
    RETURN jsonb_build_object('sessoes_descartadas', c_desc);
END
$fn$;

CREATE OR REPLACE FUNCTION etl.preparar_votacoes_historico() RETURNS jsonb LANGUAGE plpgsql AS $fn$
DECLARE
    s record; r record; v_prop uuid; v_sess uuid; v_casa casalegislativaenum; v_tipo text; c_novas int := 0; c_atual int := 0;
    c_desc int := 0; c_props int := 0; v_pol jsonb; v_ext int; v_livre uuid; v_cand int; v_livres int;
BEGIN
    CREATE TEMP TABLE IF NOT EXISTS _cache_prop (casa text, chave text, id uuid) ON COMMIT DROP;
    TRUNCATE _cache_prop;
    -- os partidos da lista de cada arquivo são criados mesmo sem voto (como antes)
    FOR r IN SELECT sigla FROM stg.historico_partido ORDER BY linha LOOP PERFORM etl.garantir_partido(r.sigla); END LOOP;
    PERFORM etl.garantir_historicos('VOTACOES');

    FOR s IN SELECT * FROM stg.historico_sessao ORDER BY linha LOOP
        v_prop := NULL;
        IF s.prop_valida THEN
            v_ext := CASE WHEN s.casa = 'CAMARA' THEN s.prop_camara_id ELSE s.prop_senado_id END;
            SELECT id INTO v_prop FROM _cache_prop
             WHERE casa = s.casa AND chave = coalesce(v_ext::text, s.prop_tipo || '/' || s.prop_numero || '/' || s.prop_ano);
            IF v_prop IS NULL THEN
                IF v_ext IS NOT NULL THEN v_prop := etl.achar_proposicao(s.casa, v_ext); END IF;
                IF v_prop IS NULL AND s.prop_ano >= 2019 THEN
                    SELECT count(*), count(*) FILTER (WHERE CASE WHEN s.casa = 'CAMARA' THEN "idExternoCamara" IS NULL
                                                                 ELSE "idExternoSenado" IS NULL END)
                      INTO v_cand, v_livres
                      FROM w_proposicoes WHERE tipo::text = s.prop_tipo AND numero = s.prop_numero AND ano = s.prop_ano;
                    IF v_cand = 1 AND v_livres = 1 THEN
                        SELECT id INTO v_prop FROM w_proposicoes WHERE tipo::text = s.prop_tipo AND numero = s.prop_numero AND ano = s.prop_ano;
                        IF v_ext IS NOT NULL THEN
                            IF s.casa = 'CAMARA' THEN UPDATE w_proposicoes SET "idExternoCamara" = v_ext WHERE id = v_prop;
                            ELSE UPDATE w_proposicoes SET "idExternoSenado" = v_ext WHERE id = v_prop; END IF;
                        END IF;
                    END IF;
                END IF;
                IF v_prop IS NULL THEN
                    v_prop := gen_random_uuid();
                    INSERT INTO w_proposicoes (id, "idExternoCamara", "idExternoSenado", tipo, numero, ano, titulo, ementa,
                                               "areaTematica", "dataApresentacao", "statusTramitacao", "urlTextoOriginal",
                                               "isReformaEstrutural", "iniciativaPoderExecutivo", "autorNome", "autorPoliticoId",
                                               "eixoImpacto", "eixosImpacto", "urlOficial")
                    SELECT v_prop, CASE WHEN s.casa = 'CAMARA' THEN v_ext END, CASE WHEN s.casa <> 'CAMARA' THEN v_ext END,
                           s.prop_tipo::tipoproposicaoenum, s.prop_numero, s.prop_ano, s.prop_titulo, s.prop_ementa, s.prop_area,
                           coalesce(s.prop_data, make_date(s.prop_ano, 1, 1)), s.prop_status::statustramitacaoenum,
                           s.prop_url_inteiro_teor, false, false, s.prop_autor_nome,
                           (SELECT id FROM w_politicos WHERE "camaraId" = s.prop_autor_camara_id LIMIT 1),
                           s.prop_eixo, s.prop_eixos, s.prop_url_oficial;
                    c_props := c_props + 1;
                END IF;
                INSERT INTO _cache_prop VALUES (s.casa, coalesce(v_ext::text, s.prop_tipo || '/' || s.prop_numero || '/' || s.prop_ano), v_prop);
            END IF;
        END IF;
        IF s.data_hora IS NULL OR v_prop IS NULL THEN c_desc := c_desc + 1; CONTINUE; END IF;
        SELECT id, "casaLegislativa" INTO v_sess, v_casa FROM w_sessoes WHERE "idExterno" = s.ext_id;
        IF v_sess IS NOT NULL AND v_casa <> (CASE WHEN s.casa = 'CAMARA' THEN 'CAMARA_DOS_DEPUTADOS' ELSE 'SENADO_FEDERAL' END)::casalegislativaenum THEN
            c_desc := c_desc + 1; CONTINUE;
        END IF;
        IF v_sess IS NULL THEN
            v_sess := gen_random_uuid();
            INSERT INTO w_sessoes (id, "idExterno", "proposicaoId", "casaLegislativa", "dataHoraVotacao", "tituloPauta",
                                   "descricaoDetalhada", "isVotacaoSecreta", aprovada, "totalSim", "totalNao", "totalAbstencao",
                                   "totalObstrucao", "orientacaoGoverno")
            VALUES (v_sess, s.ext_id, v_prop, (CASE WHEN s.casa = 'CAMARA' THEN 'CAMARA_DOS_DEPUTADOS' ELSE 'SENADO_FEDERAL' END)::casalegislativaenum,
                    s.data_hora, s.titulo_pauta, s.descricao, coalesce(s.secreta, false), coalesce(s.aprovada, false),
                    s.total_sim, s.total_nao, s.total_abstencao, s.total_obstrucao, s.orientacao_governo);
            c_novas := c_novas + 1;
        ELSE
            UPDATE w_sessoes SET "totalSim" = s.total_sim, "totalNao" = s.total_nao, "totalAbstencao" = s.total_abstencao,
                                 "totalObstrucao" = s.total_obstrucao, "orientacaoGoverno" = s.orientacao_governo
             WHERE id = v_sess;
            c_atual := c_atual + 1;
        END IF;
    END LOOP;

    RETURN jsonb_build_object('sessoes_novas', c_novas, 'sessoes_atualizadas', c_atual, 'sessoes_descartadas', c_desc,
                              'proposicoes_criadas', c_props);
END
$fn$;

-- w_votos a partir de stg.historico_voto (plenário e histórico juntos): a sessão acha-se por código e casa em w_sessoes
-- (a semeada ou a criada nesta rodada) e o parlamentar pelo id da casa; o primeiro voto do par vale
CREATE OR REPLACE FUNCTION etl.montar_votos() RETURNS bigint LANGUAGE plpgsql AS $fn$
DECLARE v_n bigint; v_total bigint := 0;
BEGIN
    DROP TABLE IF EXISTS _sigla;
    CREATE TEMP TABLE _sigla ON COMMIT DROP AS
    SELECT s AS sigla, etl.partido_id(s) AS id
      FROM (SELECT DISTINCT partido AS s FROM stg.historico_voto WHERE nullif(partido, '') IS NOT NULL) x;
    CREATE INDEX ON _sigla (sigla);
    INSERT INTO w_votos (id, "sessaoVotacaoId", "politicoId", "partidoId", voto)
    SELECT gen_random_uuid(), s.id, p.id, g.id, v.opcao::votoopcaoenum
      FROM stg.historico_voto v
      JOIN w_sessoes s ON s."idExterno" = v.sessao_ext_id AND s."casaLegislativa" = 'CAMARA_DOS_DEPUTADOS'
      JOIN w_politicos p ON p."camaraId" = v.parlamentar_ext_id
      LEFT JOIN _sigla g ON g.sigla = v.partido
     WHERE v.casa = 'CAMARA' AND v.opcao = ANY (enum_range(NULL::votoopcaoenum)::text[])
    ON CONFLICT ("sessaoVotacaoId", "politicoId") DO NOTHING;
    GET DIAGNOSTICS v_n = ROW_COUNT; v_total := v_total + v_n;
    INSERT INTO w_votos (id, "sessaoVotacaoId", "politicoId", "partidoId", voto)
    SELECT gen_random_uuid(), s.id, p.id, g.id, v.opcao::votoopcaoenum
      FROM stg.historico_voto v
      JOIN w_sessoes s ON s."idExterno" = v.sessao_ext_id AND s."casaLegislativa" = 'SENADO_FEDERAL'
      JOIN w_politicos p ON p."senadoId" = v.parlamentar_ext_id
      LEFT JOIN _sigla g ON g.sigla = v.partido
     WHERE v.casa = 'SENADO' AND v.opcao = ANY (enum_range(NULL::votoopcaoenum)::text[])
    ON CONFLICT ("sessaoVotacaoId", "politicoId") DO NOTHING;
    GET DIAGNOSTICS v_n = ROW_COUNT; v_total := v_total + v_n;
    RETURN v_total;
END
$fn$;

CREATE OR REPLACE FUNCTION etl.preparar_staging(p_sintetico boolean DEFAULT false, p_nao_verificado boolean DEFAULT false)
RETURNS jsonb LANGUAGE plpgsql AS $fn$
DECLARE resumo jsonb := '{}'::jsonb; cadastro jsonb; v_lidos bigint; v_gravados bigint;
BEGIN
    cadastro := etl.preparar_cadastro(p_sintetico, p_nao_verificado);
    resumo := resumo || jsonb_build_object('cadastro', cadastro);
    resumo := resumo || jsonb_build_object('anteriores', etl.garantir_historicos('LEGISLATURAS_ANTERIORES'));
    resumo := resumo || jsonb_build_object('proposicoes', etl.preparar_proposicoes());
    resumo := resumo || jsonb_build_object('plenario', etl.preparar_votacoes_plenario());
    resumo := resumo || jsonb_build_object('historico', etl.preparar_votacoes_historico());
    -- o que o arquivo trouxe e não virou linha: filiação sem proveniência, voto sem sessão ou político
    v_gravados := etl.montar_votos();
    v_lidos := (SELECT count(*) FROM stg.historico_voto);
    RETURN resumo || jsonb_build_object('votos_lidos', v_lidos, 'rejeitos',
        (cadastro->'rejeitos') || jsonb_build_object('SEM_SESSAO_POLITICO_OU_OPCAO', greatest(v_lidos - v_gravados, 0)));
END
$fn$;
"""

DDL_RELACIONAIS = r"""
CREATE TABLE stg.filiacoes_partidarias (
    id uuid NOT NULL,
    "politicoId" uuid NOT NULL,
    "partidoId" uuid NOT NULL,
    "dataFiliacao" date NOT NULL,
    "dataDesfiliacao" date,
    "isAtual" boolean NOT NULL,
    "motivoDesfiliacao" public.motivodesfiliacaoenum,
    uf character varying(2),
    created_at date NOT NULL
);
CREATE TABLE stg.mandatos (
    id uuid NOT NULL,
    "politicoId" uuid NOT NULL,
    "partidoId" uuid NOT NULL,
    cargo public.cargopoliticoenum NOT NULL,
    esfera public.tipoesferaenum NOT NULL,
    "ufJurisdicao" character varying(2) NOT NULL,
    "anoEleicao" integer NOT NULL,
    "numeroMandato" integer NOT NULL,
    "dataInicio" date NOT NULL,
    "dataFim" date,
    status public.statusmandatoenum NOT NULL,
    "coligacaoNome" character varying(255),
    "totalVotos" integer,
    "percentualVotos" numeric(5,2),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE stg.membros_gabinete (
    id uuid NOT NULL,
    "mandatoId" uuid NOT NULL,
    "politicoId" uuid,
    "nomeOcupante" character varying(255) NOT NULL,
    "ministerioNome" character varying(200) NOT NULL,
    "dataPosse" date NOT NULL,
    "dataExoneracao" date,
    "isMinistroEconomia" boolean NOT NULL
);
CREATE TABLE stg.partidos_politicos (
    id uuid NOT NULL,
    sigla character varying(20) NOT NULL,
    "nomeCompleto" character varying(255) NOT NULL,
    "numeroEleitoral" integer,
    "dataFundacao" date,
    "dataExtincao" date,
    "partidoSucessorId" uuid,
    "logoUrl" text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    "espectroPolitico" public.espectropoliticoenum,
    ideologia character varying(255),
    lema character varying(255)
);
CREATE TABLE stg.politicos (
    id uuid NOT NULL,
    "nomeCivil" character varying(255) NOT NULL,
    "nomeEleitoral" character varying(150) NOT NULL,
    "tseId" character varying(50),
    "camaraId" integer,
    "senadoId" integer,
    "dataNascimento" date,
    "dataFalecimento" date,
    genero character varying(20),
    "naturalidadeMunicipio" character varying(100),
    "naturalidadeUf" character varying(2),
    "fotoUrl" text,
    biografia text,
    "redesSociais" json,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    email character varying(255),
    "gabineteSala" character varying(100),
    "gabineteTelefone" character varying(50),
    "possuiProcessosDeclarados" boolean DEFAULT false NOT NULL
);
CREATE TABLE stg.proposicoes (
    id uuid NOT NULL,
    "idExternoCamara" integer,
    "idExternoSenado" integer,
    tipo public.tipoproposicaoenum NOT NULL,
    numero integer NOT NULL,
    ano integer NOT NULL,
    titulo character varying(255) NOT NULL,
    ementa text NOT NULL,
    "explicacaoEmenta" text,
    "areaTematica" character varying(100),
    "dataApresentacao" date NOT NULL,
    "dataSancaoPromulgacao" date,
    "statusTramitacao" public.statustramitacaoenum NOT NULL,
    "urlTextoOriginal" text,
    "isReformaEstrutural" boolean NOT NULL,
    "autorPoliticoId" uuid,
    "iniciativaPoderExecutivo" boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    "autorNome" text,
    "eixoImpacto" character varying(100),
    "eixosImpacto" character varying(255),
    "urlOficial" text
);
CREATE TABLE stg.sessoes_votacao (
    id uuid NOT NULL,
    "idExterno" character varying(100),
    "proposicaoId" uuid NOT NULL,
    "casaLegislativa" public.casalegislativaenum NOT NULL,
    "dataHoraVotacao" timestamp with time zone NOT NULL,
    "tituloPauta" character varying(255) NOT NULL,
    "descricaoDetalhada" text,
    "isVotacaoSecreta" boolean NOT NULL,
    aprovada boolean NOT NULL,
    "totalSim" integer NOT NULL,
    "totalNao" integer NOT NULL,
    "totalAbstencao" integer NOT NULL,
    "totalObstrucao" integer NOT NULL,
    created_at timestamp with time zone NOT NULL,
    "orientacaoGoverno" character varying(20),
    "orientacoesBancadas" text
);
CREATE TABLE stg.votos_parlamentares (
    id uuid NOT NULL,
    "sessaoVotacaoId" uuid NOT NULL,
    "politicoId" uuid NOT NULL,
    "partidoId" uuid,
    voto public.votoopcaoenum NOT NULL,
    created_at timestamp with time zone NOT NULL
);
ALTER TABLE ONLY stg.filiacoes_partidarias
    ADD CONSTRAINT filiacoes_partidarias_pkey PRIMARY KEY (id);
ALTER TABLE ONLY stg.mandatos
    ADD CONSTRAINT mandatos_pkey PRIMARY KEY (id);
ALTER TABLE ONLY stg.membros_gabinete
    ADD CONSTRAINT membros_gabinete_pkey PRIMARY KEY (id);
ALTER TABLE ONLY stg.partidos_politicos
    ADD CONSTRAINT "partidos_politicos_numeroEleitoral_key" UNIQUE ("numeroEleitoral");
ALTER TABLE ONLY stg.partidos_politicos
    ADD CONSTRAINT partidos_politicos_pkey PRIMARY KEY (id);
ALTER TABLE ONLY stg.partidos_politicos
    ADD CONSTRAINT partidos_politicos_sigla_key UNIQUE (sigla);
ALTER TABLE ONLY stg.politicos
    ADD CONSTRAINT politicos_pkey PRIMARY KEY (id);
ALTER TABLE ONLY stg.politicos
    ADD CONSTRAINT "politicos_tseId_key" UNIQUE ("tseId");
ALTER TABLE ONLY stg.proposicoes
    ADD CONSTRAINT "proposicoes_idExternoCamara_key" UNIQUE ("idExternoCamara");
ALTER TABLE ONLY stg.proposicoes
    ADD CONSTRAINT "proposicoes_idExternoSenado_key" UNIQUE ("idExternoSenado");
ALTER TABLE ONLY stg.proposicoes
    ADD CONSTRAINT proposicoes_pkey PRIMARY KEY (id);
ALTER TABLE ONLY stg.sessoes_votacao
    ADD CONSTRAINT "sessoes_votacao_idExterno_key" UNIQUE ("idExterno");
ALTER TABLE ONLY stg.sessoes_votacao
    ADD CONSTRAINT sessoes_votacao_pkey PRIMARY KEY (id);
ALTER TABLE ONLY stg.votos_parlamentares
    ADD CONSTRAINT uq_session_politician_vote UNIQUE ("sessaoVotacaoId", "politicoId");
ALTER TABLE ONLY stg.votos_parlamentares
    ADD CONSTRAINT votos_parlamentares_pkey PRIMARY KEY (id);
CREATE INDEX idx_affiliation_politician_date ON stg.filiacoes_partidarias USING btree ("politicoId", "dataFiliacao");
CREATE INDEX idx_filiacoes_partido ON stg.filiacoes_partidarias USING btree ("partidoId");
CREATE INDEX idx_filiacoes_politico ON stg.filiacoes_partidarias USING btree ("politicoId");
CREATE INDEX idx_mandate_dates ON stg.mandatos USING btree ("dataInicio", "dataFim");
CREATE INDEX idx_mandate_office_year ON stg.mandatos USING btree (cargo, "anoEleicao");
CREATE INDEX idx_mandatos_ano ON stg.mandatos USING btree ("anoEleicao");
CREATE INDEX idx_mandatos_partido ON stg.mandatos USING btree ("partidoId");
CREATE INDEX idx_mandatos_politico ON stg.mandatos USING btree ("politicoId");
CREATE INDEX idx_parliamentary_vote_choice ON stg.votos_parlamentares USING btree (voto);
CREATE INDEX idx_partidos_sigla ON stg.partidos_politicos USING btree (sigla);
CREATE INDEX idx_proposicoes_ano ON stg.proposicoes USING btree (ano);
CREATE INDEX idx_proposicoes_autor ON stg.proposicoes USING btree ("autorPoliticoId");
CREATE INDEX idx_proposition_structural ON stg.proposicoes USING btree ("isReformaEstrutural");
CREATE INDEX idx_proposition_type_num_year ON stg.proposicoes USING btree (tipo, numero, ano);
CREATE INDEX idx_votos_partido ON stg.votos_parlamentares USING btree ("partidoId");
CREATE INDEX idx_votos_politico ON stg.votos_parlamentares USING btree ("politicoId");
CREATE UNIQUE INDEX "ix_politicos_camaraId" ON stg.politicos USING btree ("camaraId");
CREATE INDEX "ix_politicos_nomeEleitoral" ON stg.politicos USING btree ("nomeEleitoral");
CREATE UNIQUE INDEX "ix_politicos_senadoId" ON stg.politicos USING btree ("senadoId");
ALTER TABLE ONLY stg.filiacoes_partidarias
    ADD CONSTRAINT "filiacoes_partidarias_partidoId_fkey" FOREIGN KEY ("partidoId") REFERENCES stg.partidos_politicos(id);
ALTER TABLE ONLY stg.filiacoes_partidarias
    ADD CONSTRAINT "filiacoes_partidarias_politicoId_fkey" FOREIGN KEY ("politicoId") REFERENCES stg.politicos(id) ON DELETE CASCADE;
ALTER TABLE ONLY stg.mandatos
    ADD CONSTRAINT "mandatos_partidoId_fkey" FOREIGN KEY ("partidoId") REFERENCES stg.partidos_politicos(id);
ALTER TABLE ONLY stg.mandatos
    ADD CONSTRAINT "mandatos_politicoId_fkey" FOREIGN KEY ("politicoId") REFERENCES stg.politicos(id) ON DELETE CASCADE;
ALTER TABLE ONLY stg.membros_gabinete
    ADD CONSTRAINT "membros_gabinete_mandatoId_fkey" FOREIGN KEY ("mandatoId") REFERENCES stg.mandatos(id) ON DELETE CASCADE;
ALTER TABLE ONLY stg.membros_gabinete
    ADD CONSTRAINT "membros_gabinete_politicoId_fkey" FOREIGN KEY ("politicoId") REFERENCES stg.politicos(id);
ALTER TABLE ONLY stg.partidos_politicos
    ADD CONSTRAINT "partidos_politicos_partidoSucessorId_fkey" FOREIGN KEY ("partidoSucessorId") REFERENCES stg.partidos_politicos(id);
ALTER TABLE ONLY stg.proposicoes
    ADD CONSTRAINT "proposicoes_autorPoliticoId_fkey" FOREIGN KEY ("autorPoliticoId") REFERENCES stg.politicos(id);
ALTER TABLE ONLY stg.sessoes_votacao
    ADD CONSTRAINT "sessoes_votacao_proposicaoId_fkey" FOREIGN KEY ("proposicaoId") REFERENCES stg.proposicoes(id) ON DELETE CASCADE;
ALTER TABLE ONLY stg.votos_parlamentares
    ADD CONSTRAINT "votos_parlamentares_partidoId_fkey" FOREIGN KEY ("partidoId") REFERENCES stg.partidos_politicos(id);
ALTER TABLE ONLY stg.votos_parlamentares
    ADD CONSTRAINT "votos_parlamentares_politicoId_fkey" FOREIGN KEY ("politicoId") REFERENCES stg.politicos(id) ON DELETE CASCADE;
ALTER TABLE ONLY stg.votos_parlamentares
    ADD CONSTRAINT "votos_parlamentares_sessaoVotacaoId_fkey" FOREIGN KEY ("sessaoVotacaoId") REFERENCES stg.sessoes_votacao(id) ON DELETE CASCADE;
"""

FKS_DAS_CONGELADAS = (
    'ALTER TABLE stg.proposicoes_autores ADD CONSTRAINT "proposicoes_autores_politicoId_fkey" FOREIGN KEY ("politicoId") REFERENCES stg.politicos(id) ON DELETE CASCADE NOT VALID;',
    'ALTER TABLE stg.proposicoes_autores ADD CONSTRAINT "proposicoes_autores_proposicaoId_fkey" FOREIGN KEY ("proposicaoId") REFERENCES stg.proposicoes(id) ON DELETE CASCADE NOT VALID;',
    'ALTER TABLE stg.registros_presenca ADD CONSTRAINT "registros_presenca_mandatoId_fkey" FOREIGN KEY ("mandatoId") REFERENCES stg.mandatos(id) ON DELETE CASCADE NOT VALID;',
    'ALTER TABLE stg.registros_presenca ADD CONSTRAINT "registros_presenca_politicoId_fkey" FOREIGN KEY ("politicoId") REFERENCES stg.politicos(id) ON DELETE CASCADE NOT VALID;',
    "ALTER TABLE stg.votacoes_proposicao ADD CONSTRAINT votacoes_proposicao_proposicao_id_fkey FOREIGN KEY (proposicao_id) REFERENCES stg.proposicoes(id) ON DELETE CASCADE NOT VALID;",
    "ALTER TABLE stg.votos_nominais ADD CONSTRAINT votos_nominais_parlamentar_id_fkey FOREIGN KEY (parlamentar_id) REFERENCES stg.politicos(id) ON DELETE CASCADE NOT VALID;",
)

TABELAS_PLANAS_DA_0040 = (
    "curadoria_partido",
    "curadoria_partido_conhecido",
    "curadoria_presidente",
    "curadoria_ministro_fazenda",
    "camara_deputado",
    "senado_senador",
    "tse_filiacao",
    "camara_proposicao_api",
    "senado_proposicao_api",
    "camara_sessao_plenario",
    "camara_voto_plenario",
    "senado_sessao_plenario",
    "senado_voto_plenario",
    "historico_parlamentar",
    "historico_partido",
    "historico_sessao",
    "historico_voto",
)
FUNCOES_DA_0040 = (
    "criar_trabalho()",
    "semear_cadastro()",
    "nome_tokens(text)",
    "nome_conjunto(text)",
    "partido_id(text)",
    "garantir_partido(text)",
    "preparar_cadastro(boolean, boolean)",
    "autor_pessoa(text, integer, integer)",
    "preparar_proposicoes()",
    "legislatura_inicio(integer)",
    "achar_proposicao(text, integer)",
    "garantir_historicos(text)",
    "preparar_votacoes_plenario()",
    "preparar_votacoes_historico()",
    "preparar_staging(boolean, boolean)",
    "montar_votos()",
)
_TRABALHO_RE = re.compile(r"\b(%s)\b" % "|".join(TRABALHO.values()))

# Os votos que o staging relacional já guardava passam para a plana cumulativa antes de ele cair: `leg.voto` é refeito inteiro
# a cada fusão, então sem isto a primeira fusão depois do deploy (a do cron, antes de a carga trazer os arquivos) o esvaziaria.
RETROPREENCHER_VOTOS = """
INSERT INTO stg.historico_voto (execucao_id, linha, casa, sessao_ext_id, parlamentar_ext_id, opcao, partido)
SELECT NULL, row_number() OVER (), x.casa, x.sessao, x.parlamentar, x.opcao, x.partido
  FROM (SELECT DISTINCT ON (c.casa, s."idExterno", c.parlamentar) c.casa, s."idExterno" AS sessao, c.parlamentar,
               v.voto::text AS opcao, pa.sigla AS partido
          FROM stg.votos_parlamentares v
          JOIN stg.sessoes_votacao s ON s.id = v."sessaoVotacaoId"
          JOIN stg.politicos p ON p.id = v."politicoId"
          LEFT JOIN stg.partidos_politicos pa ON pa.id = v."partidoId"
          CROSS JOIN LATERAL (SELECT CASE WHEN s."casaLegislativa" = 'CAMARA_DOS_DEPUTADOS' THEN 'CAMARA' ELSE 'SENADO' END AS casa,
                                      CASE WHEN s."casaLegislativa" = 'CAMARA_DOS_DEPUTADOS' THEN p."camaraId"
                                           ELSE p."senadoId" END AS parlamentar) c
         WHERE s."idExterno" IS NOT NULL AND c.parlamentar IS NOT NULL
         ORDER BY c.casa, s."idExterno", c.parlamentar, v.created_at, v.id) x
ON CONFLICT (casa, sessao_ext_id, parlamentar_ext_id) DO NOTHING
"""

FUNCOES = (FUNCOES_TRABALHO, FUNCOES_SEMENTE, FUNCOES_CADASTRO, FUNCOES_PROPOSICOES, FUNCOES_VOTACOES, FUNCOES_SESSOES)


def _executar(sql: str) -> None:
    op.get_bind().exec_driver_sql(sql.replace("%", "%%"))  # sem interpretar '%' (LIKE) como parâmetro


def _reescrever_fusao(conexao, nome: str) -> None:
    corpo = conexao.exec_driver_sql(
        "SELECT pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'etl' AND p.proname = %s",
        (nome,),
    ).scalar_one()
    novo, trocas = _ORIGEM_RE.subn(lambda m: TRABALHO[m.group(1)], corpo)
    if not trocas:
        raise RuntimeError(f"etl.{nome} não cita as tabelas de staging esperadas: foi editada fora das migrações?")
    if nome == "merge_cadastro":
        # no empate de início de filiação, a que já está em `core.filiacao` continua (a decisão antiga não se refaz)
        if novo.count(DESEMPATE) != 1:
            raise RuntimeError("etl.merge_cadastro difere do texto esperado no desempate das filiações")
        novo = novo.replace(DESEMPATE, DESEMPATE_COM_SOBREVIVENTE)
    conexao.exec_driver_sql(novo.replace("%", "%%"))


def upgrade() -> None:
    conexao = op.get_bind()
    _executar(TABELAS_PLANAS)
    for bloco in FUNCOES:
        _executar(bloco)
    for nome in FUNCOES_DE_FUSAO:
        _reescrever_fusao(conexao, nome)
    for nome in (
        "criar_trabalho",
        "semear_cadastro",
        "preparar_cadastro",
        "preparar_proposicoes",
        "garantir_historicos",
        "preparar_votacoes_plenario",
        "preparar_votacoes_historico",
        "preparar_staging",
        "garantir_partido",
        "montar_votos",
        "achar_proposicao",
    ):
        # escrevem em tabelas temporárias e leem core/leg: só o dono as executa (o papel de leitura tem USAGE em `etl`)
        conexao.exec_driver_sql(
            "DO $$ DECLARE f record; BEGIN FOR f IN SELECT oid::regprocedure AS assinatura FROM pg_proc "
            "WHERE pronamespace = 'etl'::regnamespace AND proname = '%s' LOOP "
            "EXECUTE 'REVOKE EXECUTE ON FUNCTION ' || f.assinatura || ' FROM PUBLIC'; END LOOP; END $$" % nome
        )
    _executar(RETROPREENCHER_VOTOS)
    for tabela in TABELAS_QUE_CAEM:
        op.execute(
            f"DROP TABLE IF EXISTS stg.{tabela} CASCADE"
        )  # o CASCADE leva só as chaves estrangeiras das congeladas


def _devolver_origem(conexao, nome: str) -> None:
    """O inverso de `_reescrever_fusao`: a função volta a ler as tabelas relacionais de `stg`."""
    corpo = conexao.exec_driver_sql(
        "SELECT pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'etl' AND p.proname = %s",
        (nome,),
    ).scalar_one()
    inverso = {novo: antigo for antigo, novo in TRABALHO.items()}
    corpo = corpo.replace(DESEMPATE_COM_SOBREVIVENTE, DESEMPATE)
    conexao.exec_driver_sql(_TRABALHO_RE.sub(lambda m: "stg." + inverso[m.group(1)], corpo).replace("%", "%%"))


def downgrade() -> None:
    conexao = op.get_bind()
    _executar(DDL_RELACIONAIS)
    for fk in FKS_DAS_CONGELADAS:
        _executar(fk)
    for nome in FUNCOES_DE_FUSAO:
        _devolver_origem(conexao, nome)
    for assinatura in FUNCOES_DA_0040:
        op.execute(f"DROP FUNCTION IF EXISTS etl.{assinatura}")
    for tabela in TABELAS_PLANAS_DA_0040:
        op.execute(f"DROP TABLE IF EXISTS stg.{tabela}")
