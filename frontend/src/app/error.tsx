"use client";

import { useEffect } from "react";

export default function RouteError({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <main id="main-content" className="min-h-[60vh] flex items-center justify-center px-4">
      <div role="alert" className="max-w-md text-center space-y-4 rounded-2xl border border-rose-500/30 bg-rose-500/5 p-8">
        <h1 className="text-xl font-bold text-rose-300">Algo deu errado ao exibir esta página</h1>
        <p className="text-sm text-slate-300">
          Ocorreu um erro inesperado. Seus dados não foram afetados; tente carregar a seção novamente.
        </p>
        <button
          type="button"
          onClick={() => retry()}
          className="px-4 py-2 rounded-xl bg-rose-500/20 hover:bg-rose-500/30 border border-rose-500/40 text-rose-200 text-sm font-semibold transition-colors"
        >
          Tentar novamente
        </button>
      </div>
    </main>
  );
}
