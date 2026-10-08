import { describe, it, expect, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { useApi } from './useApi';

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('useApi', () => {
  it('começa carregando e entrega o dado', async () => {
    const fetcher = vi.fn().mockResolvedValue('ok');
    const { result } = renderHook(() => useApi('k', fetcher));
    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBeUndefined();
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toBe('ok');
    expect(result.current.error).toBeNull();
  });

  it('expõe o erro e permite retry', async () => {
    const fetcher = vi.fn().mockRejectedValueOnce(new Error('boom')).mockResolvedValueOnce('depois');
    const { result } = renderHook(() => useApi('k', fetcher));
    await waitFor(() => expect(result.current.error?.message).toBe('boom'));
    expect(result.current.data).toBeUndefined();

    act(() => result.current.retry());
    await waitFor(() => expect(result.current.data).toBe('depois'));
    expect(result.current.error).toBeNull();
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it('erro síncrono do fetcher vira estado de erro', async () => {
    const { result } = renderHook(() =>
      useApi<string>('k', () => {
        throw new Error('sync');
      })
    );
    await waitFor(() => expect(result.current.error?.message).toBe('sync'));
  });

  it('rejeição não-Error vira mensagem genérica', async () => {
    const { result } = renderHook(() => useApi<string>('k', () => Promise.reject('texto')));
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error?.message).toMatch(/Falha ao carregar/);
  });

  it('ignora respostas obsoletas ao trocar a chave e aborta a anterior', async () => {
    const first = deferred<string>();
    const second = deferred<string>();
    const signals: AbortSignal[] = [];
    const fetcher = vi.fn((signal: AbortSignal) => {
      signals.push(signal);
      return signals.length === 1 ? first.promise : second.promise;
    });
    const { result, rerender } = renderHook(({ k }) => useApi(k, fetcher), { initialProps: { k: 'a' } });

    rerender({ k: 'b' });
    expect(signals[0].aborted).toBe(true);
    expect(result.current.loading).toBe(true);

    await act(async () => {
      second.resolve('B');
      await second.promise;
    });
    await act(async () => {
      first.resolve('A');
      await first.promise;
    });
    await waitFor(() => expect(result.current.data).toBe('B'));
  });

  it('não expõe o dado de uma chave anterior, mas guarda em previousData', async () => {
    const fetcher = vi.fn((signal: AbortSignal) => (signal.aborted ? Promise.reject(new Error('abortado')) : new Promise<string>(() => {})));
    fetcher.mockResolvedValueOnce('A');
    const { result, rerender } = renderHook(({ k }) => useApi(k, fetcher), { initialProps: { k: 'a' } });
    await waitFor(() => expect(result.current.data).toBe('A'));

    rerender({ k: 'b' });
    expect(result.current.data).toBeUndefined();
    expect(result.current.previousData).toBe('A');
    expect(result.current.loading).toBe(true);
  });

  it('enabled=false suspende a busca sem loading', () => {
    const fetcher = vi.fn().mockResolvedValue('x');
    const { result } = renderHook(() => useApi('k', fetcher, false));
    expect(fetcher).not.toHaveBeenCalled();
    expect(result.current.loading).toBe(false);
    expect(result.current.data).toBeUndefined();
  });

  it('ignora AbortError sem marcar erro', async () => {
    const abort = Object.assign(new Error('abort'), { name: 'AbortError' });
    const { result } = renderHook(() => useApi<string>('k', () => Promise.reject(abort)));
    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current.error).toBeNull();
  });

  it('aborta ao desmontar', () => {
    let captured: AbortSignal | undefined;
    const { unmount } = renderHook(() =>
      useApi('k', (signal) => {
        captured = signal;
        return new Promise<string>(() => {});
      })
    );
    unmount();
    expect(captured?.aborted).toBe(true);
  });
});
