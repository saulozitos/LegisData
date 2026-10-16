/** A legislatura federal dura quatro anos e começa em 1º de fevereiro (a de 2023 vai até janeiro de 2027). */
const PRIMEIRA_LEGISLATURA_CONHECIDA = 2023;
const DURACAO_ANOS = 4;

/** Ano de início da legislatura em curso na data informada. */
export function anoInicioLegislatura(hoje: Date): number {
  // em janeiro ainda vale a legislatura que começou no ano anterior ou antes
  const anoEfetivo = hoje.getMonth() === 0 ? hoje.getFullYear() - 1 : hoje.getFullYear();
  const ciclos = Math.floor((anoEfetivo - PRIMEIRA_LEGISLATURA_CONHECIDA) / DURACAO_ANOS);
  return PRIMEIRA_LEGISLATURA_CONHECIDA + ciclos * DURACAO_ANOS;
}
