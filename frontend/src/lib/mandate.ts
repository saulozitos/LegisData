const ACTIVE_STATUSES = new Set(["TITULAR_ATIVO", "EM_EXERCICIO", "ATIVO"]);

/** Mandato em curso: status explícito de exercício ou, na falta de status, ausência de data de término. */
export function isActiveMandate(status: string | null | undefined, dataFim?: string | null): boolean {
  if (status) return ACTIVE_STATUSES.has(status.toUpperCase());
  return !dataFim;
}

/** Variante estrita (só o status), usada onde a data de fim não é confiável. */
export function isActiveStatus(status: string | null | undefined): boolean {
  return Boolean(status) && ACTIVE_STATUSES.has(String(status).toUpperCase());
}

export interface MandateRange {
  id: string;
  label: string;
  /** Ano de início do mandato. */
  start: number;
  /** Ano de término (ano corrente para mandatos em curso). */
  end: number;
  /** Ano da eleição que originou o mandato. */
  electionYear: number;
}

interface MandateSource {
  id_referencia: string;
  nome_eleitoral: string;
  mandato_numero: number;
  ano_eleicao: number;
  data_inicio: string;
  data_fim: string | null;
}

/** Deriva o intervalo de anos de um mandato a partir do cadastro de presidentes da API. */
export function toMandateRange(p: MandateSource, currentYear: number): MandateRange {
  const start = Number.parseInt(p.data_inicio.slice(0, 4), 10);
  const end = p.data_fim ? Number.parseInt(p.data_fim.slice(0, 4), 10) : currentYear;
  const shortName = p.nome_eleitoral.split(" ").slice(-1)[0];
  return {
    id: p.id_referencia,
    label: `${shortName} ${p.mandato_numero}`,
    start,
    end,
    electionYear: p.ano_eleicao,
  };
}
