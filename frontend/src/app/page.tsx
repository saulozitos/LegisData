"use client";

import React, { useEffect, useState } from "react";
import Header from "@/components/Header";
import PresidentTimeline from "@/components/PresidentTimeline";
import MacroeconomicChart from "@/components/MacroeconomicChart";
import LegislativePanel from "@/components/LegislativePanel";
import PartyFidelityPanel from "@/components/PartyFidelityPanel";
import WageDisparityPanel from "@/components/WageDisparityPanel";
import CongressCompositionPanel from "@/components/CongressCompositionPanel";
import FederalTransfersPanel from "@/components/FederalTransfersPanel";
import PoliticianProfile from "@/components/PoliticianProfile";
import SocialClassesExplainer from "@/components/SocialClassesExplainer";
import DeepBrazilPanel from "@/components/DeepBrazilPanel";
import PropositionsExplorerPanel from "@/components/PropositionsExplorerPanel";
import PartiesPanel from "@/components/PartiesPanel";
import PartyMembersModal from "@/components/PartyMembersModal";
import VotingCalendarPanel from "@/components/VotingCalendarPanel";
import ExecutivoPanel from "@/components/ExecutivoPanel";
import LoadingSkeleton from "@/components/LoadingSkeleton";
import {
  getPresidentes,
  getMandatesPerformance,
  getAnnualMacroSummary,
  getLegislativePropositions,
  getPartyFidelity,
  PresidenteHistorico,
  MandatoPerformance,
  ResumoMacroeconomicoAnual,
  ProposicaoLegislativa,
  PartyFidelityResponse,
} from "@/services/api";
import {
  TrendingUp,
  Scale,
  Landmark,
  Building2,
  Users2,
  ScrollText,
  Sparkles,
  Scan,
  Vote,
  Layers,
  Compass,
  CalendarDays,
  Briefcase,
} from "lucide-react";

type TabType = "macro" | "renda" | "sociedade" | "composicao" | "partidos" | "orcamento" | "fidelidade" | "legislativo" | "produtividade" | "calendario" | "raiox";

function findCurrentPresidentId(presList: PresidenteHistorico[], perfList: MandatoPerformance[]): string {
  const activePres = presList.find(
    (p) =>
      p.status_mandato === "TITULAR_ATIVO" ||
      p.status_mandato === "EM_EXERCICIO" ||
      p.status_mandato === "ATIVO" ||
      !p.data_fim
  );
  if (activePres) return activePres.id_referencia;

  const activePerf = perfList.find(
    (m) =>
      m.status_mandato === "TITULAR_ATIVO" ||
      m.status_mandato === "EM_EXERCICIO" ||
      m.status_mandato === "ATIVO"
  );
  if (activePerf) return activePerf.id_mandato;

  if (presList.length > 0) return presList[presList.length - 1].id_referencia;
  if (perfList.length > 0) return perfList[perfList.length - 1].id_mandato;

  return "lula-2023";
}

export default function DashboardPage() {
  const [presidents, setPresidents] = useState<PresidenteHistorico[]>([]);
  const [performances, setPerformances] = useState<MandatoPerformance[]>([]);
  const [annualSummaries, setAnnualSummaries] = useState<ResumoMacroeconomicoAnual[]>([]);
  const [propositions, setPropositions] = useState<ProposicaoLegislativa[]>([]);
  const [partyFidelity, setPartyFidelity] = useState<PartyFidelityResponse | null>(null);
  const [globalMandate, setGlobalMandate] = useState<string | null>("lula-2023");
  const [selectedPoliticianId, setSelectedPoliticianId] = useState<string | null>(null);
  const [globalSelectedParty, setGlobalSelectedParty] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>("macro");
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    async function loadData() {
      setIsLoading(true);
      try {
        const [presData, perfData, annualData, propData, fidelityData] = await Promise.all([
          getPresidentes(),
          getMandatesPerformance(),
          getAnnualMacroSummary(),
          getLegislativePropositions(),
          getPartyFidelity(),
        ]);

        setPresidents(presData);
        setPerformances(perfData);
        setAnnualSummaries(annualData);
        setPropositions(propData);
        setPartyFidelity(fidelityData);

        const currentPresidentId = findCurrentPresidentId(presData, perfData);
        setGlobalMandate(currentPresidentId);
      } catch (err) {
        console.error("Erro ao carregar dados do dashboard:", err);
      } finally {
        setIsLoading(false);
      }
    }

    loadData();
  }, []);

  const selectedPerformance = globalMandate
    ? performances.find((p) => p.id_mandato === globalMandate) || null
    : null;

  const selectedPresidentMeta = globalMandate
    ? presidents.find((p) => p.id_referencia === globalMandate) || null
    : null;

  // Handlers para Navegação Global Universal (Partido -> Membros -> Raio-X)
  const handleOpenPartyMembers = (partido: string) => {
    setActiveTab("partidos");
    setGlobalSelectedParty(partido);
  };

  const handleSelectPoliticianFromParty = (polId: string) => {
    setGlobalSelectedParty(null);
    setSelectedPoliticianId(polId);
    setActiveTab("raiox");
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      <Header />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {isLoading ? (
          <LoadingSkeleton />
        ) : (
          <>
            {/* 1. Barra de Navegação: Linha do Tempo Presidencial (Filtro Global Master) */}
            <section className="bg-slate-900/40 border border-slate-800/80 rounded-3xl p-4 backdrop-blur-md shadow-lg shadow-black/20">
              <PresidentTimeline
                presidents={presidents}
                selectedId={globalMandate}
                onSelect={(id) => setGlobalMandate(id)}
              />
            </section>

            {/* 2. Menu de Navegação por Abas Analíticas com Rolagem Horizontal Suave */}
            <div className="flex items-center gap-2 overflow-x-auto flex-nowrap whitespace-nowrap pb-2 custom-scrollbar scroll-smooth">
              <button
                onClick={() => setActiveTab("macro")}
                className={`inline-flex items-center gap-2 px-4 py-2.5 rounded-2xl text-xs font-bold transition-all whitespace-nowrap ${
                  activeTab === "macro"
                    ? "bg-emerald-500 text-slate-950 shadow-md shadow-emerald-500/20"
                    : "bg-slate-900/60 border border-slate-800/80 text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
                }`}
              >
                <TrendingUp className="w-4 h-4" />
                Economia & Mandato
              </button>

              <button
                onClick={() => setActiveTab("renda")}
                className={`inline-flex items-center gap-2 px-4 py-2.5 rounded-2xl text-xs font-bold transition-all whitespace-nowrap ${
                  activeTab === "renda"
                    ? "bg-amber-500 text-slate-950 shadow-md shadow-amber-500/20"
                    : "bg-slate-900/60 border border-slate-800/80 text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
                }`}
              >
                <Scale className="w-4 h-4" />
                Renda & Classes Sociais
              </button>

              <button
                onClick={() => setActiveTab("sociedade")}
                className={`inline-flex items-center gap-2 px-4 py-2.5 rounded-2xl text-xs font-bold transition-all whitespace-nowrap ${
                  activeTab === "sociedade"
                    ? "bg-rose-500 text-slate-950 shadow-md shadow-rose-500/20"
                    : "bg-slate-900/60 border border-slate-800/80 text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
                }`}
              >
                <Vote className="w-4 h-4" />
                Sociedade & Eleições
              </button>

              <button
                onClick={() => setActiveTab("composicao")}
                className={`inline-flex items-center gap-2 px-4 py-2.5 rounded-2xl text-xs font-bold transition-all whitespace-nowrap ${
                  activeTab === "composicao"
                    ? "bg-cyan-500 text-slate-950 shadow-md shadow-cyan-500/20"
                    : "bg-slate-900/60 border border-slate-800/80 text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
                }`}
              >
                <Landmark className="w-4 h-4" />
                Composição de Governo
              </button>

              <button
                onClick={() => setActiveTab("partidos")}
                className={`inline-flex items-center gap-2 px-4 py-2.5 rounded-2xl text-xs font-bold transition-all whitespace-nowrap ${
                  activeTab === "partidos"
                    ? "bg-violet-500 text-white shadow-md shadow-violet-500/20"
                    : "bg-slate-900/60 border border-slate-800/80 text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
                }`}
              >
                <Compass className="w-4 h-4" />
                Partidos
              </button>

              <button
                onClick={() => setActiveTab("orcamento")}
                className={`inline-flex items-center gap-2 px-4 py-2.5 rounded-2xl text-xs font-bold transition-all whitespace-nowrap ${
                  activeTab === "orcamento"
                    ? "bg-emerald-400 text-slate-950 shadow-md shadow-emerald-400/20"
                    : "bg-slate-900/60 border border-slate-800/80 text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
                }`}
              >
                <Building2 className="w-4 h-4" />
                Orçamento Federal por UF
              </button>

              <button
                onClick={() => setActiveTab("fidelidade")}
                className={`inline-flex items-center gap-2 px-4 py-2.5 rounded-2xl text-xs font-bold transition-all whitespace-nowrap ${
                  activeTab === "fidelidade"
                    ? "bg-purple-500 text-slate-950 shadow-md shadow-purple-500/20"
                    : "bg-slate-900/60 border border-slate-800/80 text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
                }`}
              >
                <Users2 className="w-4 h-4" />
                Fidelidade Partidária (TSE)
              </button>

              <button
                onClick={() => setActiveTab("legislativo")}
                className={`inline-flex items-center gap-2 px-4 py-2.5 rounded-2xl text-xs font-bold transition-all whitespace-nowrap ${
                  activeTab === "legislativo"
                    ? "bg-blue-500 text-slate-950 shadow-md shadow-blue-500/20"
                    : "bg-slate-900/60 border border-slate-800/80 text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
                }`}
              >
                <ScrollText className="w-4 h-4" />
                Monitor do Congresso
              </button>

              <button
                onClick={() => setActiveTab("produtividade")}
                className={`inline-flex items-center gap-2 px-4 py-2.5 rounded-2xl text-xs font-bold transition-all whitespace-nowrap ${
                  activeTab === "produtividade"
                    ? "bg-indigo-500 text-white shadow-md shadow-indigo-500/20"
                    : "bg-slate-900/60 border border-slate-800/80 text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
                }`}
              >
                <Layers className="w-4 h-4" />
                Produtividade & Votações
              </button>

              <button
                onClick={() => setActiveTab("calendario")}
                className={`inline-flex items-center gap-2 px-4 py-2.5 rounded-2xl text-xs font-bold transition-all whitespace-nowrap ${
                  activeTab === "calendario"
                    ? "bg-amber-400 text-slate-950 shadow-md shadow-amber-400/20"
                    : "bg-slate-900/60 border border-slate-800/80 text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
                }`}
              >
                <CalendarDays className="w-4 h-4" />
                Calendário de Votações
              </button>

              <button
                onClick={() => setActiveTab("raiox")}
                className={`inline-flex items-center gap-2 px-4 py-2.5 rounded-2xl text-xs font-bold transition-all whitespace-nowrap ${
                  activeTab === "raiox"
                    ? "bg-cyan-400 text-slate-950 shadow-md shadow-cyan-400/20"
                    : "bg-slate-900/60 border border-slate-800/80 text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
                }`}
              >
                <Scan className="w-4 h-4" />
                Raio-X do Político
              </button>
            </div>

            {/* Conteúdo Dinâmico por Aba */}
            {activeTab === "macro" && (
              <div className="space-y-8">
                <section>
                  <ExecutivoPanel
                    performance={selectedPerformance}
                    presidentMeta={selectedPresidentMeta}
                    annualData={annualSummaries}
                    mandateId={globalMandate}
                    allPerformances={performances}
                  />
                </section>
                <section className="pt-6 border-t border-slate-800/80">
                  <MacroeconomicChart
                    data={annualSummaries}
                    selectedMandateId={globalMandate}
                  />
                </section>
              </div>
            )}

            {activeTab === "renda" && (
              <div className="space-y-6">
                <section>
                  <WageDisparityPanel mandateId={globalMandate} />
                </section>
                <section>
                  <SocialClassesExplainer mandateId={globalMandate} />
                </section>
              </div>
            )}

            {activeTab === "sociedade" && (
              <div className="space-y-6">
                <section>
                  <DeepBrazilPanel mandateId={globalMandate} />
                </section>
                <section>
                  <SocialClassesExplainer mandateId={globalMandate} />
                </section>
              </div>
            )}

            {activeTab === "composicao" && (
              <section>
                <CongressCompositionPanel
                  mandateId={globalMandate || "lula-2023"}
                  onSelectPolitician={(id) => {
                    setSelectedPoliticianId(id);
                    setActiveTab("raiox");
                  }}
                  onSelectParty={handleOpenPartyMembers}
                />
              </section>
            )}

            {activeTab === "partidos" && (
              <section>
                <PartiesPanel
                  targetParty={globalSelectedParty}
                  mandateId={globalMandate}
                  onSelectParty={handleOpenPartyMembers}
                />
              </section>
            )}

            {activeTab === "orcamento" && (
              <section>
                <FederalTransfersPanel mandateId={globalMandate || "lula-2023"} />
              </section>
            )}

            {activeTab === "fidelidade" && (
              <section>
                <PartyFidelityPanel
                  fidelityData={partyFidelity}
                  onSelectParty={handleOpenPartyMembers}
                />
              </section>
            )}

            {activeTab === "legislativo" && (
              <section>
                <LegislativePanel
                  propositions={propositions}
                  onSelectPolitician={(id) => {
                    setSelectedPoliticianId(id);
                    setActiveTab("raiox");
                  }}
                  onSelectParty={handleOpenPartyMembers}
                />
              </section>
            )}

            {activeTab === "produtividade" && (
              <section>
                <PropositionsExplorerPanel
                  onSelectPolitician={(id) => {
                    setSelectedPoliticianId(id);
                    setActiveTab("raiox");
                  }}
                  onSelectParty={handleOpenPartyMembers}
                />
              </section>
            )}

            {activeTab === "calendario" && (
              <section>
                <VotingCalendarPanel
                  onSelectPolitician={(id) => {
                    setSelectedPoliticianId(id);
                    setActiveTab("raiox");
                  }}
                />
              </section>
            )}

            {activeTab === "raiox" && (
              <section>
                <PoliticianProfile
                  selectedPoliticianId={selectedPoliticianId}
                  onSelectParty={handleOpenPartyMembers}
                />
              </section>
            )}
          </>
        )}

        {/* Modal Global de Bancada Partidária (Navegação Universal: Partido -> Políticos -> Raio-X) */}
        <PartyMembersModal
          partySigla={globalSelectedParty}
          isOpen={Boolean(globalSelectedParty)}
          onClose={() => setGlobalSelectedParty(null)}
          onSelectPolitician={handleSelectPoliticianFromParty}
        />
      </main>
    </div>
  );
}
