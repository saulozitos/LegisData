"use client";

import { useEffect } from "react";

export default function GlobalError({
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
    <html lang="pt-BR">
      <body style={{ margin: 0, background: "#020617", color: "#f1f5f9", fontFamily: "Arial, Helvetica, sans-serif" }}>
        <main style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", padding: "1rem" }}>
          <div role="alert" style={{ maxWidth: "28rem", textAlign: "center" }}>
            <h1 style={{ fontSize: "1.25rem", marginBottom: "0.75rem" }}>O LegisData encontrou um erro inesperado</h1>
            <p style={{ fontSize: "0.9rem", color: "#cbd5e1", marginBottom: "1rem" }}>
              Não foi possível carregar a aplicação. Tente novamente em instantes.
            </p>
            <button
              type="button"
              onClick={() => retry()}
              style={{ padding: "0.5rem 1rem", borderRadius: "0.75rem", border: "1px solid #fb7185", background: "transparent", color: "#fecdd3", cursor: "pointer" }}
            >
              Tentar novamente
            </button>
          </div>
        </main>
      </body>
    </html>
  );
}
