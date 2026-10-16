"use client";

import React from "react";
import { CheckCircle2, XCircle, UserX, ExternalLink } from "lucide-react";
import type { ResumoVotos, ResumoVotosGrupo } from "@/services/api";
import { fmtNum } from "@/lib/format";
import { safeExternalUrl } from "@/lib/safeUrl";

const GRUPOS = [
  {
    chave: "sim",
    titulo: "Votou Sim",
    vazio: "Nenhum voto Sim registrado.",
    Icone: CheckCircle2,
    tom: "text-emerald-400 border-emerald-500/30 bg-emerald-500/5",
  },
  {
    chave: "nao",
    titulo: "Votou Não",
    vazio: "Nenhum voto Não registrado.",
    Icone: XCircle,
    tom: "text-rose-400 border-rose-500/30 bg-rose-500/5",
  },
  {
    chave: "ausente",
    titulo: "Ausente",
    vazio: "Nenhuma ausência registrada em votação nominal.",
    Icone: UserX,
    tom: "text-amber-400 border-amber-500/30 bg-amber-500/5",
  },
] as const;

function Grupo({ titulo, vazio, Icone, tom, dados }: { titulo: string; vazio: string; Icone: React.ElementType; tom: string; dados: ResumoVotosGrupo }) {
  return (
    <section className={`rounded-xl border p-4 space-y-3 ${tom}`} aria-label={titulo}>
      <header className="flex items-center justify-between">
        <h4 className="flex items-center gap-1.5 text-sm font-bold">
          <Icone className="w-4 h-4" aria-hidden="true" />
          {titulo}
        </h4>
        <span className="text-lg font-extrabold font-mono">{fmtNum(dados.total, 0)}</span>
      </header>
      {dados.itens.length === 0 ? (
        <p className="text-xs text-slate-400">{vazio}</p>
      ) : (
        <ul className="space-y-2 max-h-96 overflow-y-auto pr-2 custom-scrollbar" tabIndex={0} aria-label={`Matérias: ${titulo}`}>
          {dados.itens.map((item, indice) => {
            const url = safeExternalUrl(item.url_oficial ?? undefined);
            return (
              <li key={`${item.proposicao_id}-${indice}`} className="text-xs text-slate-300">
                <div className="flex items-start justify-between gap-2">
                  <span className="font-semibold text-slate-100">{item.proposicao_numero}</span>
                  <span className="text-slate-400 whitespace-nowrap">{item.data}</span>
                </div>
                <p className="text-slate-400 line-clamp-2">{item.proposicao_titulo}</p>
                {url && (
                  <a href={url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sky-400 hover:underline">
                    Ver matéria <ExternalLink className="w-3 h-3" aria-hidden="true" />
                  </a>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

export default function VotesSummaryBlock({ resumo }: { resumo?: ResumoVotos }) {
  if (!resumo) return null;
  return (
    <div className="space-y-3" data-testid="resumo-votos">
      <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider">Como votou nas votações nominais</h4>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        {GRUPOS.map(({ chave, ...g }) => (
          <Grupo key={chave} {...g} dados={resumo[chave]} />
        ))}
      </div>
    </div>
  );
}
