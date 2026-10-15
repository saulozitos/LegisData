

CREATE TYPE public.cargopoliticoenum AS ENUM (
    'PRESIDENTE',
    'VICE_PRESIDENTE',
    'MINISTRO_DE_ESTADO',
    'GOVERNADOR',
    'VICE_GOVERNADOR',
    'SENADOR',
    'DEPUTADO_FEDERAL',
    'DEPUTADO_ESTADUAL'
);

CREATE TYPE public.casalegislativaenum AS ENUM (
    'CAMARA_DOS_DEPUTADOS',
    'SENADO_FEDERAL',
    'CONGRESSO_NACIONAL',
    'ASSEMBLEIA_LEGISLATIVA'
);

CREATE TYPE public.categoriaindicadorenum AS ENUM (
    'INFLACAO',
    'PIB',
    'CESTA_BASICA',
    'COMBUSTIVEL',
    'COMMODITY',
    'DIVIDA_PUBLICA',
    'JUROS_SELIC',
    'CAMBIO_DOLAR',
    'DESEMPREGO',
    'SALARIO_MINIMO',
    'MERCADO_FINANCEIRO'
);

CREATE TYPE public.espectropoliticoenum AS ENUM (
    'ESQUERDA',
    'CENTRO_ESQUERDA',
    'CENTRO',
    'CENTRO_DIREITA',
    'DIREITA'
);

CREATE TYPE public.motivodesfiliacaoenum AS ENUM (
    'MUDANCA_VOLUNTARIA',
    'FUSAO_OU_INCORPORACAO',
    'EXPULSAO',
    'CRIACAO_DE_NOVA_LEGENDA',
    'EXTINCAO_DO_PARTIDO'
);

CREATE TYPE public.periodicidadeindicadorenum AS ENUM (
    'DIARIA',
    'MENSAL',
    'TRIMESTRAL',
    'ANUAL'
);

CREATE TYPE public.statusmandatoenum AS ENUM (
    'TITULAR_ATIVO',
    'CONCLUIDO',
    'RENUNCIA',
    'IMPEACHMENT',
    'CASSADO',
    'LICENCIADO',
    'FALECIDO',
    'SUPLENTE_EM_EXERCICIO'
);

CREATE TYPE public.statustramitacaoenum AS ENUM (
    'APROVADA_E_SANCIONADA',
    'APROVADA_E_PROMULGADA',
    'VETADA_TOTAL',
    'VETADA_PARCIAL',
    'REJEITADA',
    'EM_TRAMITACAO',
    'ARQUIVADA',
    'APROVADO_COMISSAO',
    'APROVADO_PLENARIO'
);

CREATE TYPE public.tipoautoriaenum AS ENUM (
    'AUTOR_PRINCIPAL',
    'COAUTOR',
    'INSTITUCIONAL',
    'RELATOR'
);

CREATE TYPE public.tipoesferaenum AS ENUM (
    'FEDERAL',
    'ESTADUAL',
    'MUNICIPAL'
);

CREATE TYPE public.tipopresencaenum AS ENUM (
    'PRESENTE',
    'AUSENCIA_JUSTIFICADA',
    'AUSENCIA_NAO_JUSTIFICADA',
    'LICENCA_MEDICA',
    'MISSAO_OFICIAL'
);

CREATE TYPE public.tipoproposicaoenum AS ENUM (
    'PEC',
    'PL',
    'PLP',
    'MPV',
    'PDL',
    'DECRETO_PRES',
    'LEI_DELEGADA',
    'PR',
    'PRC',
    'PDS',
    'REQ',
    'INC'
);

CREATE TYPE public.unidademedidaenum AS ENUM (
    'PERCENTUAL',
    'BRL',
    'USD',
    'PONTOS_INDICE',
    'TONELADAS'
);

CREATE TYPE public.votoopcaoenum AS ENUM (
    'SIM',
    'NAO',
    'ABSTENCAO',
    'OBSTRUCAO',
    'AUSENTE',
    'ARTIGO_17'
);

CREATE TABLE public.analises_impacto_politica (
    id uuid NOT NULL,
    "proposicaoId" uuid NOT NULL,
    "janelaMesesAvaliacao" integer NOT NULL,
    "variacaoIpcaJanela" numeric(8,4),
    "variacaoPibJanela" numeric(8,4),
    "variacaoSelicJanela" numeric(6,2),
    "variacaoCambioJanela" numeric(8,4),
    "grauCorrelacaoScore" numeric(5,2),
    "parecerCientifico" text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE public.certidoes_judiciais (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    "politicoId" uuid NOT NULL,
    orgao character varying(100) NOT NULL,
    "tipoCertidao" character varying(50) NOT NULL,
    "statusFicha" character varying(50) NOT NULL,
    detalhes text,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    "numeroProcesso" character varying(100),
    "dataEmissao" character varying(50),
    "linkComprovacao" character varying(500),
    "codigoAutenticidade" character varying(100)
);

CREATE TABLE public.declaracoes_patrimonio (
    id uuid NOT NULL,
    "politicoId" uuid NOT NULL,
    "anoEleicao" integer NOT NULL,
    "valorDeclaradoBrl" numeric(15,2) NOT NULL,
    "detalhesBens" text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE public.despesas_cota_parlamentar (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    "politicoId" uuid NOT NULL,
    ano integer NOT NULL,
    mes integer,
    "tipoDespesa" character varying(255) NOT NULL,
    "valorLiquido" numeric(12,2) NOT NULL,
    "nomeFornecedor" character varying(255) NOT NULL,
    "cnpjCpfFornecedor" character varying(30),
    "dataEmissao" date,
    "documentoUrl" text,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);

CREATE TABLE public.doacoes_campanha (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    "politicoId" uuid NOT NULL,
    "anoEleicao" integer NOT NULL,
    "nomeDoador" character varying(255) NOT NULL,
    "cpfCnpjDoador" character varying(30),
    "valorDoado" numeric(15,2) NOT NULL,
    "tipoReceita" character varying(100),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE public.emendas_parlamentares (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    "politicoId" uuid NOT NULL,
    ano integer NOT NULL,
    "codigoEmenda" character varying(50),
    "tipoEmenda" character varying(150) NOT NULL,
    "valorEmpenhado" numeric(15,2) NOT NULL,
    "valorPago" numeric(15,2) NOT NULL,
    "localidadeDestino" character varying(150) NOT NULL,
    funcao character varying(100),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);

CREATE TABLE public.filiacoes_partidarias (
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

CREATE TABLE public.historico_mandatos (
    id uuid NOT NULL,
    "politicoId" uuid NOT NULL,
    "partidoId" uuid,
    "partidoSigla" character varying(20) NOT NULL,
    casa character varying(20) NOT NULL,
    situacao character varying(50) DEFAULT 'EXERCICIO'::character varying NOT NULL,
    "dataInicio" date NOT NULL,
    "dataFim" date,
    observacao text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE public.indicadores_sociais_anuais (
    id uuid NOT NULL,
    ano integer NOT NULL,
    "taxaAnalfabetismoPct" numeric(5,2),
    "populacaoExtremaPobrezaPct" numeric(5,2),
    "populacaoExtremaPobrezaMilhoes" numeric(6,2),
    "populacaoInsegurancaAlimentarPct" numeric(5,2),
    "populacaoInsegurancaAlimentarMilhoes" numeric(6,2),
    "indiceGini" numeric(5,3),
    "fonteDados" character varying(100) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    "populacaoPobrezaPct" numeric(5,2),
    "populacaoInsegurancaAlimentarTotalPct" numeric(5,2),
    "taxaDesempregoPct" numeric(5,2),
    "serieGini" character varying(100)
);

CREATE TABLE public.indicadores_sociais_uf (
    id uuid NOT NULL,
    ano integer NOT NULL,
    uf character varying(2) NOT NULL,
    "estadoNome" character varying(100) NOT NULL,
    regiao character varying(30) NOT NULL,
    "taxaAnalfabetismoPct" numeric(5,2),
    "extremaPobrezaPct" numeric(5,2),
    "insegurancaAlimentarPct" numeric(5,2),
    "indiceGini" numeric(5,3),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    "pobrezaPct" numeric(5,2)
);

CREATE TABLE public.log_execucao_cron (
    id uuid NOT NULL,
    "dataExecucao" timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    "statusExecucao" character varying(20) NOT NULL,
    "registrosAtualizados" integer DEFAULT 0 NOT NULL,
    "tempoProcessamentoSegundos" integer DEFAULT 0 NOT NULL,
    "erroMensagem" text,
    etapa character varying(50)
);

CREATE TABLE public.mandate_indicators (
    id uuid NOT NULL,
    mandate_id uuid NOT NULL,
    chave_indicador character varying(100) NOT NULL,
    valor double precision NOT NULL,
    data_medicao date NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE public.mandatos (
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

CREATE TABLE public.mandatos_performance_economica (
    id uuid NOT NULL,
    "mandatoId" uuid NOT NULL,
    "ipcaAcumuladoMandato" numeric(14,4) NOT NULL,
    "pibCrescimentoAcumulado" numeric(8,4) NOT NULL,
    "pibCrescimentoMedioAno" numeric(6,2) NOT NULL,
    "dividaLiquidaInicialPct" numeric(6,2),
    "dividaLiquidaFinalPct" numeric(6,2),
    "dividaLiquidaDeltaPct" numeric(6,2),
    "cambioInicialUsdBrl" numeric(18,4),
    "cambioFinalUsdBrl" numeric(18,4),
    "cambioVariacaoPct" numeric(14,2),
    "salarioMinimoInicialUsd" numeric(10,2),
    "salarioMinimoFinalUsd" numeric(10,2),
    "taxaDesempregoInicial" numeric(5,2),
    "taxaDesempregoFinal" numeric(5,2),
    "resumoAnalitico" text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    "salarioMinimoInicialBrl" numeric(12,2),
    "salarioMinimoFinalBrl" numeric(12,2)
);

CREATE TABLE public.membros_gabinete (
    id uuid NOT NULL,
    "mandatoId" uuid NOT NULL,
    "politicoId" uuid,
    "nomeOcupante" character varying(255) NOT NULL,
    "ministerioNome" character varying(200) NOT NULL,
    "dataPosse" date NOT NULL,
    "dataExoneracao" date,
    "isMinistroEconomia" boolean NOT NULL
);

CREATE TABLE public.orientacoes_partidarias (
    votacao_id uuid NOT NULL,
    partido_bancada character varying(50) NOT NULL,
    orientacao character varying(20) NOT NULL,
    created_at timestamp with time zone NOT NULL
);

CREATE TABLE public.partidos_politicos (
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

CREATE TABLE public.politicos (
    id uuid NOT NULL,
    "nomeCivil" character varying(255) NOT NULL,
    "nomeEleitoral" character varying(150) NOT NULL,
    cpf character varying(14),
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

CREATE TABLE public.pontos_dados_indicadores (
    id uuid NOT NULL,
    "serieId" uuid NOT NULL,
    "dataReferencia" date NOT NULL,
    ano integer NOT NULL,
    mes integer,
    "valorBruto" numeric(18,6) NOT NULL,
    "valorDeflacionado" numeric(18,6),
    "moedaOriginal" character varying(10) NOT NULL,
    observacao character varying(255)
);

CREATE TABLE public.presidential_mandates (
    id uuid NOT NULL,
    nome character varying(255) NOT NULL,
    inicio date NOT NULL,
    fim date,
    partido character varying(50) NOT NULL,
    foto_url character varying(500),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE public.processos_judiciais (
    id uuid NOT NULL,
    "politicoId" uuid NOT NULL,
    "numeroProcesso" character varying(100) NOT NULL,
    tribunal character varying(100) NOT NULL,
    "dataProcesso" character varying(50) NOT NULL,
    "classeAssunto" character varying(255) NOT NULL,
    descricao text NOT NULL,
    "situacaoJuridica" text NOT NULL,
    "linkComprovacao" character varying(500) NOT NULL,
    "statusResumo" character varying(50) NOT NULL,
    "declaradoTse" boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE public.proposicoes (
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

CREATE TABLE public.proposicoes_autores (
    id uuid NOT NULL,
    "proposicaoId" uuid NOT NULL,
    "politicoId" uuid,
    "nomeAutor" text NOT NULL,
    "tipoAutoria" public.tipoautoriaenum NOT NULL,
    ordem integer NOT NULL,
    created_at timestamp with time zone NOT NULL
);

CREATE TABLE public.registros_presenca (
    id uuid NOT NULL,
    "politicoId" uuid NOT NULL,
    "mandatoId" uuid NOT NULL,
    "casaLegislativa" public.casalegislativaenum NOT NULL,
    "dataSessao" date NOT NULL,
    "tipoPresenca" public.tipopresencaenum NOT NULL,
    justificativa text,
    created_at timestamp with time zone NOT NULL
);

CREATE TABLE public.remuneracoes_politicos (
    id uuid NOT NULL,
    "politicoId" uuid NOT NULL,
    "mandatoId" uuid NOT NULL,
    "anoReferencia" integer NOT NULL,
    "mesReferencia" integer NOT NULL,
    "salarioBruto" numeric(12,2) NOT NULL,
    "salarioLiquido" numeric(12,2),
    "cotaParlamentarCeap" numeric(12,2),
    "auxilioMoradia" numeric(12,2),
    "outrosBeneficios" numeric(12,2),
    "fonteDados" character varying(100) NOT NULL,
    created_at date NOT NULL
);

CREATE TABLE public.repasses_federais_uf (
    id uuid NOT NULL,
    "mandatoIdRef" character varying(100) NOT NULL,
    ano integer NOT NULL,
    uf character varying(2) NOT NULL,
    "estadoNome" character varying(100) NOT NULL,
    regiao character varying(50) NOT NULL,
    "areaTematica" character varying(100) NOT NULL,
    "valorPagoBrl" numeric(18,2) NOT NULL,
    "populacaoEstimada" integer,
    "valorPerCapitaBrl" numeric(12,2),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    "periodoInicio" character varying(7),
    "periodoFim" character varying(7),
    "mesesCobertos" integer,
    "coberturaParcial" boolean
);

CREATE TABLE public.resultados_eleicoes_presidenciais_uf (
    id uuid NOT NULL,
    "anoEleicao" integer NOT NULL,
    "mandatoIdRef" character varying(50) NOT NULL,
    uf character varying(2) NOT NULL,
    "estadoNome" character varying(100) NOT NULL,
    regiao character varying(30) NOT NULL,
    "candidatoVencedorNome" character varying(150) NOT NULL,
    "partidoVencedorSigla" character varying(20) NOT NULL,
    "votosVencedorPct" numeric(5,2) NOT NULL,
    "candidatoSegundoNome" character varying(150) NOT NULL,
    "partidoSegundoSigla" character varying(20) NOT NULL,
    "votosSegundoPct" numeric(5,2) NOT NULL,
    "totalVotosValidos" integer,
    turno integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE public.resumos_macroeconomicos_anuais (
    id uuid NOT NULL,
    ano integer NOT NULL,
    "ipcaAcumuladoAno" numeric(14,4),
    "pibTotalBrl" numeric(18,2),
    "pibCrescimentoReal" numeric(6,2),
    "pibPerCapitaBrl" numeric(12,2),
    "selicMediaAno" numeric(6,2),
    "cambioDolarMedioBrl" numeric(18,4),
    "cestaBasicaMediaBrl" numeric(10,2),
    "gasolinaPrecoMedioBrl" numeric(8,3),
    "carneBovinaPrecoMedioBrl" numeric(8,2),
    "dividaLiquidaPctPib" numeric(6,2),
    "desempregoMedio" numeric(5,2),
    "salarioMinimoNominalBrl" numeric(10,2),
    "presidenteDominanteNome" character varying(150),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    "ibovespaFechamentoAno" numeric(12,2),
    "crescimentoPibPercentual" numeric(6,2),
    "inflacaoAnualIpca" numeric(14,4),
    "inflacaoAcumuladaMandato" numeric(14,4),
    "taxaDesempregoAnual" numeric(5,2),
    "taxaDesmatamentoAmazonia" numeric(10,2),
    "insegurancaAlimentarPct" numeric(5,2),
    "cotacaoDolarFechamento" numeric(12,4),
    "salarioMinimo" numeric(10,2),
    "taxaHomicidios" numeric(6,2),
    "taxaFeminicidios" numeric(6,2)
);

CREATE TABLE public.series_indicadores (
    id uuid NOT NULL,
    "codigoSerie" character varying(50) NOT NULL,
    nome character varying(200) NOT NULL,
    categoria public.categoriaindicadorenum NOT NULL,
    periodicidade public.periodicidadeindicadorenum NOT NULL,
    unidade public.unidademedidaenum NOT NULL,
    "orgaoFonte" character varying(100) NOT NULL,
    descricao text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE public.sessoes_votacao (
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

CREATE TABLE public.votacoes_proposicao (
    id uuid NOT NULL,
    proposicao_id uuid NOT NULL,
    data_hora timestamp with time zone NOT NULL,
    local_deliberacao character varying(100) NOT NULL,
    tipo_deliberacao character varying(30) NOT NULL,
    resumo_decisao text NOT NULL,
    nome_comissao character varying(150),
    link_ata_reuniao text,
    relator_nome character varying(150),
    parecer_relator_numero character varying(80),
    parecer_relator_texto text,
    link_parecer_relator text,
    total_sim integer NOT NULL,
    total_nao integer NOT NULL,
    total_abstencao integer NOT NULL,
    total_obstrucao integer NOT NULL,
    aprovada boolean NOT NULL,
    created_at timestamp with time zone NOT NULL
);

CREATE TABLE public.votos_nominais (
    votacao_id uuid NOT NULL,
    parlamentar_id uuid NOT NULL,
    voto character varying(20) NOT NULL,
    created_at timestamp with time zone NOT NULL
);

CREATE TABLE public.votos_parlamentares (
    id uuid NOT NULL,
    "sessaoVotacaoId" uuid NOT NULL,
    "politicoId" uuid NOT NULL,
    "partidoId" uuid,
    voto public.votoopcaoenum NOT NULL,
    created_at timestamp with time zone NOT NULL
);

ALTER TABLE ONLY public.analises_impacto_politica
    ADD CONSTRAINT analises_impacto_politica_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.certidoes_judiciais
    ADD CONSTRAINT certidoes_judiciais_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.declaracoes_patrimonio
    ADD CONSTRAINT declaracoes_patrimonio_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.despesas_cota_parlamentar
    ADD CONSTRAINT despesas_cota_parlamentar_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.doacoes_campanha
    ADD CONSTRAINT doacoes_campanha_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.emendas_parlamentares
    ADD CONSTRAINT emendas_parlamentares_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.filiacoes_partidarias
    ADD CONSTRAINT filiacoes_partidarias_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.historico_mandatos
    ADD CONSTRAINT historico_mandatos_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.indicadores_sociais_anuais
    ADD CONSTRAINT indicadores_sociais_anuais_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.indicadores_sociais_uf
    ADD CONSTRAINT indicadores_sociais_uf_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.log_execucao_cron
    ADD CONSTRAINT log_execucao_cron_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.mandate_indicators
    ADD CONSTRAINT mandate_indicators_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.mandatos_performance_economica
    ADD CONSTRAINT "mandatos_performance_economica_mandatoId_key" UNIQUE ("mandatoId");

ALTER TABLE ONLY public.mandatos_performance_economica
    ADD CONSTRAINT mandatos_performance_economica_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.mandatos
    ADD CONSTRAINT mandatos_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.membros_gabinete
    ADD CONSTRAINT membros_gabinete_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.orientacoes_partidarias
    ADD CONSTRAINT orientacoes_partidarias_pkey PRIMARY KEY (votacao_id, partido_bancada);

ALTER TABLE ONLY public.partidos_politicos
    ADD CONSTRAINT "partidos_politicos_numeroEleitoral_key" UNIQUE ("numeroEleitoral");

ALTER TABLE ONLY public.partidos_politicos
    ADD CONSTRAINT partidos_politicos_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.partidos_politicos
    ADD CONSTRAINT partidos_politicos_sigla_key UNIQUE (sigla);

ALTER TABLE ONLY public.politicos
    ADD CONSTRAINT politicos_cpf_key UNIQUE (cpf);

ALTER TABLE ONLY public.politicos
    ADD CONSTRAINT politicos_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.politicos
    ADD CONSTRAINT "politicos_tseId_key" UNIQUE ("tseId");

ALTER TABLE ONLY public.pontos_dados_indicadores
    ADD CONSTRAINT pontos_dados_indicadores_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.presidential_mandates
    ADD CONSTRAINT presidential_mandates_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.processos_judiciais
    ADD CONSTRAINT processos_judiciais_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.proposicoes_autores
    ADD CONSTRAINT proposicoes_autores_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.proposicoes
    ADD CONSTRAINT "proposicoes_idExternoCamara_key" UNIQUE ("idExternoCamara");

ALTER TABLE ONLY public.proposicoes
    ADD CONSTRAINT "proposicoes_idExternoSenado_key" UNIQUE ("idExternoSenado");

ALTER TABLE ONLY public.proposicoes
    ADD CONSTRAINT proposicoes_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.registros_presenca
    ADD CONSTRAINT registros_presenca_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.remuneracoes_politicos
    ADD CONSTRAINT remuneracoes_politicos_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.repasses_federais_uf
    ADD CONSTRAINT repasses_federais_uf_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.resultados_eleicoes_presidenciais_uf
    ADD CONSTRAINT resultados_eleicoes_presidenciais_uf_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.resumos_macroeconomicos_anuais
    ADD CONSTRAINT resumos_macroeconomicos_anuais_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.series_indicadores
    ADD CONSTRAINT "series_indicadores_codigoSerie_key" UNIQUE ("codigoSerie");

ALTER TABLE ONLY public.series_indicadores
    ADD CONSTRAINT series_indicadores_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.sessoes_votacao
    ADD CONSTRAINT "sessoes_votacao_idExterno_key" UNIQUE ("idExterno");

ALTER TABLE ONLY public.sessoes_votacao
    ADD CONSTRAINT sessoes_votacao_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.resultados_eleicoes_presidenciais_uf
    ADD CONSTRAINT uq_election_year_uf_round UNIQUE ("anoEleicao", uf, turno);

ALTER TABLE ONLY public.declaracoes_patrimonio
    ADD CONSTRAINT uq_politician_election_asset UNIQUE ("politicoId", "anoEleicao");

ALTER TABLE ONLY public.remuneracoes_politicos
    ADD CONSTRAINT uq_politician_year_month UNIQUE ("politicoId", "anoReferencia", "mesReferencia");

ALTER TABLE ONLY public.pontos_dados_indicadores
    ADD CONSTRAINT uq_series_reference_date UNIQUE ("serieId", "dataReferencia");

ALTER TABLE ONLY public.votos_parlamentares
    ADD CONSTRAINT uq_session_politician_vote UNIQUE ("sessaoVotacaoId", "politicoId");

ALTER TABLE ONLY public.indicadores_sociais_uf
    ADD CONSTRAINT uq_social_indicator_year_uf UNIQUE (ano, uf);

ALTER TABLE ONLY public.votacoes_proposicao
    ADD CONSTRAINT votacoes_proposicao_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.votos_nominais
    ADD CONSTRAINT votos_nominais_pkey PRIMARY KEY (votacao_id, parlamentar_id);

ALTER TABLE ONLY public.votos_parlamentares
    ADD CONSTRAINT votos_parlamentares_pkey PRIMARY KEY (id);

CREATE INDEX idx_affiliation_politician_date ON public.filiacoes_partidarias USING btree ("politicoId", "dataFiliacao");

CREATE INDEX idx_attendance_politician_date ON public.registros_presenca USING btree ("politicoId", "dataSessao");

CREATE INDEX idx_certidao_politico ON public.certidoes_judiciais USING btree ("politicoId");

CREATE INDEX idx_certidao_status ON public.certidoes_judiciais USING btree ("statusFicha");

CREATE INDEX idx_cron_data ON public.log_execucao_cron USING btree ("dataExecucao");

CREATE INDEX idx_cron_status ON public.log_execucao_cron USING btree ("statusExecucao");

CREATE INDEX idx_despesa_cota_ano ON public.despesas_cota_parlamentar USING btree (ano);

CREATE INDEX idx_despesa_cota_politico ON public.despesas_cota_parlamentar USING btree ("politicoId");

CREATE INDEX idx_despesa_cota_tipo ON public.despesas_cota_parlamentar USING btree ("tipoDespesa");

CREATE INDEX idx_despesa_politico_ano ON public.despesas_cota_parlamentar USING btree ("politicoId", ano);

CREATE INDEX idx_doacao_ano ON public.doacoes_campanha USING btree ("anoEleicao");

CREATE INDEX idx_doacao_politico ON public.doacoes_campanha USING btree ("politicoId");

CREATE INDEX idx_doacao_politico_ano ON public.doacoes_campanha USING btree ("politicoId", "anoEleicao");

CREATE INDEX idx_economic_ref_date ON public.pontos_dados_indicadores USING btree ("dataReferencia");

CREATE INDEX idx_economic_year_month ON public.pontos_dados_indicadores USING btree (ano, mes);

CREATE INDEX idx_election_year_uf ON public.resultados_eleicoes_presidenciais_uf USING btree ("anoEleicao", uf);

CREATE INDEX idx_emenda_ano ON public.emendas_parlamentares USING btree (ano);

CREATE INDEX idx_emenda_politico ON public.emendas_parlamentares USING btree ("politicoId");

CREATE INDEX idx_emenda_politico_ano ON public.emendas_parlamentares USING btree ("politicoId", ano);

CREATE INDEX idx_emenda_tipo ON public.emendas_parlamentares USING btree ("tipoEmenda");

CREATE INDEX idx_filiacoes_partido ON public.filiacoes_partidarias USING btree ("partidoId");

CREATE INDEX idx_filiacoes_politico ON public.filiacoes_partidarias USING btree ("politicoId");

CREATE INDEX idx_hist_mandato_partido ON public.historico_mandatos USING btree ("partidoSigla");

CREATE INDEX idx_hist_mandato_periodo ON public.historico_mandatos USING btree ("dataInicio", "dataFim");

CREATE INDEX idx_hist_mandato_politico ON public.historico_mandatos USING btree ("politicoId");

CREATE INDEX idx_hist_mandato_situacao ON public.historico_mandatos USING btree (situacao);

CREATE INDEX idx_impact_proposition ON public.analises_impacto_politica USING btree ("proposicaoId");

CREATE INDEX idx_mandate_dates ON public.mandatos USING btree ("dataInicio", "dataFim");

CREATE INDEX idx_mandate_office_year ON public.mandatos USING btree (cargo, "anoEleicao");

CREATE INDEX idx_mandatos_ano ON public.mandatos USING btree ("anoEleicao");

CREATE INDEX idx_mandatos_partido ON public.mandatos USING btree ("partidoId");

CREATE INDEX idx_mandatos_politico ON public.mandatos USING btree ("politicoId");

CREATE INDEX idx_orientacoes_partido ON public.orientacoes_partidarias USING btree (partido_bancada);

CREATE INDEX idx_parliamentary_vote_choice ON public.votos_parlamentares USING btree (voto);

CREATE INDEX idx_partidos_sigla ON public.partidos_politicos USING btree (sigla);

CREATE INDEX idx_processo_numero ON public.processos_judiciais USING btree ("numeroProcesso");

CREATE INDEX idx_processo_politico ON public.processos_judiciais USING btree ("politicoId");

CREATE INDEX idx_prop_autor_pol_tipo ON public.proposicoes_autores USING btree ("politicoId", "tipoAutoria");

CREATE INDEX idx_prop_autor_prop_ordem ON public.proposicoes_autores USING btree ("proposicaoId", ordem);

CREATE INDEX idx_proposicoes_ano ON public.proposicoes USING btree (ano);

CREATE INDEX idx_proposicoes_autor ON public.proposicoes USING btree ("autorPoliticoId");

CREATE INDEX idx_proposition_structural ON public.proposicoes USING btree ("isReformaEstrutural");

CREATE INDEX idx_proposition_type_num_year ON public.proposicoes USING btree (tipo, numero, ano);

CREATE INDEX idx_remuneracoes_ano ON public.remuneracoes_politicos USING btree ("anoReferencia");

CREATE INDEX idx_remuneracoes_politico ON public.remuneracoes_politicos USING btree ("politicoId");

CREATE INDEX idx_social_indicator_uf ON public.indicadores_sociais_uf USING btree (uf);

CREATE INDEX idx_votacoes_prop_data ON public.votacoes_proposicao USING btree (data_hora);

CREATE INDEX idx_votacoes_prop_id ON public.votacoes_proposicao USING btree (proposicao_id);

CREATE INDEX idx_votacoes_prop_tipo ON public.votacoes_proposicao USING btree (tipo_deliberacao);

CREATE INDEX idx_votos_nominais_parlamentar ON public.votos_nominais USING btree (parlamentar_id);

CREATE INDEX idx_votos_nominais_voto ON public.votos_nominais USING btree (voto);

CREATE INDEX idx_votos_partido ON public.votos_parlamentares USING btree ("partidoId");

CREATE INDEX idx_votos_politico ON public.votos_parlamentares USING btree ("politicoId");

CREATE INDEX "ix_declaracoes_patrimonio_anoEleicao" ON public.declaracoes_patrimonio USING btree ("anoEleicao");

CREATE INDEX "ix_declaracoes_patrimonio_politicoId" ON public.declaracoes_patrimonio USING btree ("politicoId");

CREATE UNIQUE INDEX ix_indicadores_sociais_anuais_ano ON public.indicadores_sociais_anuais USING btree (ano);

CREATE INDEX ix_indicadores_sociais_uf_ano ON public.indicadores_sociais_uf USING btree (ano);

CREATE INDEX ix_indicadores_sociais_uf_uf ON public.indicadores_sociais_uf USING btree (uf);

CREATE UNIQUE INDEX "ix_politicos_camaraId" ON public.politicos USING btree ("camaraId");

CREATE INDEX "ix_politicos_nomeEleitoral" ON public.politicos USING btree ("nomeEleitoral");

CREATE UNIQUE INDEX "ix_politicos_senadoId" ON public.politicos USING btree ("senadoId");

CREATE INDEX ix_repasses_federais_uf_ano ON public.repasses_federais_uf USING btree (ano);

CREATE INDEX "ix_repasses_federais_uf_areaTematica" ON public.repasses_federais_uf USING btree ("areaTematica");

CREATE INDEX "ix_repasses_federais_uf_mandatoIdRef" ON public.repasses_federais_uf USING btree ("mandatoIdRef");

CREATE INDEX ix_repasses_federais_uf_regiao ON public.repasses_federais_uf USING btree (regiao);

CREATE INDEX ix_repasses_federais_uf_uf ON public.repasses_federais_uf USING btree (uf);

CREATE INDEX "ix_resultados_eleicoes_presidenciais_uf_anoEleicao" ON public.resultados_eleicoes_presidenciais_uf USING btree ("anoEleicao");

CREATE INDEX ix_resultados_eleicoes_presidenciais_uf_uf ON public.resultados_eleicoes_presidenciais_uf USING btree (uf);

CREATE UNIQUE INDEX ix_resumos_macroeconomicos_anuais_ano ON public.resumos_macroeconomicos_anuais USING btree (ano);

CREATE INDEX ix_series_indicadores_categoria ON public.series_indicadores USING btree (categoria);

ALTER TABLE ONLY public.analises_impacto_politica
    ADD CONSTRAINT "analises_impacto_politica_proposicaoId_fkey" FOREIGN KEY ("proposicaoId") REFERENCES public.proposicoes(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.certidoes_judiciais
    ADD CONSTRAINT "certidoes_judiciais_politicoId_fkey" FOREIGN KEY ("politicoId") REFERENCES public.politicos(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.declaracoes_patrimonio
    ADD CONSTRAINT "declaracoes_patrimonio_politicoId_fkey" FOREIGN KEY ("politicoId") REFERENCES public.politicos(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.despesas_cota_parlamentar
    ADD CONSTRAINT "despesas_cota_parlamentar_politicoId_fkey" FOREIGN KEY ("politicoId") REFERENCES public.politicos(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.doacoes_campanha
    ADD CONSTRAINT "doacoes_campanha_politicoId_fkey" FOREIGN KEY ("politicoId") REFERENCES public.politicos(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.emendas_parlamentares
    ADD CONSTRAINT "emendas_parlamentares_politicoId_fkey" FOREIGN KEY ("politicoId") REFERENCES public.politicos(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.filiacoes_partidarias
    ADD CONSTRAINT "filiacoes_partidarias_partidoId_fkey" FOREIGN KEY ("partidoId") REFERENCES public.partidos_politicos(id);

ALTER TABLE ONLY public.filiacoes_partidarias
    ADD CONSTRAINT "filiacoes_partidarias_politicoId_fkey" FOREIGN KEY ("politicoId") REFERENCES public.politicos(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.historico_mandatos
    ADD CONSTRAINT "historico_mandatos_partidoId_fkey" FOREIGN KEY ("partidoId") REFERENCES public.partidos_politicos(id);

ALTER TABLE ONLY public.historico_mandatos
    ADD CONSTRAINT "historico_mandatos_politicoId_fkey" FOREIGN KEY ("politicoId") REFERENCES public.politicos(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.mandate_indicators
    ADD CONSTRAINT mandate_indicators_mandate_id_fkey FOREIGN KEY (mandate_id) REFERENCES public.presidential_mandates(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.mandatos
    ADD CONSTRAINT "mandatos_partidoId_fkey" FOREIGN KEY ("partidoId") REFERENCES public.partidos_politicos(id);

ALTER TABLE ONLY public.mandatos_performance_economica
    ADD CONSTRAINT "mandatos_performance_economica_mandatoId_fkey" FOREIGN KEY ("mandatoId") REFERENCES public.mandatos(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.mandatos
    ADD CONSTRAINT "mandatos_politicoId_fkey" FOREIGN KEY ("politicoId") REFERENCES public.politicos(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.membros_gabinete
    ADD CONSTRAINT "membros_gabinete_mandatoId_fkey" FOREIGN KEY ("mandatoId") REFERENCES public.mandatos(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.membros_gabinete
    ADD CONSTRAINT "membros_gabinete_politicoId_fkey" FOREIGN KEY ("politicoId") REFERENCES public.politicos(id);

ALTER TABLE ONLY public.orientacoes_partidarias
    ADD CONSTRAINT orientacoes_partidarias_votacao_id_fkey FOREIGN KEY (votacao_id) REFERENCES public.votacoes_proposicao(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.partidos_politicos
    ADD CONSTRAINT "partidos_politicos_partidoSucessorId_fkey" FOREIGN KEY ("partidoSucessorId") REFERENCES public.partidos_politicos(id);

ALTER TABLE ONLY public.pontos_dados_indicadores
    ADD CONSTRAINT "pontos_dados_indicadores_serieId_fkey" FOREIGN KEY ("serieId") REFERENCES public.series_indicadores(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.processos_judiciais
    ADD CONSTRAINT "processos_judiciais_politicoId_fkey" FOREIGN KEY ("politicoId") REFERENCES public.politicos(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.proposicoes
    ADD CONSTRAINT "proposicoes_autorPoliticoId_fkey" FOREIGN KEY ("autorPoliticoId") REFERENCES public.politicos(id);

ALTER TABLE ONLY public.proposicoes_autores
    ADD CONSTRAINT "proposicoes_autores_politicoId_fkey" FOREIGN KEY ("politicoId") REFERENCES public.politicos(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.proposicoes_autores
    ADD CONSTRAINT "proposicoes_autores_proposicaoId_fkey" FOREIGN KEY ("proposicaoId") REFERENCES public.proposicoes(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.registros_presenca
    ADD CONSTRAINT "registros_presenca_mandatoId_fkey" FOREIGN KEY ("mandatoId") REFERENCES public.mandatos(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.registros_presenca
    ADD CONSTRAINT "registros_presenca_politicoId_fkey" FOREIGN KEY ("politicoId") REFERENCES public.politicos(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.remuneracoes_politicos
    ADD CONSTRAINT "remuneracoes_politicos_mandatoId_fkey" FOREIGN KEY ("mandatoId") REFERENCES public.mandatos(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.remuneracoes_politicos
    ADD CONSTRAINT "remuneracoes_politicos_politicoId_fkey" FOREIGN KEY ("politicoId") REFERENCES public.politicos(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.sessoes_votacao
    ADD CONSTRAINT "sessoes_votacao_proposicaoId_fkey" FOREIGN KEY ("proposicaoId") REFERENCES public.proposicoes(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.votacoes_proposicao
    ADD CONSTRAINT votacoes_proposicao_proposicao_id_fkey FOREIGN KEY (proposicao_id) REFERENCES public.proposicoes(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.votos_nominais
    ADD CONSTRAINT votos_nominais_parlamentar_id_fkey FOREIGN KEY (parlamentar_id) REFERENCES public.politicos(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.votos_nominais
    ADD CONSTRAINT votos_nominais_votacao_id_fkey FOREIGN KEY (votacao_id) REFERENCES public.votacoes_proposicao(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.votos_parlamentares
    ADD CONSTRAINT "votos_parlamentares_partidoId_fkey" FOREIGN KEY ("partidoId") REFERENCES public.partidos_politicos(id);

ALTER TABLE ONLY public.votos_parlamentares
    ADD CONSTRAINT "votos_parlamentares_politicoId_fkey" FOREIGN KEY ("politicoId") REFERENCES public.politicos(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.votos_parlamentares
    ADD CONSTRAINT "votos_parlamentares_sessaoVotacaoId_fkey" FOREIGN KEY ("sessaoVotacaoId") REFERENCES public.sessoes_votacao(id) ON DELETE CASCADE;


