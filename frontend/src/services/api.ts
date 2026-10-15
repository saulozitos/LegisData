/**
 * Serviço de Integração com a API Backend (FastAPI)
 * Endpoints: Políticos, Séries Macroeconômicas, Analytics e Legislativo
 */

import { ApiError, isAbortError } from "@/lib/errors";

export { ApiError, isAbortError };

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
  iple?: IpleData;
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
  iple?: {
    mandate1?: IpleData;
    mandate2?: IpleData;
    delta_iple_score?: number | null;
  };
}

/**
 * Executa um GET na API e devolve o JSON. Qualquer falha (rede, HTTP não-2xx,
 * corpo inválido) lança `ApiError`; o cancelamento via `signal` propaga o
 * `AbortError` original para que o chamador possa ignorá-lo.
 */
async function fetchJson<T>(endpoint: string, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${endpoint}`, {
      headers: { Accept: "application/json" },
      signal,
    });
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw new ApiError("Não foi possível conectar à API.", endpoint);
  }
  if (!res.ok) {
    throw new ApiError(`A API respondeu com status ${res.status}.`, endpoint, res.status);
  }
  try {
    return (await res.json()) as T;
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw new ApiError("Resposta inválida da API.", endpoint, res.status);
  }
}

const CATALOG_TTL_MS = 5 * 60 * 1000;
const catalogCache = new Map<string, { at: number; promise: Promise<unknown> }>();

function abortError(): Error {
  const err = new Error("The operation was aborted.");
  err.name = "AbortError";
  return err;
}

/**
 * Cache em memória (com TTL) para catálogos que várias telas consultam. A requisição
 * compartilhada não é abortável; cada chamador apenas deixa de aguardá-la ao abortar.
 */
function cachedFetch<T>(key: string, load: () => Promise<T>, signal?: AbortSignal): Promise<T> {
  let entry = catalogCache.get(key);
  if (!entry || Date.now() - entry.at > CATALOG_TTL_MS) {
    const promise = load();
    const created = { at: Date.now(), promise };
    entry = created;
    catalogCache.set(key, created);
    promise.catch(() => {
      if (catalogCache.get(key) === created) catalogCache.delete(key);
    });
  }
  const shared = entry.promise as Promise<T>;
  if (!signal) return shared;
  if (signal.aborted) return Promise.reject(abortError());
  return new Promise<T>((resolve, reject) => {
    const onAbort = () => reject(abortError());
    signal.addEventListener("abort", onAbort, { once: true });
    shared.then(
      (value) => {
        signal.removeEventListener("abort", onAbort);
        resolve(value);
      },
      (err) => {
        signal.removeEventListener("abort", onAbort);
        reject(err);
      }
    );
  });
}

/** Verificação real de disponibilidade da API (usada pelo selo do cabeçalho). */
export async function getApiHealth(signal?: AbortSignal): Promise<{ status: string }> {
  const envUrl = process.env.NEXT_PUBLIC_API_URL?.trim();
  const healthUrl = envUrl
    ? `${envUrl.replace(/\/+$/, "").replace(/\/api\/v1$/, "")}/health`
    : "/api/health";
  let res: Response;
  try {
    res = await fetch(healthUrl, { headers: { Accept: "application/json" }, signal, cache: "no-store" });
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw new ApiError("API indisponível.", healthUrl);
  }
  if (!res.ok) throw new ApiError(`A API respondeu com status ${res.status}.`, healthUrl, res.status);
  return (await res.json()) as { status: string };
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

export async function getPresidentes(signal?: AbortSignal): Promise<PresidenteHistorico[]> {
  return fetchJson<PresidenteHistorico[]>("/politicians/presidents", signal);
}

export async function getMandatesPerformance(signal?: AbortSignal): Promise<MandatoPerformance[]> {
  return fetchJson<MandatoPerformance[]>("/analytics/mandates-performance", signal);
}

export async function getAnnualMacroSummary(
  mandateId?: string | null,
  signal?: AbortSignal
): Promise<ResumoMacroeconomicoAnual[]> {
  const query = mandateId ? `?mandate_id=${encodeURIComponent(mandateId)}` : "";
  return fetchJson<ResumoMacroeconomicoAnual[]>(`/economic/annual-summary${query}`, signal);
}

export async function getLegislativePropositions(signal?: AbortSignal): Promise<ProposicaoLegislativa[]> {
  return fetchJson<ProposicaoLegislativa[]>("/legislative/propositions", signal);
}

export async function getCompareMandates(
  mandate1: string,
  mandate2: string,
  signal?: AbortSignal
): Promise<CompareMandatesResponse> {
  return fetchJson<CompareMandatesResponse>(
    `/analytics/compare-mandates?mandate1=${encodeURIComponent(mandate1)}&mandate2=${encodeURIComponent(mandate2)}`,
    signal
  );
}

export async function getPartyFidelity(signal?: AbortSignal): Promise<PartyFidelityResponse> {
  return fetchJson<PartyFidelityResponse>("/analytics/party-fidelity", signal);
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

export interface IpleCrispSetItem {
  score: number;
  corte: number;
  crisp_val: number;
  classificacao: string;
}

export interface IpleCrispSet {
  ts: IpleCrispSetItem;
  tmv: IpleCrispSetItem;
  iple: IpleCrispSetItem;
  oposicao_x1: IpleCrispSetItem;
  fragmentacao_x2: IpleCrispSetItem;
  polarizacao_x3: IpleCrispSetItem;
}

export interface IpleBaseIndicators {
  proposicoes_executivo_total: number;
  proposicoes_executivo_aprovadas: number;
  vetos_total_apreciados: number;
  vetos_mantidos: number;
  vetos_pendentes_pauta: number;
  taxa_sucesso_ts: number;
  taxa_manutencao_vetos_tmv: number;
  iple_score: number;
}

export interface IpleContextualVariables {
  tamanho_oposicao_x1: number;
  oposicao_cadeiras: number;
  total_cadeiras: number;
  fragmentacao_nep_x2: number;
  polarizacao_ipp_x3: number;
}

export interface IpleData {
  mandato_id: string;
  presidente: string;
  periodo: string;
  indicadores_base: IpleBaseIndicators;
  variaveis_contextuais: IpleContextualVariables;
  calibragem_crisp_set: IpleCrispSet;
  classificacao_geral: string;
}

export interface CongressCompositionResponse {
  mandato_id: string;
  presidente_republica: string;
  periodo: string;
  camara: ChamberComposition;
  senado: ChamberComposition;
  iple?: IpleData;
}

export interface StateTransferItem {
  uf: string;
  estado_nome: string;
  regiao: string;
  area_tematica: string;
  valor_pago_brl: number;
  populacao_estimada: number | null;
  valor_per_capita_brl: number | null;
}

export interface FederalTransfersResponse {
  mandato_id: string;
  periodo: string;
  total_repassado_brl: number;
  areas_resumo: Record<string, number>;
  regioes_resumo: Record<string, number>;
  por_uf: StateTransferItem[];
}

export async function getWageDisparity(signal?: AbortSignal): Promise<WageDisparityResponse> {
  return fetchJson<WageDisparityResponse>("/analytics/wage-disparity", signal);
}

export async function getExecutiveIple(
  mandateId?: string,
  signal?: AbortSignal
): Promise<IpleData> {
  const q = mandateId ? `?mandate_id=${encodeURIComponent(mandateId)}` : "";
  return fetchJson<IpleData>(`/executivo/iple${q}`, signal);
}

export async function getAllExecutiveIple(
  signal?: AbortSignal
): Promise<IpleData[]> {
  return fetchJson<IpleData[]>("/executivo/iple", signal);
}

export async function getCongressComposition(
  mandateId: string,
  signal?: AbortSignal
): Promise<CongressCompositionResponse> {
  return fetchJson<CongressCompositionResponse>(
    `/analytics/congress-composition?mandate_id=${encodeURIComponent(mandateId)}`,
    signal
  );
}

export async function getFederalTransfers(
  mandateId: string,
  area?: string,
  signal?: AbortSignal
): Promise<FederalTransfersResponse> {
  const url = area
    ? `/analytics/federal-transfers?mandate_id=${encodeURIComponent(mandateId)}&area=${encodeURIComponent(area)}`
    : `/analytics/federal-transfers?mandate_id=${encodeURIComponent(mandateId)}`;
  return fetchJson<FederalTransfersResponse>(url, signal);
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
    is_votacao_secreta?: boolean;
    placar?: { SIM: number; NAO: number; ABSTENCAO: number; TOTAL: number };
  } | null;
  sessoes_disponiveis?: Array<{
    id: string;
    titulo: string;
    data_hora: string;
    casa: string;
    aprovada: boolean;
    is_votacao_secreta?: boolean;
  }>;
  is_votacao_secreta?: boolean;
  aviso?: string;
  placar?: { SIM: number; NAO: number; ABSTENCAO: number; TOTAL: number };
  total: number;
  total_correspondente?: number;
  truncado?: boolean;
  votos: VotoNominalItem[];
}

export async function getPropositionVotes(
  propId: string,
  house?: string,
  sessionId?: string,
  search?: string,
  voteChoice?: string,
  signal?: AbortSignal
): Promise<PropositionVotesResponse> {
  const params = new URLSearchParams();
  if (house) params.append("house", house);
  if (sessionId) params.append("session_id", sessionId);
  if (search) params.append("search", search);
  if (voteChoice) params.append("vote_choice", voteChoice);

  const query = params.toString() ? `?${params.toString()}` : "";
  return fetchJson<PropositionVotesResponse>(
    `/legislative/propositions/${encodeURIComponent(propId)}/votes${query}`,
    signal
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
  // A fonte oficial só informa o bruto mensal (e o líquido do mês mais recente): o resto vem null.
  salario_liquido: number | null;
  cota_ceap: number | null;
  auxilio_moradia: number | null;
  outros_beneficios: number | null;
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
  papel_autoria?: "AUTOR_PRINCIPAL" | "COAUTOR" | string;
  peso_participacao?: number;
  peso_complexidade?: number;
  bonus_tramitacao?: number;
  score_calculado?: number;
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
  /** `null` quando não há orientação de governo por votação (o backend não inventa baseline). */
  taxa_governismo_pct: number | null;
  total_votacoes_analisadas: number;
  votos_alinhados: number | null;
  votos_divergentes: number | null;
  classificacao: string | null;
  partido_sigla?: string;
  /** Falso quando há menos votações com orientação do governo que `amostra_minima`. */
  dados_suficientes?: boolean;
  amostra_minima?: number;
  metodologia?: string;
}

export interface RelevanciaLegislativaData {
  total_proposicoes: number;
  total_proposicoes_registradas?: number;
  amostra_limitada?: boolean;
  projetos_impacto: number;
  projetos_simbolicos: number;
  percentual_impacto: number;
  percentual_simbolico: number;
  diagnostico: string;
  lideranca_legislativa_count?: number;
  apoio_politico_count?: number;
  taxa_eficiencia_pct?: number;
  score_atividade_ponderada?: number;
  distribuicao_complexidade?: {
    alta: number;
    media: number;
    baixa: number;
  };
  score_ialp?: number;
  desvio_foco?: {
    estruturais: number;
    burocraticas: number;
    proporcao_estrutural_pct: number;
    diagnostico?: string;
  };
}

export interface RoiCidadaoData {
  /** `null` quando faltam CEAP, remuneração ou presenças para calcular o indicador. */
  score: string | null;
  nota: number | null;
  custo_total_operacional: number | null;
  custo_por_projeto_impacto: number | null;
  projetos_estruturantes: number;
  diagnostico: string;
}

export interface ConcentracaoCeapData {
  indice_hhi: number;
  nivel_risco: "ALERTA" | "MODERADO" | "BAIXO" | null;
  percentual_maior_fornecedor: number;
  maior_fornecedor: string | null;
  cnpj_maior_fornecedor: string | null;
  diagnostico: string;
}

export interface EnriquecimentoPatrimonialData {
  delta_patrimonio: number | null;
  salario_acumulado_estimado: number | null;
  razao_patrimonio_renda: number | null;
  compatibilidade: "COMPATÍVEL" | "MODERADO" | "ATÍPICO" | null;
  diagnostico: string;
}

export interface EstabilidadePartidariaData {
  total_trocas: number;
  anos_medio_por_partido: number | null;
  classificacao: string | null;
  taxa_governismo_pct: number | null;
  diagnostico: string;
}

export interface EficienciaEmendasData {
  taxa_conversao_pct: number | null;
  total_empenhado: number;
  total_pago: number;
  percentual_pix: number;
  municipio_predileto: string | null;
  concentracao_municipio_predileto_pct: number;
  classificacao: string | null;
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
    redes_sociais?: Record<string, string | null> | null;
    camara_id?: number | null;
    senado_id?: number | null;
    possui_processos_declarados?: boolean;
  };
  trajetoria_mandatos: MandatoTrajetoria[];
  filiacoes_partidarias: FiliacaoHistorico[];
  remuneracao: {
    resumo: {
      salario_bruto_atual: number | null;
      salario_liquido_atual: number | null;
      media_ceap_mensal: number | null;
      total_bruto_2023: number | null;
      total_ceap_2023: number | null;
      total_beneficios_2023: number | null;
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
    /** null no Senado: a fonte (votações nominais) não distingue ausência não justificada. */
    faltas_nao_justificadas: number | null;
    taxa_presenca_pct: number | null;
    amostra_faltas: FaltaRegistro[];
    periodo_inicio?: string | null;
    periodo_fim?: string | null;
    /** Unidade da contagem (ex.: "dia com sessão deliberativa"). */
    unidade?: string | null;
    fonte?: string | null;
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
  /** Pessoas por classe de renda domiciliar total (PNAD) ou estimativa de referência. */
  percentual_populacao: number;
  /** Domicílios por classe de renda domiciliar total; só presente quando a origem é a PNAD. */
  percentual_domicilios?: number;
  descricao: string;
  cor: string;
  destaque: string;
}

export interface ClassesSociaisResponse {
  /** `pnad`: calculado dos microdados da PNAD Contínua; `referencia_fixa`: estimativa fixa rotulada. */
  origem?: "pnad" | "referencia_fixa";
  salario_minimo_referencia_brl: number;
  ano_referencia: number;
  anos_disponiveis?: number[];
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
  limit: number = 80,
  mandateIdOrSignal?: string | AbortSignal,
  signal?: AbortSignal
): Promise<PoliticoSearchResponse> {
  const actualSignal = mandateIdOrSignal instanceof AbortSignal ? mandateIdOrSignal : signal;
  const mandateId = typeof mandateIdOrSignal === "string" ? mandateIdOrSignal : undefined;

  const params = new URLSearchParams();
  if (search) params.append("search", search);
  if (office) params.append("office", office);
  if (party) params.append("party", party);
  if (uf) params.append("uf", uf);
  if (mandateId) params.append("mandate_id", mandateId);
  params.append("limit", limit.toString());

  return fetchJson<PoliticoSearchResponse>(`/politicians?${params.toString()}`, actualSignal);
}

export async function getPoliticianDossier(politicianId: string, signal?: AbortSignal): Promise<PoliticoDossier> {
  return fetchJson<PoliticoDossier>(`/politicians/${encodeURIComponent(politicianId)}`, signal);
}

export async function getSocialIndicators(signal?: AbortSignal): Promise<IndicadorSocialAnual[]> {
  return cachedFetch(
    "social-indicators",
    () => fetchJson<IndicadorSocialAnual[]>("/analytics/social-indicators"),
    signal
  );
}

export async function getSocialClasses(signal?: AbortSignal, ano?: number): Promise<ClassesSociaisResponse> {
  const q = ano ? `?ano=${ano}` : "";
  return cachedFetch(
    `social-classes${ano ? `:${ano}` : ""}`,
    () => fetchJson<ClassesSociaisResponse>(`/analytics/social-classes${q}`),
    signal
  );
}

export async function getSocialElectionsCorrelation(
  ano?: number,
  signal?: AbortSignal
): Promise<SocialElectionsResponse> {
  const q = ano ? `?ano=${ano}` : "";
  return fetchJson<SocialElectionsResponse>(`/analytics/social-elections${q}`, signal);
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
  autoria_principal_count?: number;
  coautoria_count?: number;
  proposicoes_aprovadas?: number;
  proposicoes_estruturantes?: number;
  taxa_eficiencia_pct?: number;
  score_produtividade?: number;
  score_ponderado?: number;
  score_ialp?: number;
  desvio_foco?: {
    estruturais: number;
    burocraticas: number;
    proporcao_estrutural_pct: number;
    diagnostico?: string;
  };
  classificacao_efetividade?: string;
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
  tipo_deliberacao?: "COMISSAO" | "SIMBOLICA" | "NOMINAL" | null;
  total_deliberacoes?: number;
  peso_complexidade?: number;
  multiplicador_tramitacao?: number;
  score_base?: number;
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

export interface OrientacaoPartidariaItem {
  partido_bancada: string;
  orientacao: string;
}

export interface DeliberacaoItem {
  id: string;
  tipo_deliberacao: "COMISSAO" | "SIMBOLICA" | "NOMINAL";
  data_hora: string;
  local_deliberacao: string;
  resumo_decisao: string;
  aprovada: boolean;
  orientacoes_partidarias?: OrientacaoPartidariaItem[];
  // Se COMISSAO
  nome_comissao?: string;
  link_ata_reuniao?: string | null;
  relator_nome?: string | null;
  parecer_relator_numero?: string | null;
  parecer_relator_texto?: string | null;
  link_parecer_relator?: string | null;
  // Se SIMBOLICA
  aviso_educativo?: string;
  // Se NOMINAL
  placar?: {
    sim: number;
    nao: number;
    abstencao: number;
    obstrucao: number;
    total: number;
  };
  total_votos_nominais?: number;
}

export interface ProposicaoDeliberacoesResponse {
  proposicao: {
    id: string;
    titulo: string;
    numero: number;
    ano: number;
    tipo: string;
    ementa: string;
    setor: string;
    autor_nome?: string | null;
    status: string;
    data_apresentacao?: string | null;
    url_oficial?: string | null;
  };
  total_deliberacoes: number;
  deliberacoes: DeliberacaoItem[];
}

export interface DeliberacaoDetalheResponse extends DeliberacaoItem {
  proposicao_id: string;
  proposicao?: {
    id: string;
    titulo: string;
    numero: number;
    ano: number;
    tipo: string;
    ementa: string;
    setor?: string;
    autor_nome?: string;
    url_oficial?: string | null;
  } | null;
  votos_sim?: ParlamentarVotoNominalItem[];
  votos_nao?: ParlamentarVotoNominalItem[];
  votos_abstencao?: ParlamentarVotoNominalItem[];
  votos_obstrucao?: ParlamentarVotoNominalItem[];
  total_votos_filtrados?: number;
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
    url_oficial?: string | null;
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
  deliberacoes?: DeliberacaoItem[];
}

export async function getAuthorsProductivityRanking(
  limit: number = 20,
  partido?: string,
  setor?: string,
  criterio: "efetividade" | "volume" | string = "efetividade",
  signal?: AbortSignal
): Promise<AuthorProductivityItem[]> {
  const q = new URLSearchParams();
  q.append("limit", String(limit));
  if (partido && partido.toUpperCase() !== "TODOS") q.append("partido", partido.trim());
  if (setor && setor.toUpperCase() !== "TODOS") q.append("setor", setor.trim());
  if (criterio) q.append("criterio", criterio.trim());
  return fetchJson<AuthorProductivityItem[]>(`/legislative/ranking/authors?${q.toString()}`, signal);
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

export async function getParties(signal?: AbortSignal): Promise<PartidoCatalogoItem[]> {
  return cachedFetch("parties", () => fetchJson<PartidoCatalogoItem[]>("/parties"), signal);
}

export interface CoauthorshipNetworkNode {
  id: string;
  name: string;
  party: string;
  uf: string;
  house: "CAMARA" | "SENADO" | string;
  photo_url?: string | null;
  community: number;
  betweenness_centrality: number;
  degree: number;
}

export interface CoauthorshipNetworkEdge {
  source: string;
  target: string;
  weight: number;
}

export interface CoauthorshipCommunity {
  community_id: number;
  total_parlamentares: number;
  partidos_predominantes: string;
  color: string;
  label: string;
}

export interface CoauthorshipNetworkStats {
  total_nodes: number;
  total_edges: number;
  total_communities: number;
  density: number;
  tipo_filtro: string;
  top_articulators: string[];
}

export interface CoauthorshipNetworkResponse {
  nodes: CoauthorshipNetworkNode[];
  edges: CoauthorshipNetworkEdge[];
  communities: CoauthorshipCommunity[];
  stats: CoauthorshipNetworkStats;
}

export interface PoliticianProductivityIalp {
  politician_id: string;
  nome_eleitoral: string;
  foto_url?: string | null;
  score_ialp_total: number;
  total_proposicoes: number;
  taxa_eficacia_pct: number;
  avancados_autor_principal: number;
  desvio_foco: {
    estruturais: number;
    burocraticas: number;
    proporcao_estrutural_pct: number;
    diagnostico: string;
  };
  distribuicao_autoria: {
    autor_principal: number;
    relator: number;
    coautor: number;
  };
  top_coautores: Array<{
    id: string;
    nome_eleitoral: string;
    foto_url?: string | null;
    projetos_compartilhados: number;
  }>;
  proposicoes_amostra: Array<{
    id: string;
    titulo: string;
    tipo: string;
    numero: number;
    ano: number;
    ementa: string;
    papel_autoria: string;
    status: string;
    peso_tipo: number;
    peso_autoria: number;
    multiplicador_sucesso: number;
    score_ialp: number;
    url_oficial?: string | null;
  }>;
}

export async function getCoauthorshipNetwork(
  tipoProposta?: string,
  minWeight: number = 1,
  casa?: string,
  limitNodes: number = 100,
  signal?: AbortSignal
): Promise<CoauthorshipNetworkResponse> {
  const q = new URLSearchParams();
  if (tipoProposta && tipoProposta !== "ALL") q.append("tipo_proposta", tipoProposta);
  if (minWeight > 1) q.append("min_weight", String(minWeight));
  if (casa && casa !== "ALL") q.append("casa", casa);
  if (limitNodes) q.append("limit_nodes", String(limitNodes));
  const qs = q.toString();
  return fetchJson<CoauthorshipNetworkResponse>(`/legislative/network${qs ? `?${qs}` : ""}`, signal);
}

export async function getPoliticianProductivity(
  politicianId: string,
  signal?: AbortSignal
): Promise<PoliticianProductivityIalp> {
  return fetchJson<PoliticianProductivityIalp>(`/legislative/politicians/${encodeURIComponent(politicianId)}/productivity`, signal);
}

export async function getLegislativeExplorer(
  params?: {
    search?: string;
    setor?: string;
    partido?: string;
    tipo?: string;
    status?: string;
    apenas_votadas?: boolean;
    page?: number;
    limit?: number;
  },
  signal?: AbortSignal
): Promise<LegislativeExplorerResponse> {
  const q = new URLSearchParams();
  if (params?.search) q.append("search", params.search);
  if (params?.setor) q.append("setor", params.setor);
  if (params?.partido) q.append("partido", params.partido);
  if (params?.tipo) q.append("tipo", params.tipo);
  if (params?.status) q.append("status", params.status);
  if (params?.apenas_votadas !== undefined) q.append("apenas_votadas", String(params.apenas_votadas));
  if (params?.page) q.append("page", String(params.page));
  if (params?.limit) q.append("limit", String(params.limit));

  return fetchJson<LegislativeExplorerResponse>(`/legislative/explorer?${q.toString()}`, signal);
}

export async function getPropositionNominalVotesSplit(
  propId: string,
  search?: string,
  signal?: AbortSignal
): Promise<PropositionNominalVotesSplitResponse> {
  const q = search ? `?search=${encodeURIComponent(search)}` : "";
  return fetchJson<PropositionNominalVotesSplitResponse>(
    `/legislative/propositions/${encodeURIComponent(propId)}/nominal-votes${q}`,
    signal
  );
}

export async function getProposicaoDeliberacoes(
  propId: string,
  signal?: AbortSignal
): Promise<ProposicaoDeliberacoesResponse> {
  return fetchJson<ProposicaoDeliberacoesResponse>(
    `/legislative/propositions/${encodeURIComponent(propId)}/deliberacoes`,
    signal
  );
}

export async function getDeliberacaoDetalhe(
  votacaoId: string,
  search?: string,
  signal?: AbortSignal
): Promise<DeliberacaoDetalheResponse> {
  const q = search ? `?search=${encodeURIComponent(search)}` : "";
  return fetchJson<DeliberacaoDetalheResponse>(
    `/legislative/deliberacoes/${encodeURIComponent(votacaoId)}${q}`,
    signal
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
  is_votacao_secreta?: boolean;
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

export async function getVotingCalendar(
  year?: number,
  signal?: AbortSignal
): Promise<CalendarioVotacoesResponse> {
  const query = year ? `?year=${year}` : "";
  try {
    return await fetchJson<CalendarioVotacoesResponse>(`/legislative/calendar${query}`, signal);
  } catch (err: unknown) {
    if (year && err && typeof err === "object" && "status" in err && (err as { status: number }).status === 404) {
      const isLeap = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
      const totalDias = isLeap ? 366 : 365;
      return {
        ano_selecionado: year,
        anos_disponiveis: [2026, 2023],
        estatisticas_anuais: {
          ano: year,
          total_dias_ano: totalDias,
          dias_com_votacao: 0,
          percentual_dias_ativos: 0.0,
          total_sessoes_ano: 0,
          texto_estatistica: `Em ${year}, de ${totalDias} dias, o Congresso realizou sessões de votação nominal em 0 dias.`,
        },
        dias: [],
      };
    }
    throw err;
  }
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

export async function getConsultasPublicas(
  casa?: string,
  forceRefresh?: boolean,
  signal?: AbortSignal
): Promise<ConsultaPublicaItem[]> {
  const params = new URLSearchParams();
  if (casa) params.set("casa", casa);
  if (forceRefresh) params.set("force_refresh", "true");
  const query = params.toString() ? `?${params.toString()}` : "";
  return fetchJson<ConsultaPublicaItem[]>(`/cidadania/consultas${query}`, signal);
}


export interface PresidentialMandate {
  id: string;
  nome: string;
  inicio: string;
  fim: string | null;
  partido: string;
  foto_url: string | null;
}

export interface MandateIndicatorData {
  data: string;
  // Indicadores econômicos
  inflacao_ipca?: number;      // IPCA acumulado 12 meses (%) - fonte: IBGE
  desemprego_pnad?: number;    // Taxa PNAD Contínua (%) - fonte: IBGE
  aprovacao_popular?: number;  // Aprovação (%) - fonte: Datafolha/CNT
  cambio_usd_brl?: number;     // Câmbio USD/BRL médio - fonte: BCB
  selic_meta?: number;         // Selic meta (%) - fonte: BCB/COPOM
  emendas_bilhoes?: number;    // Emendas parlamentares acumuladas (R$ bi)
  // Legado / outros
  taxa_sucesso_congresso?: number;
  volume_emendas?: number;
  [key: string]: string | number | undefined;
}

export async function getPresidentialMandates(signal?: AbortSignal): Promise<PresidentialMandate[]> {
  return fetchJson<PresidentialMandate[]>("/executivo/mandates", signal);
}

export async function getMandateIndicators(
  mandateId: string,
  signal?: AbortSignal
): Promise<MandateIndicatorData[]> {
  return fetchJson<MandateIndicatorData[]>(`/executivo/mandates/${encodeURIComponent(mandateId)}/indicators`, signal);
}

export interface KPIStat {
  primeiro: number | null;
  ultimo: number | null;
  minimo: number | null;
  maximo: number | null;
  media: number | null;
  variacao_pp?: number | null;
  total_acumulado?: number | null;
}

export interface MandateSummary {
  mandate_id: string;
  nome: string;
  partido: string;
  inicio: string;
  fim: string | null;
  foto_url: string | null;
  total_meses: number;
  kpis: {
    inflacao_ipca?: KPIStat;
    desemprego_pnad?: KPIStat;
    aprovacao_popular?: KPIStat;
    cambio_usd_brl?: KPIStat;
    selic_meta?: KPIStat;
    emendas_bilhoes?: KPIStat;
  };
}

export async function getMandateSummary(mandateId: string, signal?: AbortSignal): Promise<MandateSummary> {
  return fetchJson<MandateSummary>(`/executivo/mandates/${encodeURIComponent(mandateId)}/summary`, signal);
}

// ─── Emendas Orçamentárias (APIs Oficiais e Tradução Humanizada) ───────────────

export interface DicionarioEmendas {
  termos_orcamentarios: Record<string, { termo_tecnico: string; traducao: string; explicacao: string }>;
  linha_do_tempo: Array<{ etapa: number; nome: string; status: string; descricao: string }>;
  areas_tematicas: Record<string, { icone: string; rotulo: string }>;
}

export interface EmendasResumoResponse {
  estatisticas_gerais: {
    total_emendas: number;
    total_reservado_empenhado_brl: number;
    total_entregue_pago_brl: number;
    taxa_execucao_pago_pct: number;
  };
  por_tipo_autor: Record<
    string,
    {
      total_empenhado: number;
      total_pago: number;
      quantidade: number;
      categoria: string;
      icone: string;
      descricao: string;
    }
  >;
  por_area_tematica: Array<{
    area: string;
    rotulo: string;
    icone: string;
    total_empenhado: number;
    total_pago: number;
    quantidade: number;
  }>;
  por_ano: Record<string, { total_empenhado: number; total_pago: number; quantidade: number }>;
  top_ufs: Array<{ uf: string; total_empenhado: number; total_pago: number; quantidade: number }>;
  dicionario: DicionarioEmendas;
}

export interface EmendasLocalidadeResponse {
  localidade_pesquisada: string;
  total_emendas_encontradas: number;
  total_reservado_empenhado_brl: number;
  total_entregue_pago_brl: number;
  taxa_execucao_pct: number;
  divisao_por_area: Array<{
    area: string;
    rotulo: string;
    icone: string;
    total_empenhado: number;
    total_pago: number;
    quantidade: number;
  }>;
  emendas: Array<{
    codigo_emenda: string;
    ano: number;
    area_tematica: string;
    area_rotulo: string;
    area_icone: string;
    valor_reservado_empenhado: number;
    valor_entregue_pago: number;
    estagio: string;
    tipo_recurso: string;
    autor: {
      tipo_autor: string;
      categoria: string;
      nome_tecnico: string;
      nome_amigavel: string;
      descricao_amigavel: string;
      icone: string;
    };
  }>;
  dicionario: DicionarioEmendas;
}

export interface EmendasAutorResponse {
  autor_pesquisado: string;
  perfil_autor: {
    tipo_autor: string;
    categoria: string;
    nome_tecnico: string;
    nome_amigavel: string;
    descricao_amigavel: string;
    icone: string;
  };
  total_emendas_enviadas: number;
  total_reservado_empenhado_brl: number;
  total_entregue_pago_brl: number;
  taxa_execucao_pct: number;
  top_destinos: Array<{ localidade: string; total_empenhado: number; total_pago: number; quantidade: number }>;
  por_area_tematica: Array<{
    area: string;
    rotulo: string;
    icone: string;
    total_empenhado: number;
    total_pago: number;
    quantidade: number;
  }>;
  emendas: Array<{
    codigo_emenda: string;
    ano: number;
    localidade_destino: string;
    area_tematica: string;
    area_rotulo: string;
    area_icone: string;
    valor_reservado_empenhado: number;
    valor_entregue_pago: number;
    estagio: string;
  }>;
}

export async function getEmendasResumo(signal?: AbortSignal): Promise<EmendasResumoResponse> {
  return fetchJson<EmendasResumoResponse>("/emendas/resumo", signal);
}

export async function getEmendasPorLocalidade(localidade: string, limit = 50, signal?: AbortSignal): Promise<EmendasLocalidadeResponse> {
  return fetchJson<EmendasLocalidadeResponse>(`/emendas/localidade/${encodeURIComponent(localidade)}?limit=${limit}`, signal);
}

export async function getEmendasPorAutor(autor: string, limit = 50, signal?: AbortSignal): Promise<EmendasAutorResponse> {
  return fetchJson<EmendasAutorResponse>(`/emendas/autor/${encodeURIComponent(autor)}?limit=${limit}`, signal);
}


// ─── IPPM & Produtividade Partidária Média ───────────────────────────────────

export interface PartyPilares {
  /** null: sem votação nominal com orientação de bancada no período. */
  fidelidade_partidaria_pct: number | null;
  taxa_eficacia_pct: number;
  total_relatorias: number;
  volume_relatorias: number;
  /** Assinaturas de apoio a PEC (peso reduzido no índice). */
  assinaturas_apoio_quorum?: number;
}

export interface QuadranteEficiencia {
  codigo: string;
  titulo: string;
  descricao: string;
}

export interface PartyIPPMRankingItem {
  posicao: number;
  partido_id: string;
  sigla: string;
  nome_completo: string;
  numero_eleitoral?: number | null;
  espectro_politico: string;
  bloco_politico: string;
  cor_hex: string;
  logo_url?: string | null;
  total_cadeiras_ativas: number;
  cadeiras_dia_equivalentes: number;
  parlamentares_produtivos: number;
  pontuacao_bruta_ialp: number;
  ippm_score_medio: number;
  projetos_apresentados: number;
  projetos_aprovados: number;
  pilares: PartyPilares;
  quadrante_eficiencia: QuadranteEficiencia;
}

export interface IPPMRankingResponse {
  periodo: {
    ano: number;
    data_inicio: string;
    data_fim: string;
    casa: string;
    bloco: string;
    espectro: string;
    /** Explica partidos fora do ranking (ex.: período sem histórico de cadeiras na fonte). */
    aviso?: string | null;
  };
  resumo_geral: {
    total_partidos: number;
    media_ippm_geral: number;
    partido_mais_produtivo?: {
      sigla: string;
      ippm_score?: number;
      cor_hex: string;
    } | null;
    partido_mais_eficaz?: {
      sigla: string;
      taxa_eficacia?: number;
      cor_hex: string;
    } | null;
    partido_mais_coeso?: {
      sigla: string;
      fidelidade_pct?: number;
      cor_hex: string;
    } | null;
  };
  ranking: PartyIPPMRankingItem[];
}

export interface PartyMandateTimelineItem {
  id: string;
  politico_id: string;
  nome_eleitoral: string;
  foto_url?: string | null;
  casa: string;
  situacao: string;
  data_inicio: string;
  data_fim?: string | null;
  observacao?: string | null;
}

export interface PartyMandateTimelineResponse {
  partido: string;
  total_membros_registrados: number;
  titulares_exercicio: PartyMandateTimelineItem[];
  ministros_licenciados: PartyMandateTimelineItem[];
  suplentes_ativos: PartyMandateTimelineItem[];
}

export async function getPartyIPPMRanking(
  params?: { ano?: number; casa?: string; bloco?: string; espectro?: string },
  signal?: AbortSignal
): Promise<IPPMRankingResponse> {
  const query = new URLSearchParams();
  if (params?.ano) query.set("ano", String(params.ano));
  if (params?.casa && params.casa !== "ALL") query.set("casa", params.casa);
  if (params?.bloco && params.bloco !== "ALL") query.set("bloco", params.bloco);
  if (params?.espectro && params.espectro !== "ALL") query.set("espectro", params.espectro);
  const qStr = query.toString() ? `?${query.toString()}` : "";
  const cacheKey = `party_ippm_ranking_${query.toString()}`;
  return cachedFetch(cacheKey, () => fetchJson<IPPMRankingResponse>(`/parties/ippm-ranking${qStr}`), signal);
}

export async function getPartyMandateHistory(
  sigla: string,
  signal?: AbortSignal
): Promise<PartyMandateTimelineResponse> {
  const enc = encodeURIComponent(sigla);
  return cachedFetch(
    `party_mandate_history_${enc}`,
    () => fetchJson<PartyMandateTimelineResponse>(`/parties/${enc}/historico-bancada`),
    signal
  );
}
