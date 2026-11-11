import { useState } from 'react';
import { Search } from 'lucide-react';
import type { DossierTab } from '@/components/politician/types';

export interface DestinoDaEntrada {
  aba: string;
  secao?: DossierTab;
  assunto?: string;
}

const PERGUNTAS: Array<{ texto: string; ajuda: string; destino: DestinoDaEntrada }> = [
  {
    texto: 'Como meu deputado votou?',
    ajuda: 'Busque o político e veja os votos dele',
    destino: { aba: 'raiox', secao: 'votacoes' },
  },
  {
    texto: 'Quem financiou a campanha?',
    ajuda: 'Doadores de campanha de cada político',
    destino: { aba: 'raiox', secao: 'financiamento' },
  },
  {
    texto: 'Para onde foram as emendas?',
    ajuda: 'Emendas ao orçamento por autor e destino',
    destino: { aba: 'emendas' },
  },
];

export const ASSUNTOS = ['escala 6x1', 'salário mínimo', 'impostos', 'violência contra a mulher'];

/** Perguntas simples e busca por assunto na entrada do site, cada uma levando direto à consulta certa. */
export default function EntradaRapida({ onIr }: { onIr: (destino: DestinoDaEntrada) => void }) {
  const [assunto, setAssunto] = useState('');

  const buscar = (termo: string) => {
    const limpo = termo.trim();
    if (limpo) onIr({ aba: 'produtividade', assunto: limpo });
  };

  return (
    <section
      aria-label="Comece por uma pergunta"
      className="bg-slate-900/40 border border-slate-800/80 rounded-3xl p-4 sm:p-5 space-y-4"
    >
      <h2 className="text-sm font-bold text-slate-200">O que você quer saber?</h2>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
        {PERGUNTAS.map((p) => (
          <button
            type="button"
            key={p.texto}
            onClick={() => onIr(p.destino)}
            className="text-left rounded-2xl border border-slate-800 bg-slate-950/60 p-3 hover:border-cyan-500/60 focus:outline-none focus:ring-2 focus:ring-cyan-400"
          >
            <span className="block text-sm font-bold text-slate-100">{p.texto}</span>
            <span className="block text-[11px] text-slate-400 mt-0.5">{p.ajuda}</span>
          </button>
        ))}
      </div>

      <form
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          buscar(assunto);
        }}
        className="space-y-2"
      >
        <label htmlFor="busca-por-assunto" className="block text-[11px] font-semibold text-slate-300">
          Ou busque por assunto
        </label>
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" aria-hidden="true" />
            <input
              id="busca-por-assunto"
              type="search"
              value={assunto}
              onChange={(e) => setAssunto(e.target.value)}
              placeholder="Ex.: escala 6x1, salário mínimo, impostos"
              className="w-full rounded-xl bg-slate-950 border border-slate-800 pl-9 pr-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-400"
            />
          </div>
          <button
            type="submit"
            className="px-4 py-2 rounded-xl bg-cyan-500 text-slate-950 text-sm font-bold hover:bg-cyan-400"
          >
            Buscar
          </button>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {ASSUNTOS.map((a) => (
            <button
              type="button"
              key={a}
              onClick={() => buscar(a)}
              className="text-[11px] px-2.5 py-1 rounded-full border border-slate-700 bg-slate-900 text-slate-300 hover:border-cyan-400"
            >
              {a}
            </button>
          ))}
        </div>
      </form>
    </section>
  );
}
