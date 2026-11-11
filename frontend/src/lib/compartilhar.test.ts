import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  atualizarUrl,
  baixarCartao,
  desenharCartao,
  gerarCartaoPng,
  lerParametros,
  montarConsulta,
  montarLink,
  type DadosDoCartao,
} from './compartilhar';

const cartao: DadosDoCartao = {
  titulo: 'PL 123/2024',
  linhas: [['Placar', 'Sim 300 · Não 100']],
  fonte: 'Dados Abertos da Câmara dos Deputados',
  data: '12 fev 2026',
  periodo: '2019 a 2026',
  etapa: 'Requerimento de urgência',
  link: 'https://legisdata.exemplo/?aba=calendario',
};

describe('compartilhar', () => {
  it('monta a consulta só com o que está preenchido, em ordem estável', () => {
    expect(montarConsulta({ politico: 'abc', aba: 'raiox', partido: null, q: '' })).toBe('?aba=raiox&politico=abc');
    expect(montarConsulta({})).toBe('');
  });

  it('codifica o que precisa de codificação', () => {
    expect(montarConsulta({ q: 'escala 6x1' })).toBe('?q=escala+6x1');
  });

  it('monta o link completo na página atual', () => {
    expect(montarLink({ aba: 'calendario' }, '/')).toContain('/?aba=calendario');
  });

  it('recusa gerar cartão sem fonte, data, período ou etapa', () => {
    const canvas = document.createElement('canvas');
    for (const falta of ['fonte', 'data', 'periodo', 'etapa'] as const) {
      expect(() => desenharCartao({ ...cartao, [falta]: '' }, canvas)).toThrow(/exige fonte, data, período e etapa/);
    }
  });

  it('desenha o cartão quando o navegador tem canvas', () => {
    const chamadas: string[] = [];
    const ctx = new Proxy(
      { measureText: () => ({ width: 10 }), fillText: (t: string) => chamadas.push(t) },
      { get: (alvo, prop) => (prop in alvo ? (alvo as never)[prop] : () => undefined), set: () => true },
    );
    const canvas = document.createElement('canvas');
    canvas.getContext = (() => ctx) as unknown as typeof canvas.getContext;
    expect(desenharCartao(cartao, canvas)).toBe(canvas);
    const texto = chamadas.join(' | ');
    expect(texto).toContain('Etapa: Requerimento de urgência');
    expect(texto).toContain('Fonte: Dados Abertos da Câmara dos Deputados');
    expect(texto).toContain('Período: 2019 a 2026');
  });

  it('devolve null quando não há canvas', () => {
    const canvas = document.createElement('canvas');
    canvas.getContext = (() => null) as unknown as typeof canvas.getContext;
    expect(desenharCartao(cartao, canvas)).toBeNull();
  });

  it('lê e atualiza a URL sem empilhar histórico', () => {
    window.history.replaceState(null, '', '/?aba=raiox');
    expect(lerParametros().get('aba')).toBe('raiox');
    atualizarUrl({ aba: 'calendario', politico: null });
    expect(window.location.search).toBe('?aba=calendario');
    atualizarUrl({});
    expect(window.location.search).toBe('');
  });
});

describe('cartão em imagem', () => {
  afterEach(() => vi.restoreAllMocks());

  const comCanvas = (blob: Blob | null) => {
    const ctx = new Proxy({ measureText: () => ({ width: 10 }) }, {
      get: (alvo, prop) => (prop in alvo ? (alvo as never)[prop] : () => undefined),
      set: () => true,
    });
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(ctx as never);
    vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation((cb) => cb(blob));
  };

  it('gera o PNG do cartão', async () => {
    const png = new Blob(['x'], { type: 'image/png' });
    comCanvas(png);
    expect(await gerarCartaoPng(cartao)).toBe(png);
  });

  it('devolve null quando o navegador não tem canvas', async () => {
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
    expect(await gerarCartaoPng(cartao)).toBeNull();
    expect(await baixarCartao(cartao, 'x')).toBe(false);
  });

  it('baixa o arquivo com a extensão .png', async () => {
    comCanvas(new Blob(['x'], { type: 'image/png' }));
    URL.createObjectURL = vi.fn(() => 'blob:cartao');
    URL.revokeObjectURL = vi.fn();
    const cliques: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      cliques.push(this.download);
    });
    expect(await baixarCartao(cartao, 'legisdata-votacao')).toBe(true);
    expect(cliques).toEqual(['legisdata-votacao.png']);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:cartao');
  });
});
