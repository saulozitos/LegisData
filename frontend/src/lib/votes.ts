/** Rótulo legível para a decisão de um voto nominal; valores desconhecidos nunca viram "Ausente" por padrão. */
function normalizeKey(value: string): string {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toUpperCase().trim();
}

const VOTE_LABELS: Record<string, string> = {
  SIM: "Sim",
  NAO: "Não",
  ABSTENCAO: "Abstenção",
  OBSTRUCAO: "Obstrução",
  AUSENTE: "Ausente",
  ARTIGO_17: "Art. 17",
};

export function voteLabel(decisao: string | null | undefined): string {
  if (!decisao) return "Não informado";
  return VOTE_LABELS[normalizeKey(decisao)] ?? decisao.replace(/_/g, " ");
}

export type VoteTone = "yes" | "no" | "abstain" | "obstruction" | "absent" | "other";

export function voteTone(decisao: string | null | undefined): VoteTone {
  switch (normalizeKey(decisao ?? "")) {
    case "SIM":
      return "yes";
    case "NAO":
      return "no";
    case "ABSTENCAO":
      return "abstain";
    case "OBSTRUCAO":
      return "obstruction";
    case "AUSENTE":
      return "absent";
    default:
      return "other";
  }
}
