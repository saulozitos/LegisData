import { describe, it, expect } from "vitest";
import { anoInicioLegislatura } from "./legislatura";

describe("anoInicioLegislatura", () => {
  it("usa 2023 durante toda a legislatura 2023-2026", () => {
    expect(anoInicioLegislatura(new Date(2023, 1, 1))).toBe(2023);
    expect(anoInicioLegislatura(new Date(2026, 9, 15))).toBe(2023);
    expect(anoInicioLegislatura(new Date(2026, 11, 31))).toBe(2023);
  });

  it("mantém a legislatura anterior em janeiro, antes da posse de 1º de fevereiro", () => {
    expect(anoInicioLegislatura(new Date(2027, 0, 31))).toBe(2023);
  });

  it("passa para 2027 a partir de fevereiro de 2027", () => {
    expect(anoInicioLegislatura(new Date(2027, 1, 1))).toBe(2027);
    expect(anoInicioLegislatura(new Date(2027, 2, 10))).toBe(2027);
  });

  it("também funciona para legislaturas anteriores", () => {
    expect(anoInicioLegislatura(new Date(2020, 5, 1))).toBe(2019);
  });
});
