"use client";

import React from "react";
import PartyLink from "@/components/PartyLink";
import { safeExternalUrl } from "@/lib/safeUrl";

interface ParlamentarCardProps {
  parl: {
    politico_id: string;
    foto_url?: string | null;
    nome_eleitoral: string;
    partido_sigla: string;
    uf: string;
  };
  borderColor: string;
  onSelectPolitician?: (id: string) => void;
  onSelectParty?: (sigla: string) => void;
  onCloseModal?: () => void;
}

export default function ParlamentarCard({
  parl,
  borderColor,
  onSelectPolitician,
  onSelectParty,
  onCloseModal,
}: ParlamentarCardProps) {
  const photo = safeExternalUrl(parl.foto_url);
  const canOpenProfile = Boolean(parl.politico_id && onSelectPolitician);

  return (
    <div
      className={`bg-slate-900/90 border ${borderColor} rounded-xl p-2.5 flex items-center gap-3 hover:border-opacity-100 transition-colors border-opacity-40`}
    >
      {photo ? (
        <img
          src={photo}
          alt=""
          referrerPolicy="no-referrer"
          className="w-10 h-10 rounded-lg object-cover border border-slate-700 shrink-0"
          onError={(e) => {
            e.currentTarget.style.display = "none";
          }}
        />
      ) : (
        <div className="w-10 h-10 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-xs font-bold text-slate-300 shrink-0">
          {parl.nome_eleitoral.slice(0, 2).toUpperCase()}
        </div>
      )}
      <div className="min-w-0">
        {canOpenProfile ? (
          <button
            type="button"
            onClick={() => {
              onCloseModal?.();
              onSelectPolitician?.(parl.politico_id);
            }}
            className="font-bold text-white text-xs block truncate max-w-full text-left cursor-pointer hover:text-cyan-300 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 rounded"
            title={`Abrir o Raio-X de ${parl.nome_eleitoral}`}
          >
            {parl.nome_eleitoral}
          </button>
        ) : (
          <span className="font-bold text-white text-xs block truncate" title={parl.nome_eleitoral}>
            {parl.nome_eleitoral}
          </span>
        )}
        <div className="flex items-center gap-1.5 mt-0.5">
          <PartyLink
            sigla={parl.partido_sigla}
            onSelectParty={
              onSelectParty
                ? (sigla) => {
                    onCloseModal?.();
                    onSelectParty(sigla);
                  }
                : undefined
            }
            className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-slate-800 border border-slate-600 text-slate-200 hover:border-cyan-400 hover:text-cyan-300 transition-colors"
          />
          <span className="text-[10px] text-slate-400">{parl.uf}</span>
        </div>
      </div>
    </div>
  );
}
