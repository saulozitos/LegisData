"use client";

import React, { useState } from "react";
import {
  ResponsiveContainer,
  Tooltip,
  Cell,
  Pie,
  PieChart as RechartsPieChart,
} from "recharts";
import {
  Search,
  Sparkles,
  ExternalLink,
  PieChart as LucidePieChart,
  Trophy,
  Users,
  Layers,
  Award,
  Info,
  CheckCircle2,
} from "lucide-react";
import { PoliticoDossier, getPoliticianProductivity, PoliticianProductivityIalp } from "@/services/api";
import { useEffect } from "react";
import { safeExternalUrl } from "@/lib/safeUrl";
import { fmtNum } from "@/lib/format";

interface PropositionsTabProps {
  dossier: PoliticoDossier;
}

export default function PropositionsTab({ dossier }: PropositionsTabProps) {
  const [proposicaoFilter, setProposicaoFilter] = useState<"TODAS" | "IMPACTO" | "SIMBOLICO">("TODAS");
  const [autoriaFilter, setAutoriaFilter] = useState<"TODAS" | "PRINCIPAL" | "COAUTORIA">("TODAS");
  const [proposicaoSearch, setProposicaoSearch] = useState<string>("");
  const [showMetodologia, setShowMetodologia] = useState<boolean>(false);

  const polId = dossier?.perfil?.id;
  const [liveIalp, setLiveIalp] = useState<PoliticianProductivityIalp | null>(null);

  useEffect(() => {
    if (!polId) return;
    let active = true;
    getPoliticianProductivity(polId)
      .then((data) => {
        if (active) setLiveIalp(data);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [polId]);

  const rel = dossier?.relevancia_legislativa;
  const liderancaCount = liveIalp?.distribuicao_autoria?.autor_principal ?? rel?.lideranca_legislativa_count ?? rel?.total_proposicoes ?? 0;
  const apoioCount = liveIalp?.distribuicao_autoria?.coautor ?? rel?.apoio_politico_count ?? 0;
  const taxaEficiencia = liveIalp?.taxa_eficacia_pct ?? rel?.taxa_eficiencia_pct ?? 0;
  const scoreAtividade = liveIalp?.score_ialp_total ?? rel?.score_ialp ?? rel?.score_atividade_ponderada ?? 0;
  const complexidade = rel?.distribuicao_complexidade ?? { alta: 0, media: 0, baixa: 0 };
  const desvioFoco = liveIalp?.desvio_foco ?? rel?.desvio_foco ?? {
    estruturais: complexidade.alta + complexidade.media,
    burocraticas: complexidade.baixa,
    proporcao_estrutural_pct: Math.round(((complexidade.alta + complexidade.media) / Math.max(liderancaCount + apoioCount, 1)) * 100),
    diagnostico: (complexidade.alta + complexidade.media) >= complexidade.baixa ? "Foco Estrutural Predominante" : "Foco Burocrático / Operacional",
  };

  return (
    <div className="space-y-6">
      {/* ========================================================================= */}
      {/* 1. AS 3 FRENTES LIMPAS DA ATIVIDADE LEGISLATIVA (VISÃO CIDADÃ LEIGA)       */}
      {/* ========================================================================= */}
      <section aria-label="Indicadores de Atividade Legislativa Ponderada" className="space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
          <div>
            <h2 className="text-base sm:text-lg font-black text-white flex items-center gap-2">
              <Award className="w-5 h-5 text-amber-400" aria-hidden="true" />
              Atividade Legislativa Ponderada
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Métrica justa que separa autoria intelectual direta de mero apoio regimental em quóruns.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowMetodologia(!showMetodologia)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-800 text-xs font-semibold text-cyan-400 hover:text-cyan-300 hover:border-cyan-500/40 transition-colors w-fit"
            aria-expanded={showMetodologia}
          >
            <Info className="w-3.5 h-3.5" aria-hidden="true" />
            <span>{showMetodologia ? "Ocultar Metodologia" : "Entenda a Pontuação"}</span>
          </button>
        </div>

        {/* Modal / Card Retrátil de Metodologia */}
        {showMetodologia && (
          <div className="bg-slate-950/90 border border-cyan-500/30 rounded-2xl p-4 sm:p-5 text-xs text-slate-300 space-y-3 animate-in fade-in duration-300 shadow-xl">
            <h3 className="font-bold text-white text-sm flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-cyan-400" aria-hidden="true" />
              Metodologia de 4 Pilares da Atividade Legislativa Justa
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-[11px] leading-relaxed">
              <div className="bg-slate-900/60 p-3 rounded-xl border border-slate-800 space-y-1">
                <span className="font-bold text-amber-300 block">1. Modelo Ponderado (Autor vs Coautor)</span>
                <p className="text-slate-400">
                  • <strong>Autor Principal (Peso 1.0)</strong>: Liderança, redação intelectual e defesa direta da proposta.<br />
                  • <strong>Coautor / Signatário (Peso 0.2)</strong>: Apoio institucional ou subscrição para atingir o quórum de tramitação (ex: PECs exigem 27 senadores ou 171 deputados).
                </p>
              </div>
              <div className="bg-slate-900/60 p-3 rounded-xl border border-slate-800 space-y-1">
                <span className="font-bold text-sky-300 block">2. Complexidade por Tipo de Matéria</span>
                <p className="text-slate-400">
                  • <strong>Alta (Peso 3.0)</strong>: PECs (alteram a Constituição Federal).<br />
                  • <strong>Média (Peso 2.0)</strong>: PLs, PLPs e Medidas Provisórias.<br />
                  • <strong>Baixa / Apoio (Peso 1.0 ou 0.1)</strong>: Decretos legislativos e requerimentos simples.
                </p>
              </div>
              <div className="bg-slate-900/60 p-3 rounded-xl border border-slate-800 space-y-1">
                <span className="font-bold text-purple-300 block">3. Produção Institucional Isolada</span>
                <p className="text-slate-400">
                  Projetos apresentados por entidades colegiadas (Comissões Temáticas, Mesa Diretora ou Poder Executivo)
                  não concedem pontos individuais artificiais para parlamentares daquela comissão.
                </p>
              </div>
              <div className="bg-slate-900/60 p-3 rounded-xl border border-slate-800 space-y-1">
                <span className="font-bold text-emerald-300 block">4. Tramitação & Eficácia (Qualidade)</span>
                <p className="text-slate-400">
                  • <strong>Em tramitação</strong>: Multiplicador base (1.0x).<br />
                  • <strong>Relatório aprovado</strong>: Bônus de avanço (1.5x).<br />
                  • <strong>Transformado em Lei</strong>: Bônus máximo (3.0x - sucesso legislativo concreto).
                </p>
              </div>
            </div>
          </div>
        )}

        {/* As 3 Frentes Limpas + Score Ponderado */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {/* Card 1: Liderança Legislativa */}
          <div className="bg-gradient-to-br from-amber-500/10 via-slate-900/90 to-slate-950 border border-amber-500/30 rounded-2xl p-4 flex flex-col justify-between shadow-sm">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold text-amber-300 uppercase tracking-wider flex items-center gap-1.5">
                <Trophy className="w-4 h-4 text-amber-400" aria-hidden="true" />
                Liderança Legislativa
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 font-bold">
                1.0 pt
              </span>
            </div>
            <div className="my-2.5">
              <span className="text-2xl sm:text-3xl font-black text-white font-mono block">
                {liderancaCount}
              </span>
              <span className="text-[11px] text-slate-300 font-medium">
                {liderancaCount === 1 ? "Projeto como autor principal" : "Projetos como autor principal"}
              </span>
            </div>
            <div className="text-[10px] text-slate-400 pt-2 border-t border-slate-800">
              Proposições com redação, iniciativa e defesa direta do parlamentar.
            </div>
          </div>

          {/* Card 2: Apoio Político */}
          <div className="bg-gradient-to-br from-indigo-500/10 via-slate-900/90 to-slate-950 border border-indigo-500/30 rounded-2xl p-4 flex flex-col justify-between shadow-sm">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold text-indigo-300 uppercase tracking-wider flex items-center gap-1.5">
                <Users className="w-4 h-4 text-indigo-400" aria-hidden="true" />
                Apoio Político
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 font-bold">
                0.2 pt
              </span>
            </div>
            <div className="my-2.5">
              <span className="text-2xl sm:text-3xl font-black text-white font-mono block">
                {apoioCount}
              </span>
              <span className="text-[11px] text-slate-300 font-medium">
                {apoioCount === 1 ? "Projeto coassinado" : "Projetos coassinados"}
              </span>
            </div>
            <div className="text-[10px] text-slate-400 pt-2 border-t border-slate-800">
              Apoio de bancada e subscrição para quórum regimental de PECs/PLPs.
            </div>
          </div>

          {/* Card 3: Eficiência Legislativa */}
          <div className="bg-gradient-to-br from-emerald-500/10 via-slate-900/90 to-slate-950 border border-emerald-500/30 rounded-2xl p-4 flex flex-col justify-between shadow-sm">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold text-emerald-300 uppercase tracking-wider flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" aria-hidden="true" />
                Eficiência Legislativa
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-bold">
                3.0x Leis
              </span>
            </div>
            <div className="my-2.5">
              <span className="text-2xl sm:text-3xl font-black text-emerald-400 font-mono block">
                {taxaEficiencia}%
              </span>
              <span className="text-[11px] text-slate-300 font-medium">
                Taxa de avanço / aprovação
              </span>
            </div>
            <div className="text-[10px] text-slate-400 pt-2 border-t border-slate-800">
              Projetos de iniciativa própria que avançaram ou viraram norma jurídica.
            </div>
          </div>

          {/* Card 4: Score Ponderado da Atividade */}
          <div className="bg-gradient-to-br from-cyan-500/10 via-slate-900/90 to-slate-950 border border-cyan-500/30 rounded-2xl p-4 flex flex-col justify-between shadow-sm">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold text-cyan-300 uppercase tracking-wider flex items-center gap-1.5">
                <Sparkles className="w-4 h-4 text-cyan-400" aria-hidden="true" />
                Score de Atividade
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 font-bold">
                Consolidado
              </span>
            </div>
            <div className="my-2.5">
              <span className="text-2xl sm:text-3xl font-black text-cyan-300 font-mono block">
                {fmtNum(scoreAtividade)} <span className="text-sm font-normal text-slate-400">pts</span>
              </span>
              <span className="text-[11px] text-slate-300 font-medium">
                Pontuação ponderada justa
              </span>
            </div>
            <div className="text-[10px] text-slate-400 pt-2 border-t border-slate-800">
              {complexidade.alta} PECs • {complexidade.media} PLs/PLPs • {complexidade.baixa} Outros
            </div>
          </div>
        </div>

        {/* ========================================================================= */}
        {/* ÍNDICE DE DESVIO DE FOCO (ESTRUTURAL VS BUROCRÁTICA) & TOP COAUTORES       */}
        {/* ========================================================================= */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 pt-1">
          {/* Card: Desvio de Foco */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 flex flex-col justify-between">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <span className="text-xs font-bold text-white flex items-center gap-1.5">
                <Layers className="w-4 h-4 text-cyan-400" />
                Índice de Desvio de Foco (Estrutural vs. Burocrático)
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-500/15 text-cyan-300 font-bold border border-cyan-500/30">
                {desvioFoco.proporcao_estrutural_pct}% Estrutural
              </span>
            </div>

            <div className="my-3 space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-300">
                  Alta Complexidade (PEC, PLP, PL): <strong className="text-cyan-300 font-mono">{desvioFoco.estruturais}</strong>
                </span>
                <span className="text-slate-400">
                  Burocráticas (REQ, INC): <strong className="text-rose-300 font-mono">{desvioFoco.burocraticas}</strong>
                </span>
              </div>

              {/* Barra Comparativa de Proporção */}
              <div className="w-full bg-slate-950 rounded-full h-3 overflow-hidden flex border border-slate-800">
                <div
                  className="bg-gradient-to-r from-cyan-500 to-indigo-500 h-full transition-all duration-500"
                  style={{ width: `${Math.min(Math.max(desvioFoco.proporcao_estrutural_pct, 5), 100)}%` }}
                  title={`Estruturais: ${desvioFoco.estruturais}`}
                />
                <div
                  className="bg-rose-500/60 h-full transition-all duration-500"
                  style={{ width: `${Math.max(0, 100 - desvioFoco.proporcao_estrutural_pct)}%` }}
                  title={`Burocráticas: ${desvioFoco.burocraticas}`}
                />
              </div>

              <div className="flex items-center justify-between text-[10px] text-slate-400 font-mono">
                <span>Pautas Substanciais ({desvioFoco.proporcao_estrutural_pct}%)</span>
                <span>Demandas de Apoio ({(100 - desvioFoco.proporcao_estrutural_pct).toFixed(0)}%)</span>
              </div>
            </div>

            <div className="text-[11px] text-slate-300 pt-2 border-t border-slate-800 flex items-center justify-between">
              <span>Diagnóstico: <strong className="text-white">{desvioFoco.diagnostico}</strong></span>
              <span className="text-[10px] text-slate-500 font-mono">Módulo Científico 1</span>
            </div>
          </div>

          {/* Card: Articulação & Top Coautores */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 flex flex-col justify-between">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <span className="text-xs font-bold text-white flex items-center gap-1.5">
                <Users className="w-4 h-4 text-indigo-400" />
                Rede de Articulação & Principais Coautores
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-500/15 text-indigo-300 font-bold border border-indigo-500/30">
                Grafo Ponderado
              </span>
            </div>

            <div className="my-2 space-y-1.5">
              {liveIalp && liveIalp.top_coautores.length > 0 ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                  {liveIalp.top_coautores.slice(0, 4).map((coa) => (
                    <div
                      key={coa.id}
                      className="bg-slate-950/80 border border-slate-800 px-2.5 py-1.5 rounded-xl flex items-center justify-between text-xs"
                    >
                      <span className="text-slate-200 font-semibold truncate max-w-[140px]">
                        {coa.nome_eleitoral}
                      </span>
                      <span className="text-[11px] font-mono font-bold text-indigo-300 bg-indigo-500/20 px-1.5 py-0.5 rounded">
                        {coa.projetos_compartilhados} projs
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-400 italic py-2">
                  Parlamentar atua prioritariamente com autoria individual ou sem coautores recorrentes no período analisado.
                </p>
              )}
            </div>

            <div className="text-[10px] text-slate-400 pt-2 border-t border-slate-800">
              Identifica afinidades programáticas e frentes interpartidárias no Congresso.
            </div>
          </div>
        </div>
      </section>

      {/* ========================================================================= */}
      {/* 2. DETECTOR DE LEIS INÚTEIS & RELEVÂNCIA TEMÁTICA                         */}
      {/* ========================================================================= */}
      <div className="bg-gradient-to-br from-slate-900/90 via-slate-950/90 to-purple-950/30 border border-purple-500/30 rounded-2xl p-5 sm:p-6 backdrop-blur-md shadow-lg space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-800">
          <div className="flex items-center gap-3">
            <div className="p-3 rounded-2xl bg-purple-500/10 border border-purple-500/20 text-purple-400 shadow-inner">
              <LucidePieChart className="w-7 h-7" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-lg font-black text-slate-100">
                  Detector de Leis Inúteis & Relevância Legislativa
                </h3>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-500/15 text-purple-300 border border-purple-500/30 font-bold">
                  Arsenal Antidesinformação
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Classificação automatizada por processamento de linguagem natural: Leis Estruturais vs Homenagens Simbólicas
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400">Diagnóstico:</span>
            <span className={`text-xs font-mono font-bold px-3 py-1.5 rounded-xl border ${
              (rel?.percentual_impacto || 0) >= 60
                ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/40"
                : "bg-amber-500/15 text-amber-300 border-amber-500/40"
            }`}>
              {rel?.diagnostico || "Em análise"}
            </span>
          </div>
        </div>

        {/* Grid Analítico: Gráfico de Pizza + Estatísticas Detalhadas */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-center pt-2">
          {/* Painel do Gráfico de Pizza */}
          <div className="bg-slate-950/80 border border-slate-800 rounded-2xl p-4 flex flex-col items-center justify-center">
            <span className="text-xs font-bold text-slate-200 mb-1">
              Proporção de Relevância Legislativa
            </span>
            <span className="text-[10px] text-slate-400 font-mono mb-2">
              Gráfico de Pizza: Projetos de Impacto ({rel?.percentual_impacto || 0}%) vs Simbólicos ({rel?.percentual_simbolico || 0}%)
            </span>

            <div className="w-full h-52">
              <ResponsiveContainer width="100%" height="100%">
                <RechartsPieChart>
                  <Pie
                    data={[
                      {
                        name: "Projetos de Impacto / Substanciais",
                        value: rel?.projetos_impacto || 0,
                        pct: rel?.percentual_impacto || 0,
                      },
                      {
                        name: "Projetos Simbólicos / Homenagens",
                        value: rel?.projetos_simbolicos || 0,
                        pct: rel?.percentual_simbolico || 0,
                      },
                    ]}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={80}
                    paddingAngle={4}
                  >
                    <Cell fill="#10b981" />
                    <Cell fill="#f59e0b" />
                  </Pie>
                  <Tooltip
                    content={({ active, payload }) => {
                      if (!active || !payload || !payload.length) return null;
                      const d = payload[0].payload;
                      return (
                        <div className="bg-slate-900 border border-slate-700 p-2.5 rounded-xl text-xs shadow-xl space-y-1">
                          <span className="font-bold text-slate-200 block">{d.name}</span>
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-cyan-400 font-bold">{d.value} matérias</span>
                            <span className="text-slate-400 font-mono">({d.pct}%)</span>
                          </div>
                        </div>
                      );
                    }}
                  />
                </RechartsPieChart>
              </ResponsiveContainer>
            </div>

            <div className="grid grid-cols-2 gap-2 w-full pt-2 text-[11px] font-mono">
              <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg p-2 text-center">
                <span className="text-emerald-400 font-bold block">
                  Impacto ({rel?.percentual_impacto || 0}%)
                </span>
                <span className="text-slate-400 text-[10px]">
                  {rel?.projetos_impacto || 0} projetos
                </span>
              </div>
              <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-2 text-center">
                <span className="text-amber-400 font-bold block">
                  Simbólico ({rel?.percentual_simbolico || 0}%)
                </span>
                <span className="text-slate-400 text-[10px]">
                  {rel?.projetos_simbolicos || 0} projetos
                </span>
              </div>
            </div>
          </div>

          {/* Informações Metodológicas & Explicativas */}
          <div className="lg:col-span-2 space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                <span className="text-[10px] text-slate-400 font-medium block mb-1">Total de Proposições</span>
                <span className="text-xl font-black font-mono text-cyan-400 block">
                  {rel?.total_proposicoes || 0}
                </span>
                <span className="text-[10px] text-slate-400 mt-1 block">Amostra recente cadastrada</span>
              </div>
              <div className="bg-slate-950/70 border border-emerald-500/30 rounded-xl p-3.5">
                <span className="text-[10px] text-emerald-400 font-medium block mb-1">Impacto / Estrutural</span>
                <span className="text-xl font-black font-mono text-emerald-400 block">
                  {rel?.projetos_impacto || 0} ({rel?.percentual_impacto || 0}%)
                </span>
                <span className="text-[10px] text-slate-400 mt-1 block">Economia, Saúde, Código Penal</span>
              </div>
              <div className="bg-slate-950/70 border border-amber-500/30 rounded-xl p-3.5">
                <span className="text-[10px] text-amber-400 font-medium block mb-1">Simbólico / Homenagem</span>
                <span className="text-xl font-black font-mono text-amber-400 block">
                  {rel?.projetos_simbolicos || 0} ({rel?.percentual_simbolico || 0}%)
                </span>
                <span className="text-[10px] text-slate-400 mt-1 block">Títulos, Homenagens e Datas</span>
              </div>
            </div>

            <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5 space-y-2 text-xs">
              <span className="font-bold text-slate-200 block">Como funciona o algoritmo de classificação?</span>
              <p className="text-slate-400 leading-relaxed text-[11px]">
                O detector analisa a ementa de cada proposição em busca de marcadores semânticos honoríficos (como <em>&quot;Dia Nacional&quot;</em>, <em>&quot;Homenagem&quot;</em>, <em>&quot;Denomina&quot;</em>, <em>&quot;Cidadão Honorário&quot;</em> e <em>&quot;Título&quot;</em>). Matérias com essas características são categorizadas como <strong>Simbólicas</strong>, enquanto as demais são classificadas como <strong>Impacto/Substancial</strong>.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 3. FILTROS POR PAPEL DE AUTORIA, RELEVÂNCIA E BUSCA                       */}
      {/* ========================================================================= */}
      <div className="flex flex-col gap-3 bg-slate-900/60 border border-slate-800 p-3.5 rounded-2xl">
        <div className="flex flex-wrap items-center justify-between gap-3">
          {/* Filtro de Papel de Autoria */}
          <div className="flex items-center gap-1.5 overflow-x-auto text-xs">
            <span className="text-[11px] font-semibold text-slate-400 mr-1">Autoria:</span>
            <button
              type="button"
              onClick={() => setAutoriaFilter("TODAS")}
              className={`px-3 py-1.5 rounded-xl font-bold transition-all whitespace-nowrap ${
                autoriaFilter === "TODAS"
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Todos os Papéis ({dossier?.materias_propostas?.length || 0})
            </button>
            <button
              type="button"
              onClick={() => setAutoriaFilter("PRINCIPAL")}
              className={`px-3 py-1.5 rounded-xl font-bold transition-all whitespace-nowrap flex items-center gap-1 ${
                autoriaFilter === "PRINCIPAL"
                  ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Trophy className="w-3 h-3 text-amber-400" />
              Liderança ({liderancaCount})
            </button>
            <button
              type="button"
              onClick={() => setAutoriaFilter("COAUTORIA")}
              className={`px-3 py-1.5 rounded-xl font-bold transition-all whitespace-nowrap flex items-center gap-1 ${
                autoriaFilter === "COAUTORIA"
                  ? "bg-indigo-500/20 text-indigo-300 border border-indigo-500/40"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Users className="w-3 h-3 text-indigo-400" />
              Coautoria ({apoioCount})
            </button>
          </div>

          {/* Busca textual */}
          <div className="relative w-full sm:w-64">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" aria-hidden="true" />
            <input
              type="text"
              value={proposicaoSearch}
              onChange={(e) => setProposicaoSearch(e.target.value)}
              placeholder="Buscar ementa, tipo ou número..."
              className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder:text-slate-400 focus:outline-none focus:border-purple-500/50"
            />
          </div>
        </div>

        {/* Filtro de Relevância Temática (Impacto vs Simbólico) */}
        <div className="flex items-center gap-1.5 overflow-x-auto text-xs pt-1 border-t border-slate-800/80">
          <span className="text-[11px] font-semibold text-slate-400 mr-1">Relevância:</span>
          <button
            type="button"
            onClick={() => setProposicaoFilter("TODAS")}
            className={`px-2.5 py-1 rounded-lg font-semibold transition-all whitespace-nowrap ${
              proposicaoFilter === "TODAS"
                ? "bg-purple-500/20 text-purple-300 border border-purple-500/40"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Todas ({dossier?.materias_propostas?.length || 0})
          </button>
          <button
            type="button"
            onClick={() => setProposicaoFilter("IMPACTO")}
            className={`px-2.5 py-1 rounded-lg font-semibold transition-all whitespace-nowrap ${
              proposicaoFilter === "IMPACTO"
                ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Impacto ({rel?.projetos_impacto ?? "—"})
          </button>
          <button
            type="button"
            onClick={() => setProposicaoFilter("SIMBOLICO")}
            className={`px-2.5 py-1 rounded-lg font-semibold transition-all whitespace-nowrap ${
              proposicaoFilter === "SIMBOLICO"
                ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Simbólicas ({rel?.projetos_simbolicos ?? "—"})
          </button>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 4. LISTA DETALHADA DE PROPOSIÇÕES COM PONDERAÇÃO E PAPEL                  */}
      {/* ========================================================================= */}
      {(() => {
        const proposicoesExibidas = (dossier?.materias_propostas || []).filter((p) => {
          const matchRelevancia =
            proposicaoFilter === "TODAS"
              ? true
              : proposicaoFilter === "IMPACTO"
              ? p.classificacao_relevancia === "IMPACTO"
              : p.classificacao_relevancia === "SIMBOLICO";

          const isCoautor = p.papel_autoria === "COAUTOR";
          const matchAutoria =
            autoriaFilter === "TODAS"
              ? true
              : autoriaFilter === "PRINCIPAL"
              ? !isCoautor
              : isCoautor;

          const matchSearch =
            !proposicaoSearch.trim() ||
            p.titulo.toLowerCase().includes(proposicaoSearch.toLowerCase()) ||
            p.ementa.toLowerCase().includes(proposicaoSearch.toLowerCase()) ||
            `${p.tipo} ${p.numero}`.toLowerCase().includes(proposicaoSearch.toLowerCase());

          return matchRelevancia && matchAutoria && matchSearch;
        });

        if (proposicoesExibidas.length === 0) {
          return (
            <div className="bg-slate-900/40 border border-slate-800 rounded-2xl p-8 text-center text-xs text-slate-400">
              Nenhuma proposição encontrada para os filtros selecionados.
            </div>
          );
        }

        return (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {proposicoesExibidas.map((p) => {
              const isImpacto = p.classificacao_relevancia === "IMPACTO";
              const isCoautor = p.papel_autoria === "COAUTOR";
              const isPEC = p.tipo === "PEC";

              return (
                <div
                  key={p.id}
                  className={`bg-slate-900/70 border rounded-2xl p-4.5 space-y-3 transition-all ${
                    isImpacto
                      ? "border-emerald-500/20 hover:border-emerald-500/40"
                      : "border-amber-500/20 hover:border-amber-500/40"
                  }`}
                >
                  {/* Cabeçalho da Proposição: Tipo, Papel de Autoria e Score */}
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs font-mono font-bold px-2.5 py-1 rounded-lg bg-slate-950 text-purple-300 border border-purple-500/20">
                        {p.tipo} {p.numero}/{p.ano}
                      </span>

                      {/* Badge de Papel de Autoria */}
                      {isCoautor ? (
                        <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-indigo-500/15 text-indigo-300 border border-indigo-500/30 flex items-center gap-1" title="Coautor / Signatário: peso 0.2">
                          <Users className="w-2.5 h-2.5 text-indigo-400" />
                          Coautor (0.2 pt)
                        </span>
                      ) : (
                        <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30 flex items-center gap-1" title="Autor Principal: peso 1.0">
                          <Trophy className="w-2.5 h-2.5 text-amber-400" />
                          Autor Principal (1.0 pt)
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-1.5">
                      {/* Badge de Complexidade */}
                      {isPEC ? (
                        <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-rose-500/15 text-rose-300 border border-rose-500/30">
                          PEC (Alta • 3.0x)
                        </span>
                      ) : ["PL", "PLP", "MPV"].includes(p.tipo) ? (
                        <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-sky-500/15 text-sky-300 border border-sky-500/30">
                          Média (2.0x)
                        </span>
                      ) : (
                        <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                          Baixa (1.0x)
                        </span>
                      )}

                      {/* Score da Proposição */}
                      {p.score_calculado !== undefined && (
                        <span className="text-xs font-mono font-black text-amber-300 bg-slate-950 px-2 py-0.5 rounded border border-slate-800">
                          {p.score_calculado} pts
                        </span>
                      )}
                    </div>
                  </div>

                  <div>
                    <div className="flex items-start justify-between gap-2">
                      <h4 className="text-xs font-bold text-slate-100 leading-snug">
                        {p.titulo}
                      </h4>
                      {p.url_oficial && (
                        <a
                          href={safeExternalUrl(p.url_oficial)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-[11px] font-semibold text-cyan-400 hover:text-cyan-300 transition-colors shrink-0 bg-cyan-500/10 border border-cyan-500/20 px-2 py-0.5 rounded-lg"
                        >
                          <span>Íntegra</span>
                          <ExternalLink className="w-3 h-3" aria-hidden="true" />
                        </a>
                      )}
                    </div>
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      <span className="text-[10px] text-slate-400 font-mono">
                        Apresentado em {p.data_apresentacao || "Data não registrada"}
                      </span>
                      {p.area_tematica && (
                        <span className="text-[10px] text-slate-300 font-medium px-2 py-0.5 rounded bg-slate-800 border border-slate-700">
                          {p.area_tematica}
                        </span>
                      )}
                      <span className={`text-[10px] font-mono font-semibold px-2 py-0.5 rounded border ${
                        p.status?.includes("APROVADA")
                          ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                          : "bg-slate-800 text-slate-300 border-slate-700"
                      }`}>
                        {p.status || "EM_TRAMITACAO"}
                      </span>
                    </div>
                  </div>

                  <p className="text-xs text-slate-300 leading-relaxed bg-slate-950/60 p-3 rounded-xl border border-slate-800/80">
                    {p.ementa}
                  </p>

                  {p.justificativa_relevancia && (
                    <div className="flex items-center gap-1.5 text-[10px] text-slate-400 font-mono pt-1">
                      <Sparkles className="w-3 h-3 text-purple-400 shrink-0" aria-hidden="true" />
                      <span>{p.justificativa_relevancia}</span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        );
      })()}
    </div>
  );
}
