"use client";

import React, { useState } from "react";
import {
  getAuthorsProductivityRanking,
  getLegislativeExplorer,
  getParties,
} from "@/services/api";
import { useDebounce } from "@/hooks/useDebounce";
import { useApi } from "@/hooks/useApi";
import { safeExternalUrl } from "@/lib/safeUrl";
import { fmtNum } from "@/lib/format";
import { ErrorState } from "@/components/StateViews";
import PartyLink from "@/components/PartyLink";
import PropositionVoteModal from "./propositions/PropositionVoteModal";
import CoauthorshipNetworkGraph from "./legislative/CoauthorshipNetworkGraph";
import { Share2 } from "lucide-react";
import {
  Search,
  CheckCircle2,
  XCircle,
  HelpCircle,
  Trophy,
  Flame,
  Layers,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Users,
  Vote,
  Sparkles,
  BookOpen,
  BarChart3,
  X,
  Tag,
  AlertTriangle,
  Info,
  Award
} from "lucide-react";

// Mapeamento de cores para os setores temáticos
const SECTOR_BADGE_STYLES: Record<string, { bg: string; text: string; border: string }> = {
  "Saúde": { bg: "bg-teal-500/15", text: "text-teal-300", border: "border-teal-500/30" },
  "Educação": { bg: "bg-sky-500/15", text: "text-sky-300", border: "border-sky-500/30" },
  "Segurança Pública": { bg: "bg-amber-500/15", text: "text-amber-300", border: "border-amber-500/30" },
  "Economia & Finanças": { bg: "bg-cyan-500/15", text: "text-cyan-300", border: "border-cyan-500/30" },
  "Homenagens & Datas Comemorativas": { bg: "bg-purple-500/15", text: "text-purple-300", border: "border-purple-500/30" },
  "Trabalho & Previdência": { bg: "bg-indigo-500/15", text: "text-indigo-300", border: "border-indigo-500/30" },
  "Meio Ambiente & Clima": { bg: "bg-emerald-500/15", text: "text-emerald-300", border: "border-emerald-500/30" },
  "Direitos Humanos & Minorias": { bg: "bg-pink-500/15", text: "text-pink-300", border: "border-pink-500/30" },
  "Tecnologia & Inovação": { bg: "bg-violet-500/15", text: "text-violet-300", border: "border-violet-500/30" },
  "Infraestrutura & Cidades": { bg: "bg-orange-500/15", text: "text-orange-300", border: "border-orange-500/30" },
  "Agricultura & Agropecuária": { bg: "bg-lime-500/15", text: "text-lime-300", border: "border-lime-500/30" },
  "Administração & Justiça": { bg: "bg-blue-500/15", text: "text-blue-300", border: "border-blue-500/30" },
  "Administração & Cidadania": { bg: "bg-slate-500/15", text: "text-slate-300", border: "border-slate-500/30" },
};

function getSectorStyle(sector: string) {
  if (!sector) return { bg: "bg-slate-800", text: "text-slate-300", border: "border-slate-700" };
  for (const [key, val] of Object.entries(SECTOR_BADGE_STYLES)) {
    if (sector.toLowerCase().includes(key.toLowerCase())) {
      return val;
    }
  }
  return { bg: "bg-slate-800", text: "text-slate-300", border: "border-slate-700" };
}

interface PropositionsExplorerPanelProps {
  onSelectPolitician?: (id: string) => void;
  onSelectParty?: (sigla: string) => void;
}

export default function PropositionsExplorerPanel({
  onSelectPolitician,
  onSelectParty,
}: PropositionsExplorerPanelProps = {}) {
  // 0. Seletor de Visão (Visão Integrada, Ranking IALP, Grafo de Redes, Mural de Votações)
  const [viewTab, setViewTab] = useState<"INTEGRADA" | "RANKING" | "NETWORK" | "PROPOSITIONS">("INTEGRADA");

  // 1. Estados do Ranking de Produtividade (Filtros por Partido, Setor e Critério IPLE)
  const [rankingParty, setRankingParty] = useState<string>("Todos");
  const [rankingSector, setRankingSector] = useState<string>("Todos");
  const [rankingCriterio, setRankingCriterio] = useState<"efetividade" | "volume" | "lideranca" | "coautoria">("efetividade");
  const [showMetodologia, setShowMetodologia] = useState<boolean>(false);

  // 2. Estados do Mural Geral de Votações
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [selectedSetor, setSelectedSetor] = useState<string>("Todos");
  const [selectedParty, setSelectedParty] = useState<string>("Todos");
  const [selectedTipo, setSelectedTipo] = useState<string>("Todos");
  const [selectedStatus] = useState<string>("Todos");
  const [apenasVotadas, setApenasVotadas] = useState<boolean>(false);

  // 3. Estados do Modal de Votação Nominal
  const [selectedPropId, setSelectedPropId] = useState<string | null>(null);

  // Debounce da busca textual
  const debouncedSearch = useDebounce(searchTerm, 350);

  // A página volta para 1 sempre que um filtro muda, sem disparar uma segunda requisição com a página antiga.
  const filtersKey = JSON.stringify([debouncedSearch, selectedSetor, selectedParty, selectedTipo, selectedStatus, apenasVotadas]);
  const [pageState, setPageState] = useState<{ key: string; page: number }>({ key: filtersKey, page: 1 });
  const currentPage = pageState.key === filtersKey ? pageState.page : 1;
  const setCurrentPage = (next: number | ((prev: number) => number)) =>
    setPageState((prev) => {
      const base = prev.key === filtersKey ? prev.page : 1;
      return { key: filtersKey, page: typeof next === "function" ? next(base) : next };
    });

  // Opções de partido vêm do catálogo da API (cacheado); setores vêm do próprio explorador.
  const partiesCatalog = useApi("parties", (signal) => getParties(signal));
  const partyOptions = ["Todos", ...(partiesCatalog.data ?? []).map((p) => p.sigla)];

  // Ranking de Autores (Top 20) com filtros de Partido, Setor e Critério (IPLE vs Volume)
  const rankingQuery = useApi(`authors-ranking:${rankingParty}:${rankingSector}:${rankingCriterio}`, (signal) =>
    getAuthorsProductivityRanking(
      20,
      rankingParty !== "Todos" ? rankingParty : undefined,
      rankingSector !== "Todos" ? rankingSector : undefined,
      rankingCriterio,
      signal
    )
  );
  const ranking = rankingQuery.data ?? [];
  const isLoadingRanking = rankingQuery.loading;

  // Proposições com filtros e paginação (mantém a página anterior visível enquanto carrega a nova)
  const propsQuery = useApi(`explorer:${filtersKey}:${currentPage}`, (signal) =>
    getLegislativeExplorer(
      {
        search: debouncedSearch || undefined,
        setor: selectedSetor !== "Todos" ? selectedSetor : undefined,
        partido: selectedParty !== "Todos" ? selectedParty : undefined,
        tipo: selectedTipo !== "Todos" ? selectedTipo : undefined,
        status: selectedStatus !== "Todos" ? selectedStatus : undefined,
        apenas_votadas: apenasVotadas,
        page: currentPage,
        limit: 15,
      },
      signal
    )
  );
  const propositionsData = propsQuery.data ?? null;
  const isLoadingProps = propsQuery.loading;
  const sectorOptions = ["Todos", ...(propsQuery.data ?? propsQuery.previousData)?.setores_disponiveis ?? []];

  const maxProjetos = ranking.length > 0 ? ranking[0].total_proposicoes : 1;

  return (
    <div className="space-y-10 animate-in fade-in duration-500">
      {/* CABEÇALHO DO PAINEL */}
      <div className="bg-gradient-to-r from-slate-900 via-indigo-950/40 to-slate-900 border border-indigo-500/20 rounded-3xl p-6 sm:p-8 backdrop-blur-xl relative overflow-hidden shadow-2xl">
        <div className="absolute top-0 right-0 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="relative z-10 space-y-3">
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
            <Sparkles className="w-3.5 h-3.5 text-indigo-400" aria-hidden="true" />
            Produtividade Parlamentar & Mural de Votações
          </div>
          <h2 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
            Explorador Geral de Proposições & Autoria
          </h2>
          <p className="text-sm sm:text-base text-slate-300 max-w-3xl leading-relaxed">
            Acompanhe o ritmo diário do Congresso Nacional.
            Descubra quem são os parlamentares mais produtivos, em quais setores eles concentram suas propostas
            e consulte o placar nominal de aprovação ou rejeição de cada lei.
          </p>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* NAVEGAÇÃO DE VISÃO: INTEGRADA | RANKING IALP | GRAFO DE REDES | VOTAÇÕES  */}
      {/* ========================================================================= */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1 border-b border-slate-800" role="tablist" aria-label="Seletor de Módulos Legislativos">
        <button
          type="button"
          role="tab"
          aria-selected={viewTab === "INTEGRADA"}
          onClick={() => setViewTab("INTEGRADA")}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all whitespace-nowrap ${
            viewTab === "INTEGRADA"
              ? "bg-indigo-600 text-white shadow-lg shadow-indigo-500/25 border border-indigo-500"
              : "bg-slate-900/80 text-slate-300 hover:text-white border border-slate-800"
          }`}
        >
          <Layers className="w-4 h-4" />
          <span>Visão Integrada</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={viewTab === "RANKING"}
          onClick={() => setViewTab("RANKING")}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all whitespace-nowrap ${
            viewTab === "RANKING"
              ? "bg-amber-600 text-white shadow-lg shadow-amber-500/25 border border-amber-500"
              : "bg-slate-900/80 text-slate-300 hover:text-white border border-slate-800"
          }`}
        >
          <Trophy className="w-4 h-4" />
          <span>Ranking IALP (Produtividade)</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={viewTab === "NETWORK"}
          onClick={() => setViewTab("NETWORK")}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all whitespace-nowrap ${
            viewTab === "NETWORK"
              ? "bg-indigo-600 text-white shadow-lg shadow-indigo-500/25 border border-indigo-500"
              : "bg-slate-900/80 text-slate-300 hover:text-white border border-slate-800"
          }`}
        >
          <Share2 className="w-4 h-4" />
          <span>Grafo de Coautoria (Louvain & Redes)</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={viewTab === "PROPOSITIONS"}
          onClick={() => setViewTab("PROPOSITIONS")}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all whitespace-nowrap ${
            viewTab === "PROPOSITIONS"
              ? "bg-cyan-600 text-white shadow-lg shadow-cyan-500/25 border border-cyan-500"
              : "bg-slate-900/80 text-slate-300 hover:text-white border border-slate-800"
          }`}
        >
          <Vote className="w-4 h-4" />
          <span>Mural Geral de Votações</span>
        </button>
      </div>

      {/* ========================================================================= */}
      {/* SEÇÃO A: RANKING DE PRODUTIVIDADE DOS DEPUTADOS / SENADORES (IALP)       */}
      {/* ========================================================================= */}
      {(viewTab === "INTEGRADA" || viewTab === "RANKING") && (
      <section className="space-y-5">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-slate-800 pb-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-2xl bg-amber-500/10 border border-amber-500/20 text-amber-400">
              <Trophy className="w-5 h-5" aria-hidden="true" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-white flex items-center gap-2 flex-wrap">
                Ranking de Produtividade Parlamentar
                <span className="text-xs font-medium px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700">
                  {ranking.length > 0 ? `Top ${ranking.length}` : "Filtro ativo"}
                </span>
                <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md border ${
                  rankingCriterio === "efetividade"
                    ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
                    : rankingCriterio === "lideranca"
                    ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
                    : rankingCriterio === "coautoria"
                    ? "bg-indigo-500/20 text-indigo-300 border-indigo-500/40"
                    : "bg-slate-800 text-slate-300 border-slate-700"
                }`}>
                  {rankingCriterio === "efetividade"
                    ? "Score IPLE Ativo"
                    : rankingCriterio === "lideranca"
                    ? "Liderança (Autor Principal)"
                    : rankingCriterio === "coautoria"
                    ? "Apoio Político (Coautor)"
                    : "Volume Bruto"}
                </span>
                <button
                  type="button"
                  onClick={() => setShowMetodologia((v) => !v)}
                  aria-expanded={showMetodologia}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-xl bg-slate-900 border border-slate-800 text-xs font-semibold text-cyan-400 hover:text-cyan-300 hover:border-cyan-500/40 transition-colors ml-auto sm:ml-2"
                >
                  <Info className="w-3.5 h-3.5" aria-hidden="true" />
                  <span>{showMetodologia ? "Ocultar Metodologia" : "Entenda a Pontuação"}</span>
                </button>
              </h3>
              <p className="text-xs text-slate-400 mt-0.5">
                {rankingCriterio === "efetividade"
                  ? "Classificação ponderada pelo Índice IPLE: pondera papel (1.0 vs 0.2 pt), complexidade (PEC 3.0 pts) e leis aprovadas (+15 pts/3.0x)."
                  : rankingCriterio === "lideranca"
                  ? "Classificação ordenada pela quantidade de projetos em que o parlamentar figura como Autor Principal (iniciativa própria)."
                  : rankingCriterio === "coautoria"
                  ? "Classificação ordenada por projetos coassinados (apoio institucional de bancada e quórum inicial)."
                  : "Classificação por volume bruto de propostas protocoladas no mandato atual."}
              </p>
            </div>
          </div>

          {/* BARRA SUPERIOR DE FILTROS DINÂMICOS: CRITÉRIO, PARTIDO E SETOR */}
          <div className="flex flex-wrap items-center gap-2.5 bg-slate-950/80 p-2 rounded-2xl border border-slate-800/90 shadow-inner">
            {/* Toggle de Critério: IPLE Ponderado, Liderança, Apoio Político, Volume */}
            <div className="inline-flex p-1 bg-slate-900 border border-slate-800 rounded-xl text-xs font-semibold flex-wrap gap-1">
              <button
                type="button"
                aria-pressed={rankingCriterio === "efetividade"}
                onClick={() => setRankingCriterio("efetividade")}
                className={`px-3 py-1 rounded-lg transition-all flex items-center gap-1.5 ${
                  rankingCriterio === "efetividade"
                    ? "bg-gradient-to-r from-amber-500/30 to-emerald-500/20 text-amber-300 border border-amber-500/40 shadow-sm"
                    : "text-slate-300 hover:text-slate-100"
                }`}
                title="Pondera relevância e aprovações de leis (desestimula spam)"
              >
                <Sparkles className="w-3.5 h-3.5 text-amber-400" aria-hidden="true" />
                <span>Efetividade (IPLE)</span>
              </button>
              <button
                type="button"
                aria-pressed={rankingCriterio === "lideranca"}
                onClick={() => setRankingCriterio("lideranca")}
                className={`px-3 py-1 rounded-lg transition-all flex items-center gap-1.5 ${
                  rankingCriterio === "lideranca"
                    ? "bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-sm"
                    : "text-slate-300 hover:text-slate-100"
                }`}
                title="Ordena pela autoria principal (iniciativa própria)"
              >
                <Trophy className="w-3.5 h-3.5 text-amber-400" aria-hidden="true" />
                <span>Liderança</span>
              </button>
              <button
                type="button"
                aria-pressed={rankingCriterio === "coautoria"}
                onClick={() => setRankingCriterio("coautoria")}
                className={`px-3 py-1 rounded-lg transition-all flex items-center gap-1.5 ${
                  rankingCriterio === "coautoria"
                    ? "bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 shadow-sm"
                    : "text-slate-300 hover:text-slate-100"
                }`}
                title="Ordena por coautorias (apoio de bancada e quórum)"
              >
                <Users className="w-3.5 h-3.5 text-indigo-400" aria-hidden="true" />
                <span>Apoio Político</span>
              </button>
              <button
                type="button"
                aria-pressed={rankingCriterio === "volume"}
                onClick={() => setRankingCriterio("volume")}
                className={`px-3 py-1 rounded-lg transition-all flex items-center gap-1.5 ${
                  rankingCriterio === "volume"
                    ? "bg-slate-800 text-white border border-slate-700 shadow-sm"
                    : "text-slate-300 hover:text-slate-100"
                }`}
                title="Contagem bruta de projetos protocolados"
              >
                <BarChart3 className="w-3.5 h-3.5" aria-hidden="true" />
                <span>Volume Bruto</span>
              </button>
            </div>

            {/* 1. Combobox / Select de Partido */}
            <div className="flex items-center gap-1.5 bg-slate-900 border border-slate-800 rounded-xl px-2.5 py-1.5">
              <Users className="w-3.5 h-3.5 text-slate-400" aria-hidden="true" />
              <label htmlFor="ranking-partido-select" className="text-[11px] font-semibold text-slate-400">
                Partido:
              </label>
              <select
                id="ranking-partido-select"
                value={rankingParty}
                onChange={(e) => setRankingParty(e.target.value)}
                className="bg-transparent text-xs font-bold text-slate-100 focus:outline-none cursor-pointer pr-1"
              >
                {partyOptions.map((p) => (
                  <option key={p} value={p} className="bg-slate-900 text-slate-200">
                    {p === "Todos" ? "Todos os Partidos" : p}
                  </option>
                ))}
              </select>
            </div>

            {/* 2. Combobox / Select de Setor / Tema */}
            <div className="flex items-center gap-1.5 bg-slate-900 border border-slate-800 rounded-xl px-2.5 py-1.5">
              <Tag className="w-3.5 h-3.5 text-slate-400" aria-hidden="true" />
              <label htmlFor="ranking-setor-select" className="text-[11px] font-semibold text-slate-400">
                Setor:
              </label>
              <select
                id="ranking-setor-select"
                value={rankingSector}
                onChange={(e) => setRankingSector(e.target.value)}
                className="bg-transparent text-xs font-bold text-slate-100 focus:outline-none cursor-pointer pr-1 max-w-[160px] truncate"
              >
                {sectorOptions.map((s) => (
                  <option key={s} value={s} className="bg-slate-900 text-slate-200">
                    {s === "Todos" ? "Todos os Setores" : s}
                  </option>
                ))}
              </select>
            </div>

            {/* Botão de Limpar caso algum filtro esteja ativo */}
            {(rankingParty !== "Todos" || rankingSector !== "Todos" || rankingCriterio !== "efetividade") && (
              <button
                type="button"
                onClick={() => {
                  setRankingParty("Todos");
                  setRankingSector("Todos");
                  setRankingCriterio("efetividade");
                }}
                className="p-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-[11px] font-medium transition-colors flex items-center gap-1"
                title="Limpar filtros do ranking"
              >
                <X className="w-3.5 h-3.5" aria-hidden="true" />
                <span>Limpar</span>
              </button>
            )}
          </div>
        </div>
        {/* BANNER EXPLICATIVO DA METODOLOGIA (4 PILARES) */}
        {showMetodologia && (
          <div className="bg-gradient-to-br from-slate-900 via-slate-950 to-indigo-950/40 border border-indigo-500/30 rounded-2xl p-5 space-y-4 animate-in fade-in slide-in-from-top-2 duration-300">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-2.5">
              <div className="flex items-center gap-2">
                <Award className="w-4 h-4 text-amber-400" aria-hidden="true" />
                <h4 className="text-xs sm:text-sm font-bold text-white uppercase tracking-wider">
                  Metodologia de Atividade Legislativa Ponderada
                </h4>
              </div>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 w-fit">
                Score = Papel × Complexidade × Tramitação
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
              <div className="bg-slate-900/80 border border-amber-500/20 rounded-xl p-3 space-y-1">
                <span className="text-amber-300 font-bold flex items-center gap-1.5 text-[11px]">
                  <Trophy className="w-3.5 h-3.5 text-amber-400" />
                  1. Papel na Proposta
                </span>
                <p className="text-[11px] text-slate-300 leading-relaxed">
                  • <strong>Autor Principal (1.0 pt):</strong> Liderança direta e redação original.<br />
                  • <strong>Coautor (0.2 pt):</strong> Apoio partidário e atingimento de quórum.
                </p>
              </div>
              <div className="bg-slate-900/80 border border-cyan-500/20 rounded-xl p-3 space-y-1">
                <span className="text-cyan-300 font-bold flex items-center gap-1.5 text-[11px]">
                  <Layers className="w-3.5 h-3.5 text-cyan-400" />
                  2. Complexidade
                </span>
                <p className="text-[11px] text-slate-300 leading-relaxed">
                  • <strong>Alta (3.0 pts):</strong> PEC.<br />
                  • <strong>Média (2.0 pts):</strong> PL, PLP, MPV.<br />
                  • <strong>Baixa (1.0 pt):</strong> PDL, PRC, PRS.
                </p>
              </div>
              <div className="bg-slate-900/80 border border-purple-500/20 rounded-xl p-3 space-y-1">
                <span className="text-purple-300 font-bold flex items-center gap-1.5 text-[11px]">
                  <CheckCircle2 className="w-3.5 h-3.5 text-purple-400" />
                  3. Tramitação
                </span>
                <p className="text-[11px] text-slate-300 leading-relaxed">
                  • <strong>Base:</strong> 1.0x (em tramitação).<br />
                  • <strong>Aprovada:</strong> 1.5x em plenário.<br />
                  • <strong>Virou Lei:</strong> 3.0x (+15 pts).
                </p>
              </div>
              <div className="bg-slate-900/80 border border-emerald-500/20 rounded-xl p-3 space-y-1">
                <span className="text-emerald-300 font-bold flex items-center gap-1.5 text-[11px]">
                  <Users className="w-3.5 h-3.5 text-emerald-400" />
                  4. Filtro Institucional
                </span>
                <p className="text-[11px] text-slate-300 leading-relaxed">
                  • <strong>Colegiados:</strong> Comissões, Mesas Diretoras e Executivo são isolados sem inflar scores individuais.
                </p>
              </div>
            </div>
          </div>
        )}


        {rankingQuery.error ? (
          <ErrorState onRetry={rankingQuery.retry} />
        ) : isLoadingRanking ? (
          <div role="status" aria-live="polite" className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <span className="sr-only">Carregando ranking...</span>
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-32 bg-slate-900/60 border border-slate-800 rounded-2xl animate-pulse" />
            ))}
          </div>
        ) : ranking.length === 0 ? (
          <div className="bg-slate-900/40 border border-slate-800 rounded-2xl p-8 text-center text-slate-400 space-y-2">
            <Trophy className="w-8 h-8 text-slate-400 mx-auto" aria-hidden="true" />
            <p className="text-sm font-semibold text-slate-300">Nenhum parlamentar encontrado para os filtros selecionados</p>
            <p className="text-xs text-slate-400">
              Partido: <strong>{rankingParty}</strong> • Setor: <strong>{rankingSector}</strong>
            </p>
            {(rankingParty !== "Todos" || rankingSector !== "Todos") && (
              <button
                type="button"
                onClick={() => {
                  setRankingParty("Todos");
                  setRankingSector("Todos");
                }}
                className="px-3.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs text-amber-300 font-semibold transition-colors mt-2"
              >
                Restaurar todos os parlamentares
              </button>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
            {ranking.map((autor) => {
              const setorStyle = getSectorStyle(autor.principal_setor);

              return (
                <div
                  key={autor.politico_id}
                  className={`relative bg-slate-900/80 border rounded-2xl p-4 transition-all duration-300 hover:border-indigo-500/40 hover:bg-slate-850 hover:shadow-xl flex flex-col justify-between ${
                    autor.posicao === 1
                      ? "border-amber-500/50 bg-gradient-to-b from-amber-500/5 to-slate-900/80"
                      : autor.posicao === 2
                      ? "border-slate-400/40 bg-gradient-to-b from-slate-400/5 to-slate-900/80"
                      : autor.posicao === 3
                      ? "border-amber-700/40 bg-gradient-to-b from-amber-700/5 to-slate-900/80"
                      : "border-slate-800/90"
                  }`}
                >
                  {/* Posição / Medalha */}
                  <div className="flex items-start justify-between gap-3 mb-3">
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                      <div className="relative shrink-0 w-12 h-12">
                        {safeExternalUrl(autor.foto_url) ? (
                          <img
                            src={safeExternalUrl(autor.foto_url)}
                            alt=""
                            referrerPolicy="no-referrer"
                            className="w-12 h-12 rounded-xl object-cover border border-slate-700 shadow-sm shrink-0 aspect-square"
                            onError={(e) => {
                              // Fallback se a imagem falhar
                              e.currentTarget.style.display = "none";
                            }}
                          />
                        ) : (
                          <div className="w-12 h-12 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300 font-bold shrink-0 aspect-square">
                            {autor.nome_eleitoral.slice(0, 2).toUpperCase()}
                          </div>
                        )}
                        <span
                          className={`absolute -top-2 -left-2 w-6 h-6 rounded-full flex items-center justify-center text-xs font-black shadow-md ${
                            autor.posicao === 1
                              ? "bg-amber-400 text-slate-950 ring-2 ring-amber-300/40"
                              : autor.posicao === 2
                              ? "bg-slate-300 text-slate-950 ring-2 ring-slate-200/40"
                              : autor.posicao === 3
                              ? "bg-amber-700 text-amber-100 ring-2 ring-amber-600/40"
                              : "bg-slate-800 text-slate-300 border border-slate-700"
                          }`}
                        >
                          #{autor.posicao}
                        </span>
                      </div>

                      <div className="min-w-0 flex-1">
                        <h4 className="text-sm font-bold text-white transition-colors line-clamp-1">
                          {autor.politico_id && onSelectPolitician ? (
                            <button
                              type="button"
                              onClick={() => onSelectPolitician(autor.politico_id)}
                              className="cursor-pointer hover:text-cyan-300 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 rounded"
                              title="Clique para abrir o Raio-X"
                            >
                              {autor.nome_eleitoral}
                            </button>
                          ) : (
                            autor.nome_eleitoral
                          )}
                        </h4>
                        <div className="flex items-center gap-1.5 mt-0.5">
                          <PartyLink
                            sigla={autor.partido_sigla}
                            onSelectParty={onSelectParty}
                            className="text-xs font-semibold px-2 py-0.5 rounded-md bg-slate-800 text-slate-300 border border-slate-700 hover:border-cyan-400 hover:text-cyan-300 transition-colors"
                          />
                          <span className="text-xs text-slate-400 font-medium">{autor.uf}</span>
                        </div>
                      </div>
                    </div>

                    <div className="text-right shrink-0">
                      {rankingCriterio === "efetividade" ? (
                        <div>
                          <span className="text-base font-black text-amber-400 tracking-tight flex items-center justify-end gap-1">
                            <Sparkles className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" aria-hidden="true" />
                            {fmtNum(autor.score_ponderado ?? autor.score_produtividade)}
                          </span>
                          <span className="block text-[10px] text-amber-300 uppercase tracking-wider font-semibold">
                            Score IALP (T×A×S)
                          </span>
                          <span className="text-[10px] text-slate-400">
                            {autor.total_proposicoes} {autor.total_proposicoes === 1 ? "projeto" : "projetos"}
                          </span>
                        </div>
                      ) : rankingCriterio === "lideranca" ? (
                        <div>
                          <span className="text-lg font-black text-amber-400 tracking-tight flex items-center justify-end gap-1">
                            <Trophy className="w-4 h-4 text-amber-400" />
                            {autor.autoria_principal_count ?? autor.total_proposicoes}
                          </span>
                          <span className="block text-[10px] text-amber-300 uppercase tracking-wider font-semibold">
                            Liderança
                          </span>
                          <span className="text-[10px] text-slate-400">
                            de {autor.total_proposicoes} total
                          </span>
                        </div>
                      ) : rankingCriterio === "coautoria" ? (
                        <div>
                          <span className="text-lg font-black text-indigo-400 tracking-tight flex items-center justify-end gap-1">
                            <Users className="w-4 h-4 text-indigo-400" />
                            {autor.coautoria_count ?? 0}
                          </span>
                          <span className="block text-[10px] text-indigo-300 uppercase tracking-wider font-semibold">
                            Coautorias
                          </span>
                          <span className="text-[10px] text-slate-400">
                            de {autor.total_proposicoes} total
                          </span>
                        </div>
                      ) : (
                        <div>
                          <span className="text-lg font-black text-indigo-400 tracking-tight">
                            {autor.total_proposicoes}
                          </span>
                          <span className="block text-[10px] text-slate-400 uppercase tracking-wider font-semibold">
                            projetos
                          </span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* 3 Frentes Cidadãs: Liderança, Apoio Político, Eficiência */}
                  <div className="grid grid-cols-3 gap-1.5 my-2 text-[10px] font-mono">
                    <div className="bg-slate-950/70 border border-amber-500/20 rounded-lg px-1.5 py-1 flex flex-col items-center text-center">
                      <span className="text-amber-300 font-semibold flex items-center gap-0.5">
                        <Trophy className="w-2.5 h-2.5 text-amber-400" />
                        Líder
                      </span>
                      <span className="font-bold text-white text-xs mt-0.5">{autor.autoria_principal_count ?? autor.total_proposicoes}</span>
                    </div>
                    <div className="bg-slate-950/70 border border-indigo-500/20 rounded-lg px-1.5 py-1 flex flex-col items-center text-center">
                      <span className="text-indigo-300 font-semibold flex items-center gap-0.5">
                        <Users className="w-2.5 h-2.5 text-indigo-400" />
                        Apoio
                      </span>
                      <span className="font-bold text-white text-xs mt-0.5">{autor.coautoria_count ?? 0}</span>
                    </div>
                    <div className="bg-slate-950/70 border border-teal-500/20 rounded-lg px-1.5 py-1 flex flex-col items-center text-center">
                      <span className="text-teal-300 font-semibold flex items-center gap-0.5">
                        <Sparkles className="w-2.5 h-2.5 text-teal-400" />
                        Efic.
                      </span>
                      <span className="font-bold text-white text-xs mt-0.5">{autor.taxa_eficiencia_pct ?? 0}%</span>
                    </div>
                  </div>

                  {/* Badges de Eficácia & Alerta de Volume */}
                  <div className="flex items-center gap-1.5 flex-wrap my-1.5">
                    {autor.proposicoes_estruturantes !== undefined && autor.proposicoes_estruturantes > 0 && (
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-purple-500/20 text-purple-300 border border-purple-500/30">
                        {autor.proposicoes_estruturantes} Estruturantes
                      </span>
                    )}
                    {autor.proposicoes_aprovadas !== undefined && autor.proposicoes_aprovadas > 0 && (
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                        {autor.proposicoes_aprovadas} Aprovadas
                      </span>
                    )}
                    {autor.taxa_eficiencia_pct !== undefined && autor.taxa_eficiencia_pct > 0 && (
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-teal-500/20 text-teal-300 border border-teal-500/30">
                        {autor.taxa_eficiencia_pct}% Eficiência
                      </span>
                    )}
                    {autor.classificacao_efetividade === "Volume Alto sem Leis Aprovadas" && (
                      <span className="text-[10px] font-medium px-2 py-0.5 rounded-md bg-amber-500/15 text-amber-300 border border-amber-500/30 flex items-center gap-1" title="Parlamentar protocolou grande volume de projetos mas nenhuma lei foi aprovada no período">
                        <AlertTriangle className="w-2.5 h-2.5 text-amber-400" aria-hidden="true" />
                        Volume s/ Leis
                      </span>
                    )}
                  </div>

                  {/* Barra proporcional */}
                  <div className="w-full bg-slate-950/80 rounded-full h-1.5 overflow-hidden mb-3 border border-slate-800">
                    <div
                      className={`h-full rounded-full transition-all duration-700 ${
                        rankingCriterio === "efetividade"
                          ? "bg-gradient-to-r from-amber-500 via-orange-400 to-emerald-400"
                          : rankingCriterio === "lideranca"
                          ? "bg-gradient-to-r from-amber-500 to-amber-300"
                          : rankingCriterio === "coautoria"
                          ? "bg-gradient-to-r from-indigo-500 to-violet-400"
                          : "bg-gradient-to-r from-indigo-500 to-cyan-400"
                      }`}
                      style={{
                        width: `${
                          rankingCriterio === "efetividade"
                            ? Math.min(100, Math.max(10, autor.score_ponderado ?? autor.score_produtividade ?? 0))
                            : rankingCriterio === "lideranca"
                            ? Math.min(100, Math.max(10, ((autor.autoria_principal_count ?? autor.total_proposicoes) / Math.max(1, maxProjetos)) * 100))
                            : rankingCriterio === "coautoria"
                            ? Math.min(100, Math.max(10, ((autor.coautoria_count ?? 0) / Math.max(1, maxProjetos)) * 100))
                            : Math.min(100, Math.max(10, (autor.total_proposicoes / maxProjetos) * 100))
                        }%`
                      }}
                    />
                  </div>

                  {/* Principal Setor de Foco */}
                  <div className="mt-auto pt-2 border-t border-slate-800/80 space-y-1.5">
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="text-slate-400 flex items-center gap-1">
                        <Flame className="w-3 h-3 text-amber-400" aria-hidden="true" />
                        Maior Foco:
                      </span>
                      <span className="text-slate-300 font-semibold text-[11px]">
                        {autor.total_principal_setor}{autor.total_proposicoes > 0 ? ` (${Math.round((autor.total_principal_setor / autor.total_proposicoes) * 100)}%)` : ""}
                      </span>
                    </div>
                    <div
                      className={`px-2.5 py-1 rounded-lg text-xs font-semibold border flex items-center justify-between ${setorStyle.bg} ${setorStyle.text} ${setorStyle.border}`}
                    >
                      <span className="truncate">{autor.principal_setor}</span>
                      <span className="text-[10px] opacity-80 uppercase tracking-wide">Setor</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>
      )}

      {/* ========================================================================= */}
      {/* SEÇÃO REDES: GRAFO DE COAUTORIA, BANCADAS LOUVAIN & PONTES DE ARTICULAÇÃO */}
      {/* ========================================================================= */}
      {(viewTab === "INTEGRADA" || viewTab === "NETWORK") && (
        <section className="space-y-4" aria-label="Grafo de Coautoria e Articulação Parlamentar">
          <CoauthorshipNetworkGraph onSelectPolitician={onSelectPolitician} />
        </section>
      )}

      {/* ========================================================================= */}
      {/* SEÇÃO B: MURAL GERAL DE VOTAÇÕES (DATAGRID COM FILTROS & MODAL SIM/NÃO)   */}
      {/* ========================================================================= */}
      {(viewTab === "INTEGRADA" || viewTab === "PROPOSITIONS") && (
      <section className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-2xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
              <Layers className="w-5 h-5" aria-hidden="true" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-white flex items-center gap-2">
                Mural Geral de Votações & Proposições
                {propositionsData && (
                  <span className="text-xs font-medium px-2.5 py-0.5 rounded-full bg-slate-800 text-cyan-300 border border-slate-700">
                    {propositionsData.total} matérias
                  </span>
                )}
              </h3>
              <p className="text-xs text-slate-400">
                Explore as matérias legislativas com setorização automática e clique para ver a divisão nominal de votos Sim/Não.
              </p>
            </div>
          </div>
        </div>

        {/* BARRA DE CONTROLES E FILTROS */}
        <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3">
            {/* Campo de Busca Textual */}
            <div className="relative">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" aria-hidden="true" />
              <input
                type="text"
                aria-label="Buscar por título, ementa ou autor"
                placeholder="Buscar por título, ementa ou autor..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-xs text-slate-100 placeholder-slate-400 focus:outline-none focus:border-cyan-500 transition-colors"
              />
              {searchTerm && (
                <button
                  type="button"
                  aria-label="Limpar busca"
                  onClick={() => setSearchTerm("")}
                  className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-200"
                >
                  <X className="w-3.5 h-3.5" aria-hidden="true" />
                </button>
              )}
            </div>

            {/* Filtro de Autor por Partido */}
            <div>
              <select
                id="explorer-partido-select"
                aria-label="Filtrar por partido do autor"
                value={selectedParty}
                onChange={(e) => setSelectedParty(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
              >
                <option value="Todos">Todos os Partidos (Autor)</option>
                {partyOptions
                  .filter((p) => p !== "Todos")
                  .map((sigla) => (
                    <option key={sigla} value={sigla}>
                      {sigla}
                    </option>
                  ))}
                <option value="GOV">GOV (Poder Executivo)</option>
              </select>
            </div>

            {/* Filtro de Setor */}
            <div>
              <select
                aria-label="Filtrar por setor"
                value={selectedSetor}
                onChange={(e) => setSelectedSetor(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
              >
                <option value="Todos">Todos os Setores (Temas)</option>
                {(propsQuery.data ?? propsQuery.previousData)?.setores_disponiveis.map((st) => (
                  <option key={st} value={st}>
                    {st}
                  </option>
                ))}
              </select>
            </div>

            {/* Filtro de Tipo de Proposição */}
            <div>
              <select
                aria-label="Filtrar por tipo de proposição"
                value={selectedTipo}
                onChange={(e) => setSelectedTipo(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
              >
                <option value="Todos">Todos os Tipos (PL, PEC, PLP...)</option>
                <option value="PL">PL - Projeto de Lei</option>
                <option value="PEC">PEC - Proposta de Emenda à Constituição</option>
                <option value="PLP">PLP - Projeto de Lei Complementar</option>
                <option value="MPV">MPV - Medida Provisória</option>
              </select>
            </div>

            {/* Toggle de Apenas com Votação Nominal */}
            <div className="flex items-center">
              <label className="flex items-center gap-2 cursor-pointer text-xs font-semibold text-slate-300 select-none bg-slate-950/70 border border-slate-800/80 px-3 py-2 rounded-xl w-full hover:border-slate-700 transition-colors">
                <input
                  type="checkbox"
                  checked={apenasVotadas}
                  onChange={(e) => setApenasVotadas(e.target.checked)}
                  className="rounded border-slate-700 text-cyan-500 focus:ring-0 focus:ring-offset-0 bg-slate-900"
                />
                <Vote className="w-3.5 h-3.5 text-cyan-400" aria-hidden="true" />
                <span>Apenas com votação nominal</span>
              </label>
            </div>
          </div>
        </div>

        {/* TABELA DATAGRID DE PROPOSIÇÕES */}
        <div className="bg-slate-900/90 border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
          {isLoadingProps ? (
            <div role="status" aria-live="polite" className="p-12 text-center text-slate-400 space-y-3">
              <div className="w-8 h-8 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin mx-auto" aria-hidden="true" />
              <p className="text-xs">Carregando proposições legislativas...</p>
            </div>
          ) : propsQuery.error ? (
            <div className="p-6"><ErrorState onRetry={propsQuery.retry} /></div>
          ) : !propositionsData || propositionsData.items.length === 0 ? (
            <div role="status" className="p-12 text-center text-slate-400 space-y-2">
              <BookOpen className="w-8 h-8 text-slate-400 mx-auto" aria-hidden="true" />
              <p className="text-sm font-semibold text-slate-300">Nenhuma proposição encontrada</p>
              <p className="text-xs text-slate-400">Tente ajustar os filtros ou o termo de busca acima.</p>
              {(searchTerm || selectedParty !== "Todos" || selectedSetor !== "Todos" || selectedTipo !== "Todos" || apenasVotadas) && (
                <button
                  type="button"
                  onClick={() => {
                    setSearchTerm("");
                    setSelectedParty("Todos");
                    setSelectedSetor("Todos");
                    setSelectedTipo("Todos");
                    setApenasVotadas(false);
                  }}
                  className="mt-2 text-xs font-medium text-cyan-400 hover:text-cyan-300 underline underline-offset-4"
                >
                  Limpar todos os filtros
                </button>
              )}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-200">
                <caption className="sr-only">Proposições legislativas</caption>
                <thead className="bg-slate-950/80 text-[11px] uppercase tracking-wider text-slate-400 border-b border-slate-800">
                  <tr>
                    <th scope="col" className="py-3 px-4 font-semibold">Título / Matéria</th>
                    <th scope="col" className="py-3 px-4 font-semibold">Setor (Tema)</th>
                    <th scope="col" className="py-3 px-4 font-semibold">Autor Oficial</th>
                    <th scope="col" className="py-3 px-4 font-semibold text-center">Placar Geral</th>
                    <th scope="col" className="py-3 px-4 font-semibold text-center">Status</th>
                    <th scope="col" className="py-3 px-4 font-semibold text-right">Ação</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-medium">
                  {propositionsData.items.map((prop) => {
                    const setorStyle = getSectorStyle(prop.setor);
                    const temPlacar = prop.tem_votacao && prop.placar.total > 0;

                    return (
                      <tr
                        key={prop.id}
                        className="hover:bg-slate-800/50 transition-colors group"
                      >
                        {/* Título & Ementa */}
                        <td className="py-3.5 px-4 max-w-sm">
                          <div className="font-bold text-white group-hover:text-cyan-300 transition-colors flex items-center justify-between gap-2">
                            <div className="flex items-center gap-2">
                              <button
                                type="button"
                                onClick={() => setSelectedPropId(prop.id)}
                                className="text-left cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 rounded"
                              >
                                {prop.titulo}
                              </button>
                              {prop.is_reforma_estrutural && (
                                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
                                  Reforma
                                </span>
                              )}
                              {prop.tipo === "PEC" ? (
                                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 font-mono">
                                  PEC • T=3.0
                                </span>
                              ) : prop.tipo === "PLP" ? (
                                <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-indigo-500/15 text-indigo-300 border border-indigo-500/25 font-mono">
                                  PLP • T=2.5
                                </span>
                              ) : ["PL", "MPV"].includes(prop.tipo) ? (
                                <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-blue-500/15 text-blue-300 border border-blue-500/25 font-mono">
                                  {prop.tipo} • T=2.0
                                </span>
                              ) : ["REQ", "INC"].includes(prop.tipo) ? (
                                <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-rose-500/15 text-rose-300 border border-rose-500/25 font-mono">
                                  {prop.tipo} • T=0.1
                                </span>
                              ) : (
                                <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700 font-mono">
                                  {prop.tipo} • T=1.0
                                </span>
                              )}
                            </div>
                            {safeExternalUrl(prop.url_oficial) && (
                              <a
                                href={safeExternalUrl(prop.url_oficial)}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1 text-[11px] font-semibold text-cyan-400 hover:text-cyan-300 bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/20 px-2 py-0.5 rounded-lg transition-colors shrink-0"
                                title="Ler na íntegra no site oficial"
                              >
                                <span>Íntegra</span>
                                <ExternalLink className="w-3 h-3" aria-hidden="true" />
                              </a>
                            )}
                          </div>
                          <p className="text-[11px] text-slate-400 line-clamp-1 mt-0.5" title={prop.ementa}>
                            {prop.ementa}
                          </p>
                        </td>

                        {/* Setor */}
                        <td className="py-3.5 px-4 whitespace-nowrap">
                          <span
                            className={`inline-block px-2.5 py-1 rounded-lg text-xs font-semibold border ${setorStyle.bg} ${setorStyle.text} ${setorStyle.border}`}
                          >
                            {prop.setor}
                          </span>
                        </td>

                        {/* Autor */}
                        <td className="py-3.5 px-4 whitespace-nowrap">
                          <div className="flex items-center gap-2">
                            {safeExternalUrl(prop.autor_foto) ? (
                              <img
                                src={safeExternalUrl(prop.autor_foto)}
                                alt=""
                                referrerPolicy="no-referrer"
                                className="w-6 h-6 rounded-full object-cover border border-slate-700"
                                onError={(e) => {
                                  e.currentTarget.style.display = "none";
                                }}
                              />
                            ) : (
                              <div className="w-6 h-6 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-[10px] text-slate-300">
                                <Users className="w-3 h-3" aria-hidden="true" />
                              </div>
                            )}
                            <div>
                              <span className="font-semibold text-slate-200 block text-xs">{prop.autor_nome}</span>
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <span className="text-[10px] text-slate-400">
                                  {prop.autor_partido} {prop.autor_uf ? `• ${prop.autor_uf}` : ""}
                                </span>
                                {prop.iniciativa_executivo && (
                                  <span className="text-[9px] font-mono px-1 py-0.2 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
                                    Institucional (Executivo)
                                  </span>
                                )}
                              </div>
                            </div>
                          </div>
                        </td>

                        {/* Placar Geral */}
                        <td className="py-3.5 px-4 text-center whitespace-nowrap">
                          {temPlacar ? (
                            <div className="inline-flex flex-col items-center">
                              <div className="flex items-center gap-1.5 text-xs font-bold">
                                <span className="text-emerald-400">Sim: {prop.placar.sim}</span>
                                <span className="text-slate-400" aria-hidden="true">|</span>
                                <span className="text-rose-400">Não: {prop.placar.nao}</span>
                              </div>
                              <div className="w-24 bg-slate-800 h-1 rounded-full overflow-hidden flex mt-1">
                                <div
                                  className="bg-emerald-500 h-full"
                                  style={{
                                    width: `${(prop.placar.sim / prop.placar.total) * 100}%`,
                                  }}
                                />
                                <div
                                  className="bg-rose-500 h-full"
                                  style={{
                                    width: `${(prop.placar.nao / prop.placar.total) * 100}%`,
                                  }}
                                />
                              </div>
                            </div>
                          ) : (
                            <span className="text-[11px] text-slate-400 italic">Sem votação em plenário</span>
                          )}
                        </td>

                        {/* Status */}
                        <td className="py-3.5 px-4 text-center whitespace-nowrap">
                          {prop.placar.resultado === "APROVADA" || prop.status.includes("APROVADA") ? (
                            <div className="flex flex-col items-center">
                              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                                <CheckCircle2 className="w-3 h-3" aria-hidden="true" />
                                Aprovada
                              </span>
                              <span className="text-[9px] font-mono text-emerald-400 mt-0.5">
                                {["APROVADA_E_SANCIONADA", "APROVADA_E_PROMULGADA"].includes(prop.status)
                                  ? "Norma Jurídica (3.0x)"
                                  : "Aprovada (1.5x)"}
                              </span>
                            </div>
                          ) : prop.placar.resultado === "REJEITADA" || prop.status.includes("REJEITADA") ? (
                            <div className="flex flex-col items-center">
                              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-rose-500/15 text-rose-300 border border-rose-500/30">
                                <XCircle className="w-3 h-3" aria-hidden="true" />
                                Rejeitada
                              </span>
                              <span className="text-[9px] font-mono text-rose-400/80 mt-0.5">Arquivada (0.0x)</span>
                            </div>
                          ) : (
                            <div className="flex flex-col items-center">
                              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-slate-800 text-slate-300 border border-slate-700">
                                <HelpCircle className="w-3 h-3 text-slate-400" aria-hidden="true" />
                                Em Tramitação
                              </span>
                              <span className="text-[9px] font-mono text-slate-400 mt-0.5">Base (1.0x)</span>
                            </div>
                          )}
                        </td>

                        {/* Ação */}
                        <td className="py-3.5 px-4 text-right whitespace-nowrap">
                          <button
                            type="button"
                            onClick={() => setSelectedPropId(prop.id)}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 transition-all hover:scale-105"
                          >
                            <Vote className="w-3.5 h-3.5" aria-hidden="true" />
                            <span>{temPlacar ? "Ver Votos" : "Detalhes"}</span>
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* PAGINAÇÃO */}
          {propositionsData && propositionsData.total_pages > 1 && (
            <div className="bg-slate-950/80 px-4 py-3 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400">
              <div>
                Exibindo página <span className="font-bold text-white">{propositionsData.page}</span> de{" "}
                <span className="font-bold text-white">{propositionsData.total_pages}</span> (Total de{" "}
                <span className="font-bold text-white">{propositionsData.total}</span> matérias)
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={currentPage <= 1}
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  className="px-3 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1 transition-colors"
                >
                  <ChevronLeft className="w-3.5 h-3.5" aria-hidden="true" />
                  Anterior
                </button>
                <button
                  type="button"
                  disabled={currentPage >= propositionsData.total_pages}
                  onClick={() => setCurrentPage((p) => Math.min(propositionsData.total_pages, p + 1))}
                  className="px-3 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1 transition-colors"
                >
                  Próxima
                  <ChevronRight className="w-3.5 h-3.5" aria-hidden="true" />
                </button>
              </div>
            </div>
          )}
        </div>
      </section>
      )}

      {/* ========================================================================= */}
      {/* MODAL DETALHADO: "QUEM VOTOU SIM (A FAVOR)" vs "QUEM VOTOU NÃO (CONTRA)"   */}
      {/* ========================================================================= */}
      {selectedPropId && (
        <PropositionVoteModal
          propId={selectedPropId}
          onClose={() => setSelectedPropId(null)}
          onSelectPolitician={onSelectPolitician}
          onSelectParty={onSelectParty}
        />
      )}
    </div>
  );
}
