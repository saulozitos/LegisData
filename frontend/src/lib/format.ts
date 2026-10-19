/** Formatadores que nunca imprimem "null", "undefined" ou "NaN". */

export const UNAVAILABLE_LABEL = "Indisponível";

export function isNum(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

export function fmtNum(value: number | null | undefined, digits = 1): string {
  return isNum(value) ? value.toLocaleString("pt-BR", { minimumFractionDigits: digits, maximumFractionDigits: digits }) : UNAVAILABLE_LABEL;
}

export function fmtPct(value: number | null | undefined, digits = 1): string {
  return isNum(value) ? `${fmtNum(value, digits)}%` : UNAVAILABLE_LABEL;
}

/** "R$ 1.234,56" (espaço comum); valor ausente nunca vira "R$ 0,00". */
export function fmtReais(value: number | null | undefined): string {
  return isNum(value) ? `R$ ${value.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}` : UNAVAILABLE_LABEL;
}

export function fmtBRL(value: number | null | undefined, digits = 2): string {
  return isNum(value)
    ? value.toLocaleString("pt-BR", { style: "currency", currency: "BRL", minimumFractionDigits: digits, maximumFractionDigits: digits })
    : UNAVAILABLE_LABEL;
}

export function fmtSigned(value: number | null | undefined, suffix = "", digits = 1): string {
  if (!isNum(value)) return UNAVAILABLE_LABEL;
  const sign = value > 0 ? "+" : "";
  return `${sign}${fmtNum(value, digits)}${suffix}`;
}
