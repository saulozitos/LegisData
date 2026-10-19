import type { PoliticoDossier } from '@/services/api';

/** Dossiê completo, no formato devolvido pela API quando todos os dados existem. */
export function fullDossier(): PoliticoDossier {
  return {
    perfil: {
      id: 'pol-1',
      nome_eleitoral: 'Ana Silva',
      nome_civil: 'Ana Maria da Silva',
      genero: 'F',
      data_nascimento: '1980-05-10',
      naturalidade: 'São Paulo',
      foto_url: 'https://upload.wikimedia.org/ana.jpg',
      cargo_atual: 'DEPUTADO_FEDERAL',
      partido_atual: 'PT',
      uf: 'SP',
      biografia: 'Biografia da parlamentar.',
      email: 'dep.ana@camara.leg.br',
      gabinete_sala: 'Anexo IV, 301',
      gabinete_telefone: '(61) 3215-1234',
      redes_sociais: { twitter: 'https://twitter.com/ana', instagram: null },
      camara_id: 1234,
      senado_id: null,
      possui_processos_declarados: false,
    },
    trajetoria_mandatos: [
      { id: 'm1', cargo: 'DEPUTADO_FEDERAL', esfera: 'FEDERAL', ano_eleicao: 2022, numero_mandato: 2, data_inicio: '2023-02-01', data_fim: null, status: 'TITULAR_ATIVO', partido_sigla: 'PT', uf: 'SP', total_votos: 150000, percentual_votos: 0.8, coligacao: 'Coligação X' },
      { id: 'm0', cargo: 'VEREADOR', esfera: 'MUNICIPAL', ano_eleicao: 2016, numero_mandato: 1, data_inicio: '2017-01-01', data_fim: '2020-12-31', status: 'CONCLUIDO', partido_sigla: 'PSB', uf: 'SP', total_votos: null, percentual_votos: null, coligacao: null },
    ],
    filiacoes_partidarias: [
      { id: 'f1', partido_sigla: 'PT', partido_nome: 'Partido dos Trabalhadores', data_filiacao: '2018-01-01', data_desfiliacao: null, is_atual: true, motivo_desfiliacao: null, uf: 'SP' },
      { id: 'f0', partido_sigla: 'PSB', partido_nome: 'Partido Socialista Brasileiro', data_filiacao: '2010-01-01', data_desfiliacao: '2017-12-31', is_atual: false, motivo_desfiliacao: 'TROCA_PARTIDARIA', uf: 'SP' },
    ],
    remuneracao: {
      resumo: { salario_bruto_atual: 44008.52, salario_liquido_atual: 33000, media_ceap_mensal: 30000, total_bruto_2023: 528102.24, total_ceap_2023: 360000, total_beneficios_2023: 50000 },
      historico: [
        { ano: 2023, mes: 1, salario_bruto: 44008.52, salario_liquido: 33000, cota_ceap: 29000, auxilio_moradia: 4900, outros_beneficios: 100, fonte: 'Portal da Transparência' },
        { ano: 2023, mes: 2, salario_bruto: 44008.52, salario_liquido: 33000, cota_ceap: 31000, auxilio_moradia: 4900, outros_beneficios: 0, fonte: 'Portal da Transparência' },
      ],
    },
    custos_ceap: {
      possui_dados: true,
      gasto_total_recente: 900000,
      total_notas: 120,
      gastos_por_tipo: [
        { tipo_despesa: 'Divulgação da atividade parlamentar', total_gasto: 500000, percentual: 55.6 },
        { tipo_despesa: 'Passagens aéreas', total_gasto: 400000, percentual: 44.4 },
      ],
      maiores_fornecedores: [{ nome_fornecedor: 'Gráfica Alfa LTDA', cnpj_cpf: '12345678000190', total_recebido: 300000, num_notas: 40 }],
      gastos_por_ano: [
        { ano: 2024, total_gasto: 500000 },
        { ano: 2023, total_gasto: 400000 },
      ],
    },
    emendas_parlamentares: {
      possui_dados: true,
      total_empenhado: 10000000,
      total_pago: 8000000,
      percentual_execucao: 80,
      destinos_principais: [{ localidade: 'Campinas/SP', valor_pago: 3000000, percentual: 37.5 }],
      distribuicao_por_tipo: [{ tipo: 'Individual', valor_pago: 8000000, percentual: 100 }],
      distribuicao_por_area: [{ area: 'Saúde', valor_pago: 5000000, percentual: 62.5 }],
      lista_emendas: [{ id: 'e1', ano: 2023, codigo_emenda: '2023001', tipo_emenda: 'Individual', valor_empenhado: 1000000, valor_pago: 800000, localidade_destino: 'Campinas/SP', funcao: 'Saúde' }],
    },
    ficha_limpa: {
      possui_processos_declarados: false,
      status_geral: 'NADA_CONSTA',
      orgaos_declarados: [],
      certidoes: [{ id: 'c1', orgao: 'STF', tipo_certidao: 'Criminal', status_ficha: 'Negativa', detalhes: null, numero_processo: null, data_emissao: null, link_comprovacao: null, codigo_autenticidade: null }],
    },
    financiamento_campanha: {
      possui_dados: true,
      ano_eleicao: 2022,
      total_arrecadado: 2000000,
      total_doadores: 2,
      demais_doadores: null,
      eleicoes_disponiveis: [2022],
      top_doadores: [{ nome_doador: 'Doador Um', cpf_cnpj_doador: '***.456.789-**', valor_doado: 1000000, tipo_receita: 'Fundo Partidário', percentual: 50 }],
      todas_doacoes: [
        { id: 'd1', ano_eleicao: 2022, nome_doador: 'Doador Um', cpf_cnpj_doador: '***.456.789-**', valor_doado: 1000000, tipo_receita: 'Fundo Partidário', agregado: false, quantidade_doadores: 1 },
        { id: 'd2', ano_eleicao: 2022, nome_doador: 'Empresa Dois', cpf_cnpj_doador: null, valor_doado: 1000000, tipo_receita: null, agregado: false, quantidade_doadores: 1 },
      ],
    },
    basometro: { taxa_governismo_pct: 72, total_votacoes_analisadas: 50, votos_alinhados: 36, votos_divergentes: 14, classificacao: 'GOVERNISTA' },
    relevancia_legislativa: { total_proposicoes: 10, total_proposicoes_registradas: 10, projetos_impacto: 4, projetos_simbolicos: 6, percentual_impacto: 40, percentual_simbolico: 60, diagnostico: 'Diagnóstico de relevância.', lideranca_legislativa_count: 7, apoio_politico_count: 3, taxa_eficiencia_pct: 14.3, score_atividade_ponderada: 18.6, distribuicao_complexidade: { alta: 2, media: 7, baixa: 1 } },
    materias_propostas: [
      { id: 'pr1', tipo: 'PL', numero: 100, ano: 2023, titulo: 'PL 100/2023', ementa: 'Ementa do PL 100', status: 'Em tramitação', area_tematica: 'Saúde', data_apresentacao: '2023-03-01', is_reforma_estrutural: true, url_oficial: 'https://camara.leg.br/pl100', classificacao_relevancia: 'IMPACTO', justificativa_relevancia: 'Muda o SUS.' },
      { id: 'pr2', tipo: 'PL', numero: 200, ano: 2022, titulo: 'PL 200/2022', ementa: 'Dia nacional', status: 'Aprovada', area_tematica: null, data_apresentacao: null, is_reforma_estrutural: false, url_oficial: null, classificacao_relevancia: 'SIMBOLICO' },
    ],
    votacoes_principais: [
      { proposicao_id: 'pr1', proposicao_titulo: 'PL 100/2023', proposicao_tipo: 'PL', proposicao_numero: 100, proposicao_ano: 2023, decisao: 'SIM', sessao_titulo: 'Sessão 1', sessao_data: '2023-05-10T10:00:00', sessao_aprovada: true, casa_legislativa: 'CAMARA_DOS_DEPUTADOS' },
      { proposicao_id: 'pr3', proposicao_titulo: 'PEC 3/2023', proposicao_tipo: 'PEC', proposicao_numero: 3, proposicao_ano: 2023, decisao: 'OBSTRUCAO', sessao_titulo: 'Sessão 2', sessao_data: '2023-06-10T10:00:00', sessao_aprovada: false, casa_legislativa: 'CAMARA_DOS_DEPUTADOS' },
    ],
    alinhamento_tematico: [{ eixo: 'Economia', total_votacoes: 10, votos_sim: 7, votos_nao: 3, votos_abstencao: 0, percentual_favoravel: 70 }],
    assiduidade: {
      total_sessoes: 100,
      total_presencas: 95,
      faltas_justificadas: 3,
      faltas_nao_justificadas: 2,
      total_faltas: 5,
      taxa_presenca_pct: 95,
      amostra_faltas: [{ data: '2023-04-01', tipo: 'FALTA_JUSTIFICADA', justificativa: 'Missão oficial', casa: 'CAMARA_DOS_DEPUTADOS' }],
    },
    evolucao_patrimonial: {
      resumo: { possui_dados: true, total_declaracoes: 2, primeiro_ano: 2018, primeiro_valor: 500000, primeiro_valor_formatado: 'R$ 500.000,00', ultimo_ano: 2022, ultimo_valor: 900000, ultimo_valor_formatado: 'R$ 900.000,00', crescimento_pct: 80, crescimento_absoluto: 400000 },
      historico: [
        { ano: 2018, valor: 500000, valor_formatado: 'R$ 500.000,00', detalhes: 'Imóvel' },
        { ano: 2022, valor: 900000, valor_formatado: 'R$ 900.000,00', detalhes: 'Imóvel e veículo' },
      ],
    },
    indices_inteligencia: {
      roi_cidadao: { score: 'B+', nota: 78, custo_total_operacional: 1200000, pontos_ialp: 40, custo_por_ponto_ialp: 30000, projetos_estruturantes: 4, diagnostico: 'ROI diagnóstico.' },
      concentracao_ceap: { indice_hhi: 1500, nivel_risco: 'MODERADO', percentual_maior_fornecedor: 33.3, maior_fornecedor: 'Gráfica Alfa LTDA', cnpj_maior_fornecedor: '12345678000190', diagnostico: 'HHI diagnóstico.' },
      enriquecimento_patrimonial: { delta_patrimonio: 400000, salario_acumulado_estimado: 1000000, razao_patrimonio_renda: 0.4, compatibilidade: 'COMPATÍVEL', diagnostico: 'Patrimônio diagnóstico.' },
      estabilidade_partidaria: { total_trocas: 1, anos_medio_por_partido: 6.5, classificacao: 'ALTA_FIDELIDADE', taxa_governismo_pct: 72, diagnostico: 'Estabilidade diagnóstico.' },
      eficiencia_emendas: { taxa_conversao_pct: 80, total_empenhado: 10000000, total_pago: 8000000, percentual_pix: 10, municipio_predileto: 'Campinas/SP', concentracao_municipio_predileto_pct: 37.5, classificacao: 'MÉDIA_EFICIÊNCIA', diagnostico: 'Emendas diagnóstico.' },
    },
  };
}

/**
 * Dossiê "esparso": exatamente o que a API devolve quando faltam dados (contrato do backend):
 * campos opcionais ausentes e índices com valores `null` em vez de números/classificações inventados.
 */
export function sparseDossier(): PoliticoDossier {
  return {
    perfil: {
      id: 'pol-2',
      nome_eleitoral: 'Beto Souza',
      nome_civil: 'Roberto Souza',
      cargo_atual: 'SENADOR',
      partido_atual: 'PL',
      uf: 'RJ',
      email: null,
      gabinete_sala: null,
      gabinete_telefone: null,
      foto_url: null,
    },
    trajetoria_mandatos: [],
    filiacoes_partidarias: [],
    remuneracao: {
      resumo: {
        salario_bruto_atual: null,
        salario_liquido_atual: null,
        media_ceap_mensal: null,
        total_bruto_2023: null,
        total_ceap_2023: null,
        total_beneficios_2023: null,
      },
      historico: [],
    },
    materias_propostas: [],
    votacoes_principais: [],
    assiduidade: { total_sessoes: 0, total_presencas: 0, faltas_justificadas: 0, faltas_nao_justificadas: 0, taxa_presenca_pct: null, amostra_faltas: [] },
    basometro: { taxa_governismo_pct: null, total_votacoes_analisadas: 0, votos_alinhados: null, votos_divergentes: null, classificacao: null },
    indices_inteligencia: {
      roi_cidadao: { score: null, nota: null, custo_total_operacional: null, pontos_ialp: null, custo_por_ponto_ialp: null, projetos_estruturantes: 0, diagnostico: 'Dados insuficientes.' },
      concentracao_ceap: { indice_hhi: null, nivel_risco: null, percentual_maior_fornecedor: null, maior_fornecedor: null, cnpj_maior_fornecedor: null, diagnostico: 'Sem despesas.' },
      enriquecimento_patrimonial: { delta_patrimonio: null, salario_acumulado_estimado: null, razao_patrimonio_renda: null, compatibilidade: null, diagnostico: 'Dados insuficientes.' },
      estabilidade_partidaria: { total_trocas: 0, anos_medio_por_partido: null, classificacao: null, taxa_governismo_pct: null, diagnostico: 'Sem filiações.' },
      eficiencia_emendas: { taxa_conversao_pct: null, total_empenhado: 0, total_pago: 0, percentual_pix: 0, municipio_predileto: null, concentracao_municipio_predileto_pct: 0, classificacao: null, diagnostico: 'Sem emendas.' },
    },
  };
}
