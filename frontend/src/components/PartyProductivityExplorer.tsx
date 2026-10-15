"use client";

import React, { useState, useMemo } from "react";
import {
  Search,
  BarChart3,
  TrendingUp,
  ShieldCheck,
  Award,
  Layers,
  Table2,
  ChevronDown,
  ArrowUpDown,
  Users,
  Briefcase,
  Calendar,
  X,
} from "lucide-react";
import { useApi } from "@/hooks/useApi";
import {
  getPartyIPPMRanking,
  getPartyMandateHistory,
} from "@/services/api";
import { ErrorState, EmptyState } from "@/components/StateViews";
import { PartyLogoBadge } from "@/components/PartiesPanel";
import InfoHint from "@/components/InfoHint";
import PartyCompareCharts from "@/components/PartyCompareCharts";
import PartyEvolutionChart from "@/components/PartyEvolutionChart";
import {
  EXPLICACAO_MATRIZ,
  EXPLICACAO_TELAS,
  EXPLICACOES,
  GUIA_MATRIZ,
  evidenciaCoeso,
  evidenciaEficaz,
  evidenciaLider,
  evidenciaMedia,
} from "@/lib/ippmExplicacoes";

interface PartyProductivityExplorerProps {
  onSelectPartyMembers?: (sigla: string) => void;
  onOpenCatalog?: () => void;
}

type SortField =
  | "posicao"
  | "sigla"
  | "cadeiras_dia_equivalentes"
  | "pontuacao_bruta_ialp"
  | "ippm_score_medio"
  | "fidelidade"
  | "eficacia"
  | "relatorias";

const SPECTRUM_BADGE_CONFIG: Record<
  string,
  { label: string; bg: string; text: string; border: string }
> = {
  ESQUERDA: {
    label: "Esquerda",
    bg: "bg-red-500/15",
    text: "text-red-400",
    border: "border-red-500/30",
  },
  CENTRO_ESQUERDA: {
    label: "Centro-Esquerda",
    bg: "bg-rose-500/15",
    text: "text-rose-300",
    border: "border-rose-500/30",
  },
  CENTRO: {
    label: "Centro",
    bg: "bg-amber-500/15",
    text: "text-amber-300",
    border: "border-amber-500/30",
  },
  CENTRO_DIREITA: {
    label: "Centro-Direita",
    bg: "bg-sky-500/15",
    text: "text-sky-300",
    border: "border-sky-500/30",
  },
  DIREITA: {
    label: "Direita",
    bg: "bg-blue-600/15",
    text: "text-blue-400",
    border: "border-blue-600/30",
  },
};

const BLOC_BADGE_CONFIG: Record<
  string,
  { label: string; bg: string; text: string; border: string }
> = {
  BASE_GOVERNO: {
    label: "Base Governista",
    bg: "bg-emerald-500/15",
    text: "text-emerald-300",
    border: "border-emerald-500/30",
  },
  OPOSICAO: {
    label: "Oposição",
    bg: "bg-rose-500/15",
    text: "text-rose-300",
    border: "border-rose-500/30",
  },
  INDEPENDENTE_CENTRO: {
    label: "Independente / Centro",
    bg: "bg-slate-500/15",
    text: "text-slate-300",
    border: "border-slate-500/30",
  },
};

export default function PartyProductivityExplorer({
  onSelectPartyMembers,
  onOpenCatalog,
}: PartyProductivityExplorerProps) {
  // Filtros
  const [selectedAno, setSelectedAno] = useState<number>(2026);
  const [selectedCasa, setSelectedCasa] = useState<string>("ALL");
  const [selectedBloco, setSelectedBloco] = useState<string>("ALL");
  const [selectedEspectro, setSelectedEspectro] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [activeView, setActiveView] = useState<"comparar" | "tabela" | "evolucao">("comparar");
  const [matrizAberta, setMatrizAberta] = useState<boolean>(false);

  // Ordenação
  const [sortField, setSortField] = useState<SortField>("ippm_score_medio");
  const [sortAsc, setSortAsc] = useState<boolean>(false);

  // Modal de Histórico Dinâmico de Mandato
  const [selectedPartyTimeline, setSelectedPartyTimeline] = useState<string | null>(null);

  // Consulta API
  const {
    data: rankingData,
    loading,
    error,
    retry,
  } = useApi(
    `party_ippm_ranking_${selectedAno}_${selectedCasa}_${selectedBloco}_${selectedEspectro}`,
    (signal) =>
      getPartyIPPMRanking(
        {
          ano: selectedAno,
          casa: selectedCasa,
          bloco: selectedBloco,
          espectro: selectedEspectro,
        },
        signal
      )
  );

  // Modal Data
  const {
    data: timelineData,
    loading: timelineLoading,
  } = useApi(
    `party_timeline_${selectedPartyTimeline}`,
    (signal) =>
      selectedPartyTimeline
        ? getPartyMandateHistory(selectedPartyTimeline, signal)
        : Promise.resolve(null),
    Boolean(selectedPartyTimeline)
  );

  const rankingList = rankingData?.ranking;

  // Filtragem de Texto e Ordenação Local
  const filteredAndSortedRanking = useMemo(() => {
    if (!rankingList) return [];
    let list = [...rankingList];

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      list = list.filter(
        (p) =>
          p.sigla.toLowerCase().includes(q) ||
          p.nome_completo.toLowerCase().includes(q)
      );
    }

    list.sort((a, b) => {
      let valA: number | string = 0;
      let valB: number | string = 0;

      switch (sortField) {
        case "posicao":
          valA = a.posicao;
          valB = b.posicao;
          break;
        case "sigla":
          valA = a.sigla;
          valB = b.sigla;
          break;
        case "cadeiras_dia_equivalentes":
          valA = a.cadeiras_dia_equivalentes;
          valB = b.cadeiras_dia_equivalentes;
          break;
        case "pontuacao_bruta_ialp":
          valA = a.pontuacao_bruta_ialp;
          valB = b.pontuacao_bruta_ialp;
          break;
        case "ippm_score_medio":
          valA = a.ippm_score_medio;
          valB = b.ippm_score_medio;
          break;
        case "fidelidade":
          valA = a.pilares.fidelidade_partidaria_pct ?? -1;
          valB = b.pilares.fidelidade_partidaria_pct ?? -1;
          break;
        case "eficacia":
          valA = a.pilares.taxa_eficacia_pct;
          valB = b.pilares.taxa_eficacia_pct;
          break;
        case "relatorias":
          valA = a.pilares.volume_relatorias;
          valB = b.pilares.volume_relatorias;
          break;
        default:
          valA = a.ippm_score_medio;
          valB = b.ippm_score_medio;
      }

      if (valA < valB) return sortAsc ? -1 : 1;
      if (valA > valB) return sortAsc ? 1 : -1;
      return 0;
    });

    return list;
  }, [rankingList, searchQuery, sortField, sortAsc]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(false);
    }
  };

  const maxIppm = useMemo(() => {
    if (!rankingList || rankingList.length === 0) return 1;
    return Math.max(...rankingList.map((p) => p.ippm_score_medio), 1);
  }, [rankingList]);

  return (
    <div className="space-y-8" id="party-productivity-explorer">
      {/* ─── CABEÇALHO HERO COM RESUMO EXECUTIVO ─── */}
      <div className="relative rounded-3xl bg-gradient-to-br from-slate-900/90 via-slate-900/60 to-violet-950/40 border border-slate-800/80 p-6 md:p-8 backdrop-blur-xl shadow-2xl overflow-hidden">
        <div className="absolute top-0 right-0 w-96 h-96 bg-violet-600/10 rounded-full blur-3xl pointer-events-none -mr-20 -mt-20" />
        <div className="relative z-10 flex flex-col lg:flex-row items-start lg:items-center justify-between gap-6">
          <div className="space-y-3 max-w-3xl">
            <h1 className="text-2xl md:text-3xl font-extrabold text-white tracking-tight">
              Raio-X dos Partidos & Índice de Produtividade Partidária Média (IPPM)
            </h1>
            <p className="text-sm text-slate-300 leading-relaxed">
              Metodologia ponderada que calcula a produção legislativa agregada (IALP) dividida pelo tamanho
              equivalente de <strong>Cadeiras-Dia ativas em exercício</strong>. Isola o peso de ministros licenciados e
              suplentes temporários, superando vantagens puramente numéricas de bancada para avaliar a eficiência real de cada legenda.
            </p>
          </div>

          {/* Botão de Alternância de Visão e Catálogo */}
          <div className="flex flex-wrap items-center gap-2 self-stretch lg:self-auto justify-end">
            {onOpenCatalog && (
              <button
                type="button"
                id="btn-open-catalog"
                onClick={onOpenCatalog}
                className="px-4 py-2 rounded-xl bg-slate-800/80 hover:bg-slate-700/80 text-xs font-semibold text-slate-200 border border-slate-700/80 transition-all shadow-sm"
              >
                Catálogo de Estatutos & Filiados
              </button>
            )}
            <div className="inline-flex p-1 bg-slate-950/80 border border-slate-800 rounded-xl" role="tablist" aria-label="Forma de visualizar">
              {(
                [
                  { id: "comparar", rotulo: EXPLICACAO_TELAS.comparar.nome, Icone: BarChart3 },
                  { id: "tabela", rotulo: EXPLICACAO_TELAS.tabela.nome, Icone: Table2 },
                  { id: "evolucao", rotulo: EXPLICACAO_TELAS.evolucao.nome, Icone: TrendingUp },
                ] as const
              ).map(({ id, rotulo, Icone }) => (
                <button
                  key={id}
                  type="button"
                  role="tab"
                  id={`tab-view-${id}`}
                  aria-selected={activeView === id}
                  onClick={() => setActiveView(id)}
                  className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all ${
                    activeView === id ? "bg-violet-600 text-white shadow-sm" : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <Icone className="w-3.5 h-3.5" aria-hidden="true" />
                  <span>{rotulo}</span>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Explicação, em linguagem simples, do que cada visão mostra */}
        <div
          className="mt-4 flex items-start gap-2 rounded-xl border border-slate-800/80 bg-slate-950/50 px-3.5 py-2.5 text-xs text-slate-300 leading-relaxed"
          id="explicacao-visao-atual"
        >
          <InfoHint
            explicacao={{
              titulo: "Como ler esta tela",
              oQueE:
                "A tela mostra o mesmo resultado de três jeitos. Comece por Comparar, que é o mais simples; use a Tabela quando quiser os números exatos e a Evolução para ver a tendência ao longo dos anos. Mais abaixo na página há ainda a Matriz de Eficiência, para quem quer cruzar volume de projetos com aprovação.",
              comoCalcula: [
                `${EXPLICACAO_TELAS.comparar.nome}: ${EXPLICACAO_TELAS.comparar.resumo}`,
                `${EXPLICACAO_TELAS.tabela.nome}: ${EXPLICACAO_TELAS.tabela.resumo}`,
                `${EXPLICACAO_TELAS.evolucao.nome}: ${EXPLICACAO_TELAS.evolucao.resumo}`,
                `${EXPLICACAO_MATRIZ.nome}: ${EXPLICACAO_MATRIZ.resumo} As linhas tracejadas marcam o valor do meio (a mediana) entre os partidos e criam 4 grupos: ` +
                  GUIA_MATRIZ.map((g) => `${g.nome} (${g.posicao.toLowerCase()})`).join("; ") +
                  ".",
              ],
              cuidado:
                "Os números comparam os partidos entre si e medem volume e andamento dos projetos, não se o trabalho foi bom ou ruim para a população.",
            }}
          />
          <p>
            <strong className="text-slate-100">{EXPLICACAO_TELAS[activeView].nome}:</strong>{" "}
            {EXPLICACAO_TELAS[activeView].resumo}
          </p>
        </div>

        {/* ─── CARDS DE INDICADORES DESTAQUE ─── */}
        {rankingData?.resumo_geral && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6 pt-6 border-t border-slate-800/60">
            {/* Média Nacional IPPM */}
            <div className="bg-slate-950/50 border border-slate-800/80 rounded-2xl p-4 flex flex-col justify-between">
              <div className="flex items-center justify-between text-slate-400 text-xs">
                <span className="inline-flex items-center gap-1.5">
                  Média IPPM Geral
                  <InfoHint
                    explicacao={EXPLICACOES.media}
                    resultado={`${rankingData.resumo_geral.media_ippm_geral.toFixed(2)} pontos por cadeira-dia`}
                    evidencia={evidenciaMedia(rankingData.ranking, rankingData.resumo_geral.media_ippm_geral)}
                  />
                </span>
                <TrendingUp className="w-4 h-4 text-violet-400" aria-hidden="true" />
              </div>
              <div className="mt-2">
                <span className="text-2xl font-black text-white">
                  {rankingData.resumo_geral.media_ippm_geral.toFixed(2)}
                </span>
                <span className="text-[11px] text-slate-400 block">pontos / cadeira-dia</span>
              </div>
            </div>

            {/* Partido Mais Produtivo */}
            <div className="bg-slate-950/50 border border-slate-800/80 rounded-2xl p-4 flex flex-col justify-between">
              <div className="flex items-center justify-between text-slate-400 text-xs">
                <span className="inline-flex items-center gap-1.5">
                  Líder em Produtividade
                  <InfoHint
                    explicacao={EXPLICACOES.lider}
                    resultado={rankingData.resumo_geral.partido_mais_produtivo?.sigla ?? "sem líder neste período"}
                    evidencia={evidenciaLider(rankingData.ranking, rankingData.resumo_geral.partido_mais_produtivo?.sigla)}
                  />
                </span>
                <Award className="w-4 h-4 text-amber-400" aria-hidden="true" />
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                <span
                  className="text-2xl font-black"
                  style={{ color: rankingData.resumo_geral.partido_mais_produtivo?.cor_hex || "#38bdf8" }}
                >
                  {rankingData.resumo_geral.partido_mais_produtivo?.sigla || "—"}
                </span>
                <span className="text-xs font-bold text-slate-300">
                  {rankingData.resumo_geral.partido_mais_produtivo?.ippm_score?.toFixed(2)} IPPM
                </span>
              </div>
            </div>

            {/* Maior Eficácia Legislativa */}
            <div className="bg-slate-950/50 border border-slate-800/80 rounded-2xl p-4 flex flex-col justify-between">
              <div className="flex items-center justify-between text-slate-400 text-xs">
                <span className="inline-flex items-center gap-1.5">
                  Maior Eficácia Real
                  <InfoHint
                    explicacao={EXPLICACOES.eficaz}
                    resultado={rankingData.resumo_geral.partido_mais_eficaz?.sigla ?? "nenhum projeto aprovado neste período"}
                    evidencia={evidenciaEficaz(rankingData.ranking, rankingData.resumo_geral.partido_mais_eficaz?.sigla)}
                  />
                </span>
                <Briefcase className="w-4 h-4 text-emerald-400" aria-hidden="true" />
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                <span
                  className="text-2xl font-black"
                  style={{
                    color:
                      rankingData.resumo_geral.partido_mais_eficaz &&
                      (rankingData.resumo_geral.partido_mais_eficaz.taxa_eficacia ?? 0) > 0
                        ? rankingData.resumo_geral.partido_mais_eficaz.cor_hex || "#10b981"
                        : "#94a3b8",
                  }}
                >
                  {rankingData.resumo_geral.partido_mais_eficaz &&
                  (rankingData.resumo_geral.partido_mais_eficaz.taxa_eficacia ?? 0) > 0
                    ? rankingData.resumo_geral.partido_mais_eficaz.sigla
                    : "—"}
                </span>
                <span className="text-xs font-medium text-slate-400">
                  {rankingData.resumo_geral.partido_mais_eficaz &&
                  (rankingData.resumo_geral.partido_mais_eficaz.taxa_eficacia ?? 0) > 0
                    ? `${(rankingData.resumo_geral.partido_mais_eficaz.taxa_eficacia ?? 0).toFixed(1)}% aprovados`
                    : "Sem matérias aprovadas"}
                </span>
              </div>
            </div>

            {/* Maior Fidelidade Partidária */}
            <div className="bg-slate-950/50 border border-slate-800/80 rounded-2xl p-4 flex flex-col justify-between">
              <div className="flex items-center justify-between text-slate-400 text-xs">
                <span className="inline-flex items-center gap-1.5">
                  Maior Coesão de Bancada
                  <InfoHint
                    explicacao={EXPLICACOES.coeso}
                    resultado={rankingData.resumo_geral.partido_mais_coeso?.sigla ?? "sem votações com orientação neste período"}
                    evidencia={evidenciaCoeso(rankingData.ranking, rankingData.resumo_geral.partido_mais_coeso?.sigla)}
                  />
                </span>
                <ShieldCheck className="w-4 h-4 text-cyan-400" aria-hidden="true" />
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                <span
                  className="text-2xl font-black"
                  style={{ color: rankingData.resumo_geral.partido_mais_coeso?.cor_hex || "#06b6d4" }}
                >
                  {rankingData.resumo_geral.partido_mais_coeso?.sigla || "—"}
                </span>
                <span className="text-xs font-medium text-slate-300">
                  {rankingData.resumo_geral.partido_mais_coeso?.fidelidade_pct != null
                    ? `${(rankingData.resumo_geral.partido_mais_coeso.fidelidade_pct ?? 0).toFixed(1)}% alinhados`
                    : "—"}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ─── BARRA DE FILTROS E CONTROLES ─── */}
      <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-4 md:p-5 backdrop-blur-md space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          {/* Campo de Busca */}
          <div className="relative flex-1 min-w-[240px] max-w-md">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" aria-hidden="true" />
            <input
              type="text"
              id="input-party-search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Buscar legenda por sigla ou nome oficial..."
              className="w-full pl-10 pr-4 py-2 bg-slate-950/80 border border-slate-800 rounded-xl text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-violet-500/60 focus:ring-1 focus:ring-violet-500/30 transition-all"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery("")}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
                aria-label="Limpar busca"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {/* Filtros em Linha */}
          <div className="flex flex-wrap items-center gap-3">
            {/* Seletor de Casa */}
            <div className="flex items-center gap-1.5 bg-slate-950/80 border border-slate-800 rounded-xl px-2.5 py-1 text-xs">
              <span className="text-slate-500 font-semibold text-[11px]">Casa:</span>
              <select
                id="select-casa-filter"
                value={selectedCasa}
                onChange={(e) => setSelectedCasa(e.target.value)}
                className="bg-transparent text-slate-200 font-semibold focus:outline-none cursor-pointer"
              >
                <option value="ALL" className="bg-slate-900">Congresso Nacional</option>
                <option value="CAMARA" className="bg-slate-900">Câmara dos Deputados</option>
                <option value="SENADO" className="bg-slate-900">Senado Federal</option>
              </select>
            </div>

            {/* Filtro de Bloco Político */}
            <div className="flex items-center gap-1.5 bg-slate-950/80 border border-slate-800 rounded-xl px-2.5 py-1 text-xs">
              <span className="text-slate-500 font-semibold text-[11px]">Bloco:</span>
              <select
                id="select-bloco-filter"
                value={selectedBloco}
                onChange={(e) => setSelectedBloco(e.target.value)}
                className="bg-transparent text-slate-200 font-semibold focus:outline-none cursor-pointer"
              >
                <option value="ALL" className="bg-slate-900">Todos os Blocos</option>
                <option value="GOVERNO" className="bg-slate-900">Base Governista</option>
                <option value="OPOSICAO" className="bg-slate-900">Oposição</option>
                <option value="INDEPENDENTE" className="bg-slate-900">Centro & Independentes</option>
              </select>
            </div>

            {/* Filtro de Espectro Político */}
            <div className="flex items-center gap-1.5 bg-slate-950/80 border border-slate-800 rounded-xl px-2.5 py-1 text-xs">
              <span className="text-slate-500 font-semibold text-[11px]">Espectro:</span>
              <select
                id="select-espectro-filter"
                value={selectedEspectro}
                onChange={(e) => setSelectedEspectro(e.target.value)}
                className="bg-transparent text-slate-200 font-semibold focus:outline-none cursor-pointer"
              >
                <option value="ALL" className="bg-slate-900">Todos os Espectros</option>
                <option value="ESQUERDA" className="bg-slate-900">Esquerda</option>
                <option value="CENTRO" className="bg-slate-900">Centro</option>
                <option value="DIREITA" className="bg-slate-900">Direita</option>
              </select>
            </div>

            {/* Seletor de Ano */}
            <div className="flex items-center gap-1.5 bg-slate-950/80 border border-slate-800 rounded-xl px-2.5 py-1 text-xs">
              <Calendar className="w-3.5 h-3.5 text-slate-500" aria-hidden="true" />
              <select
                id="select-ano-filter"
                value={selectedAno}
                onChange={(e) => setSelectedAno(Number(e.target.value))}
                className="bg-transparent text-slate-200 font-semibold focus:outline-none cursor-pointer"
              >
                <option value={2026} className="bg-slate-900">2026 (Atual)</option>
                <option value={2025} className="bg-slate-900">2025</option>
                <option value={2024} className="bg-slate-900">2024</option>
                <option value={2023} className="bg-slate-900">2023</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* ─── ESTADOS DE CARREGAMENTO E ERRO ─── */}
      {loading && activeView !== "evolucao" && (
        <div className="py-20 flex flex-col items-center justify-center space-y-4">
          <div className="w-10 h-10 border-4 border-violet-500/20 border-t-violet-500 rounded-full animate-spin" />
          <p className="text-sm font-semibold text-slate-400 animate-pulse">
            Calculando índices de produtividade partidária e cadeiras-dia...
          </p>
        </div>
      )}

      {error && !loading && activeView !== "evolucao" && (
        <ErrorState
          title="Erro ao carregar ranking partidário"
          message={error.message || "Não foi possível consolidar os índices das bancadas."}
          onRetry={retry}
        />
      )}

      {/* ─── CONTEÚDO PRINCIPAL: TABELA DE RANKING GERAL ─── */}
      {!loading && !error && activeView === "comparar" && (
        <div className="space-y-4">
          {rankingData?.periodo?.aviso && (
            <div role="status" className="rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-xs text-amber-200">
              {rankingData.periodo.aviso}
            </div>
          )}
          {filteredAndSortedRanking.length === 0 ? (
            <EmptyState
              title="Nenhum partido localizado"
              message="Nenhuma bancada atende aos filtros de casa, bloco ou busca informados."
            />
          ) : (
            <PartyCompareCharts ranking={filteredAndSortedRanking} onSelectParty={setSelectedPartyTimeline} />
          )}
        </div>
      )}

      {activeView === "evolucao" && <PartyEvolutionChart casa={selectedCasa} />}

      {!loading && !error && activeView === "tabela" && (
        <div className="space-y-4">
          {rankingData?.periodo?.aviso && (
            <div
              role="status"
              className="rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-xs text-amber-200"
            >
              {rankingData.periodo.aviso}
            </div>
          )}
          {filteredAndSortedRanking.length === 0 ? (
            <EmptyState
              title="Nenhum partido localizado"
              message="Nenhuma bancada atende aos filtros de casa, bloco ou busca informados."
            />
          ) : (
            <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl overflow-hidden shadow-xl backdrop-blur-md">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs" id="table-party-ranking">
                  <thead className="bg-slate-950/80 text-slate-400 font-bold uppercase tracking-wider text-[10px] border-b border-slate-800">
                    <tr>
                      <th className="py-3.5 px-3 text-center w-12 cursor-pointer hover:text-white" onClick={() => handleSort("posicao")}>
                        <div className="flex items-center justify-center gap-1">
                          <span>#</span>
                          <ArrowUpDown className="w-3 h-3" />
                        </div>
                      </th>
                      <th className="py-3.5 px-4 cursor-pointer hover:text-white" onClick={() => handleSort("sigla")}>
                        <div className="flex items-center gap-1">
                          <span>Partido & Espectro</span>
                          <ArrowUpDown className="w-3 h-3" />
                        </div>
                      </th>
                      <th className="py-3.5 px-3 text-right cursor-pointer hover:text-white" onClick={() => handleSort("cadeiras_dia_equivalentes")} title="Cadeiras-Dia equivalentes em exercício (divisor dinâmico)">
                        <div className="flex items-center justify-end gap-1">
                          <span>Bancada (C-Dia)</span>
                          <ArrowUpDown className="w-3 h-3" />
                        </div>
                      </th>
                      <th className="py-3.5 px-3 text-right cursor-pointer hover:text-white" onClick={() => handleSort("pontuacao_bruta_ialp")} title="Soma total do IALP de todos os membros do partido">
                        <div className="flex items-center justify-end gap-1">
                          <span>IALP Bruto</span>
                          <ArrowUpDown className="w-3 h-3" />
                        </div>
                      </th>
                      <th className="py-3.5 px-4 text-right cursor-pointer hover:text-white min-w-[140px]" onClick={() => handleSort("ippm_score_medio")} title="Score médio por parlamentar ativo (IPPM = IALP / Cadeiras-Dia)">
                        <div className="flex items-center justify-end gap-1 text-violet-300">
                          <span>IPPM Médio</span>
                          <ArrowUpDown className="w-3 h-3" />
                        </div>
                      </th>
                      <th className="py-3.5 px-3 text-right cursor-pointer hover:text-white" onClick={() => handleSort("fidelidade")} title="Percentual de votos nominais alinhados com o líder da bancada">
                        <div className="flex items-center justify-end gap-1">
                          <span>Coesão</span>
                          <ArrowUpDown className="w-3 h-3" />
                        </div>
                      </th>
                      <th className="py-3.5 px-3 text-right cursor-pointer hover:text-white" onClick={() => handleSort("eficacia")} title="Taxa de aprovação de proposições apresentadas">
                        <div className="flex items-center justify-end gap-1">
                          <span>Eficácia</span>
                          <ArrowUpDown className="w-3 h-3" />
                        </div>
                      </th>
                      <th className="py-3.5 px-3 text-right cursor-pointer hover:text-white" onClick={() => handleSort("relatorias")} title="Volume ponderado de relatorias de matérias complexas">
                        <div className="flex items-center justify-end gap-1">
                          <span>Relatorias</span>
                          <ArrowUpDown className="w-3 h-3" />
                        </div>
                      </th>
                      <th className="py-3.5 px-4 text-center">Diagnóstico / Ações</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {filteredAndSortedRanking.map((p) => {
                      const spectrumStyle =
                        SPECTRUM_BADGE_CONFIG[p.espectro_politico] || {
                          label: p.espectro_politico,
                          bg: "bg-slate-500/15",
                          text: "text-slate-400",
                          border: "border-slate-500/30",
                        };

                      const blocStyle =
                        BLOC_BADGE_CONFIG[p.bloco_politico] || {
                          label: p.bloco_politico,
                          bg: "bg-slate-500/15",
                          text: "text-slate-400",
                          border: "border-slate-500/30",
                        };

                      const ippmBarWidth = Math.min(100, Math.round((p.ippm_score_medio / maxIppm) * 100));

                      return (
                        <tr
                          key={p.partido_id}
                          className="hover:bg-slate-800/40 transition-colors group"
                        >
                          {/* Posição */}
                          <td className="py-3 px-3 text-center font-bold text-slate-400">
                            {p.posicao <= 3 ? (
                              <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-violet-500/20 text-violet-300 font-extrabold text-[11px] border border-violet-500/30">
                                {p.posicao}
                              </span>
                            ) : (
                              <span>{p.posicao}</span>
                            )}
                          </td>

                          {/* Partido e Badges */}
                          <td className="py-3 px-4">
                            <div className="flex items-center gap-3">
                              <PartyLogoBadge
                                sigla={p.sigla}
                                logoUrl={p.logo_url}
                                corHex={p.cor_hex}
                                size="sm"
                              />
                              <div className="space-y-1">
                                <div className="flex items-center gap-2">
                                  <span className="font-extrabold text-sm text-white group-hover:text-violet-300 transition-colors">
                                    {p.sigla}
                                  </span>
                                  {p.numero_eleitoral && (
                                    <span className="text-[10px] text-slate-500 font-mono">
                                      #{p.numero_eleitoral}
                                    </span>
                                  )}
                                </div>
                                <span className="text-[11px] text-slate-400 block truncate max-w-[180px]">
                                  {p.nome_completo}
                                </span>
                                <div className="flex flex-wrap items-center gap-1.5">
                                  <span
                                    className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border ${spectrumStyle.bg} ${spectrumStyle.text} ${spectrumStyle.border}`}
                                  >
                                    {spectrumStyle.label}
                                  </span>
                                  <span
                                    className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border ${blocStyle.bg} ${blocStyle.text} ${blocStyle.border}`}
                                  >
                                    {blocStyle.label}
                                  </span>
                                </div>
                              </div>
                            </div>
                          </td>

                          {/* Bancada / Cadeiras-Dia */}
                          <td className="py-3 px-3 text-right">
                            <span className="font-bold text-slate-200">
                              {p.cadeiras_dia_equivalentes.toFixed(1)}
                            </span>
                            <span className="text-[10px] text-slate-500 block">
                              {p.total_cadeiras_ativas} eleitos
                            </span>
                          </td>

                          {/* IALP Bruto */}
                          <td className="py-3 px-3 text-right font-mono font-semibold text-slate-300">
                            {p.pontuacao_bruta_ialp.toFixed(1)}
                          </td>

                          {/* IPPM Médio com Barra */}
                          <td className="py-3 px-4 text-right">
                            <div className="space-y-1">
                              <span className="text-sm font-black text-violet-300 font-mono">
                                {p.ippm_score_medio.toFixed(2)}
                              </span>
                              <div className="w-full bg-slate-950 rounded-full h-1.5 overflow-hidden">
                                <div
                                  className="h-full rounded-full bg-gradient-to-r from-violet-600 to-cyan-400 transition-all duration-500"
                                  style={{ width: `${ippmBarWidth}%` }}
                                />
                              </div>
                            </div>
                          </td>

                          {/* Fidelidade Partidária (Coesão) */}
                          <td className="py-3 px-3 text-right">
                            <span
                              className={`font-bold font-mono ${
                                p.pilares.fidelidade_partidaria_pct == null
                                  ? "text-slate-500"
                                  : p.pilares.fidelidade_partidaria_pct >= 85
                                  ? "text-emerald-400"
                                  : p.pilares.fidelidade_partidaria_pct >= 75
                                  ? "text-amber-400"
                                  : "text-rose-400"
                              }`}
                            >
                              {p.pilares.fidelidade_partidaria_pct == null ? "—" : `${p.pilares.fidelidade_partidaria_pct.toFixed(1)}%`}
                            </span>
                          </td>

                          {/* Taxa de Eficácia */}
                          <td className="py-3 px-3 text-right">
                            <span className="font-bold font-mono text-slate-200">
                              {p.pilares.taxa_eficacia_pct.toFixed(1)}%
                            </span>
                            <span className="text-[10px] text-slate-500 block">
                              {p.projetos_aprovados}/{p.projetos_apresentados}
                            </span>
                          </td>

                          {/* Volume de Relatorias */}
                          <td className="py-3 px-3 text-right">
                            <span className="font-semibold text-slate-300 font-mono">
                              {p.pilares.volume_relatorias.toFixed(1)}
                            </span>
                            <span className="text-[10px] text-slate-500 block">
                              {p.pilares.total_relatorias} relatórios
                            </span>
                          </td>

                          {/* Diagnóstico e Ação de Linha do Tempo */}
                          <td className="py-3 px-4 text-center">
                            <div className="flex flex-col items-center gap-1.5">
                              <span
                                className="text-[10px] font-bold px-2 py-0.5 rounded-lg border max-w-[130px] truncate"
                                style={{
                                  backgroundColor: `${p.cor_hex}15`,
                                  borderColor: `${p.cor_hex}30`,
                                  color: p.cor_hex,
                                }}
                                title={p.quadrante_eficiencia.descricao}
                              >
                                {p.quadrante_eficiencia.titulo.split(" ")[0]} {p.quadrante_eficiencia.titulo.split(" ")[1] || ""}
                              </span>
                              <div className="flex items-center gap-2">
                                <button
                                  type="button"
                                  onClick={() => setSelectedPartyTimeline(p.sigla)}
                                  className="text-[10px] font-semibold text-violet-400 hover:text-violet-300 underline underline-offset-2 transition-colors"
                                  title="Ver Linha do Tempo de Mandatos e Licenças"
                                >
                                  Licenças / Suplentes
                                </button>
                                {onSelectPartyMembers && (
                                  <button
                                    type="button"
                                    onClick={() => onSelectPartyMembers(p.sigla)}
                                    className="text-[10px] font-semibold text-cyan-400 hover:text-cyan-300 underline underline-offset-2 transition-colors"
                                    title="Ver Parlamentares do Partido"
                                  >
                                    Membros
                                  </button>
                                )}
                              </div>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ─── MATRIZ DE EFICIÊNCIA: ÚLTIMA PARTE DA PÁGINA, RECOLHÍVEL ─── */}
      {!loading && !error && filteredAndSortedRanking.length > 0 && (
        <section className="border-t border-slate-800/80 pt-6 space-y-4" id="matriz-eficiencia-secao">
          <button
            type="button"
            id="toggle-matriz"
            aria-expanded={matrizAberta}
            aria-controls="quadrant-efficiency-view"
            onClick={() => setMatrizAberta(!matrizAberta)}
            className="w-full flex items-center justify-between gap-3 rounded-2xl bg-slate-900/60 border border-slate-800/80 px-5 py-4 text-left hover:border-violet-500/40 transition-colors"
          >
            <span className="space-y-0.5">
              <span className="flex items-center gap-2 text-sm font-bold text-white">
                <Layers className="w-4 h-4 text-violet-400" aria-hidden="true" />
                {EXPLICACAO_MATRIZ.nome}
                <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">análise avançada</span>
              </span>
              <span className="block text-xs text-slate-400">{EXPLICACAO_MATRIZ.resumo}</span>
            </span>
            <ChevronDown
              className={`w-5 h-5 text-slate-400 shrink-0 transition-transform ${matrizAberta ? "rotate-180" : ""}`}
              aria-hidden="true"
            />
          </button>
          {matrizAberta && (
        <div className="space-y-6" id="quadrant-efficiency-view">
          {/* Guia Metodológico dos Quadrantes */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-emerald-950/20 border border-emerald-500/30 rounded-2xl p-4 space-y-1.5">
              <span className="text-[10px] font-extrabold uppercase tracking-wider text-emerald-400">
                Quadrante Superior Esquerdo
              </span>
              <p className="text-xs font-bold text-emerald-200">Poucos projetos e boa aprovação</p>
              <h3 className="text-sm font-bold text-white">Técnicos & Articuladores</h3>
              <p className="text-xs text-slate-300 leading-relaxed">
                Produção altamente focada e seletiva. Apresentam menos projetos, mas convertem proporção expressiva em leis aprovadas.
              </p>
            </div>

            <div className="bg-cyan-950/20 border border-cyan-500/30 rounded-2xl p-4 space-y-1.5">
              <span className="text-[10px] font-extrabold uppercase tracking-wider text-cyan-400">
                Quadrante Superior Direito
              </span>
              <p className="text-xs font-bold text-cyan-200">Muitos projetos e boa aprovação</p>
              <h3 className="text-sm font-bold text-white">Liderança de Bancada</h3>
              <p className="text-xs text-slate-300 leading-relaxed">
                Alta capacidade legislativa em massa combinada com força de aprovação e trânsito político em plenário.
              </p>
            </div>

            <div className="bg-amber-950/20 border border-amber-500/30 rounded-2xl p-4 space-y-1.5">
              <span className="text-[10px] font-extrabold uppercase tracking-wider text-amber-400">
                Quadrante Inferior Esquerdo
              </span>
              <p className="text-xs font-bold text-amber-200">Poucos projetos e pouca aprovação</p>
              <h3 className="text-sm font-bold text-white">Bancada Reduzida / Início</h3>
              <p className="text-xs text-slate-300 leading-relaxed">
                Volume contido de matérias em fase preliminar de comissão ou atuação pontual da legenda.
              </p>
            </div>

            <div className="bg-rose-950/20 border border-rose-500/30 rounded-2xl p-4 space-y-1.5">
              <span className="text-[10px] font-extrabold uppercase tracking-wider text-rose-400">
                Quadrante Inferior Direito
              </span>
              <p className="text-xs font-bold text-rose-200">Muitos projetos e pouca aprovação</p>
              <h3 className="text-sm font-bold text-white">Populismo Legislativo</h3>
              <p className="text-xs text-slate-300 leading-relaxed">
                Volume massivo de matérias protocoladas para gerar notícia ou palanque, porém com baixa aprovação efetiva.
              </p>
            </div>
          </div>

          {/* Gráfico Scatter Plot / Dispersão Visual */}
          <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-6 backdrop-blur-md shadow-2xl space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-white">Dispersão: Volume de Projetos vs. Eficácia de Aprovação</h3>
                <p className="text-xs text-slate-400">
                  O tamanho de cada bolha reflete o score do IPPM da legenda. Clique em qualquer partido para inspecionar.
                </p>
              </div>
            </div>

            {/* Canvas de Dispersão Relativa */}
            <div className="relative w-full h-[480px] bg-slate-950/90 rounded-2xl border border-slate-800 p-6 flex flex-col justify-between overflow-hidden">
              {/* Linhas de Cruzamento dos Quadrantes (Medianas) */}
              <div className="absolute left-1/2 top-0 bottom-0 w-px bg-slate-800 border-l border-dashed border-slate-700/60 pointer-events-none" />
              <div className="absolute top-1/2 left-0 right-0 h-px bg-slate-800 border-t border-dashed border-slate-700/60 pointer-events-none" />

              {/* Rótulos dos Eixos */}
              <span className="absolute top-3 left-4 text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                ▲ Taxa de Eficácia (% Aprovados)
              </span>
              <span className="absolute bottom-3 right-4 text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                Volume de Projetos Apresentados ►
              </span>

              {/* Pontos / Bolhas Partidárias */}
              <div className="relative w-full h-full">
                {filteredAndSortedRanking.map((p) => {
                  const maxProj = Math.max(...filteredAndSortedRanking.map((item) => item.projetos_apresentados), 1);
                  const maxEff = Math.max(...filteredAndSortedRanking.map((item) => item.pilares.taxa_eficacia_pct), 1);

                  // Posição percentual mapeada com margem de 10% a 90%
                  const leftPct = 10 + Math.min(80, Math.round((p.projetos_apresentados / maxProj) * 80));
                  const topPct = 90 - Math.min(80, Math.round((p.pilares.taxa_eficacia_pct / Math.max(1, maxEff)) * 80));

                  return (
                    <div
                      key={p.sigla}
                      className="absolute -translate-x-1/2 -translate-y-1/2 group cursor-pointer transition-transform hover:scale-125 z-10"
                      style={{ left: `${leftPct}%`, top: `${topPct}%` }}
                      onClick={() => setSelectedPartyTimeline(p.sigla)}
                      title={`${p.sigla}: ${p.projetos_apresentados} projetos, ${p.pilares.taxa_eficacia_pct.toFixed(1)}% aprovados, IPPM: ${p.ippm_score_medio.toFixed(2)}`}
                    >
                      <div
                        className="rounded-2xl flex items-center justify-center font-extrabold text-xs shadow-lg border border-white/20 transition-all group-hover:ring-4 group-hover:ring-violet-500/40"
                        style={{
                          backgroundColor: p.cor_hex || "#3b82f6",
                          color: "#ffffff",
                          width: `${32 + Math.round((p.ippm_score_medio / maxIppm) * 28)}px`,
                          height: `${32 + Math.round((p.ippm_score_medio / maxIppm) * 28)}px`,
                        }}
                      >
                        {p.sigla}
                      </div>

                      {/* Tooltip Hover */}
                      <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block bg-slate-900 border border-slate-700 text-slate-200 text-xs rounded-xl p-3 shadow-2xl pointer-events-none whitespace-nowrap z-30">
                        <p className="font-extrabold text-sm text-white">{p.nome_completo} ({p.sigla})</p>
                        <div className="mt-1 space-y-0.5 text-[11px] text-slate-300">
                          <p>• <strong>IPPM Médio:</strong> {p.ippm_score_medio.toFixed(2)}</p>
                          <p>• <strong>Apresentados:</strong> {p.projetos_apresentados} | <strong>Aprovados:</strong> {p.projetos_aprovados}</p>
                          <p>• <strong>Eficácia:</strong> {p.pilares.taxa_eficacia_pct.toFixed(1)}%</p>
                          <p>• <strong>Coesão de Voto:</strong> {p.pilares.fidelidade_partidaria_pct == null ? "sem votações no período" : `${p.pilares.fidelidade_partidaria_pct.toFixed(1)}%`}</p>
                          {(p.pilares.assinaturas_apoio_quorum ?? 0) > 0 && (
                            <p>• <strong>Assinaturas de apoio a PEC:</strong> {p.pilares.assinaturas_apoio_quorum} (peso reduzido)</p>
                          )}
                          <p>• <strong>Bancada:</strong> {p.cadeiras_dia_equivalentes.toFixed(1)} cadeiras-dia</p>
                          <p className="text-violet-300 font-semibold">• {p.quadrante_eficiencia.titulo}</p>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
          )}
        </section>
      )}

      {/* ─── MODAL DE HISTÓRICO DINÂMICO DE MANDATOS E LICENÇAS ─── */}
      {selectedPartyTimeline && (
        <div
          className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-md flex items-center justify-center p-4"
          id="modal-party-timeline"
          role="dialog"
          aria-modal="true"
        >
          <div className="bg-slate-900 border border-slate-800 rounded-3xl max-w-2xl w-full p-6 md:p-8 space-y-6 shadow-2xl relative overflow-hidden">
            <button
              type="button"
              onClick={() => setSelectedPartyTimeline(null)}
              className="absolute top-5 right-5 text-slate-400 hover:text-white p-2 rounded-xl bg-slate-800/60 transition-colors"
              aria-label="Fechar modal"
            >
              <X className="w-5 h-5" />
            </button>

            <div className="space-y-1">
              <div className="inline-flex items-center gap-1.5 text-violet-400 text-xs font-semibold">
                <Users className="w-3.5 h-3.5" aria-hidden="true" />
                <span>Módulo 8: Histórico Dinâmico de Mandatos</span>
              </div>
              <h3 className="text-xl font-extrabold text-white">
                Bancada & Licenças Temporárias: {selectedPartyTimeline}
              </h3>
              <p className="text-xs text-slate-400">
                O rateio do divisor de cadeiras desconta proporcionalmente períodos em que parlamentares
                assumem ministérios ou secretarias, evitando distorções no score médio da bancada.
              </p>
            </div>

            {timelineLoading && (
              <div className="py-12 flex justify-center">
                <div className="w-8 h-8 border-4 border-violet-500/20 border-t-violet-500 rounded-full animate-spin" />
              </div>
            )}

            {!timelineLoading && timelineData && (
              <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-2 divide-y divide-slate-800/60">
                {/* Ministros / Licenciados */}
                {timelineData.ministros_licenciados.length > 0 && (
                  <div className="pt-2 space-y-2">
                    <h4 className="text-xs font-extrabold text-amber-400 uppercase tracking-wider flex items-center gap-1.5">
                      <Briefcase className="w-3.5 h-3.5" />
                      <span>Licenciados para Ministérios / Secretarias ({timelineData.ministros_licenciados.length})</span>
                    </h4>
                    <div className="space-y-2">
                      {timelineData.ministros_licenciados.map((m) => (
                        <div key={m.id} className="bg-amber-500/10 border border-amber-500/20 rounded-xl p-3 flex items-center justify-between text-xs">
                          <div>
                            <span className="font-bold text-white block">{m.nome_eleitoral}</span>
                            <span className="text-[11px] text-amber-300">{m.observacao || "Ministério de Estado"}</span>
                          </div>
                          <span className="text-[10px] font-mono text-slate-400">
                            Desde {m.data_inicio}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Suplentes Ativos */}
                {timelineData.suplentes_ativos.length > 0 && (
                  <div className="pt-4 space-y-2">
                    <h4 className="text-xs font-extrabold text-cyan-400 uppercase tracking-wider flex items-center gap-1.5">
                      <Users className="w-3.5 h-3.5" />
                      <span>Suplentes em Exercício Ativo ({timelineData.suplentes_ativos.length})</span>
                    </h4>
                    <div className="space-y-2">
                      {timelineData.suplentes_ativos.map((s) => (
                        <div key={s.id} className="bg-cyan-500/10 border border-cyan-500/20 rounded-xl p-3 flex items-center justify-between text-xs">
                          <div>
                            <span className="font-bold text-white block">{s.nome_eleitoral}</span>
                            <span className="text-[11px] text-cyan-300">Suplente convocada(o)</span>
                          </div>
                          <span className="text-[10px] font-mono text-slate-400">
                            {s.data_inicio} até {s.data_fim || "vigente"}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Titulares em Exercício */}
                <div className="pt-4 space-y-2">
                  <h4 className="text-xs font-extrabold text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
                    <ShieldCheck className="w-3.5 h-3.5" />
                    <span>Titulares em Exercício Regular ({timelineData.titulares_exercicio.length})</span>
                  </h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                    {timelineData.titulares_exercicio.slice(0, 12).map((t) => (
                      <div key={t.id} className="bg-slate-950/60 border border-slate-800 rounded-xl p-2.5 flex items-center justify-between text-xs">
                        <span className="font-semibold text-slate-200">{t.nome_eleitoral}</span>
                        <span className="text-[10px] font-mono text-slate-500">{t.casa}</span>
                      </div>
                    ))}
                  </div>
                  {timelineData.titulares_exercicio.length > 12 && (
                    <p className="text-[11px] text-slate-500 text-center pt-1">
                      + {timelineData.titulares_exercicio.length - 12} outros titulares ativos na base.
                    </p>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
