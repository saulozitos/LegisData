"use client";

import React, { useState } from "react";
import { Users, Info, ShieldAlert, Calculator } from "lucide-react";
import { getSocialClasses } from "@/services/api";
import { useApi } from "@/hooks/useApi";
import { EmptyState, ErrorState, LoadingState } from "@/components/StateViews";
import { fmtNum, isNum } from "@/lib/format";

/**
 * Converte a renda digitada em número. Aceita "5000,50", "5.000,50", "5000.50" e "5.000".
 * Retorna `null` quando o texto não representa um valor monetário válido.
 */
export function parseIncome(raw: string): number | null {
  const text = raw.trim().replace(/\s/g, "").replace(/^R\$/i, "");
  if (!text || !/^[\d.,]+$/.test(text)) return null;
  let normalized: string;
  if (text.includes(",")) {
    normalized = text.replace(/\./g, "").replace(",", ".");
  } else if (/^\d{1,3}(\.\d{3})+$/.test(text)) {
    normalized = text.replace(/\./g, "");
  } else {
    normalized = text;
  }
  const value = Number(normalized);
  return Number.isFinite(value) && value >= 0 ? value : null;
}

export default function SocialClassesExplainer() {
  const [ano, setAno] = useState<number | null>(null);
  const { data, loading, error, retry } = useApi(`social-classes:${ano ?? "latest"}`, (signal) =>
    getSocialClasses(signal, ano ?? undefined)
  );
  const [selectedClass, setSelectedClass] = useState<string | null>(null);
  const [userIncome, setUserIncome] = useState<string>("");
  const [calculatedClass, setCalculatedClass] = useState<string | null>(null);
  const [incomeError, setIncomeError] = useState<string | null>(null);

  const handleCalculateClass = (e: React.FormEvent) => {
    e.preventDefault();
    if (!data) return;
    const income = parseIncome(userIncome);
    if (income === null) {
      setCalculatedClass(null);
      setIncomeError("Informe um valor válido, por exemplo 5000,00.");
      return;
    }
    setIncomeError(null);

    const smCount = income / data.salario_minimo_referencia_brl;
    // Faixas vindas da API (em salários mínimos); a última faixa não tem teto.
    const match = data.classes.find(
      (c) => smCount >= c.faixa_salarios_minimos_min && (c.faixa_salarios_minimos_max === null || smCount < c.faixa_salarios_minimos_max)
    );
    setCalculatedClass(match ? match.classe : null);
    if (!match) setIncomeError("Não foi possível enquadrar este valor nas faixas disponíveis.");
  };

  if (loading) return <LoadingState label="Carregando classes sociais..." />;
  if (error) return <ErrorState onRetry={retry} />;
  if (!data || !data.classes?.length) {
    return <EmptyState title="Classes sociais indisponíveis" />;
  }

  // Classe padrão: a mais populosa; evita índice fixo.
  const mostPopulous = data.classes.reduce((a, b) => (b.percentual_populacao > a.percentual_populacao ? b : a));
  const currentClassInfo = data.classes.find((c) => c.classe === selectedClass) ?? mostPopulous;
  const topClass = data.classes[0];
  const lowerClasses = data.classes.filter((c) => c.classe === "Classe D" || c.classe === "Classe E");
  const lowerPct = isNum(data.resumo_populacional?.maioria_populacao_acumulada_d_e_pct)
    ? data.resumo_populacional.maioria_populacao_acumulada_d_e_pct
    : lowerClasses.reduce((acc, c) => acc + c.percentual_populacao, 0);

  return (
    <div className="bg-slate-900/70 border border-slate-800/80 rounded-2xl p-6 backdrop-blur-md shadow-xl space-y-6">
      {/* Cabeçalho */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800/80 pb-5">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-emerald-500/10 border border-emerald-500/20 rounded-xl text-emerald-400">
              <Users className="w-5 h-5" aria-hidden="true" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                Estratificação Social no Brasil (Classes A, B, C, D e E)
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Microdados da PNAD Contínua (IBGE) • renda domiciliar em salários mínimos
                {" "}• Salário Mínimo de {data.ano_referencia}: R$ {data.salario_minimo_referencia_brl.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-950/80 rounded-xl border border-slate-800 text-xs text-slate-300">
          <Info className="w-4 h-4 text-sky-400 flex-shrink-0" aria-hidden="true" />
          <span>Fonte: {data.fonte}</span>
        </div>
        {data.anos_disponiveis && data.anos_disponiveis.length > 1 && (
          <label className="flex items-center gap-2 text-xs text-slate-300">
            <span>Ano da PNAD</span>
            <select
              value={data.ano_referencia}
              onChange={(e) => setAno(Number(e.target.value))}
              className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-slate-200"
            >
              {data.anos_disponiveis.map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {/* Destaque Educativo: Onde o Brasileiro Realmente Está */}
      <div className="bg-gradient-to-r from-amber-500/10 via-amber-500/5 to-transparent border border-amber-500/20 rounded-xl p-4.5 text-xs text-amber-200/90 flex flex-col md:flex-row items-start md:items-center gap-3">
        <div className="p-2 bg-amber-500/20 rounded-lg text-amber-400 flex-shrink-0">
          <ShieldAlert className="w-5 h-5" aria-hidden="true" />
        </div>
        <div className="space-y-1">
          <h4 className="font-bold text-amber-200 text-sm">
            A Ilusão da &quot;Classe Média&quot; e a Realidade da Renda Nacional
          </h4>
          <p className="text-amber-300/80 leading-relaxed">
            {data.resumo_populacional?.texto_educativo}
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
                  type="button"
                  key={c.classe}
                  aria-pressed={isSelected}
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
                      {fmtNum(c.percentual_populacao)}%
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
              <span className="text-slate-300 font-semibold">{fmtNum(lowerPct)}% em Classes D/E</span>
            </div>
            <div className="w-full h-3.5 bg-slate-800 rounded-lg overflow-hidden flex shadow-inner">
              {data.classes.map((c) => (
                <button
                  type="button"
                  key={c.classe}
                  style={{
                    width: `${c.percentual_populacao}%`,
                    backgroundColor: c.cor
                  }}
                  title={`${c.classe}: ${fmtNum(c.percentual_populacao)}% da população`}
                  aria-label={`${c.classe}: ${fmtNum(c.percentual_populacao)}% da população`}
                  className="h-full border-r border-slate-900/60 last:border-0 hover:opacity-80 transition-opacity cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-white"
                  onClick={() => setSelectedClass(c.classe)}
                />
              ))}
            </div>
            <div className="flex justify-between text-[10px] text-slate-400 mt-1 px-0.5">
              <span>Topo ({topClass.classe}: {fmtNum(topClass.percentual_populacao)}%)</span>
              <span>{mostPopulous.classe} ({fmtNum(mostPopulous.percentual_populacao, 0)}%)</span>
              <span>Base (Classes D/E: {fmtNum(lowerPct, 0)}%)</span>
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
                <span className="font-bold text-slate-200">
                  {isNum(currentClassInfo.percentual_domicilios)
                    ? `${fmtNum(currentClassInfo.percentual_domicilios)}% dos domicílios`
                    : `${fmtNum(currentClassInfo.percentual_populacao)}% dos lares`}
                </span>
              </div>
            </div>

            <p className="text-xs text-slate-300 mt-3.5 leading-relaxed bg-slate-950/60 p-3 rounded-xl border border-slate-800/80">
              {currentClassInfo.descricao}
            </p>
          </div>

          {/* Simulador Interativo de Enquadramento */}
          <div className="p-4.5 rounded-2xl bg-slate-950/80 border border-slate-800 text-xs space-y-3">
            <div className="flex items-center gap-2 text-slate-200 font-bold">
              <Calculator className="w-4 h-4 text-emerald-400" aria-hidden="true" />
              <span>Simulador de Enquadramento de Renda</span>
            </div>
            <p className="text-slate-400 text-[11px]">
              Insira a renda total bruta de todas as pessoas que moram na sua residência para ver o estrato oficial:
            </p>

            <form onSubmit={handleCalculateClass} className="space-y-2.5">
              <div className="relative">
                <span className="absolute left-3 top-2.5 text-slate-400 font-semibold" aria-hidden="true">R$</span>
                <input
                  type="text"
                  inputMode="decimal"
                  aria-label="Renda familiar mensal total em reais"
                  aria-invalid={incomeError ? true : undefined}
                  placeholder="Ex: 5000,00"
                  value={userIncome}
                  onChange={(e) => setUserIncome(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700/80 rounded-xl pl-9 pr-3 py-2 text-slate-100 placeholder-slate-400 focus:outline-none focus:border-emerald-500 text-xs font-medium"
                />
              </div>
              <button
                type="submit"
                className="w-full py-2 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/30 font-bold rounded-xl transition-all"
              >
                Identificar Minha Classe Social
              </button>
            </form>

            {incomeError && (
              <p role="alert" className="text-rose-300 text-[11px]">{incomeError}</p>
            )}

            {calculatedClass && (
              <div className="p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-xl text-center mt-2 animate-in fade-in duration-300">
                <span className="text-slate-400 text-[11px] block">Seu enquadramento oficial:</span>
                <span className="text-base font-extrabold text-emerald-300">{calculatedClass}</span>
                <button
                  type="button"
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
