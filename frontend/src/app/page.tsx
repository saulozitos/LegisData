"use client";

import React, { useMemo, useState } from "react";
import dynamic from "next/dynamic";
import Header from "@/components/Header";
import PresidentTimeline from "@/components/PresidentTimeline";
import PartyMembersModal from "@/components/PartyMembersModal";
import LoadingSkeleton from "@/components/LoadingSkeleton";
import { EmptyState, ErrorState, LoadingState } from "@/components/StateViews";
import { useApi } from "@/hooks/useApi";
import { isActiveMandate, isActiveStatus, toMandateRange } from "@/lib/mandate";
import {
  getPresidentes,
  getMandatesPerformance,
  getAnnualMacroSummary,
  getLegislativePropositions,
  getPartyFidelity,
  PresidenteHistorico,
  MandatoPerformance,
} from "@/services/api";
import {
  TrendingUp,
  Scale,
  Landmark,
  Building2,
  Users2,
  ScrollText,
  Scan,
  Vote,
  Layers,
  Compass,
  CalendarDays,
  Coins,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

// Cada aba pesada é carregada sob demanda (code splitting): o gráfico/Recharts só entra no bundle quando necessário.
const panelLoading = () => <LoadingState label="Carregando painel..." />;
const MacroeconomicChart = dynamic(() => import("@/components/MacroeconomicChart"), { loading: panelLoading });
const ExecutivoPanel = dynamic(() => import("@/components/ExecutivoPanel"), { loading: panelLoading });
const LegislativePanel = dynamic(() => import("@/components/LegislativePanel"), { loading: panelLoading });
const PartyFidelityPanel = dynamic(() => import("@/components/PartyFidelityPanel"), { loading: panelLoading });
const WageDisparityPanel = dynamic(() => import("@/components/WageDisparityPanel"), { loading: panelLoading });
const CongressCompositionPanel = dynamic(() => import("@/components/CongressCompositionPanel"), { loading: panelLoading });
const FederalTransfersPanel = dynamic(() => import("@/components/FederalTransfersPanel"), { loading: panelLoading });
const EmendasExplorerPanel = dynamic(() => import("@/components/EmendasExplorerPanel"), { loading: panelLoading });
const PoliticianProfile = dynamic(() => import("@/components/PoliticianProfile"), { loading: panelLoading });
const SocialClassesExplainer = dynamic(() => import("@/components/SocialClassesExplainer"), { loading: panelLoading });
const DeepBrazilPanel = dynamic(() => import("@/components/DeepBrazilPanel"), { loading: panelLoading });
const PropositionsExplorerPanel = dynamic(() => import("@/components/PropositionsExplorerPanel"), { loading: panelLoading });
const PartiesPanel = dynamic(() => import("@/components/PartiesPanel"), { loading: panelLoading });
const VotingCalendarPanel = dynamic(() => import("@/components/VotingCalendarPanel"), { loading: panelLoading });

type TabType =
  | "macro"
  | "renda"
  | "sociedade"
  | "composicao"
  | "partidos"
  | "orcamento"
  | "emendas"
  | "fidelidade"
  | "legislativo"
  | "produtividade"
  | "calendario"
  | "raiox";

const TABS: Array<{ id: TabType; label: string; icon: LucideIcon; active: string }> = [
  { id: "macro", label: "Economia & Mandato", icon: TrendingUp, active: "bg-emerald-500 text-slate-950 shadow-md shadow-emerald-500/20" },
  { id: "renda", label: "Renda & Classes Sociais", icon: Scale, active: "bg-amber-500 text-slate-950 shadow-md shadow-amber-500/20" },
  { id: "sociedade", label: "Sociedade & Eleições", icon: Vote, active: "bg-rose-500 text-slate-950 shadow-md shadow-rose-500/20" },
  { id: "composicao", label: "Composição de Governo", icon: Landmark, active: "bg-cyan-500 text-slate-950 shadow-md shadow-cyan-500/20" },
  { id: "partidos", label: "Partidos", icon: Compass, active: "bg-violet-500 text-white shadow-md shadow-violet-500/20" },
  { id: "orcamento", label: "Orçamento Federal por UF", icon: Building2, active: "bg-emerald-400 text-slate-950 shadow-md shadow-emerald-400/20" },
  { id: "emendas", label: "Emendas Orçamentárias", icon: Coins, active: "bg-amber-400 text-slate-950 shadow-md shadow-amber-400/20" },
  { id: "fidelidade", label: "Fidelidade Partidária (TSE)", icon: Users2, active: "bg-purple-500 text-slate-950 shadow-md shadow-purple-500/20" },
  { id: "legislativo", label: "Monitor do Congresso", icon: ScrollText, active: "bg-blue-500 text-slate-950 shadow-md shadow-blue-500/20" },
  { id: "produtividade", label: "Produtividade & Votações", icon: Layers, active: "bg-indigo-500 text-white shadow-md shadow-indigo-500/20" },
  { id: "calendario", label: "Calendário de Votações", icon: CalendarDays, active: "bg-amber-400 text-slate-950 shadow-md shadow-amber-400/20" },
  { id: "raiox", label: "Raio-X do Político", icon: Scan, active: "bg-cyan-400 text-slate-950 shadow-md shadow-cyan-400/20" },
];

function findCurrentPresidentId(presList: PresidenteHistorico[], perfList: MandatoPerformance[]): string | null {
  const activePres = presList.find((p) => isActiveMandate(p.status_mandato, p.data_fim));
  if (activePres) return activePres.id_referencia;

  const activePerf = perfList.find((m) => isActiveStatus(m.status_mandato));
  if (activePerf) return activePerf.id_mandato;

  if (presList.length > 0) return presList[presList.length - 1].id_referencia;
  if (perfList.length > 0) return perfList[perfList.length - 1].id_mandato;

  return null;
}

export default function DashboardPage() {
  // Dados essenciais da aba inicial; as demais abas buscam o que precisam quando abertas.
  const presidentsQuery = useApi("dashboard-presidents", (signal) => getPresidentes(signal));
  const performancesQuery = useApi("dashboard-performances", (signal) => getMandatesPerformance(signal));
  const annualQuery = useApi("dashboard-annual-summary", (signal) => getAnnualMacroSummary(undefined, signal));

  const presidents = useMemo(() => presidentsQuery.data ?? [], [presidentsQuery.data]);
  const performances = useMemo(() => performancesQuery.data ?? [], [performancesQuery.data]);
  const annualSummaries = useMemo(() => annualQuery.data ?? [], [annualQuery.data]);

  const [activeTab, setActiveTab] = useState<TabType>("macro");
  const [selectedPoliticianId, setSelectedPoliticianId] = useState<string | null>(null);
  const [globalSelectedParty, setGlobalSelectedParty] = useState<string | null>(null);

  // `undefined` = o usuário ainda não escolheu (usa o mandato atual); `null` = "todos os mandatos".
  const [pickedMandate, setPickedMandate] = useState<string | null | undefined>(undefined);
  const currentMandateId = useMemo(() => findCurrentPresidentId(presidents, performances), [presidents, performances]);
  const globalMandate = pickedMandate === undefined ? currentMandateId : pickedMandate;
  // Painéis que exigem um mandato usam o atual quando o filtro está em "todos".
  const effectiveMandateId = globalMandate ?? currentMandateId;

  const mandateRanges = useMemo(() => {
    const currentYear = new Date().getFullYear();
    return presidents.map((p) => toMandateRange(p, currentYear));
  }, [presidents]);
  const selectedRange = mandateRanges.find((m) => m.id === globalMandate) ?? null;

  // Dados sob demanda por aba
  const propositionsQuery = useApi(
    "dashboard-propositions",
    (signal) => getLegislativePropositions(signal),
    activeTab === "legislativo"
  );
  const fidelityQuery = useApi("dashboard-party-fidelity", (signal) => getPartyFidelity(signal), activeTab === "fidelidade");

  const selectedPerformance = globalMandate ? performances.find((p) => p.id_mandato === globalMandate) || null : null;
  const selectedPresidentMeta = globalMandate ? presidents.find((p) => p.id_referencia === globalMandate) || null : null;

  const coreLoading = presidentsQuery.loading || performancesQuery.loading;
  const coreError = presidentsQuery.error ?? performancesQuery.error;

  // Handlers para Navegação Global Universal (Partido -> Membros -> Raio-X)
  const handleOpenPartyMembers = (partido: string) => {
    setActiveTab("partidos");
    setGlobalSelectedParty(partido);
  };

  const openPolitician = (id: string) => {
    setSelectedPoliticianId(id);
    setActiveTab("raiox");
  };

  const handleSelectPoliticianFromParty = (polId: string) => {
    setGlobalSelectedParty(null);
    openPolitician(polId);
  };

  const needsMandate = activeTab === "composicao" || activeTab === "orcamento";

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      <Header />

      <main id="main-content" className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        <h1 className="sr-only">LegisData: painel de transparência política e econômica</h1>

        {coreLoading ? (
          <LoadingSkeleton />
        ) : (
          <>
            {coreError && <ErrorState onRetry={() => { presidentsQuery.retry(); performancesQuery.retry(); }} />}

            {/* 1. Barra de Navegação: Linha do Tempo Presidencial (Filtro Global Master) */}
            <section
              aria-label="Linha do tempo presidencial"
              className="bg-slate-900/40 border border-slate-800/80 rounded-3xl p-4 backdrop-blur-md shadow-lg shadow-black/20"
            >
              <PresidentTimeline
                presidents={presidents}
                selectedId={globalMandate}
                onSelect={(id) => setPickedMandate(id)}
              />
            </section>

            {/* 2. Menu de Navegação por Abas Analíticas com Rolagem Horizontal Suave */}
            <div
              role="tablist"
              aria-label="Seções do painel"
              className="flex items-center gap-2 overflow-x-auto flex-nowrap whitespace-nowrap pb-2 custom-scrollbar scroll-smooth"
            >
              {TABS.map((tab) => {
                const Icon = tab.icon;
                const isActive = activeTab === tab.id;
                return (
                  <button
                    type="button"
                    key={tab.id}
                    role="tab"
                    id={`dashboard-tab-${tab.id}`}
                    aria-selected={isActive}
                    aria-controls="dashboard-tabpanel"
                    onClick={() => setActiveTab(tab.id)}
                    className={`inline-flex items-center gap-2 px-4 py-2.5 rounded-2xl text-xs font-bold transition-all whitespace-nowrap ${
                      isActive
                        ? tab.active
                        : "bg-slate-900/60 border border-slate-800/80 text-slate-300 hover:text-slate-100 hover:bg-slate-800/60"
                    }`}
                  >
                    <Icon className="w-4 h-4" aria-hidden="true" />
                    {tab.label}
                  </button>
                );
              })}
            </div>

            {/* Conteúdo Dinâmico por Aba */}
            <div role="tabpanel" id="dashboard-tabpanel" aria-labelledby={`dashboard-tab-${activeTab}`}>
              {needsMandate && !effectiveMandateId && (
                <EmptyState
                  title="Mandato indisponível"
                  message="Não foi possível determinar o mandato para esta seção. Selecione um presidente na linha do tempo."
                />
              )}

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
                    {annualQuery.error ? (
                      <ErrorState onRetry={annualQuery.retry} />
                    ) : annualQuery.loading ? (
                      <LoadingState label="Carregando série macroeconômica..." />
                    ) : (
                      <MacroeconomicChart
                        data={annualSummaries}
                        selectedMandateId={globalMandate}
                        mandates={mandateRanges}
                      />
                    )}
                  </section>
                </div>
              )}

              {activeTab === "renda" && (
                <div className="space-y-6">
                  <section>
                    <WageDisparityPanel />
                  </section>
                  <section>
                    <SocialClassesExplainer />
                  </section>
                </div>
              )}

              {activeTab === "sociedade" && (
                <div className="space-y-6">
                  <section>
                    <DeepBrazilPanel key={globalMandate ?? "todos"} mandate={selectedRange} />
                  </section>
                </div>
              )}

              {activeTab === "composicao" && effectiveMandateId && (
                <section>
                  <CongressCompositionPanel
                    mandateId={effectiveMandateId}
                    onSelectPolitician={openPolitician}
                  />
                </section>
              )}

              {activeTab === "partidos" && (
                <section>
                  <PartiesPanel targetParty={globalSelectedParty} onSelectParty={handleOpenPartyMembers} />
                </section>
              )}

              {activeTab === "orcamento" && effectiveMandateId && (
                <section>
                  <FederalTransfersPanel mandateId={effectiveMandateId} />
                </section>
              )}

              {activeTab === "emendas" && (
                <section>
                  <EmendasExplorerPanel onSelectPolitician={openPolitician} />
                </section>
              )}

              {activeTab === "fidelidade" && (
                <section>
                  {fidelityQuery.error ? (
                    <ErrorState onRetry={fidelityQuery.retry} />
                  ) : fidelityQuery.loading ? (
                    <LoadingState label="Carregando fidelidade partidária..." />
                  ) : (
                    <PartyFidelityPanel fidelityData={fidelityQuery.data ?? null} onSelectParty={handleOpenPartyMembers} />
                  )}
                </section>
              )}

              {activeTab === "legislativo" && (
                <section>
                  {propositionsQuery.error ? (
                    <ErrorState onRetry={propositionsQuery.retry} />
                  ) : propositionsQuery.loading ? (
                    <LoadingState label="Carregando proposições..." />
                  ) : (
                    <LegislativePanel
                      propositions={propositionsQuery.data ?? []}
                      onSelectPolitician={openPolitician}
                      onSelectParty={handleOpenPartyMembers}
                    />
                  )}
                </section>
              )}

              {activeTab === "produtividade" && (
                <section>
                  <PropositionsExplorerPanel onSelectPolitician={openPolitician} onSelectParty={handleOpenPartyMembers} />
                </section>
              )}

              {activeTab === "calendario" && (
                <section>
                  <VotingCalendarPanel
                    onSelectPolitician={openPolitician}
                    onSelectParty={handleOpenPartyMembers}
                  />
                </section>
              )}

              {activeTab === "raiox" && (
                <section>
                  <PoliticianProfile
                    selectedPoliticianId={selectedPoliticianId}
                    onSelectParty={handleOpenPartyMembers}
                    onSelectionChange={setSelectedPoliticianId}
                  />
                </section>
              )}
            </div>
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
