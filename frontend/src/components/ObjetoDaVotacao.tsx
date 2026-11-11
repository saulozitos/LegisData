import { Info } from 'lucide-react';
import type { ObjetoVotacao } from '@/services/api';

/**
 * Diz o que a votação decidiu, junto do placar: um requerimento de urgência, um destaque ou uma emenda não são a
 * aprovação do projeto. Sem objeto, a fonte não informa e a tela diz isso em vez de supor.
 */
export default function ObjetoDaVotacao({ objeto }: { objeto?: ObjetoVotacao | null }) {
  if (!objeto) {
    return (
      <p className="text-[11px] text-slate-400" data-testid="objeto-votacao">
        <span className="font-semibold text-slate-300">O que foi votado:</span> a fonte oficial não informa.
      </p>
    );
  }
  return (
    <div className="space-y-1" data-testid="objeto-votacao">
      <p className="flex items-center gap-1.5 flex-wrap text-[11px] text-slate-400">
        <span className="font-semibold text-slate-300">O que foi votado:</span>
        <span
          className={`px-2 py-0.5 rounded-full border font-bold ${
            objeto.decide_merito
              ? 'bg-cyan-500/10 text-cyan-300 border-cyan-500/30'
              : 'bg-amber-500/10 text-amber-300 border-amber-500/30'
          }`}
        >
          {objeto.rotulo}
        </span>
      </p>
      {!objeto.decide_merito && (
        <p className="flex items-start gap-1.5 text-[11px] text-amber-200/90">
          <Info className="w-3 h-3 mt-0.5 flex-shrink-0" aria-hidden="true" />
          <span>{objeto.explicacao}</span>
        </p>
      )}
    </div>
  );
}
