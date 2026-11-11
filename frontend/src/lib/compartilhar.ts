/**
 * Links diretos e cartões de compartilhamento.
 *
 * O link guarda na URL o que a tela está mostrando (aba, político, partido, votação, comparação), para abrir exatamente
 * aquela consulta. O cartão é uma imagem gerada no navegador a partir dos dados já na tela, e sempre traz fonte, data,
 * período e etapa, para ninguém ler o placar sem saber de onde veio nem o que foi votado.
 */

export type ParametrosDoLink = Record<string, string | null | undefined>;

/** Monta `?a=1&b=2` só com os parâmetros preenchidos, em ordem estável. */
export function montarConsulta(parametros: ParametrosDoLink): string {
  const busca = new URLSearchParams();
  for (const chave of Object.keys(parametros).sort()) {
    const valor = parametros[chave];
    if (valor !== null && valor !== undefined && valor !== '') busca.set(chave, valor);
  }
  const texto = busca.toString();
  return texto ? `?${texto}` : '';
}

/** Endereço completo da consulta, na página atual (ou em `caminho`). */
export function montarLink(parametros: ParametrosDoLink, caminho?: string): string {
  const base = typeof window === 'undefined' ? '' : window.location.origin;
  const rota = caminho ?? (typeof window === 'undefined' ? '/' : window.location.pathname);
  return `${base}${rota}${montarConsulta(parametros)}`;
}

/** Parâmetros da URL atual; vazio fora do navegador. */
export function lerParametros(): URLSearchParams {
  return new URLSearchParams(typeof window === 'undefined' ? '' : window.location.search);
}

/** Troca a URL sem recarregar nem empilhar histórico. */
export function atualizarUrl(parametros: ParametrosDoLink): void {
  if (typeof window === 'undefined') return;
  const destino = `${window.location.pathname}${montarConsulta(parametros)}${window.location.hash}`;
  if (destino !== `${window.location.pathname}${window.location.search}${window.location.hash}`) {
    window.history.replaceState(null, '', destino);
  }
}

export interface DadosDoCartao {
  titulo: string;
  /** Linhas de destaque (rótulo, valor): placar, partido, mandato... */
  linhas: Array<[string, string]>;
  /** Quem publica o dado. Obrigatório: cartão sem fonte não é gerado. */
  fonte: string;
  /** Data do dado ou da consulta, já formatada. */
  data: string;
  /** Período que o dado cobre, já formatado. */
  periodo: string;
  /** O que exatamente foi votado ou medido (ex.: "Requerimento de urgência", "Texto principal"). */
  etapa: string;
  link: string;
}

const LARGURA = 1200;
const ALTURA = 630;

function quebrar(ctx: CanvasRenderingContext2D, texto: string, larguraMax: number): string[] {
  const linhas: string[] = [];
  let atual = '';
  for (const palavra of texto.split(/\s+/)) {
    const teste = atual ? `${atual} ${palavra}` : palavra;
    if (ctx.measureText(teste).width > larguraMax && atual) {
      linhas.push(atual);
      atual = palavra;
    } else {
      atual = teste;
    }
  }
  if (atual) linhas.push(atual);
  return linhas;
}

/** Desenha o cartão num canvas. Devolve `null` se o navegador não oferece canvas. */
export function desenharCartao(dados: DadosDoCartao, canvas: HTMLCanvasElement): HTMLCanvasElement | null {
  if (!dados.fonte || !dados.data || !dados.periodo || !dados.etapa) {
    throw new Error('O cartão exige fonte, data, período e etapa.');
  }
  canvas.width = LARGURA;
  canvas.height = ALTURA;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;

  ctx.fillStyle = '#020617';
  ctx.fillRect(0, 0, LARGURA, ALTURA);
  ctx.fillStyle = '#22d3ee';
  ctx.fillRect(0, 0, 12, ALTURA);

  ctx.fillStyle = '#e2e8f0';
  ctx.font = 'bold 44px sans-serif';
  let y = 90;
  for (const linha of quebrar(ctx, dados.titulo, LARGURA - 120).slice(0, 3)) {
    ctx.fillText(linha, 60, y);
    y += 56;
  }

  y += 10;
  for (const [rotulo, valor] of dados.linhas.slice(0, 5)) {
    ctx.fillStyle = '#94a3b8';
    ctx.font = '26px sans-serif';
    ctx.fillText(`${rotulo}:`, 60, y);
    ctx.fillStyle = '#f8fafc';
    ctx.font = 'bold 30px sans-serif';
    ctx.fillText(valor, 340, y);
    y += 46;
  }

  ctx.fillStyle = '#fbbf24';
  ctx.font = 'bold 26px sans-serif';
  ctx.fillText(`Etapa: ${dados.etapa}`, 60, ALTURA - 190);

  ctx.fillStyle = '#94a3b8';
  ctx.font = '22px sans-serif';
  const rodape = [`Fonte: ${dados.fonte}`, `Período: ${dados.periodo}`, `Dado de: ${dados.data}`];
  let ry = ALTURA - 140;
  for (const linha of rodape) {
    for (const parte of quebrar(ctx, linha, LARGURA - 120).slice(0, 2)) {
      ctx.fillText(parte, 60, ry);
      ry += 30;
    }
  }
  ctx.fillStyle = '#22d3ee';
  ctx.fillText(dados.link.replace(/^https?:\/\//, ''), 60, ALTURA - 24);
  return canvas;
}

/** Imagem PNG do cartão, ou `null` quando o navegador não consegue gerá-la. */
export async function gerarCartaoPng(dados: DadosDoCartao): Promise<Blob | null> {
  if (typeof document === 'undefined') return null;
  const canvas = desenharCartao(dados, document.createElement('canvas'));
  if (!canvas) return null;
  return new Promise((resolve) => canvas.toBlob((blob) => resolve(blob), 'image/png'));
}

/** Gera o cartão e o baixa como arquivo. Devolve `false` se não foi possível gerar a imagem. */
export async function baixarCartao(dados: DadosDoCartao, nomeDoArquivo: string): Promise<boolean> {
  const blob = await gerarCartaoPng(dados);
  if (!blob) return false;
  const url = URL.createObjectURL(blob);
  const ancora = document.createElement('a');
  ancora.href = url;
  ancora.download = nomeDoArquivo.endsWith('.png') ? nomeDoArquivo : `${nomeDoArquivo}.png`;
  document.body.appendChild(ancora);
  ancora.click();
  ancora.remove();
  URL.revokeObjectURL(url);
  return true;
}
