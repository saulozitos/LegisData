import { isNum } from "@/lib/format";
import type { PoliticoDossier } from "@/services/api";

/** Máscara de CPF/CNPJ para exibição (defesa em profundidade; o backend já deve mascarar). */
export function formatCpfCnpj(doc: string | null | undefined): string {
  if (!doc) return "Não informado";
  const clean = doc.replace(/\D/g, "");
  if (clean.length === 11) {
    return `***.${clean.slice(3, 6)}.${clean.slice(6, 9)}-**`;
  }
  if (clean.length === 14) {
    return `**.${clean.slice(2, 5)}.${clean.slice(5, 8)}/${clean.slice(8, 12)}-**`;
  }
  return doc;
}

/** Valor monetário; valores ausentes nunca viram "R$ 0,00". */
export function formatMoney(val: number | null | undefined): string {
  if (!isNum(val)) return "Indisponível";
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(val);
}

export type FichaStatus = "declared" | "none" | "unknown";

/**
 * Situação judicial a exibir. "none" só quando a API informou explicitamente que não há processos
 * declarados; ausência do bloco `ficha_limpa` é "unknown" (dado indisponível), nunca "Nada Consta".
 */
export function getFichaStatus(dossier: PoliticoDossier): FichaStatus {
  const ficha = dossier.ficha_limpa;
  if (!ficha) return "unknown";
  if (ficha.possui_processos_declarados === true) return "declared";
  if (ficha.possui_processos_declarados === false) return "none";
  return "unknown";
}

export const NA_BADGE = "bg-slate-800 text-slate-300 border border-slate-700";
const GOOD_BADGE = "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30";
const INFO_BADGE = "bg-cyan-500/15 text-cyan-400 border border-cyan-500/30";
const WARN_BADGE = "bg-amber-500/15 text-amber-400 border border-amber-500/30";
const BAD_BADGE = "bg-rose-500/15 text-rose-400 border border-rose-500/30";

/** Classes do selo da nota (A/B/…); sem nota (dados insuficientes) o selo é neutro. */
export function gradeBadgeClass(score: string | null | undefined): string {
  if (!score) return NA_BADGE;
  if (score.startsWith("A")) return GOOD_BADGE;
  if (score.startsWith("B")) return INFO_BADGE;
  return WARN_BADGE;
}

/** Classes do selo de risco de concentração; nível ausente é neutro (nunca "alerta" por padrão). */
export function riskBadgeClass(nivel: string | null | undefined): string {
  if (nivel === "BAIXO") return GOOD_BADGE;
  if (nivel === "MODERADO") return WARN_BADGE;
  if (nivel === "ALERTA") return BAD_BADGE;
  return NA_BADGE;
}

/** Classes do selo de compatibilidade patrimonial; ausência de classificação é neutra. */
export function compatBadgeClass(compat: string | null | undefined): string {
  if (compat === "COMPATÍVEL") return GOOD_BADGE;
  if (compat === "MODERADO") return WARN_BADGE;
  if (compat === "ATÍPICO") return BAD_BADGE;
  return NA_BADGE;
}

/** Texto de classificação: valor da API ou "Indisponível". */
export function orUnavailable(value: string | null | undefined): string {
  return value ? value : "Indisponível";
}
