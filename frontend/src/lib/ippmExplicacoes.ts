/**
 * Textos em linguagem simples e as "provas" (os números que levaram ao resultado) dos destaques do Raio-X dos Partidos.
 * As provas são calculadas a partir do mesmo ranking que a tela já recebeu, com as mesmas regras do backend.
 */
import type { PartyIPPMRankingItem } from "@/services/api";

/** Bancada mínima para disputar o título de "Líder em Produtividade" (evita que um partido de 1 parlamentar ganhe). */
export const MIN_BANCADA_LIDERANCA = 3;

export interface ExplicacaoIndicador {
  titulo: string;
  oQueE: string;
  comoCalcula: string[];
  cuidado?: string;
}

export const EXPLICACOES: Record<"media" | "lider" | "eficaz" | "coeso", ExplicacaoIndicador> = {
  media: {
    titulo: "Média IPPM Geral",
    oQueE:
      "É a nota média de produtividade dos partidos no ano escolhido. O IPPM de cada partido mostra quanto trabalho legislativo ele produziu para cada cadeira que ocupou.",
    comoCalcula: [
      "Cada projeto apresentado por um parlamentar do partido vale pontos: o tipo da proposta (uma PEC pesa mais que um requerimento), o papel da pessoa (autor principal pesa mais que quem só assina) e o andamento (projeto aprovado pesa mais que projeto parado).",
      "Somam-se os pontos de todos os projetos do partido no ano.",
      "O total é dividido pelo tamanho da bancada ao longo do ano, medido em cadeiras-dia: cada dia em que uma cadeira esteve ocupada pelo partido conta uma vez. Quem passou seis meses no cargo vale meia cadeira. Assim partido grande não ganha só por ser grande.",
      "A média geral é a soma das notas de todos os partidos da lista dividida pelo número de partidos.",
    ],
    cuidado:
      "O índice mede a quantidade e o peso dos projetos, não se eles são bons ou ruins para a população.",
  },
  lider: {
    titulo: "Líder em Produtividade",
    oQueE: "É o partido com o maior IPPM entre os que têm uma bancada de tamanho relevante.",
    comoCalcula: [
      "Calcula-se o IPPM de cada partido (pontos dos projetos ÷ cadeiras-dia).",
      `Só disputam o título partidos com pelo menos ${MIN_BANCADA_LIDERANCA} parlamentares em exercício: um partido de uma única pessoa não representa uma bancada.`,
      "Vence o maior IPPM.",
    ],
    cuidado: "Bancadas muito pequenas costumam ter nota alta por causa da divisão por poucas cadeiras.",
  },
  eficaz: {
    titulo: "Maior Eficácia Real",
    oQueE: "É o partido que mais transformou os projetos que apresentou em projetos aprovados.",
    comoCalcula: [
      "Contam só projetos de verdade (leis, emendas à Constituição, decretos legislativos...). Requerimentos, indicações e pedidos de informação ficam de fora.",
      "Considera-se aprovado o projeto que virou norma, foi sancionado, promulgado ou aprovado no plenário.",
      "Eficácia = projetos aprovados ÷ projetos apresentados pelo partido como autor principal.",
      "Só entram na disputa partidos com ao menos um projeto aprovado.",
    ],
    cuidado:
      "Uma emenda à Constituição quase nunca é aprovada no mesmo ano em que é apresentada: quem protocola mais PECs tende a ter taxa menor sem fazer nada errado.",
  },
  coeso: {
    titulo: "Maior Coesão de Bancada",
    oQueE: "É o partido cujos parlamentares mais votaram do jeito que a própria bancada orientou.",
    comoCalcula: [
      "Em cada votação nominal, o líder da bancada indica como o partido deve votar (sim, não ou obstrução).",
      "Coesão = votos de parlamentares do partido iguais à orientação ÷ total de votos desses parlamentares nas votações com orientação.",
      "Votações em que a bancada foi liberada ficam de fora.",
      "No período sem votações nominais com orientação, a coesão aparece como indisponível (—).",
    ],
    cuidado: "Coesão alta mostra disciplina do partido, não que o voto tenha sido certo ou errado.",
  },
};

export const EXPLICACAO_TELAS = {
  comparar: {
    nome: "Comparar",
    resumo:
      "Barras para comparar os partidos de uma olhada: escolha um indicador (produtividade, aprovação ou coesão) e veja quem está na frente. O segundo gráfico mostra, para cada partido, quantos projetos foram apresentados e quantos foram aprovados.",
  },
  tabela: {
    nome: "Tabela",
    resumo:
      "Todos os números de cada partido lado a lado. Dá para buscar, ordenar por qualquer coluna e abrir o histórico da bancada.",
  },
  evolucao: {
    nome: "Evolução",
    resumo:
      "Como a produtividade (IPPM) de cada partido mudou ano a ano. Escolha os partidos para acompanhar a linha de cada um.",
  },
} as const;

export const EXPLICACAO_MATRIZ = {
  nome: "Matriz de Eficiência",
  resumo:
    "Um gráfico que compara os partidos entre si: quanto mais à direita, mais projetos o partido apresentou; quanto mais acima, maior a parte desses projetos que foi aprovada. O tamanho da bolha mostra o IPPM.",
} as const;

export const GUIA_MATRIZ = [
  { nome: "Muitos projetos e boa aprovação", titulo: "Liderança de Bancada", posicao: "Parte de cima, à direita" },
  { nome: "Poucos projetos e boa aprovação", titulo: "Técnicos & Articuladores", posicao: "Parte de cima, à esquerda" },
  { nome: "Muitos projetos e pouca aprovação", titulo: "Populismo Legislativo", posicao: "Parte de baixo, à direita" },
  { nome: "Poucos projetos e pouca aprovação", titulo: "Bancada Reduzida", posicao: "Parte de baixo, à esquerda" },
] as const;

export interface LinhaEvidencia {
  sigla: string;
  cor: string;
  colunas: string[];
  vencedor: boolean;
}

export interface Evidencia {
  cabecalho: string[];
  linhas: LinhaEvidencia[];
  rodape?: string;
}

const num = (valor: number, casas = 2) => valor.toFixed(casas).replace(".", ",");

export function evidenciaMedia(ranking: PartyIPPMRankingItem[], media: number): Evidencia {
  const linhas = [...ranking]
    .sort((a, b) => b.ippm_score_medio - a.ippm_score_medio)
    .map((p) => ({ sigla: p.sigla, cor: p.cor_hex, colunas: [num(p.ippm_score_medio)], vencedor: false }));
  const soma = ranking.reduce((total, p) => total + p.ippm_score_medio, 0);
  return {
    cabecalho: ["Partido", "IPPM"],
    linhas,
    rodape: ranking.length
      ? `Soma ${num(soma)} ÷ ${ranking.length} partidos = ${num(media)}`
      : "Nenhum partido no ranking deste período.",
  };
}

export function evidenciaLider(ranking: PartyIPPMRankingItem[], liderSigla?: string): Evidencia {
  const candidatos = ranking
    .filter((p) => p.total_cadeiras_ativas >= MIN_BANCADA_LIDERANCA)
    .sort((a, b) => b.ippm_score_medio - a.ippm_score_medio || b.pontuacao_bruta_ialp - a.pontuacao_bruta_ialp)
    .slice(0, 5);
  const fora = ranking.length - ranking.filter((p) => p.total_cadeiras_ativas >= MIN_BANCADA_LIDERANCA).length;
  return {
    cabecalho: ["Partido", "Pontos dos projetos", "Cadeiras-dia", "IPPM (pontos ÷ cadeiras-dia)"],
    linhas: candidatos.map((p) => ({
      sigla: p.sigla,
      cor: p.cor_hex,
      colunas: [num(p.pontuacao_bruta_ialp, 1), num(p.cadeiras_dia_equivalentes, 1), num(p.ippm_score_medio)],
      vencedor: p.sigla === liderSigla,
    })),
    rodape: `Mostrando os 5 maiores. ${fora} partido(s) com menos de ${MIN_BANCADA_LIDERANCA} parlamentares não disputam o título.`,
  };
}

export function evidenciaEficaz(ranking: PartyIPPMRankingItem[], eficazSigla?: string): Evidencia {
  const candidatos = ranking
    .filter((p) => p.pilares.taxa_eficacia_pct > 0 && p.projetos_aprovados > 0)
    .sort(
      (a, b) =>
        b.pilares.taxa_eficacia_pct - a.pilares.taxa_eficacia_pct ||
        b.projetos_aprovados - a.projetos_aprovados ||
        b.ippm_score_medio - a.ippm_score_medio
    )
    .slice(0, 5);
  return {
    cabecalho: ["Partido", "Projetos apresentados", "Aprovados", "Eficácia (aprovados ÷ apresentados)"],
    linhas: candidatos.map((p) => ({
      sigla: p.sigla,
      cor: p.cor_hex,
      colunas: [String(p.projetos_apresentados), String(p.projetos_aprovados), `${num(p.pilares.taxa_eficacia_pct, 1)}%`],
      vencedor: p.sigla === eficazSigla,
    })),
    rodape: candidatos.length ? "Mostrando os 5 maiores." : "Nenhum partido teve projeto aprovado neste período.",
  };
}

export function evidenciaCoeso(ranking: PartyIPPMRankingItem[], coesoSigla?: string): Evidencia {
  const candidatos = ranking
    .filter((p) => (p.pilares.fidelidade_partidaria_pct ?? 0) > 0)
    .sort(
      (a, b) =>
        (b.pilares.fidelidade_partidaria_pct ?? 0) - (a.pilares.fidelidade_partidaria_pct ?? 0) ||
        b.total_cadeiras_ativas - a.total_cadeiras_ativas ||
        b.ippm_score_medio - a.ippm_score_medio
    )
    .slice(0, 5);
  return {
    cabecalho: ["Partido", "Coesão nas votações", "Parlamentares em exercício"],
    linhas: candidatos.map((p) => ({
      sigla: p.sigla,
      cor: p.cor_hex,
      colunas: [`${num(p.pilares.fidelidade_partidaria_pct ?? 0, 1)}%`, String(p.total_cadeiras_ativas)],
      vencedor: p.sigla === coesoSigla,
    })),
    rodape: candidatos.length
      ? "Em empate, vence a bancada maior. Mostrando os 5 maiores."
      : "Sem votações nominais com orientação de bancada neste período.",
  };
}
