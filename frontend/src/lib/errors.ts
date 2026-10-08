/** Erro de requisição à API: falha de rede, status HTTP não-2xx ou corpo inválido. */
export class ApiError extends Error {
  readonly status: number | null;
  readonly endpoint: string;

  constructor(message: string, endpoint: string, status: number | null = null) {
    super(message);
    this.name = "ApiError";
    this.endpoint = endpoint;
    this.status = status;
  }
}

/** Cancelamentos (AbortController) não são falhas: devem ser ignorados pelo chamador. */
export function isAbortError(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "name" in error &&
    (error as { name?: string }).name === "AbortError"
  );
}
