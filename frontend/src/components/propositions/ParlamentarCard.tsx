import React from 'react';

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
  return (
    <div
      className={`bg-slate-900/90 border ${borderColor} rounded-xl p-2.5 flex items-center gap-3 hover:border-opacity-100 transition-colors border-opacity-40`}
    >
      {parl.foto_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={parl.foto_url}
          alt={parl.nome_eleitoral}
          className="w-10 h-10 rounded-lg object-cover border border-slate-700 shrink-0"
          onError={(e) => {
            (e.target as HTMLElement).style.display = "none";
          }}
        />
      ) : (
        <div className="w-10 h-10 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-xs font-bold text-slate-400 shrink-0">
          {parl.nome_eleitoral.slice(0, 2).toUpperCase()}
        </div>
      )}
      <div className="min-w-0">
        <span
          onClick={() => {
            if (parl.politico_id && onSelectPolitician) {
              if (onCloseModal) onCloseModal();
              onSelectPolitician(parl.politico_id);
            }
          }}
          className={`font-bold text-white text-xs block truncate ${
            parl.politico_id && onSelectPolitician ? "cursor-pointer hover:text-cyan-300 transition-colors" : ""
          }`}
          title={parl.nome_eleitoral}
        >
          {parl.nome_eleitoral}
        </span>
        <div className="flex items-center gap-1.5 mt-0.5">
          <span
            onClick={(e) => {
              if (parl.partido_sigla && onSelectParty) {
                e.stopPropagation();
                if (onCloseModal) onCloseModal();
                onSelectParty(parl.partido_sigla);
              }
            }}
            className={`text-[10px] font-semibold px-1.5 py-0.2 rounded bg-slate-800 border ${
              borderColor.replace("border-", "border-").replace("/20", "/30")
            } text-opacity-90 ${
              onSelectParty ? "cursor-pointer hover:border-cyan-400 hover:text-cyan-300 transition-colors" : ""
            }`}
            title={onSelectParty ? `Ver bancada do ${parl.partido_sigla}` : undefined}
          >
            {parl.partido_sigla}
          </span>
          <span className="text-[10px] text-slate-400">{parl.uf}</span>
        </div>
      </div>
    </div>
  );
}
