import { useCallback, useEffect, useRef, useState } from "react";
import { isAbortError } from "@/lib/errors";

export interface UseApiResult<T> {
  /** Dado da requisição atual. `undefined` enquanto carrega ou em caso de erro. */
  data: T | undefined;
  /** Último dado recebido com sucesso, mesmo que de uma chave anterior (paginação/filtros). */
  previousData: T | undefined;
  error: Error | null;
  loading: boolean;
  retry: () => void;
}

interface Settled<T> {
  id: string;
  data?: T;
  error?: Error;
}

/**
 * Busca de dados com cancelamento e proteção contra respostas obsoletas.
 *
 * - `key` identifica a requisição; ao mudar, a anterior é abortada e o dado antigo deixa de ser exposto.
 * - `fetcher` recebe um `AbortSignal` e pode ser recriado a cada render sem disparar nova busca.
 * - `enabled=false` suspende a busca (sem loading).
 */
export function useApi<T>(
  key: string,
  fetcher: (signal: AbortSignal) => Promise<T>,
  enabled: boolean = true
): UseApiResult<T> {
  const [attempt, setAttempt] = useState(0);
  const [settled, setSettled] = useState<Settled<T> | null>(null);
  const [lastData, setLastData] = useState<T | undefined>(undefined);
  const fetcherRef = useRef(fetcher);

  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  const requestId = `${key}#${attempt}`;

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    // Um erro síncrono do fetcher vira estado de erro (nunca derruba a árvore de componentes).
    let request: Promise<T>;
    try {
      request = Promise.resolve(fetcherRef.current(controller.signal));
    } catch (err) {
      request = Promise.reject(err);
    }
    request
      .then((data) => {
        if (controller.signal.aborted) return;
        setSettled({ id: requestId, data });
        setLastData(data);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted || isAbortError(err)) return;
        setSettled({
          id: requestId,
          error: err instanceof Error ? err : new Error("Falha ao carregar dados."),
        });
      });
    return () => controller.abort();
  }, [requestId, enabled]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  const isCurrent = enabled && settled?.id === requestId;
  return {
    data: isCurrent ? settled?.data : undefined,
    previousData: lastData,
    error: isCurrent ? (settled?.error ?? null) : null,
    loading: enabled && !isCurrent,
    retry,
  };
}
