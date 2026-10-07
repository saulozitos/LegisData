"use client";

import React, { useState, useEffect } from "react";
import {
  Users,
  Info,
  DollarSign,
  TrendingDown,
  PieChart as PieChartIcon,
  HelpCircle,
  ShieldAlert,
  ArrowUpRight,
  Calculator
} from "lucide-react";
import { getSocialClasses, ClassesSociaisResponse, ClasseSocialItem } from "@/services/api";

interface SocialClassesExplainerProps {
  mandateId?: string | null;
}

export default function SocialClassesExplainer({ mandateId }: SocialClassesExplainerProps = {}) {
  const [data, setData] = useState<ClassesSociaisResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedClass, setSelectedClass] = useState<string>("Classe C");
  const [userIncome, setUserIncome] = useState<string>("");
  const [calculatedClass, setCalculatedClass] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      try {
        const res = await getSocialClasses();
        if (res) {
          setData(res);
        }
      } catch (err) {
        console.error("Erro ao carregar dados de classes sociais:", err);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  const handleCalculateClass = (e: React.FormEvent) => {
    e.preventDefault();
    if (!userIncome || !data) return;
    const income = parseFloat(userIncome.replace(/\./g, "").replace(",", "."));
    if (isNaN(income) || income < 0) return;

    const sm = data.salario_minimo_referencia_brl;
    const smCount = income / sm;

    if (smCount > 20) {
      setCalculatedClass("Classe A");
    } else if (smCount >= 10) {
      setCalculatedClass("Classe B");
    } else if (smCount >= 4) {
      setCalculatedClass("Classe C");
    } else if (smCount >= 2) {
      setCalculatedClass("Classe D");
    } else {
      setCalculatedClass("Classe E");
    }
  };

  if (loading) {
    return (
      <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-8 backdrop-blur-md animate-pulse text-center">
        <div className="h-6 w-64 bg-slate-800 rounded mx-auto mb-4" />
        <div className="h-4 w-96 bg-slate-800/60 rounded mx-auto" />
      </div>
    );
  }

  if (!data) return null;

  const currentClassInfo = data.classes.find((c) => c.classe === selectedClass) || data.classes[2];

  return (
    <div className="bg-slate-900/70 border border-slate-800/80 rounded-2xl p-6 backdrop-blur-md shadow-xl space-y-6">
      {/* Cabeçalho */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800/80 pb-5">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-emerald-500/10 border border-emerald-500/20 rounded-xl text-emerald-400">
              <Users className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                Estratificação Social no Brasil (Classes A, B, C, D e E)
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Critério Oficial de Renda Familiar do IBGE / FGV Social • Salário Mínimo de Referência: R$ {data.salario_minimo_referencia_brl.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-950/80 rounded-xl border border-slate-800 text-xs text-slate-300">
          <Info className="w-4 h-4 text-sky-400 flex-shrink-0" />
          <span>Fonte: {data.fonte}</span>
        </div>
      </div>

      {/* Destaque Educativo: Onde o Brasileiro Realmente Está */}
      <div className="bg-gradient-to-r from-amber-500/10 via-amber-500/5 to-transparent border border-amber-500/20 rounded-xl p-4.5 text-xs text-amber-200/90 flex flex-col md:flex-row items-start md:items-center gap-3">
        <div className="p-2 bg-amber-500/20 rounded-lg text-amber-400 flex-shrink-0">
          <ShieldAlert className="w-5 h-5" />
        </div>
        <div className="space-y-1">
          <h4 className="font-bold text-amber-200 text-sm">
            A Ilusão da &quot;Classe Média&quot; e a Realidade da Renda Nacional
          </h4>
          <p className="text-amber-300/80 leading-relaxed">
            {data.resumo_populacional.texto_educativo}
          </p>
        </div>
      </div>

      {/* Pirâmide Visual e Comparação de Classes */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Lado Esquerdo: Seletor Visual da Pirâmide */}
        <div className="lg:col-span-7 space-y-3">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-400 mb-1 px-1">
            <span>ESTRATOS SOCIAIS (DO TOPO À BASE)</span>
            <span>% DA POPULAÇÃO</span>
          </div>

          <div className="space-y-2">
            {data.classes.map((c) => {
              const isSelected = selectedClass === c.classe;
              return (
                <button
                  key={c.classe}
                  onClick={() => setSelectedClass(c.classe)}
                  className={`w-full text-left p-3.5 rounded-xl border transition-all flex items-center justify-between group ${
                    isSelected
                      ? "bg-slate-800/90 border-slate-600 shadow-lg scale-[1.01]"
                      : "bg-slate-950/50 border-slate-800/70 hover:bg-slate-800/40 hover:border-slate-700"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <div
                      className="w-3.5 h-3.5 rounded-full ring-2 ring-slate-800 flex-shrink-0"
                      style={{ backgroundColor: c.cor }}
                    />
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-slate-100 text-sm">
                          {c.classe}
                        </span>
                        <span className="text-[11px] px-2 py-0.5 rounded-md bg-slate-800 text-slate-300 font-medium">
                          {c.destaque}
                        </span>
                      </div>
                      <p className="text-xs text-slate-400 mt-0.5">
                        {c.faixa_salarios_minimos} ({c.faixa_renda_formatada})
                      </p>
                    </div>
                  </div>

                  <div className="text-right">
                    <span className="text-base font-extrabold text-slate-100">
                      {c.percentual_populacao.toFixed(1)}%
                    </span>
                    <div className="w-24 h-1.5 bg-slate-800 rounded-full mt-1 overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-500"
                        style={{
                          width: `${Math.min(c.percentual_populacao * 2.8, 100)}%`,
                          backgroundColor: c.cor
                        }}
                      />
                    </div>
                  </div>
                </button>
              );
            })}
          </div>

          {/* Barra de Distribuição Agregada */}
          <div className="pt-2">
            <div className="text-[11px] text-slate-400 mb-1.5 flex justify-between">
              <span>Distribuição Total da População Brasileira (100%):</span>
              <span className="text-slate-300 font-semibold">53% em Classes D/E</span>
            </div>
            <div className="w-full h-3.5 bg-slate-800 rounded-lg overflow-hidden flex shadow-inner">
              {data.classes.map((c) => (
                <div
                  key={c.classe}
                  style={{
                    width: `${c.percentual_populacao}%`,
                    backgroundColor: c.cor
                  }}
                  title={`${c.classe}: ${c.percentual_populacao}% da população`}
                  className="h-full border-r border-slate-900/60 last:border-0 hover:opacity-80 transition-opacity cursor-pointer"
                  onClick={() => setSelectedClass(c.classe)}
                />
              ))}
            </div>
            <div className="flex justify-between text-[10px] text-slate-500 mt-1 px-0.5">
              <span>Topo (Classe A: 2.8%)</span>
              <span>Classe C (31%)</span>
              <span>Base (Classes D/E: 53%)</span>
            </div>
          </div>
        </div>

        {/* Lado Direito: Detalhes da Classe Selecionada + Simulador Rápido */}
        <div className="lg:col-span-5 space-y-4">
          {/* Card da Classe Selecionada */}
          <div
            className="p-5 rounded-2xl border backdrop-blur-md transition-all"
            style={{
              backgroundColor: `${currentClassInfo.cor}0a`,
              borderColor: `${currentClassInfo.cor}33`
            }}
          >
            <div className="flex items-center justify-between mb-3">
              <span
                className="text-xs font-bold px-2.5 py-1 rounded-lg uppercase tracking-wider"
                style={{
                  backgroundColor: `${currentClassInfo.cor}20`,
                  color: currentClassInfo.cor
                }}
              >
                {currentClassInfo.destaque}
              </span>
              <span className="text-xl font-black text-slate-100">
                {currentClassInfo.classe}
              </span>
            </div>

            <div className="space-y-2 text-xs">
              <div className="flex justify-between py-1.5 border-b border-slate-800/80">
                <span className="text-slate-400">Faixa de Salários Mínimos:</span>
                <span className="font-bold text-slate-200">{currentClassInfo.faixa_salarios_minimos}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-slate-800/80">
                <span className="text-slate-400">Renda Familiar Mensal:</span>
                <span className="font-bold text-emerald-400">{currentClassInfo.faixa_renda_formatada}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-slate-800/80">
                <span className="text-slate-400">Parcela da População:</span>
                <span className="font-bold text-slate-200">{currentClassInfo.percentual_populacao.toFixed(1)}% dos lares</span>
              </div>
            </div>

            <p className="text-xs text-slate-300 mt-3.5 leading-relaxed bg-slate-950/60 p-3 rounded-xl border border-slate-800/80">
              {currentClassInfo.descricao}
            </p>
          </div>

          {/* Simulador Interativo de Enquadramento */}
          <div className="p-4.5 rounded-2xl bg-slate-950/80 border border-slate-800 text-xs space-y-3">
            <div className="flex items-center gap-2 text-slate-200 font-bold">
              <Calculator className="w-4 h-4 text-emerald-400" />
              <span>Simulador de Enquadramento de Renda</span>
            </div>
            <p className="text-slate-400 text-[11px]">
              Insira a renda total bruta de todas as pessoas que moram na sua residência para ver o estrato oficial:
            </p>

            <form onSubmit={handleCalculateClass} className="space-y-2.5">
              <div className="relative">
                <span className="absolute left-3 top-2.5 text-slate-500 font-semibold">R$</span>
                <input
                  type="text"
                  placeholder="Ex: 5000,00"
                  value={userIncome}
                  onChange={(e) => setUserIncome(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700/80 rounded-xl pl-9 pr-3 py-2 text-slate-100 placeholder-slate-600 focus:outline-none focus:border-emerald-500 text-xs font-medium"
                />
              </div>
              <button
                type="submit"
                className="w-full py-2 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/30 font-bold rounded-xl transition-all"
              >
                Identificar Minha Classe Social
              </button>
            </form>

            {calculatedClass && (
              <div className="p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-xl text-center mt-2 animate-in fade-in duration-300">
                <span className="text-slate-400 text-[11px] block">Seu enquadramento oficial:</span>
                <span className="text-base font-extrabold text-emerald-300">{calculatedClass}</span>
                <button
                  onClick={() => setSelectedClass(calculatedClass)}
                  className="block mx-auto text-[10px] text-emerald-400 underline mt-1 hover:text-emerald-300"
                >
                  Ver detalhes desta classe
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
