/**
 * Aceita apenas URLs http(s). Qualquer outro esquema (javascript:, data:, etc.)
 * ou valor inválido resulta em `undefined`, para uso em `href`/`src`.
 * Normaliza URLs de fotos oficiais do Senado Federal para o endpoint HTTPS canônico.
 */
export function safeExternalUrl(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  try {
    const trimmed = url.trim();
    const senadoMatch = trimmed.match(
      /^https?:\/\/(?:www|legis)\.senado\.leg\.br\/senadores\/(?:img\/fotos-oficiais\/senador|fotos-oficiais\/)(\d+)(?:\.jpg)?$/i
    );
    if (senadoMatch) {
      return `https://legis.senado.leg.br/senadores/fotos-oficiais/${senadoMatch[1]}`;
    }

    const parsed = new URL(trimmed);
    if (parsed.protocol === "https:" || parsed.protocol === "http:") {
      if (parsed.protocol === "http:" && parsed.hostname.endsWith("senado.leg.br")) {
        parsed.protocol = "https:";
      }
      return parsed.toString();
    }
    return undefined;
  } catch {
    return undefined;
  }
}
