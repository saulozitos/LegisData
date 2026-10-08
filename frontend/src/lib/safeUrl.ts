/**
 * Aceita apenas URLs http(s). Qualquer outro esquema (javascript:, data:, etc.)
 * ou valor inválido resulta em `undefined`, para uso em `href`/`src`.
 */
export function safeExternalUrl(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  try {
    const parsed = new URL(url.trim());
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.toString() : undefined;
  } catch {
    return undefined;
  }
}
