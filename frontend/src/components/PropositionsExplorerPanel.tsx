"use client";

import React, { useState, useEffect, useMemo } from "react";
import {
  AuthorProductivityItem,
  PropositionExplorerItem,
  LegislativeExplorerResponse,
  PropositionNominalVotesSplitResponse,
  getAuthorsProductivityRanking,
  getLegislativeExplorer,
  getPropositionNominalVotesSplit,
} from "@/services/api";
import {
  Search,
  Filter,
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
  Award,
  BarChart3,
  X,
  FileText,
  Building,
  Check,
  Ban,
  Tag
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
  for (const [key, val] of Object.entries(SECTOR_BADGE_STYLES)) {
    if (sector.toLowerCase().includes(key.toLowerCase())) {
      return val;
    }
  }
  return { bg: "bg-slate-800", text: "text-slate-300", border: "border-slate-700" };
}

const RANKING_PARTIDOS_OPTIONS = [
  "Todos",
  "PL",
  "PT",
  "UNIÃO",
  "PP",
  "MDB",
  "PSD",
  "Republicanos",
  "PSDB",
  "PODEMOS",
  "PSOL",
  "PDT",
  "PSB",
  "NOVO",
];

const RANKING_SETORES_OPTIONS = [
  "Todos",
  "Saúde",
  "Educação",
  "Segurança Pública",
  "Economia & Finanças",
  "Trabalho & Previdência",
  "Meio Ambiente & Clima",
  "Direitos Humanos & Minorias",
  "Tecnologia & Inovação",
  "Infraestrutura & Cidades",
  "Agricultura & Agropecuária",
  "Administração & Justiça",
  "Administração & Cidadania",
  "Homenagens & Datas Comemorativas",
];

interface PropositionsExplorerPanelProps {
  onSelectPolitician?: (id: string) => void;
  onSelectParty?: (sigla: string) => void;
}

export default function PropositionsExplorerPanel({
  onSelectPolitician,
  onSelectParty,
}: PropositionsExplorerPanelProps = {}) {
  // 1. Estados do Ranking de Produtividade (Filtros por Partido e Setor)
  const [ranking, setRanking] = useState<AuthorProductivityItem[]>([]);
  const [isLoadingRanking, setIsLoadingRanking] = useState<boolean>(true);
  const [rankingParty, setRankingParty] = useState<string>("Todos");
  const [rankingSector, setRankingSector] = useState<string>("Todos");

  // 2. Estados do Mural Geral de Votações
  const [propositionsData, setPropositionsData] = useState<LegislativeExplorerResponse | null>(null);
  const [isLoadingProps, setIsLoadingProps] = useState<boolean>(true);
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [debouncedSearch, setDebouncedSearch] = useState<string>("");
  const [selectedSetor, setSelectedSetor] = useState<string>("Todos");
  const [selectedTipo, setSelectedTipo] = useState<string>("Todos");
  const [selectedStatus, setSelectedStatus] = useState<string>("Todos");
  const [apenasVotadas, setApenasVotadas] = useState<boolean>(false);
  const [currentPage, setCurrentPage] = useState<number>(1);

  // 3. Estados do Modal de Votação Nominal (Sim vs Não)
  const [selectedPropId, setSelectedPropId] = useState<string | null>(null);
  const [modalData, setModalData] = useState<PropositionNominalVotesSplitResponse | null>(null);
  const [isLoadingModal, setIsLoadingModal] = useState<boolean>(false);
  const [modalSearch, setModalSearch] = useState<string>("");
  const [activeModalTab, setActiveModalTab] = useState<"lado_a_lado" | "sim" | "nao">("lado_a_lado");

  // Debounce da busca textual
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchTerm);
      setCurrentPage(1);
    }, 350);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  // Carregar Ranking de Autores (Top 20) com filtros de Partido e Setor
  useEffect(() => {
    async function fetchRanking() {
      setIsLoadingRanking(true);
      try {
        const data = await getAuthorsProductivityRanking(
          20,
          rankingParty !== "Todos" ? rankingParty : undefined,
          rankingSector !== "Todos" ? rankingSector : undefined
        );
        setRanking(data);
      } catch (err) {
        console.error("Erro ao carregar ranking de autores:", err);
      } finally {
        setIsLoadingRanking(false);
      }
    }
    fetchRanking();
  }, [rankingParty, rankingSector]);

  // Carregar Proposições com filtros e paginação
  useEffect(() => {
    async function fetchPropositions() {
      setIsLoadingProps(true);
      try {
        const data = await getLegislativeExplorer({
          search: debouncedSearch || undefined,
          setor: selectedSetor !== "Todos" ? selectedSetor : undefined,
          tipo: selectedTipo !== "Todos" ? selectedTipo : undefined,
          status: selectedStatus !== "Todos" ? selectedStatus : undefined,
          apenas_votadas: apenasVotadas,
          page: currentPage,
          limit: 15,
        });
        setPropositionsData(data);
      } catch (err) {
        console.error("Erro ao carregar explorador de proposições:", err);
      } finally {
        setIsLoadingProps(false);
      }
    }
    fetchPropositions();
  }, [debouncedSearch, selectedSetor, selectedTipo, selectedStatus, apenasVotadas, currentPage]);

  // Carregar dados de Votação Nominal do Modal ao clicar em uma proposição
  useEffect(() => {
    if (!selectedPropId) {
      setModalData(null);
      return;
    }

    async function fetchModalVotes() {
      setIsLoadingModal(true);
      try {
        const data = await getPropositionNominalVotesSplit(selectedPropId!);
        setModalData(data);
      } catch (err) {
        console.error("Erro ao carregar votos nominais da proposição:", err);
      } finally {
        setIsLoadingModal(false);
      }
    }
    fetchModalVotes();
  }, [selectedPropId]);

  // Fechar modal com tecla Esc
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSelectedPropId(null);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Filtragem interna no modal de votos
  const filteredVotosSim = useMemo(() => {
    if (!modalData?.votos_sim) return [];
    if (!modalSearch.trim()) return modalData.votos_sim;
    const s = modalSearch.toLowerCase();
    return modalData.votos_sim.filter(
      (v) =>
        v.nome_eleitoral.toLowerCase().includes(s) ||
        v.partido_sigla.toLowerCase().includes(s) ||
        v.uf.toLowerCase().includes(s)
    );
  }, [modalData, modalSearch]);

  const filteredVotosNao = useMemo(() => {
    if (!modalData?.votos_nao) return [];
    if (!modalSearch.trim()) return modalData.votos_nao;
    const s = modalSearch.toLowerCase();
    return modalData.votos_nao.filter(
      (v) =>
        v.nome_eleitoral.toLowerCase().includes(s) ||
        v.partido_sigla.toLowerCase().includes(s) ||
        v.uf.toLowerCase().includes(s)
    );
  }, [modalData, modalSearch]);

  const maxProjetos = ranking.length > 0 ? ranking[0].total_proposicoes : 1;

  return (
    <div className="space-y-10 animate-in fade-in duration-500">
      {/* CABEÇALHO DO PAINEL */}
      <div className="bg-gradient-to-r from-slate-900 via-indigo-950/40 to-slate-900 border border-indigo-500/20 rounded-3xl p-6 sm:p-8 backdrop-blur-xl relative overflow-hidden shadow-2xl">
        <div className="absolute top-0 right-0 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="relative z-10 space-y-3">
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
            <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
            Fase 10: Produtividade Parlamentar & Mural de Votações
          </div>
          <h2 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
            Explorador Geral de Proposições & Autoria
          </h2>
          <p className="text-sm sm:text-base text-slate-300 max-w-3xl leading-relaxed">
            Acompanhe o ritmo diário do Congresso Nacional na 57ª Legislatura (2023-2026).
            Descubra quem são os parlamentares mais produtivos, em quais setores eles concentram suas propostas
            e consulte o placar nominal de aprovação ou rejeição de cada lei.
          </p>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* SEÇÃO A: RANKING DE PRODUTIVIDADE DOS DEPUTADOS / SENADORES              */}
      {/* ========================================================================= */}
      <section className="space-y-5">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-slate-800 pb-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-2xl bg-amber-500/10 border border-amber-500/20 text-amber-400">
              <Trophy className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-white flex items-center gap-2">
                Ranking de Produtividade Parlamentar
                <span className="text-xs font-medium px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700">
                  {ranking.length > 0 ? `Top ${ranking.length}` : "Filtro ativo"}
                </span>
              </h3>
              <p className="text-xs text-slate-400">
                Parlamentares com maior volume de propostas legislativas protocoladas no mandato atual.
              </p>
            </div>
          </div>

          {/* BARRA SUPERIOR DE FILTROS DINÂMICOS: PARTIDO E SETOR */}
          <div className="flex flex-wrap items-center gap-2.5 bg-slate-950/80 p-2 rounded-2xl border border-slate-800/90 shadow-inner">
            {/* 1. Combobox / Select de Partido */}
            <div className="flex items-center gap-1.5 bg-slate-900 border border-slate-800 rounded-xl px-2.5 py-1.5">
              <Users className="w-3.5 h-3.5 text-slate-400" />
              <label htmlFor="ranking-partido-select" className="text-[11px] font-semibold text-slate-400">
                Partido:
              </label>
              <select
                id="ranking-partido-select"
                value={rankingParty}
                onChange={(e) => setRankingParty(e.target.value)}
                className="bg-transparent text-xs font-bold text-slate-100 focus:outline-none cursor-pointer pr-1"
              >
                {RANKING_PARTIDOS_OPTIONS.map((p) => (
                  <option key={p} value={p} className="bg-slate-900 text-slate-200">
                    {p === "Todos" ? "Todos os Partidos" : p}
                  </option>
                ))}
              </select>
            </div>

            {/* 2. Combobox / Select de Setor / Tema */}
            <div className="flex items-center gap-1.5 bg-slate-900 border border-slate-800 rounded-xl px-2.5 py-1.5">
              <Tag className="w-3.5 h-3.5 text-slate-400" />
              <label htmlFor="ranking-setor-select" className="text-[11px] font-semibold text-slate-400">
                Setor:
              </label>
              <select
                id="ranking-setor-select"
                value={rankingSector}
                onChange={(e) => setRankingSector(e.target.value)}
                className="bg-transparent text-xs font-bold text-slate-100 focus:outline-none cursor-pointer pr-1 max-w-[160px] truncate"
              >
                {RANKING_SETORES_OPTIONS.map((s) => (
                  <option key={s} value={s} className="bg-slate-900 text-slate-200">
                    {s === "Todos" ? "Todos os Setores" : s}
                  </option>
                ))}
              </select>
            </div>

            {/* Botão de Limpar caso algum filtro esteja ativo */}
            {(rankingParty !== "Todos" || rankingSector !== "Todos") && (
              <button
                onClick={() => {
                  setRankingParty("Todos");
                  setRankingSector("Todos");
                }}
                className="p-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-[11px] font-medium transition-colors flex items-center gap-1"
                title="Limpar filtros do ranking"
              >
                <X className="w-3.5 h-3.5" />
                <span>Limpar</span>
              </button>
            )}
          </div>
        </div>

        {isLoadingRanking ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-32 bg-slate-900/60 border border-slate-800 rounded-2xl animate-pulse" />
            ))}
          </div>
        ) : ranking.length === 0 ? (
          <div className="bg-slate-900/40 border border-slate-800 rounded-2xl p-8 text-center text-slate-400 space-y-2">
            <Trophy className="w-8 h-8 text-slate-600 mx-auto" />
            <p className="text-sm font-semibold text-slate-300">Nenhum parlamentar encontrado para os filtros selecionados</p>
            <p className="text-xs text-slate-500">
              Partido: <strong>{rankingParty}</strong> • Setor: <strong>{rankingSector}</strong>
            </p>
            {(rankingParty !== "Todos" || rankingSector !== "Todos") && (
              <button
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
              const isTop3 = autor.posicao <= 3;

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
                    <div className="flex items-center gap-3">
                      <div className="relative">
                        {autor.foto_url ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={autor.foto_url}
                            alt={autor.nome_eleitoral}
                            className="w-12 h-12 rounded-xl object-cover border border-slate-700 shadow-sm"
                            onError={(e) => {
                              // Fallback se a imagem falhar
                              (e.target as HTMLElement).style.display = "none";
                            }}
                          />
                        ) : (
                          <div className="w-12 h-12 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-400 font-bold">
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

                      <div>
                        <h4
                          onClick={() => {
                            if (autor.politico_id && onSelectPolitician) {
                              onSelectPolitician(autor.politico_id);
                            }
                          }}
                          className={`text-sm font-bold text-white transition-colors line-clamp-1 ${
                            autor.politico_id && onSelectPolitician ? "cursor-pointer hover:text-cyan-300" : "hover:text-indigo-300"
                          }`}
                          title={autor.politico_id && onSelectPolitician ? "Clique para abrir o Raio-X" : undefined}
                        >
                          {autor.nome_eleitoral}
                        </h4>
                        <div className="flex items-center gap-1.5 mt-0.5">
                          <span
                            onClick={(e) => {
                              if (onSelectParty && autor.partido_sigla) {
                                e.stopPropagation();
                                onSelectParty(autor.partido_sigla);
                              }
                            }}
                            className={`text-xs font-semibold px-2 py-0.5 rounded-md bg-slate-800 text-slate-300 border border-slate-700 ${
                              onSelectParty ? "cursor-pointer hover:border-cyan-400 hover:text-cyan-300 transition-colors" : ""
                            }`}
                            title={onSelectParty ? `Ver bancada do ${autor.partido_sigla}` : undefined}
                          >
                            {autor.partido_sigla}
                          </span>
                          <span className="text-xs text-slate-400 font-medium">{autor.uf}</span>
                        </div>
                      </div>
                    </div>

                    <div className="text-right">
                      <span className="text-lg font-black text-indigo-400 tracking-tight">
                        {autor.total_proposicoes}
                      </span>
                      <span className="block text-[10px] text-slate-500 uppercase tracking-wider font-semibold">
                        projetos
                      </span>
                    </div>
                  </div>

                  {/* Barra de volume proporcional */}
                  <div className="w-full bg-slate-950/80 rounded-full h-1.5 overflow-hidden mb-3 border border-slate-800">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-cyan-400 transition-all duration-700"
                      style={{ width: `${Math.min(100, Math.max(12, (autor.total_proposicoes / maxProjetos) * 100))}%` }}
                    />
                  </div>

                  {/* Principal Setor de Foco */}
                  <div className="mt-auto pt-2 border-t border-slate-800/80 space-y-1.5">
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="text-slate-400 flex items-center gap-1">
                        <Flame className="w-3 h-3 text-amber-400" />
                        Maior Foco:
                      </span>
                      <span className="text-slate-300 font-semibold text-[11px]">
                        {autor.total_principal_setor} ({Math.round((autor.total_principal_setor / autor.total_proposicoes) * 100)}%)
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

      {/* ========================================================================= */}
      {/* SEÇÃO B: MURAL GERAL DE VOTAÇÕES (DATAGRID COM FILTROS & MODAL SIM/NÃO)   */}
      {/* ========================================================================= */}
      <section className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-2xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
              <Layers className="w-5 h-5" />
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
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {/* Campo de Busca Textual */}
            <div className="relative">
              <Search className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
              <input
                type="text"
                placeholder="Buscar por título, ementa ou autor..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition-colors"
              />
              {searchTerm && (
                <button
                  onClick={() => setSearchTerm("")}
                  className="absolute right-2.5 top-2.5 text-slate-500 hover:text-slate-300"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            {/* Filtro de Setor */}
            <div>
              <select
                value={selectedSetor}
                onChange={(e) => {
                  setSelectedSetor(e.target.value);
                  setCurrentPage(1);
                }}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
              >
                <option value="Todos">Todos os Setores (Temas)</option>
                {propositionsData?.setores_disponiveis.map((st) => (
                  <option key={st} value={st}>
                    {st}
                  </option>
                ))}
              </select>
            </div>

            {/* Filtro de Tipo de Proposição */}
            <div>
              <select
                value={selectedTipo}
                onChange={(e) => {
                  setSelectedTipo(e.target.value);
                  setCurrentPage(1);
                }}
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
                  onChange={(e) => {
                    setApenasVotadas(e.target.checked);
                    setCurrentPage(1);
                  }}
                  className="rounded border-slate-700 text-cyan-500 focus:ring-0 focus:ring-offset-0 bg-slate-900"
                />
                <Vote className="w-3.5 h-3.5 text-cyan-400" />
                <span>Apenas com votação nominal</span>
              </label>
            </div>
          </div>
        </div>

        {/* TABELA DATAGRID DE PROPOSIÇÕES */}
        <div className="bg-slate-900/90 border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
          {isLoadingProps ? (
            <div className="p-12 text-center text-slate-400 space-y-3">
              <div className="w-8 h-8 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin mx-auto" />
              <p className="text-xs">Carregando proposições legislativas...</p>
            </div>
          ) : !propositionsData || propositionsData.items.length === 0 ? (
            <div className="p-12 text-center text-slate-400 space-y-2">
              <BookOpen className="w-8 h-8 text-slate-600 mx-auto" />
              <p className="text-sm font-semibold text-slate-300">Nenhuma proposição encontrada</p>
              <p className="text-xs text-slate-500">Tente ajustar os filtros ou o termo de busca acima.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-200">
                <thead className="bg-slate-950/80 text-[11px] uppercase tracking-wider text-slate-400 border-b border-slate-800">
                  <tr>
                    <th className="py-3 px-4 font-semibold">Título / Matéria</th>
                    <th className="py-3 px-4 font-semibold">Setor (Tema)</th>
                    <th className="py-3 px-4 font-semibold">Autor Oficial</th>
                    <th className="py-3 px-4 font-semibold text-center">Placar Geral</th>
                    <th className="py-3 px-4 font-semibold text-center">Status</th>
                    <th className="py-3 px-4 font-semibold text-right">Ação</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-medium">
                  {propositionsData.items.map((prop) => {
                    const setorStyle = getSectorStyle(prop.setor);
                    const temPlacar = prop.tem_votacao && prop.placar.total > 0;

                    return (
                      <tr
                        key={prop.id}
                        onClick={() => setSelectedPropId(prop.id)}
                        className="hover:bg-slate-800/50 cursor-pointer transition-colors group"
                      >
                        {/* Título & Ementa */}
                        <td className="py-3.5 px-4 max-w-sm">
                          <div className="font-bold text-white group-hover:text-cyan-300 transition-colors flex items-center justify-between gap-2">
                            <div className="flex items-center gap-2">
                              <span>{prop.titulo}</span>
                              {prop.is_reforma_estrutural && (
                                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
                                  Reforma
                                </span>
                              )}
                            </div>
                            {prop.url_oficial && (
                              <a
                                href={prop.url_oficial}
                                target="_blank"
                                rel="noopener noreferrer"
                                onClick={(e) => e.stopPropagation()}
                                className="inline-flex items-center gap-1 text-[11px] font-semibold text-cyan-400 hover:text-cyan-300 bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/20 px-2 py-0.5 rounded-lg transition-colors shrink-0"
                                title="Ler na íntegra no site oficial"
                              >
                                <span>Íntegra</span>
                                <ExternalLink className="w-3 h-3" />
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
                            {prop.autor_foto ? (
                              // eslint-disable-next-line @next/next/no-img-element
                              <img
                                src={prop.autor_foto}
                                alt={prop.autor_nome}
                                className="w-6 h-6 rounded-full object-cover border border-slate-700"
                                onError={(e) => {
                                  (e.target as HTMLElement).style.display = "none";
                                }}
                              />
                            ) : (
                              <div className="w-6 h-6 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-[10px] text-slate-400">
                                <Users className="w-3 h-3" />
                              </div>
                            )}
                            <div>
                              <span className="font-semibold text-slate-200 block text-xs">{prop.autor_nome}</span>
                              <span className="text-[10px] text-slate-400">
                                {prop.autor_partido} {prop.autor_uf ? `• ${prop.autor_uf}` : ""}
                              </span>
                            </div>
                          </div>
                        </td>

                        {/* Placar Geral */}
                        <td className="py-3.5 px-4 text-center whitespace-nowrap">
                          {temPlacar ? (
                            <div className="inline-flex flex-col items-center">
                              <div className="flex items-center gap-1.5 text-xs font-bold">
                                <span className="text-emerald-400">Sim: {prop.placar.sim}</span>
                                <span className="text-slate-600">|</span>
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
                            <span className="text-[11px] text-slate-500 italic">Sem votação em plenário</span>
                          )}
                        </td>

                        {/* Status */}
                        <td className="py-3.5 px-4 text-center whitespace-nowrap">
                          {prop.placar.resultado === "APROVADA" || prop.status.includes("APROVADA") ? (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                              <CheckCircle2 className="w-3 h-3" />
                              Aprovada
                            </span>
                          ) : prop.placar.resultado === "REJEITADA" || prop.status.includes("REJEITADA") ? (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-rose-500/15 text-rose-300 border border-rose-500/30">
                              <XCircle className="w-3 h-3" />
                              Rejeitada
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-slate-800 text-slate-300 border border-slate-700">
                              <HelpCircle className="w-3 h-3 text-slate-400" />
                              Em Tramitação
                            </span>
                          )}
                        </td>

                        {/* Ação */}
                        <td className="py-3.5 px-4 text-right whitespace-nowrap">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedPropId(prop.id);
                            }}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 transition-all hover:scale-105"
                          >
                            <Vote className="w-3.5 h-3.5" />
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
                  disabled={currentPage <= 1}
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  className="px-3 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1 transition-colors"
                >
                  <ChevronLeft className="w-3.5 h-3.5" />
                  Anterior
                </button>
                <button
                  disabled={currentPage >= propositionsData.total_pages}
                  onClick={() => setCurrentPage((p) => Math.min(propositionsData.total_pages, p + 1))}
                  className="px-3 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1 transition-colors"
                >
                  Próxima
                  <ChevronRight className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* ========================================================================= */}
      {/* MODAL DETALHADO: "QUEM VOTOU SIM (A FAVOR)" vs "QUEM VOTOU NÃO (CONTRA)"   */}
      {/* ========================================================================= */}
      {selectedPropId && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-200"
          onClick={() => setSelectedPropId(null)}
        >
          <div
            className="bg-slate-900 border border-slate-700 rounded-3xl w-full max-w-5xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden relative"
            onClick={(e) => e.stopPropagation()}
          >
            {/* CABEÇALHO DO MODAL */}
            <div className="p-6 border-b border-slate-800 bg-slate-950/80 relative">
              <button
                onClick={() => setSelectedPropId(null)}
                className="absolute top-5 right-5 p-2 rounded-xl bg-slate-800/80 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>

              {isLoadingModal ? (
                <div className="space-y-2 animate-pulse">
                  <div className="h-4 bg-slate-800 rounded w-1/4" />
                  <div className="h-6 bg-slate-800 rounded w-3/4" />
                </div>
              ) : modalData?.proposicao ? (
                <div className="space-y-3 pr-8">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-bold px-2.5 py-1 rounded-lg bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                      {modalData.proposicao.numero ? `Nº ${modalData.proposicao.numero}/${modalData.proposicao.ano}` : "Proposição"}
                    </span>
                    {modalData.proposicao.setor && (
                      <span className="text-xs font-semibold px-2.5 py-1 rounded-lg bg-teal-500/20 text-teal-300 border border-teal-500/30">
                        {modalData.proposicao.setor}
                      </span>
                    )}
                    {modalData.sessao?.aprovada !== undefined && (
                      <span
                        className={`text-xs font-bold px-2.5 py-1 rounded-lg border ${
                          modalData.sessao.aprovada
                            ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
                            : "bg-rose-500/20 text-rose-300 border-rose-500/30"
                        }`}
                      >
                        {modalData.sessao.aprovada ? "Aprovada em Plenário" : "Rejeitada em Plenário"}
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-3 flex-wrap">
                    <h3 className="text-xl sm:text-2xl font-black text-white leading-tight">
                      {modalData.proposicao.titulo}
                    </h3>
                    {(modalData.proposicao as any).url_oficial && (
                      <a
                        href={(modalData.proposicao as any).url_oficial}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1.5 text-xs font-semibold text-cyan-400 hover:text-cyan-300 bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/30 px-2.5 py-1 rounded-lg transition-colors shadow-sm"
                        title="Ler íntegra no site oficial"
                      >
                        <span>Ler na Íntegra (Site Oficial)</span>
                        <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                    )}
                  </div>

                  <p className="text-xs sm:text-sm text-slate-300 leading-relaxed bg-slate-950/60 p-3 rounded-xl border border-slate-800/80 max-h-24 overflow-y-auto">
                    {modalData.proposicao.ementa}
                  </p>

                  <div className="flex flex-wrap items-center justify-between gap-4 pt-1 text-xs text-slate-400">
                    <div>
                      Autor: <span className="text-slate-200 font-bold">{modalData.proposicao.autor_nome || "Parlamentar"}</span>
                    </div>
                    {modalData.sessao && (
                      <div>
                        Sessão: <span className="text-slate-200 font-medium">{modalData.sessao.data_hora.slice(0, 10)}</span>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <p className="text-sm text-slate-400">Dados da matéria indisponíveis.</p>
              )}
            </div>

            {/* CORPO DO MODAL */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {isLoadingModal ? (
                <div className="p-16 text-center text-slate-400 space-y-3">
                  <div className="w-10 h-10 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto" />
                  <p className="text-sm">Buscando votos nominais de cada parlamentar...</p>
                </div>
              ) : !modalData || (modalData.placar.total === 0 && modalData.votos_sim.length === 0 && modalData.votos_nao.length === 0) ? (
                <div className="p-12 text-center text-slate-400 space-y-3 bg-slate-950/50 rounded-2xl border border-slate-800">
                  <Vote className="w-10 h-10 text-slate-600 mx-auto" />
                  <h4 className="text-base font-bold text-slate-200">Sem Votação Nominal em Plenário</h4>
                  <p className="text-xs text-slate-400 max-w-md mx-auto">
                    Esta matéria tramita nas comissões temáticas da Câmara dos Deputados e ainda não foi submetida a escrutínio nominal com registro individual de votos no plenário.
                  </p>
                </div>
              ) : (
                <>
                  {/* BARRA DO PLACAR CONSOLIDADO */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <div className="bg-emerald-950/30 border border-emerald-500/30 rounded-2xl p-4 text-center">
                      <span className="text-2xl sm:text-3xl font-black text-emerald-400 block">
                        {modalData.placar.sim}
                      </span>
                      <span className="text-xs font-bold text-emerald-300 uppercase tracking-wider flex items-center justify-center gap-1 mt-1">
                        <Check className="w-3.5 h-3.5" />
                        Votos SIM (A Favor)
                      </span>
                    </div>

                    <div className="bg-rose-950/30 border border-rose-500/30 rounded-2xl p-4 text-center">
                      <span className="text-2xl sm:text-3xl font-black text-rose-400 block">
                        {modalData.placar.nao}
                      </span>
                      <span className="text-xs font-bold text-rose-300 uppercase tracking-wider flex items-center justify-center gap-1 mt-1">
                        <Ban className="w-3.5 h-3.5" />
                        Votos NÃO (Contra)
                      </span>
                    </div>

                    <div className="bg-slate-950/60 border border-slate-800 rounded-2xl p-4 text-center">
                      <span className="text-2xl sm:text-3xl font-black text-slate-300 block">
                        {modalData.placar.abstencao}
                      </span>
                      <span className="text-xs font-bold text-slate-400 uppercase tracking-wider block mt-1">
                        Abstenções
                      </span>
                    </div>

                    <div className="bg-slate-950/60 border border-slate-800 rounded-2xl p-4 text-center">
                      <span className="text-2xl sm:text-3xl font-black text-indigo-400 block">
                        {modalData.placar.total}
                      </span>
                      <span className="text-xs font-bold text-slate-400 uppercase tracking-wider block mt-1">
                        Total de Votos
                      </span>
                    </div>
                  </div>

                  {/* BARRA DE PROPORÇÃO VISUAL */}
                  <div className="w-full bg-slate-950 h-3 rounded-full overflow-hidden flex border border-slate-800">
                    <div
                      className="bg-emerald-500 h-full transition-all duration-700"
                      style={{
                        width: `${(modalData.placar.sim / Math.max(1, modalData.placar.total)) * 100}%`,
                      }}
                      title={`Sim: ${modalData.placar.sim}`}
                    />
                    <div
                      className="bg-rose-500 h-full transition-all duration-700"
                      style={{
                        width: `${(modalData.placar.nao / Math.max(1, modalData.placar.total)) * 100}%`,
                      }}
                      title={`Não: ${modalData.placar.nao}`}
                    />
                  </div>

                  {/* CAMPO DE BUSCA INTERNO NO MODAL */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div className="relative flex-1">
                      <Search className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
                      <input
                        type="text"
                        placeholder="Buscar parlamentar por nome, partido ou UF nesta votação..."
                        value={modalSearch}
                        onChange={(e) => setModalSearch(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                      />
                      {modalSearch && (
                        <button
                          onClick={() => setModalSearch("")}
                          className="absolute right-2.5 top-2.5 text-slate-500 hover:text-slate-300"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>

                    {/* SELETOR DE ABA (LADO A LADO / APENAS SIM / APENAS NÃO) */}
                    <div className="inline-flex rounded-xl bg-slate-950 p-1 border border-slate-800 text-xs">
                      <button
                        onClick={() => setActiveModalTab("lado_a_lado")}
                        className={`px-3 py-1.5 rounded-lg font-bold transition-colors ${
                          activeModalTab === "lado_a_lado"
                            ? "bg-slate-800 text-white"
                            : "text-slate-400 hover:text-slate-200"
                        }`}
                      >
                        Lado a Lado
                      </button>
                      <button
                        onClick={() => setActiveModalTab("sim")}
                        className={`px-3 py-1.5 rounded-lg font-bold transition-colors ${
                          activeModalTab === "sim"
                            ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                            : "text-slate-400 hover:text-emerald-400"
                        }`}
                      >
                        Apenas SIM ({filteredVotosSim.length})
                      </button>
                      <button
                        onClick={() => setActiveModalTab("nao")}
                        className={`px-3 py-1.5 rounded-lg font-bold transition-colors ${
                          activeModalTab === "nao"
                            ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                            : "text-slate-400 hover:text-rose-400"
                        }`}
                      >
                        Apenas NÃO ({filteredVotosNao.length})
                      </button>
                    </div>
                  </div>

                  {/* DUAS COLUNAS CLARAS: QUEM VOTOU SIM (A FAVOR) VS QUEM VOTOU NÃO (CONTRA) */}
                  <div
                    className={`grid gap-6 ${
                      activeModalTab === "lado_a_lado"
                        ? "grid-cols-1 md:grid-cols-2"
                        : "grid-cols-1"
                    }`}
                  >
                    {/* COLUNA 1: QUEM VOTOU SIM */}
                    {(activeModalTab === "lado_a_lado" || activeModalTab === "sim") && (
                      <div className="bg-emerald-950/15 border border-emerald-500/30 rounded-2xl p-4 space-y-3">
                        <div className="flex items-center justify-between border-b border-emerald-500/20 pb-2">
                          <h4 className="text-sm font-black text-emerald-400 flex items-center gap-2">
                            <Check className="w-4 h-4" />
                            Quem votou SIM (A Favor)
                          </h4>
                          <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                            {filteredVotosSim.length} parlamentares
                          </span>
                        </div>

                        {filteredVotosSim.length === 0 ? (
                          <p className="text-xs text-slate-500 italic py-4 text-center">
                            Nenhum voto SIM encontrado para a busca.
                          </p>
                        ) : (
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 max-h-96 overflow-y-auto pr-1">
                            {filteredVotosSim.map((parl) => (
                              <div
                                key={parl.politico_id}
                                className="bg-slate-900/90 border border-emerald-500/20 rounded-xl p-2.5 flex items-center gap-3 hover:border-emerald-500/40 transition-colors"
                              >
                                {parl.foto_url ? (
                                  // eslint-disable-next-line @next/next/no-img-element
                                  <img
                                    src={parl.foto_url}
                                    alt={parl.nome_eleitoral}
                                    className="w-10 h-10 rounded-lg object-cover border border-slate-700 shrink-0"
                                    onError={(e) => {
                                      (e.target as HTMLElement).style.display = "none";
                                    }}
                                  />
                                ) : (
                                  <div className="w-10 h-10 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-xs font-bold text-slate-400 shrink-0">
                                    {parl.nome_eleitoral.slice(0, 2).toUpperCase()}
                                  </div>
                                )}
                                <div className="min-w-0">
                                  <span
                                    onClick={() => {
                                      if (parl.politico_id && onSelectPolitician) {
                                        setSelectedPropId(null);
                                        onSelectPolitician(parl.politico_id);
                                      }
                                    }}
                                    className={`font-bold text-white text-xs block truncate ${
                                      parl.politico_id && onSelectPolitician ? "cursor-pointer hover:text-cyan-300 transition-colors" : ""
                                    }`}
                                    title={parl.nome_eleitoral}
                                  >
                                    {parl.nome_eleitoral}
                                  </span>
                                  <div className="flex items-center gap-1.5 mt-0.5">
                                    <span
                                      onClick={(e) => {
                                        if (parl.partido_sigla && onSelectParty) {
                                          e.stopPropagation();
                                          setSelectedPropId(null);
                                          onSelectParty(parl.partido_sigla);
                                        }
                                      }}
                                      className={`text-[10px] font-semibold px-1.5 py-0.2 rounded bg-slate-800 text-emerald-400 border border-emerald-500/20 ${
                                        onSelectParty ? "cursor-pointer hover:border-cyan-400 hover:text-cyan-300 transition-colors" : ""
                                      }`}
                                      title={onSelectParty ? `Ver bancada do ${parl.partido_sigla}` : undefined}
                                    >
                                      {parl.partido_sigla}
                                    </span>
                                    <span className="text-[10px] text-slate-400">{parl.uf}</span>
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    {/* COLUNA 2: QUEM VOTOU NÃO */}
                    {(activeModalTab === "lado_a_lado" || activeModalTab === "nao") && (
                      <div className="bg-rose-950/15 border border-rose-500/30 rounded-2xl p-4 space-y-3">
                        <div className="flex items-center justify-between border-b border-rose-500/20 pb-2">
                          <h4 className="text-sm font-black text-rose-400 flex items-center gap-2">
                            <Ban className="w-4 h-4" />
                            Quem votou NÃO (Contra)
                          </h4>
                          <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/30">
                            {filteredVotosNao.length} parlamentares
                          </span>
                        </div>

                        {filteredVotosNao.length === 0 ? (
                          <p className="text-xs text-slate-500 italic py-4 text-center">
                            Nenhum voto NÃO encontrado para a busca.
                          </p>
                        ) : (
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 max-h-96 overflow-y-auto pr-1">
                            {filteredVotosNao.map((parl) => (
                              <div
                                key={parl.politico_id}
                                className="bg-slate-900/90 border border-rose-500/20 rounded-xl p-2.5 flex items-center gap-3 hover:border-rose-500/40 transition-colors"
                              >
                                {parl.foto_url ? (
                                  // eslint-disable-next-line @next/next/no-img-element
                                  <img
                                    src={parl.foto_url}
                                    alt={parl.nome_eleitoral}
                                    className="w-10 h-10 rounded-lg object-cover border border-slate-700 shrink-0"
                                    onError={(e) => {
                                      (e.target as HTMLElement).style.display = "none";
                                    }}
                                  />
                                ) : (
                                  <div className="w-10 h-10 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-xs font-bold text-slate-400 shrink-0">
                                    {parl.nome_eleitoral.slice(0, 2).toUpperCase()}
                                  </div>
                                )}
                                <div className="min-w-0">
                                  <span
                                    onClick={() => {
                                      if (parl.politico_id && onSelectPolitician) {
                                        setSelectedPropId(null);
                                        onSelectPolitician(parl.politico_id);
                                      }
                                    }}
                                    className={`font-bold text-white text-xs block truncate ${
                                      parl.politico_id && onSelectPolitician ? "cursor-pointer hover:text-cyan-300 transition-colors" : ""
                                    }`}
                                    title={parl.nome_eleitoral}
                                  >
                                    {parl.nome_eleitoral}
                                  </span>
                                  <div className="flex items-center gap-1.5 mt-0.5">
                                    <span
                                      onClick={(e) => {
                                        if (parl.partido_sigla && onSelectParty) {
                                          e.stopPropagation();
                                          setSelectedPropId(null);
                                          onSelectParty(parl.partido_sigla);
                                        }
                                      }}
                                      className={`text-[10px] font-semibold px-1.5 py-0.2 rounded bg-slate-800 text-rose-400 border border-rose-500/20 ${
                                        onSelectParty ? "cursor-pointer hover:border-cyan-400 hover:text-cyan-300 transition-colors" : ""
                                      }`}
                                      title={onSelectParty ? `Ver bancada do ${parl.partido_sigla}` : undefined}
                                    >
                                      {parl.partido_sigla}
                                    </span>
                                    <span className="text-[10px] text-slate-400">{parl.uf}</span>
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>

            {/* RODAPÉ DO MODAL */}
            <div className="p-4 bg-slate-950 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400">
              <span className="flex items-center gap-1.5">
                <FileText className="w-4 h-4 text-slate-500" />
                Dados oficiais abertos da Câmara dos Deputados e do Senado Federal
              </span>
              <button
                onClick={() => setSelectedPropId(null)}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-semibold transition-colors"
              >
                Fechar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
