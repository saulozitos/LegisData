"use client";

import React from "react";
import { AlertTriangle, Inbox, RefreshCw } from "lucide-react";

interface ErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
}

export function ErrorState({
  title = "Não foi possível carregar os dados",
  message = "A API não respondeu como esperado. Isto não significa que não existam dados.",
  onRetry,
}: ErrorStateProps) {
  return (
    <div
      role="alert"
      className="rounded-2xl border border-rose-500/30 bg-rose-500/5 p-6 text-center space-y-3"
    >
      <AlertTriangle className="w-8 h-8 text-rose-400 mx-auto" aria-hidden="true" />
      <h3 className="text-sm font-bold text-rose-300">{title}</h3>
      <p className="text-xs text-slate-300 max-w-md mx-auto">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-rose-500/20 hover:bg-rose-500/30 border border-rose-500/40 text-rose-200 text-xs font-semibold transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" aria-hidden="true" />
          Tentar novamente
        </button>
      )}
    </div>
  );
}

interface EmptyStateProps {
  title?: string;
  message?: string;
}

export function EmptyState({
  title = "Dado indisponível",
  message = "Nenhum registro foi encontrado para esta seleção.",
}: EmptyStateProps) {
  return (
    <div
      role="status"
      className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 text-center space-y-2"
    >
      <Inbox className="w-8 h-8 text-slate-400 mx-auto" aria-hidden="true" />
      <h3 className="text-sm font-bold text-slate-200">{title}</h3>
      <p className="text-xs text-slate-300">{message}</p>
    </div>
  );
}

export function LoadingState({ label = "Carregando dados..." }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="animate-pulse space-y-3">
      <span className="sr-only">{label}</span>
      <div className="h-8 w-1/3 bg-slate-900/60 border border-slate-800 rounded-xl" />
      <div className="h-48 bg-slate-900/60 border border-slate-800 rounded-2xl" />
    </div>
  );
}

/** Texto padrão para um valor ausente (nunca exibir "0", "null" ou "undefined"). */
export const UNAVAILABLE = "Dado indisponível";
