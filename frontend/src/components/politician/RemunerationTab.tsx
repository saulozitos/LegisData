"use client";

import React from "react";
import {
  DollarSign,
} from "lucide-react";
import type { PoliticoDossier } from "@/services/api";
import { formatMoney } from "./format";

interface RemunerationTabProps {
  dossier: PoliticoDossier;
}

/** Soma valores opcionais preservando "não informado": se todos são null, o resultado é null (nunca 0). */
function somaOpcional(...valores: Array<number | null | undefined>): number | null {
  const informados = valores.filter((v): v is number => typeof v === "number");
  return informados.length === 0 ? null : informados.reduce((a, b) => a + b, 0);
}

export default function RemunerationTab({ dossier }: RemunerationTabProps) {
  const remuneracao = dossier.remuneracao;
  return (
            <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 sm:p-6 space-y-6">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
                <div>
                  <h3 className="text-sm sm:text-base font-bold text-slate-100 flex items-center gap-2">
                    <DollarSign className="w-4 h-4 text-cyan-400" aria-hidden="true" />
                    Transparência Remuneratória e Benefícios Oficiais
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Dados obtidos via Portal da Transparência da Câmara dos Deputados e Senado Federal
                  </p>
                </div>

                <div className="text-xs text-slate-400">
                  Total Bruto 2023: <strong className="text-cyan-400 font-mono">{formatMoney(remuneracao?.resumo?.total_bruto_2023)}</strong>
                </div>
              </div>

              {/* Tabela de Folha Mensal */}
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400 bg-slate-950/60">
                      <th className="py-2.5 px-3">Mês/Ano</th>
                      <th className="py-2.5 px-3">Salário Bruto</th>
                      <th className="py-2.5 px-3">Salário Líquido</th>
                      <th className="py-2.5 px-3">Cota CEAP (Gastos)</th>
                      <th className="py-2.5 px-3">Auxílios / Moradia</th>
                      <th className="py-2.5 px-3">Fonte dos Dados</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {remuneracao?.historico?.map((r) => (
                      <tr key={`${r.ano}-${r.mes}`} className="hover:bg-slate-900/80 transition-colors">
                        <td className="py-2.5 px-3 font-mono font-bold text-slate-200">
                          {String(r.mes).padStart(2, "0")}/{r.ano}
                        </td>
                        <td className="py-2.5 px-3 font-mono text-cyan-400 font-bold">
                          {formatMoney(r.salario_bruto)}
                        </td>
                        <td className="py-2.5 px-3 font-mono text-slate-300">
                          {formatMoney(r.salario_liquido)}
                        </td>
                        <td className="py-2.5 px-3 font-mono text-amber-400">
                          {formatMoney(r.cota_ceap)}
                        </td>
                        <td className="py-2.5 px-3 font-mono text-slate-400">
                          {formatMoney(somaOpcional(r.auxilio_moradia, r.outros_beneficios))}
                        </td>
                        <td className="py-2.5 px-3 text-slate-400 text-[11px]">
                          {r.fonte}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
  );
}
