import { beforeEach, describe, expect, it, vi } from 'vitest';

type Api = typeof import('./api');

function okResponse(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) } as Response;
}

async function loadApi(env?: string): Promise<Api> {
  vi.resetModules();
  if (env !== undefined) vi.stubEnv('NEXT_PUBLIC_API_URL', env);
  return import('./api');
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
});

describe('fetchJson (via endpoints)', () => {
  it('chama a base relativa no navegador e devolve o JSON', async () => {
    const api = await loadApi('');
    fetchMock.mockResolvedValue(okResponse([{ id: 1 }]));
    await expect(api.getPresidentes()).resolves.toEqual([{ id: 1 }]);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/politicians/presidents',
      expect.objectContaining({ headers: { Accept: 'application/json' } })
    );
  });

  it('respeita NEXT_PUBLIC_API_URL e normaliza /api/v1', async () => {
    const api = await loadApi('https://api.exemplo.org/');
    fetchMock.mockResolvedValue(okResponse([]));
    await api.getPartyFidelity();
    expect(fetchMock.mock.calls[0][0]).toBe('https://api.exemplo.org/api/v1/analytics/party-fidelity');

    const api2 = await loadApi('https://api.exemplo.org/api/v1');
    fetchMock.mockResolvedValue(okResponse([]));
    await api2.getWageDisparity();
    expect(fetchMock.mock.calls[1][0]).toBe('https://api.exemplo.org/api/v1/analytics/wage-disparity');
  });

  it('lança ApiError com status em respostas não-2xx (nunca devolve fallback)', async () => {
    const api = await loadApi('');
    fetchMock.mockResolvedValue(okResponse({}, 503));
    const err = await api.getMandatesPerformance().catch((e) => e);
    expect(err).toBeInstanceOf(api.ApiError);
    expect(err.status).toBe(503);
    expect(err.endpoint).toBe('/analytics/mandates-performance');
  });

  it('converte falha de rede em ApiError sem status', async () => {
    const api = await loadApi('');
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));
    const err = await api.getPresidentes().catch((e) => e);
    expect(err).toBeInstanceOf(api.ApiError);
    expect(err.status).toBeNull();
  });

  it('JSON inválido vira ApiError', async () => {
    const api = await loadApi('');
    fetchMock.mockResolvedValue({ ok: true, status: 200, json: () => Promise.reject(new SyntaxError('x')) });
    const err = await api.getPresidentes().catch((e) => e);
    expect(err).toBeInstanceOf(api.ApiError);
    expect(err.message).toMatch(/inválida/i);
  });

  it('propaga o AbortSignal e mantém o AbortError original', async () => {
    const api = await loadApi('');
    const controller = new AbortController();
    const abort = Object.assign(new Error('abort'), { name: 'AbortError' });
    fetchMock.mockRejectedValue(abort);
    controller.abort();
    const err = await api.getPresidentes(controller.signal).catch((e) => e);
    expect(err).toBe(abort);
    expect(api.isAbortError(err)).toBe(true);
    expect(fetchMock.mock.calls[0][1].signal).toBe(controller.signal);
  });

  it('AbortError durante res.json() também é propagado', async () => {
    const api = await loadApi('');
    const abort = Object.assign(new Error('abort'), { name: 'AbortError' });
    fetchMock.mockResolvedValue({ ok: true, status: 200, json: () => Promise.reject(abort) });
    await expect(api.getPresidentes()).rejects.toBe(abort);
  });
});

describe('construção de URLs', () => {
  beforeEach(() => {
    fetchMock.mockImplementation(() => Promise.resolve(okResponse({})));
  });

  const lastUrl = () => fetchMock.mock.calls[fetchMock.mock.calls.length - 1][0] as string;

  it('codifica parâmetros e omite os vazios', async () => {
    const api = await loadApi('');
    await api.getAnnualMacroSummary('lula 2023');
    expect(lastUrl()).toBe('/api/v1/economic/annual-summary?mandate_id=lula%202023');
    await api.getAnnualMacroSummary(null);
    expect(lastUrl()).toBe('/api/v1/economic/annual-summary');
    await api.getCompareMandates('a', 'b&c');
    expect(lastUrl()).toBe('/api/v1/analytics/compare-mandates?mandate1=a&mandate2=b%26c');
    await api.getCongressComposition('x/y');
    expect(lastUrl()).toBe('/api/v1/analytics/congress-composition?mandate_id=x%2Fy');
  });

  it('getFederalTransfers inclui a área só quando informada', async () => {
    const api = await loadApi('');
    await api.getFederalTransfers('m1');
    expect(lastUrl()).toBe('/api/v1/analytics/federal-transfers?mandate_id=m1');
    await api.getFederalTransfers('m1', 'Saúde');
    expect(lastUrl()).toBe('/api/v1/analytics/federal-transfers?mandate_id=m1&area=Sa%C3%BAde');
  });

  it('searchPoliticians monta a query com limite padrão', async () => {
    const api = await loadApi('');
    await api.searchPoliticians('ana', 'DEPUTADO_FEDERAL', 'PT', 'SP');
    expect(lastUrl()).toBe('/api/v1/politicians?search=ana&office=DEPUTADO_FEDERAL&party=PT&uf=SP&limit=80');
    await api.searchPoliticians();
    expect(lastUrl()).toBe('/api/v1/politicians?limit=80');
  });

  it('getPoliticianDossier escapa o identificador (sem path traversal)', async () => {
    const api = await loadApi('');
    await api.getPoliticianDossier('../admin');
    expect(lastUrl()).toBe('/api/v1/politicians/..%2Fadmin');
  });

  it('getPropositionVotes só inclui filtros informados', async () => {
    const api = await loadApi('');
    await api.getPropositionVotes('p1');
    expect(lastUrl()).toBe('/api/v1/legislative/propositions/p1/votes');
    await api.getPropositionVotes('p1', 'CAMARA', 's1', 'ana', 'SIM');
    expect(lastUrl()).toBe(
      '/api/v1/legislative/propositions/p1/votes?house=CAMARA&session_id=s1&search=ana&vote_choice=SIM'
    );
  });

  it('getLegislativeExplorer preserva apenas_votadas=false', async () => {
    const api = await loadApi('');
    await api.getLegislativeExplorer({ search: 'x', apenas_votadas: false, page: 2, limit: 10 });
    expect(lastUrl()).toBe('/api/v1/legislative/explorer?search=x&apenas_votadas=false&page=2&limit=10');
    await api.getLegislativeExplorer();
    expect(lastUrl()).toBe('/api/v1/legislative/explorer?');
  });

  it('getAuthorsProductivityRanking ignora TODOS e faz trim', async () => {
    const api = await loadApi('');
    await api.getAuthorsProductivityRanking(5, 'todos', ' Saúde ', 'volume');
    expect(lastUrl()).toBe('/api/v1/legislative/ranking/authors?limit=5&setor=Sa%C3%BAde&criterio=volume');
  });

  it('demais endpoints usam o caminho esperado', async () => {
    const api = await loadApi('');
    await api.getPropositionNominalVotesSplit('p/1', 'jo ao');
    expect(lastUrl()).toBe('/api/v1/legislative/propositions/p%2F1/nominal-votes?search=jo%20ao');
    await api.getVotingCalendar(2024);
    expect(lastUrl()).toBe('/api/v1/legislative/calendar?year=2024');
    await api.getVotingCalendar();
    expect(lastUrl()).toBe('/api/v1/legislative/calendar');
    await api.getSocialElectionsCorrelation(2022);
    expect(lastUrl()).toBe('/api/v1/analytics/social-elections?ano=2022');
    await api.getConsultasPublicas('CAMARA', true);
    expect(lastUrl()).toBe('/api/v1/cidadania/consultas?casa=CAMARA&force_refresh=true');
    await api.getConsultasPublicas();
    expect(lastUrl()).toBe('/api/v1/cidadania/consultas');
    await api.getPresidentialMandates();
    expect(lastUrl()).toBe('/api/v1/executivo/mandates');
    await api.getMandateIndicators('m 1');
    expect(lastUrl()).toBe('/api/v1/executivo/mandates/m%201/indicators');
    await api.getMandateSummary('m1');
    expect(lastUrl()).toBe('/api/v1/executivo/mandates/m1/summary');
    await api.getLegislativePropositions();
    expect(lastUrl()).toBe('/api/v1/legislative/propositions');
  });
});

describe('cache de catálogos', () => {
  it('compartilha uma única requisição entre chamadores', async () => {
    const api = await loadApi('');
    fetchMock.mockResolvedValue(okResponse([{ sigla: 'PT' }]));
    const [a, b] = await Promise.all([api.getParties(), api.getParties()]);
    expect(a).toEqual(b);
    await api.getParties();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('renova após o TTL', async () => {
    vi.useFakeTimers();
    const api = await loadApi('');
    fetchMock.mockResolvedValue(okResponse([]));
    await api.getSocialClasses();
    vi.advanceTimersByTime(5 * 60 * 1000 + 1);
    await api.getSocialClasses();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('não cacheia falhas', async () => {
    const api = await loadApi('');
    fetchMock.mockResolvedValueOnce(okResponse({}, 500)).mockResolvedValueOnce(okResponse([{ ano: 2020 }]));
    await expect(api.getSocialIndicators()).rejects.toBeInstanceOf(api.ApiError);
    await Promise.resolve();
    await expect(api.getSocialIndicators()).resolves.toEqual([{ ano: 2020 }]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('aborta apenas a espera do chamador, sem derrubar a requisição compartilhada', async () => {
    const api = await loadApi('');
    let resolveFetch!: (r: Response) => void;
    fetchMock.mockReturnValue(new Promise<Response>((res) => (resolveFetch = res)));
    const controller = new AbortController();
    const waiting = api.getParties(controller.signal);
    controller.abort();
    await expect(waiting).rejects.toMatchObject({ name: 'AbortError' });

    const other = api.getParties();
    resolveFetch(okResponse([{ sigla: 'PL' }]));
    await expect(other).resolves.toEqual([{ sigla: 'PL' }]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('signal já abortado rejeita imediatamente', async () => {
    const api = await loadApi('');
    fetchMock.mockResolvedValue(okResponse([]));
    const controller = new AbortController();
    controller.abort();
    await expect(api.getParties(controller.signal)).rejects.toMatchObject({ name: 'AbortError' });
  });

  it('propaga erro ao chamador que aguarda com signal', async () => {
    const api = await loadApi('');
    fetchMock.mockResolvedValue(okResponse({}, 500));
    await expect(api.getParties(new AbortController().signal)).rejects.toBeInstanceOf(api.ApiError);
  });
});

describe('getApiHealth', () => {
  it('usa /api/health por padrão', async () => {
    const api = await loadApi('');
    fetchMock.mockResolvedValue(okResponse({ status: 'ok' }));
    await expect(api.getApiHealth()).resolves.toEqual({ status: 'ok' });
    expect(fetchMock.mock.calls[0][0]).toBe('/api/health');
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ cache: 'no-store' });
  });

  it('deriva /health da URL configurada', async () => {
    const api = await loadApi('https://api.exemplo.org/api/v1');
    fetchMock.mockResolvedValue(okResponse({ status: 'ok' }));
    await api.getApiHealth();
    expect(fetchMock.mock.calls[0][0]).toBe('https://api.exemplo.org/health');
  });

  it('falha de rede e status ruim viram ApiError', async () => {
    const api = await loadApi('');
    fetchMock.mockRejectedValueOnce(new TypeError('x'));
    await expect(api.getApiHealth()).rejects.toBeInstanceOf(api.ApiError);
    fetchMock.mockResolvedValueOnce(okResponse({}, 502));
    await expect(api.getApiHealth()).rejects.toMatchObject({ status: 502 });
  });

  it('preserva AbortError', async () => {
    const api = await loadApi('');
    const abort = Object.assign(new Error('a'), { name: 'AbortError' });
    fetchMock.mockRejectedValue(abort);
    await expect(api.getApiHealth()).rejects.toBe(abort);
  });
});
