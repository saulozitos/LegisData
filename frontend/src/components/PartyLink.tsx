"use client";

import React from "react";

interface PartyLinkProps {
  sigla: string | null | undefined;
  onSelectParty?: (sigla: string) => void;
  className?: string;
  children?: React.ReactNode;
}

/**
 * Sigla de partido clicável e acessível: vira <button> quando há `onSelectParty`
 * (foco/Enter/Espaço funcionam) e <span> quando é apenas informativa.
 */
export default function PartyLink({ sigla, onSelectParty, className = "", children }: PartyLinkProps) {
  if (!sigla) return <span className={className}>{children ?? "Indisponível"}</span>;
  if (!onSelectParty) return <span className={className}>{children ?? sigla}</span>;
  return (
    <button
      type="button"
      onClick={() => onSelectParty(sigla)}
      title={`Ver bancada do ${sigla}`}
      className={`cursor-pointer hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 rounded ${className}`}
    >
      {children ?? sigla}
    </button>
  );
}
