/**
 * Serviço de Integração com a API Backend (FastAPI)
 * Endpoints: Políticos, Séries Macroeconômicas, Analytics e Legislativo
 */

function resolveApiBaseUrl(): string {
  const envUrl = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (envUrl) {
    const clean = envUrl.replace(/\/+$/, "");
    return clean.endsWith("/api/v1") ? clean : `${clean}/api/v1`;
  }
  if (typeof window !== "undefined") {
    return "/api/v1";
  }
  return (process.env.INTERNAL_BACKEND_URL || "http://127.0.0.1:8000") + "/api/v1";
}

const API_BASE_URL = resolveApiBaseUrl();

export interface PresidenteHistorico {
  id_referencia: string;
  nome_civil: string;
  nome_eleitoral: string;
  partido_sigla: string;
  partido_nome: string;
  mandato_numero: number;
  ano_eleicao: number;
  data_inicio: string;
  data_fim: string | null;
  status_mandato: string;
  vice_presidente?: string;
  foto_url?: string;
  ministros_fazenda_chave: Array<{
    nome: string;
    inicio: string;
    fim: string | null;
    papel?: string;
  }>;
  marcos_economicos: string[];
}

export interface ScoreProsperidadeData {
  score_geral: number;
  subscore_economico: number;
  subscore_social: number;
  subscore_estabilidade: number;
  classificacao: string;
  destaque_positivo: string;
  destaque_atencao: string;
}

export interface TermometroRepassesData {
  m1_lider_per_capita: { uf: string; estado: string; valor_per_capita: number };
  m2_lider_per_capita: { uf: string; estado: string; valor_per_capita: number };
  diagnostico: string;
}

export interface MandatoPerformance {
  id_mandato: string;
  presidente: string;
  partido: string;
  data_inicio: string;
  data_fim: string;
  status_mandato: string;
  anos_cobertos: string;
  ipca_acumulado_pct: number;
  ipca_pos_real_pct: number;
  pib_crescimento_acumulado_pct: number;
  pib_medio_anual_pct: number;
  cambio_inicial_usd_brl: number | null;
  cambio_final_usd_brl: number | null;
  cambio_variacao_pct: number | null;
  divida_liquida_inicial_pct_pib: number | null;
  divida_liquida_final_pct_pib: number | null;
  divida_liquida_delta_pct: number | null;
  salario_minimo_inicial_brl: number | null;
  salario_minimo_final_brl: number | null;
  salario_minimo_inicial_usd: number | null;
  salario_minimo_final_usd: number | null;
  desemprego_inicial_pct?: number | null;
  desemprego_final_pct?: number | null;
  desemprego_medio_pct?: number | null;
  desmatamento_acumulado_km2?: number | null;
  desmatamento_medio_anual_km2?: number | null;
  fome_inicial_pct?: number | null;
  fome_final_pct?: number | null;
  fome_media_pct?: number | null;
  homicidios_inicial?: number | null;
  homicidios_final?: number | null;
  homicidios_medio?: number | null;
  feminicidios_inicial?: number | null;
  feminicidios_final?: number | null;
  feminicidios_medio?: number | null;
  valores_anuais?: Array<ResumoMacroeconomicoAnual>;
  ministros_fazenda_principais: string[];
  marcos_economicos_principais: string[];
  score_prosperidade?: ScoreProsperidadeData;
}

export interface ResumoMacroeconomicoAnual {
  ano: number;
  presidente_dominante: string;
  ipca_acumulado_ano_pct: number | null;
  pib_crescimento_real_pct: number | null;
  crescimento_pib_percentual?: number | null;
  inflacao_anual_ipca?: number | null;
  inflacao_acumulada_mandato?: number | null;
  taxa_desemprego_anual?: number | null;
  taxa_desmatamento_amazonia?: number | null;
  inseguranca_alimentar_pct?: number | null;
  cambio_dolar_medio: number | null;
  cotacao_dolar_fechamento?: number | null;
  salario_minimo?: number | null;
  taxa_homicidios?: number | null;
  taxa_feminicidios?: number | null;
  divida_liquida_pct_pib: number | null;
  salario_minimo_nominal_brl: number | null;
  ibovespa_fechamento?: number | null;
}

export interface PlacarVotos {
  SIM: number;
  NAO: number;
  ABSTENCAO: number;
  TOTAL: number;
}

export interface SessaoVotacaoDetalhes {
  sessao_id: string;
  data_hora: string;
  titulo?: string;
  descricao: string;
  aprovada: boolean;
  external_id?: string;
  placar?: PlacarVotos;
}

export interface ProposicaoLegislativa {
  id: string;
  camara_id: number;
  tipo: string;
  numero: number;
  ano: number;
  titulo: string;
  ementa: string;
  autor_nome?: string;
  area_tematica: string;
  data_apresentacao: string;
  status: string;
  is_reforma_estrutural: boolean;
  iniciativa_executivo: boolean;
  placar: PlacarVotos;
  sessao?: SessaoVotacaoDetalhes | null;
  placar_camara?: PlacarVotos;
  sessao_camara?: SessaoVotacaoDetalhes | null;
  sessoes_camara_lista?: SessaoVotacaoDetalhes[];
  placar_senado?: PlacarVotos;
  sessao_senado?: SessaoVotacaoDetalhes | null;
  sessoes_senado_lista?: SessaoVotacaoDetalhes[];
  url_oficial?: string | null;
}

export interface TrajectoryPoint {
  label: string;
  year_index: number;
  m1_calendar_year: number | null;
  m1_pib: number | null;
  m1_ipca: number | null;
  m1_usd: number | null;
  m1_salario_minimo?: number | null;
  m1_extrema_pobreza?: number | null;
  m1_analfabetismo?: number | null;
  m1_inseguranca_alimentar?: number | null;
  m1_gini?: number | null;
  m1_homicidios?: number | null;
  m1_feminicidios?: number | null;
  m1_desmatamento?: number | null;
  m2_calendar_year: number | null;
  m2_pib: number | null;
  m2_ipca: number | null;
  m2_usd: number | null;
  m2_salario_minimo?: number | null;
  m2_extrema_pobreza?: number | null;
  m2_analfabetismo?: number | null;
  m2_inseguranca_alimentar?: number | null;
  m2_gini?: number | null;
  m2_homicidios?: number | null;
  m2_feminicidios?: number | null;
  m2_desmatamento?: number | null;
}

export interface CompareSocialMetrics {
  extrema_pobreza_inicial_pct?: number | null;
  extrema_pobreza_final_pct?: number | null;
  analfabetismo_inicial_pct?: number | null;
  analfabetismo_final_pct?: number | null;
  inseguranca_alimentar_inicial_pct?: number | null;
  inseguranca_alimentar_final_pct?: number | null;
  gini_inicial?: number | null;
  gini_final?: number | null;
}

export interface CompareDeltas {
  ipca_acumulado_diff_pp: number;
  ipca_acumulado_relative_pct: number;
  pib_medio_diff_pp: number;
  pib_medio_relative_pct: number;
  pib_acumulado_diff_pp: number;
  cambio_variacao_diff_pp: number | null;
  salario_minimo_brl_diff?: number | null;
  salario_minimo_brl_relative_pct?: number | null;
  salario_minimo_usd_diff: number | null;
  salario_minimo_usd_relative_pct: number | null;
  extrema_pobreza_diff_pp?: number | null;
  analfabetismo_diff_pp?: number | null;
  inseguranca_alimentar_diff_pp?: number | null;
  gini_diff?: number | null;
  homicidios_medio_diff?: number | null;
  feminicidios_medio_diff?: number | null;
  desmatamento_medio_diff?: number | null;
}

export interface AreaRepasseComparison {
  area: string;
  sublabel: string;
  m1_total: number;
  m2_total: number;
  diff_brl: number;
  growth_pct: number;
}

export interface UFRepasseComparison {
  uf: string;
  estado_nome: string;
  regiao: string;
  m1_total: number;
  m2_total: number;
  diff_brl: number;
  growth_pct: number;
  m1_per_capita: number;
  m2_per_capita: number;
  diff_per_capita: number;
  areas: Record<string, { m1: number; m2: number; diff: number; growth_pct: number }>;
}

export interface RepassesComparison {
  by_area: Record<string, AreaRepasseComparison>;
  by_uf: UFRepasseComparison[];
  summary: {
    m1_total_geral: number;
    m2_total_geral: number;
    diff_total_brl: number;
    growth_total_pct: number;
  };
}

export interface CompareMandatesResponse {
  mandate1: MandatoPerformance & { sociais?: CompareSocialMetrics };
  mandate2: MandatoPerformance & { sociais?: CompareSocialMetrics };
  deltas: CompareDeltas;
  normalized_trajectory: TrajectoryPoint[];
  repasses_comparison?: RepassesComparison;
  scores_prosperidade?: {
    mandate1: ScoreProsperidadeData;
    mandate2: ScoreProsperidadeData;
    delta_score_geral: number;
    delta_economico: number;
    delta_social: number;
    delta_estabilidade: number;
  };
  termometro_repasses_apoio?: TermometroRepassesData;
}

async function fetchJson<T>(endpoint: string, fallbackData: T): Promise<T> {
  try {
    const res = await fetch(`${API_BASE_URL}${endpoint}`, {
      next: { revalidate: 60 },
      headers: { Accept: "application/json" }
    });
    if (!res.ok) {
      console.warn(`[API] Resposta não-200 em ${endpoint}: status ${res.status}`);
      return fallbackData;
    }
    return await res.json();
  } catch (error) {
    console.warn(`[API] Falha ao conectar em ${API_BASE_URL}${endpoint}:`, error);
    return fallbackData;
  }
}

export interface PartyBalanceItem {
  partido: string;
  bancada_atual: number;
  bancada_inicial: number;
  ganhos: number;
  perdas: number;
  saldo_liquido: number;
}

export interface NomadHistoryItem {
  partido: string;
  data_filiacao: string;
  data_desfiliacao: string | null;
  motivo: string | null;
  is_atual: boolean;
}

export interface TopNomad {
  id: string;
  nome_eleitoral: string;
  nome_civil: string;
  cargo: string;
  uf: string;
  foto_url: string | null;
  partido_atual: string;
  total_trocas: number;
  total_partidos: number;
  siglas_sequencia: string[];
  historico: NomadHistoryItem[];
}

export interface PartyFidelitySummary {
  total_parlamentares: number;
  total_nomades: number;
  taxa_migracao_pct: number;
  partido_maior_ganho: string | null;
  saldo_maior_ganho: number;
  partido_maior_perda: string | null;
  saldo_maior_perda: number;
}

export interface PartyFidelityResponse {
  party_balance: PartyBalanceItem[];
  top_nomads: TopNomad[];
  summary: PartyFidelitySummary;
}

export async function getPresidentes(): Promise<PresidenteHistorico[]> {
  return fetchJson<PresidenteHistorico[]>("/politicians/presidents", []);
}

export async function getMandatesPerformance(): Promise<MandatoPerformance[]> {
  return fetchJson<MandatoPerformance[]>("/analytics/mandates-performance", []);
}

export async function getAnnualMacroSummary(mandateId?: string | null): Promise<ResumoMacroeconomicoAnual[]> {
  const query = mandateId ? `?mandate_id=${encodeURIComponent(mandateId)}` : "";
  return fetchJson<ResumoMacroeconomicoAnual[]>(`/economic/annual-summary${query}`, []);
}

export async function getLegislativePropositions(): Promise<ProposicaoLegislativa[]> {
  return fetchJson<ProposicaoLegislativa[]>("/legislative/propositions", []);
}

export async function getCompareMandates(mandate1: string, mandate2: string): Promise<CompareMandatesResponse | null> {
  return fetchJson<CompareMandatesResponse | null>(
    `/analytics/compare-mandates?mandate1=${encodeURIComponent(mandate1)}&mandate2=${encodeURIComponent(mandate2)}`,
    null
  );
}

export async function getPartyFidelity(): Promise<PartyFidelityResponse | null> {
  return fetchJson<PartyFidelityResponse | null>("/analytics/party-fidelity", null);
}

export interface WagePoint {
  ano: number;
  presidente_dominante: string;
  salario_minimo_brl: number;
  salario_parlamentar_brl: number;
  multiplo_salarios_minimos: number;
  ipca_acumulado_ano_pct: number | null;
  indice_salario_minimo_base100: number;
  indice_salario_parlamentar_base100: number;
  indice_ipca_base100: number;
}

export interface MinimumWageVoteRecord {
  deputado_nome: string;
  partido_sigla: string;
  uf: string;
  cargo: string;
  voto: string;
  foto_url?: string | null;
}

export interface MinimumWageVotingSummary {
  proposicao_titulo: string;
  ementa: string;
  data_votacao: string;
  casa: string;
  placar: {
    SIM: number;
    NAO: number;
    ABSTENCAO: number;
    TOTAL: number;
  };
  votos_amostra: MinimumWageVoteRecord[];
}

export interface WageDisparityResponse {
  serie_historica: WagePoint[];
  votacao_salario_minimo: MinimumWageVotingSummary;
  estatisticas_disparidade: {
    salario_minimo_inicial_real_1994: number;
    salario_minimo_atual_2024: number;
    salario_parlamentar_inicial_1994: number;
    salario_parlamentar_atual_2024: number;
    multiplo_medio_historico: number;
    pico_multiplo_ano: number;
    pico_multiplo_valor: number;
    multiplo_atual: number;
    crescimento_acumulado_salario_minimo_pct: number;
    crescimento_acumulado_salario_parlamentar_pct: number;
  };
}

export interface LeaderProfile {
  nome: string;
  partido: string;
  uf: string;
  periodo: string;
  foto_url?: string | null;
}

export interface PartySeat {
  partido: string;
  cadeiras: number;
  percentual: number;
  alinhamento: "BASE_GOVERNO" | "INDEPENDENTE_CENTRO" | "OPOSICAO" | string;
  cor_hex: string;
}

export interface ChamberComposition {
  total_cadeiras: number;
  presidentes: LeaderProfile[];
  bancadas: PartySeat[];
  governabilidade: {
    base_aliada_cadeiras: number;
    base_aliada_pct: number;
    centro_cadeiras: number;
    centro_pct: number;
    oposicao_cadeiras: number;
    oposicao_pct: number;
    maioria_simples_atingida: boolean;
    maioria_pec_atingida: boolean;
  };
}

export interface CongressCompositionResponse {
  mandato_id: string;
  presidente_republica: string;
  periodo: string;
  camara: ChamberComposition;
  senado: ChamberComposition;
}

export interface StateTransferItem {
  uf: string;
  estado_nome: string;
  regiao: string;
  area_tematica: string;
  valor_pago_brl: number;
  populacao_estimada: number;
  valor_per_capita_brl: number;
}

export interface FederalTransfersResponse {
  mandato_id: string;
  periodo: string;
  total_repassado_brl: number;
  areas_resumo: Record<string, number>;
  regioes_resumo: Record<string, number>;
  por_uf: StateTransferItem[];
}

export async function getWageDisparity(): Promise<WageDisparityResponse | null> {
  return fetchJson<WageDisparityResponse | null>("/analytics/wage-disparity", null);
}

export async function getCongressComposition(mandateId: string = "lula-2023"): Promise<CongressCompositionResponse | null> {
  return fetchJson<CongressCompositionResponse | null>(
    `/analytics/congress-composition?mandate_id=${encodeURIComponent(mandateId)}`,
    null
  );
}

export async function getFederalTransfers(mandateId: string = "lula-2023", area?: string): Promise<FederalTransfersResponse | null> {
  const url = area
    ? `/analytics/federal-transfers?mandate_id=${encodeURIComponent(mandateId)}&area=${encodeURIComponent(area)}`
    : `/analytics/federal-transfers?mandate_id=${encodeURIComponent(mandateId)}`;
  return fetchJson<FederalTransfersResponse | null>(url, null);
}

// ==========================================
// VOTAÇÕES NOMINAIS DETALHADAS (ACCORDION/MODAL)
// ==========================================

export interface VotoNominalItem {
  voto_id: string;
  politico_id: string;
  nome_eleitoral: string;
  nome_civil: string;
  partido_sigla: string;
  uf: string;
  cargo: string;
  foto_url: string | null;
  decisao: "SIM" | "NAO" | "ABSTENCAO" | "OBSTRUCAO" | "AUSENTE" | string;
  sessao_id: string;
  sessao_titulo: string;
  casa_legislativa: string;
  data_sessao: string;
}

export interface PropositionVotesResponse {
  proposicao: {
    id: string;
    titulo: string;
    numero: number;
    ano: number;
    autor_nome: string;
    area_tematica?: string;
  } | null;
  sessao_ativa?: {
    id: string;
    titulo: string;
    descricao?: string;
    data_hora: string;
    casa: string;
    aprovada: boolean;
  } | null;
  sessoes_disponiveis?: Array<{
    id: string;
    titulo: string;
    data_hora: string;
    casa: string;
    aprovada: boolean;
  }>;
  total: number;
  votos: VotoNominalItem[];
}

export async function getPropositionVotes(
  propId: string,
  house?: string,
  sessionId?: string,
  search?: string,
  voteChoice?: string
): Promise<PropositionVotesResponse | null> {
  const params = new URLSearchParams();
  if (house) params.append("house", house);
  if (sessionId) params.append("session_id", sessionId);
  if (search) params.append("search", search);
  if (voteChoice) params.append("vote_choice", voteChoice);

  const query = params.toString() ? `?${params.toString()}` : "";
  return fetchJson<PropositionVotesResponse | null>(
    `/legislative/propositions/${encodeURIComponent(propId)}/votes${query}`,
    null
  );
}

// ==========================================
// RAIO-X INDIVIDUAL DO POLÍTICO (DOSSIÊ 360º)
// ==========================================

export interface PoliticoBuscaItem {
  id: string;
  nome_eleitoral: string;
  nome_civil: string;
  cargo: string;
  partido_sigla: string;
  partido_nome: string;
  uf: string;
  foto_url: string | null;
  camara_id?: number | null;
  senado_id?: number | null;
}

export type PoliticoSearchResultItem = PoliticoBuscaItem;

export interface PoliticoSearchResponse {
  total: number;
  limit: number;
  offset: number;
  politicos: PoliticoBuscaItem[];
}

export interface MandatoTrajetoria {
  id: string;
  cargo: string;
  esfera: string;
  ano_eleicao: number;
  numero_mandato: number;
  data_inicio: string | null;
  data_fim: string | null;
  status: string;
  partido_sigla: string;
  uf: string;
  total_votos?: number | null;
  percentual_votos?: number | null;
  coligacao?: string | null;
}

export interface FiliacaoHistorico {
  id: string;
  partido_sigla: string;
  partido_nome: string;
  data_filiacao: string | null;
  data_desfiliacao: string | null;
  is_atual: boolean;
  motivo_desfiliacao: string | null;
  uf?: string | null;
}

export interface RemuneracaoItem {
  ano: number;
  mes: number;
  salario_bruto: number;
  salario_liquido: number;
  cota_ceap: number;
  auxilio_moradia: number;
  outros_beneficios: number;
  fonte: string;
}

export interface ProposicaoAutorItem {
  id: string;
  tipo: string;
  numero: number;
  ano: number;
  titulo: string;
  ementa: string;
  status: string;
  area_tematica?: string | null;
  data_apresentacao?: string | null;
  is_reforma_estrutural: boolean;
  url_oficial?: string | null;
  classificacao_relevancia?: "IMPACTO" | "SIMBOLICO" | string;
  justificativa_relevancia?: string;
}

export interface VotoHistoricoItem {
  proposicao_id: string;
  proposicao_titulo: string;
  proposicao_tipo: string;
  proposicao_numero: number;
  proposicao_ano: number;
  decisao: string;
  sessao_titulo: string;
  sessao_data: string;
  sessao_aprovada: boolean;
  casa_legislativa: string;
}

export interface FaltaRegistro {
  data: string;
  tipo: string;
  justificativa?: string | null;
  casa: string;
}

export interface VotoHistoricoDetalhadoItem {
  proposicao_id: string;
  proposicao_titulo: string;
  proposicao_numero: string;
  proposicao_tipo: string;
  tema: string;
  setor?: string;
  eixo_impacto?: string;
  data: string;
  data_iso?: string | null;
  voto: string;
  decisao: string;
  sessao_titulo: string;
  sessao_aprovada: boolean;
  casa_legislativa: string;
  url_oficial?: string | null;
}

export interface DeclaracaoPatrimonioItem {
  ano: number;
  valor: number;
  valor_formatado: string;
  detalhes: string;
}

export interface EvolucaoPatrimonialResumo {
  possui_dados: boolean;
  total_declaracoes: number;
  primeiro_ano: number | null;
  primeiro_valor: number;
  primeiro_valor_formatado: string;
  ultimo_ano: number | null;
  ultimo_valor: number;
  ultimo_valor_formatado: string;
  crescimento_pct: number;
  crescimento_absoluto: number;
}

export interface EvolucaoPatrimonial {
  resumo: EvolucaoPatrimonialResumo;
  historico: DeclaracaoPatrimonioItem[];
}

export interface CeapGastoTipo {
  tipo_despesa: string;
  total_gasto: number;
  percentual: number;
}

export interface CeapFornecedor {
  nome_fornecedor: string;
  cnpj_cpf: string | null;
  total_recebido: number;
  num_notas: number;
}

export interface CeapDespesaRecente {
  ano: number;
  mes: number | null;
  tipo_despesa: string;
  valor_liquido: number;
  nome_fornecedor: string;
  cnpj_cpf: string | null;
  data_emissao: string | null;
  documento_url: string | null;
}

export interface CustosCeapData {
  possui_dados: boolean;
  gasto_total_recente: number;
  total_notas: number;
  gastos_por_tipo: CeapGastoTipo[];
  maiores_fornecedores: CeapFornecedor[];
  despesas_recentes: CeapDespesaRecente[];
}

export interface EmendaDestinoItem {
  localidade: string;
  valor_pago: number;
  percentual: number;
}

export interface EmendaDistribuicaoItem {
  tipo?: string;
  area?: string;
  valor_pago: number;
  percentual: number;
}

export interface EmendaDetalheItem {
  id: string;
  ano: number;
  codigo_emenda: string | null;
  tipo_emenda: string;
  valor_empenhado: number;
  valor_pago: number;
  localidade_destino: string;
  funcao: string | null;
}

export interface EmendasParlamentaresData {
  possui_dados: boolean;
  total_empenhado: number;
  total_pago: number;
  percentual_execucao: number;
  destinos_principais: EmendaDestinoItem[];
  distribuicao_por_tipo: EmendaDistribuicaoItem[];
  distribuicao_por_area: EmendaDistribuicaoItem[];
  lista_emendas: EmendaDetalheItem[];
}

export interface CertidaoItem {
  id: string;
  orgao: string;
  tipo_certidao: string;
  status_ficha: string;
  detalhes: string | null;
  numero_processo?: string | null;
  data_emissao?: string | null;
  link_comprovacao?: string | null;
  codigo_autenticidade?: string | null;
  tipo?: string;
  status?: string;
}

export interface ProcessoDetalhadoItem {
  numero_processo: string;
  tribunal: string;
  data_processo: string;
  classe_assunto: string;
  descricao: string;
  situacao_juridica: string;
  link_comprovacao: string;
  status_resumo: string;
}

export interface FichaLimpaData {
  possui_processos_declarados: boolean;
  status_geral: string;
  orgaos_declarados: string[];
  link_tse_divulgacand?: string;
  processos_detalhados?: ProcessoDetalhadoItem[];
  certidoes: CertidaoItem[];
}

export interface DoacaoItem {
  id: string;
  ano_eleicao: number;
  nome_doador: string;
  cpf_cnpj_doador: string | null;
  valor_doado: number;
  tipo_receita?: string | null;
}

export interface TopDoadorItem {
  nome_doador: string;
  cpf_cnpj_doador: string | null;
  valor_doado: number;
  tipo_receita?: string | null;
  percentual: number;
}

export interface FinanciamentoCampanhaData {
  possui_dados: boolean;
  ano_eleicao: number;
  total_arrecadado: number;
  total_doadores: number;
  top_doadores: TopDoadorItem[];
  todas_doacoes: DoacaoItem[];
}

export interface BasometroData {
  taxa_governismo_pct: number;
  total_votacoes_analisadas: number;
  votos_alinhados: number;
  votos_divergentes: number;
  classificacao: string;
  partido_sigla?: string;
}

export interface RelevanciaLegislativaData {
  total_proposicoes: number;
  projetos_impacto: number;
  projetos_simbolicos: number;
  percentual_impacto: number;
  percentual_simbolico: number;
  diagnostico: string;
}

export interface RoiCidadaoData {
  score: string;
  nota: number;
  custo_total_operacional: number;
  custo_por_projeto_impacto: number;
  projetos_estruturantes: number;
  diagnostico: string;
}

export interface ConcentracaoCeapData {
  indice_hhi: number;
  nivel_risco: "ALERTA" | "MODERADO" | "BAIXO";
  percentual_maior_fornecedor: number;
  maior_fornecedor: string | null;
  cnpj_maior_fornecedor: string | null;
  diagnostico: string;
}

export interface EnriquecimentoPatrimonialData {
  delta_patrimonio: number;
  salario_acumulado_estimado: number;
  razao_patrimonio_renda: number;
  compatibilidade: "COMPATÍVEL" | "MODERADO" | "ATÍPICO";
  diagnostico: string;
}

export interface EstabilidadePartidariaData {
  total_trocas: number;
  anos_medio_por_partido: number;
  classificacao: string;
  taxa_governismo_pct: number;
  diagnostico: string;
}

export interface EficienciaEmendasData {
  taxa_conversao_pct: number;
  total_empenhado: number;
  total_pago: number;
  percentual_pix: number;
  municipio_predileto: string | null;
  concentracao_municipio_predileto_pct: number;
  classificacao: string;
  diagnostico: string;
}

export interface IndicesInteligenciaData {
  roi_cidadao: RoiCidadaoData;
  concentracao_ceap: ConcentracaoCeapData;
  enriquecimento_patrimonial: EnriquecimentoPatrimonialData;
  estabilidade_partidaria: EstabilidadePartidariaData;
  eficiencia_emendas: EficienciaEmendasData;
}

export interface PoliticoDossier {
  perfil: {
    id: string;
    nome_eleitoral: string;
    nome_civil: string;
    cpf?: string | null;
    genero?: string | null;
    data_nascimento?: string | null;
    naturalidade?: string;
    foto_url?: string | null;
    cargo_atual: string;
    partido_atual: string;
    uf: string;
    biografia?: string | null;
    email?: string | null;
    gabinete_sala?: string | null;
    gabinete_telefone?: string | null;
    redes_sociais?: Record<string, any> | null;
    camara_id?: number | null;
    senado_id?: number | null;
    possui_processos_declarados?: boolean;
  };
  trajetoria_mandatos: MandatoTrajetoria[];
  filiacoes_partidarias: FiliacaoHistorico[];
  remuneracao: {
    resumo: {
      salario_bruto_atual: number;
      salario_liquido_atual: number;
      media_ceap_mensal: number;
      total_bruto_2023: number;
      total_ceap_2023: number;
      total_beneficios_2023: number;
    };
    historico: RemuneracaoItem[];
  };
  custos_ceap?: CustosCeapData;
  emendas_parlamentares?: EmendasParlamentaresData;
  ficha_limpa?: FichaLimpaData;
  financiamento_campanha?: FinanciamentoCampanhaData;
  basometro?: BasometroData;
  relevancia_legislativa?: RelevanciaLegislativaData;
  materias_propostas: ProposicaoAutorItem[];
  votacoes_principais: VotoHistoricoItem[];
  historico_votos?: VotoHistoricoDetalhadoItem[];
  alinhamento_tematico?: Array<{
    eixo: string;
    total_votacoes: number;
    votos_sim: number;
    votos_nao: number;
    votos_abstencao: number;
    percentual_favoravel: number;
  }>;
  assiduidade: {
    total_sessoes: number;
    total_presencas: number;
    faltas_justificadas: number;
    faltas_nao_justificadas: number;
    taxa_presenca_pct: number;
    amostra_faltas: FaltaRegistro[];
  };
  evolucao_patrimonial?: EvolucaoPatrimonial;
  indices_inteligencia?: IndicesInteligenciaData;
}

export interface IndicadorSocialAnual {
  ano: number;
  analfabetismo_pct: number | null;
  extrema_pobreza_pct: number | null;
  extrema_pobreza_milhoes: number | null;
  inseguranca_alimentar_pct: number | null;
  inseguranca_alimentar_milhoes: number | null;
  gini: number | null;
  fonte?: string;
}

export interface ClasseSocialItem {
  classe: string;
  faixa_salarios_minimos: string;
  faixa_salarios_minimos_min: number;
  faixa_salarios_minimos_max: number | null;
  renda_familiar_min_brl: number;
  renda_familiar_max_brl: number | null;
  faixa_renda_formatada: string;
  percentual_populacao: number;
  descricao: string;
  cor: string;
  destaque: string;
}

export interface ClassesSociaisResponse {
  salario_minimo_referencia_brl: number;
  ano_referencia: number;
  fonte: string;
  resumo_populacional: {
    maioria_populacao_acumulada_d_e_pct: number;
    texto_educativo: string;
  };
  classes: ClasseSocialItem[];
}

export interface EstadoEleicaoSocialItem {
  uf: string;
  estado_nome: string;
  regiao: string;
  ano_eleicao: number;
  vencedor_nome: string;
  vencedor_partido: string;
  vencedor_votos_pct: number;
  segundo_nome: string;
  segundo_partido: string;
  segundo_votos_pct: number;
  taxa_analfabetismo_pct: number | null;
  extrema_pobreza_pct: number | null;
  inseguranca_alimentar_pct: number | null;
  indice_gini: number | null;
}

export interface RegiaoSocialEleicaoResumo {
  regiao: string;
  total_estados: number;
  media_extrema_pobreza_pct: number;
  media_analfabetismo_pct: number;
  vencedores_contagem: Record<string, number>;
}

export interface SocialElectionsResponse {
  ano_eleicao: number;
  total_estados: number;
  anos_disponiveis: number[];
  regioes_resumo: RegiaoSocialEleicaoResumo[];
  estados: EstadoEleicaoSocialItem[];
}

export async function searchPoliticians(
  search?: string,
  office?: string,
  party?: string,
  uf?: string,
  limit: number = 80
): Promise<PoliticoSearchResponse | null> {
  const params = new URLSearchParams();
  if (search) params.append("search", search);
  if (office) params.append("office", office);
  if (party) params.append("party", party);
  if (uf) params.append("uf", uf);
  params.append("limit", limit.toString());

  return fetchJson<PoliticoSearchResponse | null>(`/politicians?${params.toString()}`, null);
}

export async function getPoliticianDossier(politicianId: string): Promise<PoliticoDossier | null> {
  return fetchJson<PoliticoDossier | null>(`/politicians/${encodeURIComponent(politicianId)}`, null);
}

export async function getSocialIndicators(): Promise<IndicadorSocialAnual[]> {
  return fetchJson<IndicadorSocialAnual[]>("/analytics/social-indicators", []);
}

export async function getSocialClasses(): Promise<ClassesSociaisResponse | null> {
  return fetchJson<ClassesSociaisResponse | null>("/analytics/social-classes", null);
}

export async function getSocialElectionsCorrelation(ano?: number): Promise<SocialElectionsResponse | null> {
  const q = ano ? `?ano=${ano}` : "";
  return fetchJson<SocialElectionsResponse | null>(`/analytics/social-elections${q}`, null);
}

// ==========================================
// PRODUTIVIDADE & EXPLORADOR LEGISLATIVO
// ==========================================

export interface SetorDistribuicaoItem {
  setor: string;
  total: number;
  percentual: number;
}

export interface AuthorProductivityItem {
  posicao: number;
  politico_id: string;
  nome_eleitoral: string;
  nome_civil: string;
  partido_sigla: string;
  espectro_politico: string;
  uf: string;
  cargo: string;
  foto_url?: string | null;
  total_proposicoes: number;
  principal_setor: string;
  total_principal_setor: number;
  distribuicao_setores: SetorDistribuicaoItem[];
}

export interface PropositionExplorerPlacar {
  sim: number;
  nao: number;
  abstencao: number;
  total: number;
  resultado: string;
}

export interface PropositionExplorerItem {
  id: string;
  camara_id?: number | null;
  tipo: string;
  numero: number;
  ano: number;
  titulo: string;
  ementa: string;
  setor: string;
  eixo_impacto: string;
  autor_nome: string;
  autor_politico_id?: string | null;
  autor_partido: string;
  autor_uf: string;
  autor_foto?: string | null;
  status: string;
  data_apresentacao: string;
  is_reforma_estrutural: boolean;
  iniciativa_executivo: boolean;
  tem_votacao: boolean;
  sessao_id?: string | null;
  placar: PropositionExplorerPlacar;
  url_oficial?: string | null;
}

export interface LegislativeExplorerResponse {
  total: number;
  page: number;
  limit: number;
  total_pages: number;
  setores_disponiveis: string[];
  items: PropositionExplorerItem[];
}

export interface ParlamentarVotoNominalItem {
  politico_id: string;
  nome_eleitoral: string;
  nome_civil: string;
  partido_sigla: string;
  espectro_politico: string;
  uf: string;
  cargo: string;
  foto_url?: string | null;
  decisao: string;
}

export interface PropositionNominalVotesSplitResponse {
  proposicao: {
    id: string;
    titulo: string;
    numero: number;
    ano: number;
    ementa: string;
    setor?: string;
    autor_nome?: string;
    status: string;
    data_apresentacao: string;
  } | null;
  sessao: {
    id: string;
    titulo: string;
    descricao?: string;
    data_hora: string;
    casa_legislativa: string;
    aprovada: boolean;
    total_votos: number;
  } | null;
  placar: {
    sim: number;
    nao: number;
    abstencao: number;
    obstrucao: number;
    total: number;
  };
  votos_sim: ParlamentarVotoNominalItem[];
  votos_nao: ParlamentarVotoNominalItem[];
  votos_abstencao: ParlamentarVotoNominalItem[];
  votos_obstrucao: ParlamentarVotoNominalItem[];
}

export async function getAuthorsProductivityRanking(
  limit: number = 20,
  partido?: string,
  setor?: string
): Promise<AuthorProductivityItem[]> {
  const q = new URLSearchParams();
  q.append("limit", String(limit));
  if (partido && partido.toUpperCase() !== "TODOS") q.append("partido", partido.trim());
  if (setor && setor.toUpperCase() !== "TODOS") q.append("setor", setor.trim());
  return fetchJson<AuthorProductivityItem[]>(`/legislative/ranking/authors?${q.toString()}`, []);
}

export interface PartidoCatalogoItem {
  id: string;
  sigla: string;
  nome_completo: string;
  numero_eleitoral: number | null;
  espectro_politico: "ESQUERDA" | "CENTRO_ESQUERDA" | "CENTRO" | "CENTRO_DIREITA" | "DIREITA" | string;
  ideologia: string;
  lema: string;
  logo_url?: string | null;
  total_deputados: number;
  total_senadores: number;
  total_parlamentares: number;
  total_filiados_ativos: number;
  cor_hex: string;
}

export async function getParties(): Promise<PartidoCatalogoItem[]> {
  return fetchJson<PartidoCatalogoItem[]>("/parties", []);
}

export async function getLegislativeExplorer(params?: {
  search?: string;
  setor?: string;
  tipo?: string;
  status?: string;
  apenas_votadas?: boolean;
  page?: number;
  limit?: number;
}): Promise<LegislativeExplorerResponse | null> {
  const q = new URLSearchParams();
  if (params?.search) q.append("search", params.search);
  if (params?.setor) q.append("setor", params.setor);
  if (params?.tipo) q.append("tipo", params.tipo);
  if (params?.status) q.append("status", params.status);
  if (params?.apenas_votadas !== undefined) q.append("apenas_votadas", String(params.apenas_votadas));
  if (params?.page) q.append("page", String(params.page));
  if (params?.limit) q.append("limit", String(params.limit));

  return fetchJson<LegislativeExplorerResponse | null>(`/legislative/explorer?${q.toString()}`, null);
}

export async function getPropositionNominalVotesSplit(
  propId: string,
  search?: string
): Promise<PropositionNominalVotesSplitResponse | null> {
  const q = search ? `?search=${encodeURIComponent(search)}` : "";
  return fetchJson<PropositionNominalVotesSplitResponse | null>(
    `/legislative/propositions/${encodeURIComponent(propId)}/nominal-votes${q}`,
    null
  );
}

// ==========================================
// DIÁRIO DO CONGRESSO (CALENDÁRIO)
// ==========================================

export interface SessaoCalendarioItem {
  sessao_id: string;
  casa: string;
  casa_nome: string;
  hora: string;
  titulo: string;
  descricao: string;
  aprovada: boolean;
  placar: {
    sim: number;
    nao: number;
    abstencao: number;
    total: number;
  };
  proposicao: {
    id: string;
    titulo: string;
    tipo: string;
    numero: number;
    ano: number;
    ementa: string;
    setor: string;
    autor_nome: string;
    status: string;
    url_oficial: string | null;
  };
}

export interface DiaVotacaoItem {
  data: string;
  dia: number;
  mes: number;
  ano: number;
  dia_semana: string;
  data_formatada: string;
  total_votacoes: number;
  camara_count: number;
  senado_count: number;
  sessoes: SessaoCalendarioItem[];
}

export interface CalendarioVotacoesResponse {
  ano_selecionado: number;
  anos_disponiveis: number[];
  estatisticas_anuais: {
    ano: number;
    total_dias_ano: number;
    dias_com_votacao: number;
    percentual_dias_ativos: number;
    total_sessoes_ano: number;
    texto_estatistica: string;
  };
  dias: DiaVotacaoItem[];
}

export async function getVotingCalendar(year?: number): Promise<CalendarioVotacoesResponse | null> {
  const query = year ? `?year=${year}` : "";
  return fetchJson<CalendarioVotacoesResponse | null>(`/legislative/calendar${query}`, null);
}

// ==========================================
// CIDADANIA ATIVA: CONSULTAS PÚBLICAS & VOTAÇÕES
// ==========================================

export interface ConsultaPublicaItem {
  id_externo: string;
  casa: string;
  sigla_projeto: string;
  ementa: string;
  link_oficial_votacao: string;
  link_tramitacao_oficial?: string | null;
  em_votacao_aberta?: boolean;
  votos_sim: number | null;
  votos_nao: number | null;
  total_votos?: number | null;
  percentual_sim?: number | null;
  percentual_nao?: number | null;
  tema?: string | null;
  status?: string | null;
  autor?: string | null;
  data_apresentacao?: string | null;
  destaque?: boolean;
}

export async function getConsultasPublicas(casa?: string, forceRefresh?: boolean): Promise<ConsultaPublicaItem[]> {
  const params = new URLSearchParams();
  if (casa) params.set("casa", casa);
  if (forceRefresh) params.set("force_refresh", "true");
  const query = params.toString() ? `?${params.toString()}` : "";
  return fetchJson<ConsultaPublicaItem[]>(`/cidadania/consultas${query}`, []);
}





