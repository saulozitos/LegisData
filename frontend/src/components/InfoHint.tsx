"use client";

import React, { useId, useState } from "react";
import { createPortal } from "react-dom";
import { Info, X } from "lucide-react";
import Modal from "@/components/Modal";
import type { Evidencia, ExplicacaoIndicador } from "@/lib/ippmExplicacoes";

interface InfoHintProps {
  explicacao: ExplicacaoIndicador;
  /** Números que levaram ao resultado mostrado no cartão (opcional). */
  evidencia?: Evidencia;
  /** Valor exibido no cartão, repetido no topo do diálogo. */
  resultado?: string;
}

/** Botão "i" pequeno que abre uma explicação em linguagem simples e, se houver, os dados por trás do resultado. */
export default function InfoHint({ explicacao, evidencia, resultado }: InfoHintProps) {
  const [aberto, setAberto] = useState(false);
  const tituloId = useId();

  return (
    <>
      <button
        type="button"
        onClick={() => setAberto(true)}
        aria-label={`Entenda: ${explicacao.titulo}`}
        title="O que é isto? Clique para entender"
        className="inline-flex items-center justify-center w-4 h-4 rounded-full text-slate-500 hover:text-violet-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-violet-400 transition-colors"
      >
        <Info className="w-3.5 h-3.5" aria-hidden="true" />
      </button>

      {/* Portal em document.body: os cartões ficam dentro de contêineres com backdrop-blur/overflow, que prendem e
          cortam elementos `fixed`. Fora deles o diálogo ocupa a tela inteira. */}
      {aberto &&
        createPortal(
          <Modal
            isOpen={aberto}
            onClose={() => setAberto(false)}
            titleId={tituloId}
            className="bg-slate-900 border border-slate-800 rounded-3xl max-w-xl w-full max-h-[85vh] overflow-y-auto p-6 md:p-7 space-y-5 shadow-2xl relative text-left"
          >
            <button
              type="button"
              onClick={() => setAberto(false)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white p-2 rounded-xl bg-slate-800/60 transition-colors"
              aria-label="Fechar explicação"
            >
              <X className="w-4 h-4" aria-hidden="true" />
            </button>

            <div className="space-y-1 pr-10">
              <h3 id={tituloId} className="text-lg font-extrabold text-white">
                {explicacao.titulo}
              </h3>
              {resultado && <p className="text-xs text-violet-300 font-semibold">Resultado atual: {resultado}</p>}
            </div>

            <section className="space-y-1.5">
              <h4 className="text-[11px] font-extrabold uppercase tracking-wider text-slate-400">O que significa</h4>
              <p className="text-sm text-slate-200 leading-relaxed">{explicacao.oQueE}</p>
            </section>

            <section className="space-y-1.5">
              <h4 className="text-[11px] font-extrabold uppercase tracking-wider text-slate-400">Como é calculado</h4>
              <ol className="list-decimal pl-5 space-y-1.5 text-sm text-slate-300 leading-relaxed">
                {explicacao.comoCalcula.map((passo) => (
                  <li key={passo}>{passo}</li>
                ))}
              </ol>
            </section>

            {explicacao.cuidado && (
              <p className="text-xs text-amber-200 bg-amber-500/5 border border-amber-500/30 rounded-xl px-3 py-2 leading-relaxed">
                <strong>Atenção:</strong> {explicacao.cuidado}
              </p>
            )}

            {evidencia && (
              <section className="space-y-2">
                <h4 className="text-[11px] font-extrabold uppercase tracking-wider text-slate-400">
                  Os números por trás deste resultado
                </h4>
                {evidencia.linhas.length > 0 ? (
                  <div className="max-h-56 overflow-y-auto rounded-xl border border-slate-800">
                    <table className="w-full text-xs text-left">
                      <thead className="bg-slate-950/80 text-slate-400 sticky top-0">
                        <tr>
                          {evidencia.cabecalho.map((titulo, i) => (
                            <th key={titulo} className={`py-2 px-3 font-semibold ${i === 0 ? "" : "text-right"}`}>
                              {titulo}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/70">
                        {evidencia.linhas.map((linha) => (
                          <tr key={linha.sigla} className={linha.vencedor ? "bg-violet-500/10" : undefined}>
                            <td className="py-2 px-3 font-bold" style={{ color: linha.cor || "#e2e8f0" }}>
                              {linha.sigla}
                              {linha.vencedor && <span className="ml-1.5 text-[10px] text-violet-300">vencedor</span>}
                            </td>
                            {linha.colunas.map((coluna, i) => (
                              <td key={`${linha.sigla}-${i}`} className="py-2 px-3 text-right font-mono text-slate-200">
                                {coluna}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : null}
                {evidencia.rodape && <p className="text-[11px] text-slate-400">{evidencia.rodape}</p>}
              </section>
            )}
          </Modal>,
          document.body
        )}
    </>
  );
}
