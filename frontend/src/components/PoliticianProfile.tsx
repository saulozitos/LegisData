"use client";

import React, { useState } from "react";
import dynamic from "next/dynamic";
import type { PoliticoBuscaItem } from "@/services/api";
import { searchPoliticians, getPoliticianDossier } from "@/services/api";
import { useApi } from "@/hooks/useApi";
import { useDebounce } from "@/hooks/useDebounce";
import { EmptyState, ErrorState, LoadingState } from "@/components/StateViews";
import PoliticianSearchBar from "./politician/PoliticianSearchBar";
import PoliticianHome from "./politician/PoliticianHome";
import PoliticianHeaderCard from "./politician/PoliticianHeaderCard";
import PoliticianTabNav from "./politician/PoliticianTabNav";
import type { DossierTab } from "./politician/types";

// Cada aba do dossiê é carregada sob demanda (code splitting).
const tabLoading = () => <LoadingState label="Carregando seção..." />;
const OverviewTab = dynamic(() => import("./politician/OverviewTab"), { loading: tabLoading });
const IntelligenceTab = dynamic(() => import("./politician/IntelligenceTab"), { loading: tabLoading });
const PropositionsTab = dynamic(() => import("./politician/PropositionsTab"), { loading: tabLoading });
const FinancingTab = dynamic(() => import("./politician/FinancingTab"), { loading: tabLoading });
const CeapTab = dynamic(() => import("./politician/CeapTab"), { loading: tabLoading });
const AmendmentsTab = dynamic(() => import("./politician/AmendmentsTab"), { loading: tabLoading });
const JusticeTab = dynamic(() => import("./politician/JusticeTab"), { loading: tabLoading });
const AttendanceTab = dynamic(() => import("./politician/AttendanceTab"), { loading: tabLoading });
const RemunerationTab = dynamic(() => import("./politician/RemunerationTab"), { loading: tabLoading });
const VotesTab = dynamic(() => import("./politician/VotesTab"), { loading: tabLoading });

interface PoliticianProfileProps {
  selectedPoliticianId?: string | null;
  onSelectParty?: (sigla: string) => void;
  /** Notifica o contêiner quando a seleção muda localmente (busca, catálogo ou "voltar"). */
  onSelectionChange?: (id: string | null) => void;
}

export default function PoliticianProfile({
  selectedPoliticianId: initialPoliticianId,
  onSelectParty,
  onSelectionChange,
}: PoliticianProfileProps = {}) {
  const [searchTerm, setSearchTerm] = useState("");
  const [officeFilter, setOfficeFilter] = useState<string>("TODOS");
  const [selectedPoliticianId, setSelectedPoliticianId] = useState<string | null>(initialPoliticianId || null);
  const [tabState, setTabState] = useState<{ id: string | null; tab: DossierTab }>({
    id: initialPoliticianId || null,
    tab: "visao_geral",
  });

  // Sincroniza quando a seleção externa muda (ex.: drill-down do painel de bancadas).
  const [lastInitialId, setLastInitialId] = useState(initialPoliticianId);
  if (initialPoliticianId !== lastInitialId) {
    setLastInitialId(initialPoliticianId);
    setSelectedPoliticianId(initialPoliticianId || null);
  }

  // A aba volta para "Visão Geral" sempre que o político muda.
  const activeTab: DossierTab = tabState.id === selectedPoliticianId ? tabState.tab : "visao_geral";
  const setActiveTab = (tab: DossierTab) => setTabState({ id: selectedPoliticianId, tab });

  // Autocomplete: a resposta só vale para o termo/cargo atuais (sem respostas fora de ordem).
  const debouncedSearch = useDebounce(searchTerm, 250);
  const search = useApi(`politician-search:${debouncedSearch}:${officeFilter}`, (signal) =>
    searchPoliticians(debouncedSearch || undefined, officeFilter === "TODOS" ? undefined : officeFilter, undefined, undefined, 40, signal)
  );
  const searchResults = search.data?.politicos ?? search.previousData?.politicos ?? [];
  const isSearching = search.loading || debouncedSearch !== searchTerm;

  // Dossiê: nunca exibe o político anterior sob o ID novo.
  const dossierQuery = useApi(
    `dossier:${selectedPoliticianId}`,
    (signal) => getPoliticianDossier(selectedPoliticianId as string, signal),
    Boolean(selectedPoliticianId)
  );
  const dossier = dossierQuery.data ?? null;

  // `lastInitialId` só acompanha a prop (nunca a seleção local): assim o componente também funciona sem
  // contêiner controlando `selectedPoliticianId`, e uma seleção local não é desfeita na renderização seguinte.
  const selectById = (id: string) => {
    setSelectedPoliticianId(id);
    onSelectionChange?.(id);
  };

  const handleSelectPolitician = (pol: PoliticoBuscaItem) => {
    setSearchTerm(pol.nome_eleitoral);
    selectById(pol.id);
  };

  const handleBack = () => {
    setSelectedPoliticianId(null);
    setSearchTerm("");
    onSelectionChange?.(null);
  };

  const renderTab = () => {
    if (!dossier) return null;
    switch (activeTab) {
      case "visao_geral":
        return <OverviewTab dossier={dossier} onChangeTab={setActiveTab} onSelectParty={onSelectParty} />;
      case "inteligencia":
        return <IntelligenceTab dossier={dossier} />;
      case "proposicoes":
        return <PropositionsTab dossier={dossier} />;
      case "financiamento":
        return <FinancingTab dossier={dossier} />;
      case "ceap":
        return <CeapTab dossier={dossier} />;
      case "emendas":
        return <AmendmentsTab dossier={dossier} />;
      case "justica":
        return <JusticeTab dossier={dossier} />;
      case "assiduidade":
        return <AttendanceTab dossier={dossier} />;
      case "remuneracao":
        return <RemunerationTab dossier={dossier} />;
      case "votacoes":
        return <VotesTab dossier={dossier} />;
    }
  };

  const backButton = (
    <button
      type="button"
      onClick={handleBack}
      className="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl bg-slate-950 hover:bg-slate-800 text-slate-300 hover:text-cyan-300 border border-slate-700/80 transition-all text-xs font-semibold shadow-md max-w-fit"
    >
      <span aria-hidden="true">←</span>
      <span>Voltar ao Catálogo Geral (Home do Raio-X)</span>
    </button>
  );

  return (
    <div className="space-y-6">
      <PoliticianSearchBar
        searchTerm={searchTerm}
        setSearchTerm={setSearchTerm}
        officeFilter={officeFilter}
        setOfficeFilter={setOfficeFilter}
        searchResults={searchResults}
        isSearching={isSearching}
        onSelect={handleSelectPolitician}
        onSelectParty={onSelectParty}
      />

      {!selectedPoliticianId ? (
        <PoliticianHome onSelectPolitician={selectById} />
      ) : dossierQuery.loading ? (
        <LoadingState label="Carregando dossiê do político..." />
      ) : dossierQuery.error ? (
        <div className="space-y-4">
          <ErrorState
            title="Não foi possível carregar o dossiê"
            message="A API não respondeu. Isso não significa que o parlamentar não tenha dados."
            onRetry={dossierQuery.retry}
          />
          {backButton}
        </div>
      ) : !dossier ? (
        <div className="space-y-4">
          <EmptyState title="Dossiê indisponível" message="Nenhum dado foi encontrado para este político." />
          {backButton}
        </div>
      ) : (
        <div className="space-y-6">
          <PoliticianHeaderCard
            dossier={dossier}
            onBack={handleBack}
            onChangeTab={setActiveTab}
            onSelectParty={onSelectParty}
          />
          <PoliticianTabNav dossier={dossier} activeTab={activeTab} onChange={setActiveTab} />
          <div role="tabpanel" id="dossier-tabpanel" aria-labelledby={`dossier-tab-${activeTab}`}>
            {renderTab()}
          </div>
        </div>
      )}
    </div>
  );
}
