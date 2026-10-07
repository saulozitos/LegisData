"use client";

import React, { useState, useMemo, useEffect } from "react";
import {
  ProposicaoLegislativa,
  PlacarVotos,
  VotoNominalItem,
  PropositionVotesResponse,
  getPropositionVotes,
} from "@/services/api";
import {
  FileText,
  CheckCircle2,
  XCircle,
  Clock,
  Sparkles,
  Users,
  Landmark,
  Layers,
  Search,
  Filter,
  User,
  X,
  ExternalLink,
  ChevronRight,
  ShieldCheck,
  Building2,
} from "lucide-react";

interface LegislativePanelProps {
  propositions: ProposicaoLegislativa[];
  onSelectPolitician?: (id: string) => void;
  onSelectParty?: (sigla: string) => void;
}

export default function LegislativePanel({
  propositions,
  onSelectPolitician,
  onSelectParty,
}: LegislativePanelProps) {
  // Filtros principais
  const [activeHouse, setActiveHouse] = useState<"CAMARA" | "SENADO">("CAMARA");
  const [filterTheme, setFilterTheme] = useState<string>("TODOS");
  const [filterYear, setFilterYear] = useState<string>("TODOS");
  const [filterOnlyReforms, setFilterOnlyReforms] = useState(false);

  // Estado do Modal de Votos Nominais
  const [modalProp, setModalProp] = useState<ProposicaoLegislativa | null>(null);
  const [loadingVotes, setLoadingVotes] = useState(false);
  const [votesData, setVotesData] = useState<PropositionVotesResponse | null>(null);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [modalSearch, setModalSearch] = useState("");
  const [modalVoteFilter, setModalVoteFilter] = useState<string>("TODOS");

  // Lista única de Temas e Anos para os Comboboxes
  const themesList = useMemo(() => {
    const set = new Set<string>();
    for (const p of propositions) {
      if (p.area_tematica) set.add(p.area_tematica);
    }
    return Array.from(set).sort();
  }, [propositions]);

  const yearsList = useMemo(() => {
    const set = new Set<number>();
    for (const p of propositions) {
      if (p.ano) set.add(p.ano);
    }
    return Array.from(set).sort((a, b) => b - a);
  }, [propositions]);

  // Filtragem de proposições:
  // 1. Ocultar automaticamente as proposições que não possuem votos registrados
  // 2. Aplicar filtros de Tema, Ano, Casa e Reforma
  const filteredProps = useMemo(() => {
    return propositions.filter((p) => {
      const isCamara = activeHouse === "CAMARA";
      const totalVotos = isCamara
        ? (p.placar_camara?.TOTAL || 0)
        : (p.placar_senado?.TOTAL || 0);

      // REGRA OBRIGATÓRIA: Ocultar matérias sem votos na Casa ativa
      if (totalVotos <= 0) return false;

      // Filtro de Tema
      if (filterTheme !== "TODOS" && p.area_tematica !== filterTheme) {
        return false;
      }

      // Filtro de Ano
      if (filterYear !== "TODOS" && p.ano.toString() !== filterYear) {
        return false;
      }

      // Filtro de Reformas
      if (filterOnlyReforms && !p.is_reforma_estrutural) {
        return false;
      }

      return true;
    });
  }, [propositions, activeHouse, filterTheme, filterYear, filterOnlyReforms]);

  // Carregar votos nominais ao abrir o modal ou mudar de sessão
  useEffect(() => {
    if (!modalProp) {
      setVotesData(null);
      setSelectedSessionId(null);
      setModalSearch("");
      setModalVoteFilter("TODOS");
      return;
    }

    async function loadVotes() {
      setLoadingVotes(true);
      try {
        const res = await getPropositionVotes(
          modalProp!.id,
          activeHouse,
          selectedSessionId || undefined
        );
        setVotesData(res);
      } catch (err) {
        console.error("Erro ao carregar votos nominais:", err);
      } finally {
        setLoadingVotes(false);
      }
    }

    loadVotes();
  }, [modalProp, activeHouse, selectedSessionId]);

  // Filtrar votos nominais no Modal
  const modalFilteredVotes = useMemo(() => {
    if (!votesData || !votesData.votos) return [];
    let list = votesData.votos;

    if (modalVoteFilter !== "TODOS") {
      list = list.filter((v) => v.decisao === modalVoteFilter);
    }

    if (modalSearch.trim()) {
      const term = modalSearch.toLowerCase();
      list = list.filter(
        (v) =>
          v.nome_eleitoral.toLowerCase().includes(term) ||
          v.nome_civil.toLowerCase().includes(term) ||
          v.partido_sigla.toLowerCase().includes(term) ||
          v.uf.toLowerCase().includes(term)
      );
    }

    return list;
  }, [votesData, modalVoteFilter, modalSearch]);

  const handleOpenModal = (prop: ProposicaoLegislativa) => {
    setModalProp(prop);
  };

  const handleCloseModal = () => {
    setModalProp(null);
  };

  return (
    <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 backdrop-blur-md space-y-6">
      {/* Topo do Header do Painel */}
      <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <FileText className="w-5 h-5 text-cyan-400" />
            <h2 className="text-base sm:text-lg font-bold text-slate-100">
              Congresso Nacional: Votações Nominais e Transparência
            </h2>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Mapeamento nominal auditável de votos (Sim, Não, Abstenção) em matérias estruturantes com quórum registrado
          </p>
        </div>

        {/* Seletor de Casa Legislativa */}
        <div className="flex items-center bg-slate-950 border border-slate-800 p-1 rounded-xl">
          <button
            onClick={() => setActiveHouse("CAMARA")}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeHouse === "CAMARA"
                ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-sm shadow-emerald-500/10"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Users className="w-3.5 h-3.5 text-emerald-400" />
            <span>Câmara dos Deputados</span>
          </button>

          <button
            onClick={() => setActiveHouse("SENADO")}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeHouse === "SENADO"
                ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm shadow-cyan-500/10"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Landmark className="w-3.5 h-3.5 text-cyan-400" />
            <span>Senado Federal</span>
          </button>
        </div>
      </div>

      {/* Barra de Filtros (Comboboxes de Tema, Ano e Reformas) */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-3 rounded-xl bg-slate-950/70 border border-slate-800/80">
        <div className="flex flex-wrap items-center gap-2.5">
          <div className="flex items-center gap-1.5 text-xs text-slate-400 font-medium">
            <Filter className="w-3.5 h-3.5 text-cyan-400" />
            <span>Filtrar por:</span>
          </div>

          {/* Combobox Tema */}
          <select
            value={filterTheme}
            onChange={(e) => setFilterTheme(e.target.value)}
            className="bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-cyan-500 cursor-pointer"
          >
            <option value="TODOS">Todos os Temas</option>
            {themesList.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>

          {/* Combobox Ano */}
          <select
            value={filterYear}
            onChange={(e) => setFilterYear(e.target.value)}
            className="bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-cyan-500 cursor-pointer"
          >
            <option value="TODOS">Todos os Anos</option>
            {yearsList.map((y) => (
              <option key={y} value={y.toString()}>
                {y}
              </option>
            ))}
          </select>

          {/* Botão Apenas Reformas */}
          <button
            onClick={() => setFilterOnlyReforms(!filterOnlyReforms)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all ${
              filterOnlyReforms
                ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
                : "bg-slate-900 text-slate-400 border-slate-800 hover:text-slate-200"
            }`}
          >
            <Sparkles className="w-3 h-3 text-amber-400" />
            <span>Apenas Reformas</span>
          </button>
        </div>

        <div className="text-[11px] text-slate-400 self-end sm:self-auto">
          Exibindo <strong className="text-cyan-400">{filteredProps.length}</strong> matérias com votação nominal auditada
        </div>
      </div>

      {/* Grid de Cards de Proposição (Clicáveis) */}
      {filteredProps.length === 0 ? (
        <div className="text-center py-12 bg-slate-950/40 border border-slate-800/60 rounded-xl space-y-2">
          <Clock className="w-8 h-8 text-slate-600 mx-auto" />
          <p className="text-sm font-semibold text-slate-400">
            Nenhuma proposição com votação registrada encontrada para este filtro.
          </p>
          <p className="text-xs text-slate-500">
            Tente redefinir os filtros de tema, ano ou alternar para a outra Casa Legislativa.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {filteredProps.map((prop) => {
            const isCamara = activeHouse === "CAMARA";
            const placar: PlacarVotos = isCamara
              ? prop.placar_camara || prop.placar || { SIM: 0, NAO: 0, ABSTENCAO: 0, TOTAL: 0 }
              : prop.placar_senado || { SIM: 0, NAO: 0, ABSTENCAO: 0, TOTAL: 0 };

            const sessao = isCamara ? prop.sessao_camara || prop.sessao : prop.sessao_senado;
            const total = placar.TOTAL || 0;
            const pctSim = total > 0 ? Math.round((placar.SIM / total) * 100) : 0;
            const pctNao = total > 0 ? Math.round((placar.NAO / total) * 100) : 0;
            const pctAbst = total > 0 ? Math.round((placar.ABSTENCAO / total) * 100) : 0;

            const isAprovado = sessao?.aprovada || placar.SIM > placar.NAO;

            return (
              <div
                key={prop.id}
                onClick={() => handleOpenModal(prop)}
                role="button"
                tabIndex={0}
                className="group bg-slate-950/80 border border-slate-800/90 hover:border-cyan-500/60 rounded-2xl p-5 transition-all duration-200 cursor-pointer hover:shadow-lg hover:shadow-cyan-500/5 flex flex-col justify-between space-y-4"
              >
                <div className="space-y-2.5">
                  {/* Badges do Topo */}
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-xs font-mono font-extrabold px-2.5 py-0.5 rounded-lg bg-cyan-500/10 text-cyan-300 border border-cyan-500/20">
                        {prop.tipo} {prop.numero}/{prop.ano}
                      </span>

                      {prop.area_tematica && (
                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                          {prop.area_tematica}
                        </span>
                      )}

                      {prop.is_reforma_estrutural && (
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-300 border border-amber-500/20 flex items-center gap-1">
                          <Sparkles className="w-3 h-3 text-amber-400" />
                          Reforma Estrutural
                        </span>
                      )}
                    </div>

                    <span className="text-[11px] text-slate-500 font-mono">
                      {prop.data_apresentacao}
                    </span>
                  </div>

                  {/* Título com Link Oficial */}
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="text-sm font-bold text-slate-100 group-hover:text-cyan-300 transition-colors leading-snug">
                      {prop.titulo}
                    </h3>
                    {prop.url_oficial && (
                      <a
                        href={prop.url_oficial}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="inline-flex items-center gap-1 text-[11px] font-semibold text-cyan-400 hover:text-cyan-300 transition-colors shrink-0 bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/20 px-2 py-0.5 rounded-lg z-10"
                        title="Ler íntegra no site oficial"
                      >
                        <span>Íntegra</span>
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    )}
                  </div>

                  {/* Autor / Propositor */}
                  <div className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-800/80 text-slate-300">
                    <User className="w-3.5 h-3.5 text-cyan-400 flex-shrink-0" />
                    <span className="text-slate-400">Autor:</span>
                    <strong className="text-slate-200 truncate font-semibold">
                      {prop.autor_nome || (prop.iniciativa_executivo ? "Poder Executivo Federal" : "Congresso Nacional")}
                    </strong>
                  </div>

                  {/* Ementa */}
                  <p className="text-xs text-slate-400 line-clamp-2 leading-relaxed">
                    {prop.ementa}
                  </p>
                </div>

                {/* Placar e Barra de Votação */}
                <div className="pt-3 border-t border-slate-900/90 space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-slate-400 font-medium flex items-center gap-1">
                      {isCamara ? (
                        <Users className="w-3.5 h-3.5 text-emerald-400" />
                      ) : (
                        <Landmark className="w-3.5 h-3.5 text-cyan-400" />
                      )}
                      {isCamara ? "Placar na Câmara" : "Placar no Senado"} ({total} votos):
                    </span>

                    <span className="font-semibold text-xs">
                      {isAprovado ? (
                        <span className="text-emerald-400 flex items-center gap-1">
                          <CheckCircle2 className="w-3.5 h-3.5" /> Aprovada
                        </span>
                      ) : (
                        <span className="text-rose-400 flex items-center gap-1">
                          <XCircle className="w-3.5 h-3.5" /> Rejeitada
                        </span>
                      )}
                    </span>
                  </div>

                  {/* Barra Tripla de Votos */}
                  <div className="w-full h-2.5 rounded-full bg-slate-800 flex overflow-hidden">
                    <div
                      style={{ width: `${pctSim}%` }}
                      className="bg-emerald-500 transition-all"
                      title={`Sim: ${placar.SIM} (${pctSim}%)`}
                    />
                    <div
                      style={{ width: `${pctNao}%` }}
                      className="bg-rose-500 transition-all"
                      title={`Não: ${placar.NAO} (${pctNao}%)`}
                    />
                    <div
                      style={{ width: `${pctAbst}%` }}
                      className="bg-amber-500 transition-all"
                      title={`Abstenções: ${placar.ABSTENCAO} (${pctAbst}%)`}
                    />
                  </div>

                  {/* Legenda dos Votos e Gatilho do Modal */}
                  <div className="flex items-center justify-between pt-1">
                    <div className="flex items-center gap-3 text-[11px] font-mono">
                      <span className="text-emerald-400 font-bold">Sim: {placar.SIM} ({pctSim}%)</span>
                      <span className="text-rose-400 font-bold">Não: {placar.NAO} ({pctNao}%)</span>
                      <span className="text-amber-400">Abst: {placar.ABSTENCAO}</span>
                    </div>

                    <div className="flex items-center gap-1 text-[11px] font-bold text-cyan-400 group-hover:text-cyan-300">
                      <span>Ver Votos Nominais</span>
                      <ChevronRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ======================================================== */}
      {/* MODAL DETALHADO DE VOTOS NOMINAIS */}
      {/* ======================================================== */}
      {modalProp && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-200"
          onClick={handleCloseModal}
        >
          <div
            className="bg-slate-900 border border-slate-700/80 rounded-2xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl shadow-cyan-950/30 overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Topo do Modal */}
            <div className="p-4 sm:p-5 border-b border-slate-800 flex items-start justify-between gap-4 bg-slate-950/60">
              <div className="space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/20">
                    {modalProp.tipo} {modalProp.numero}/{modalProp.ano}
                  </span>
                  <span className="text-xs text-slate-400">
                    Votação Nominal na {activeHouse === "CAMARA" ? "Câmara dos Deputados" : "Senado Federal"}
                  </span>
                </div>
                <div className="flex items-center gap-3 flex-wrap">
                  <h2 className="text-base sm:text-lg font-bold text-slate-100">
                    {modalProp.titulo}
                  </h2>
                  {modalProp.url_oficial && (
                    <a
                      href={modalProp.url_oficial}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 text-xs font-semibold text-cyan-400 hover:text-cyan-300 bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/30 px-2.5 py-1 rounded-lg transition-colors shadow-sm"
                      title="Abrir página oficial do Congresso"
                    >
                      <span>Ler na Íntegra (Site Oficial)</span>
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  )}
                </div>
                <div className="flex items-center gap-2 text-xs text-slate-400 pt-0.5">
                  <span className="text-slate-500">Autor:</span>
                  <strong className="text-slate-300 font-semibold">
                    {modalProp.autor_nome || (modalProp.iniciativa_executivo ? "Poder Executivo Federal" : "Parlamentar")}
                  </strong>
                </div>
              </div>

              <button
                onClick={handleCloseModal}
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors"
                title="Fechar"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Controles do Modal: Sessão, Busca e Filtro de Voto */}
            <div className="p-4 border-b border-slate-800/80 bg-slate-950/40 space-y-3">
              {/* Seletor de Sessões/Turnos caso haja mais de uma */}
              {votesData?.sessoes_disponiveis && votesData.sessoes_disponiveis.length > 1 && (
                <div className="flex items-center gap-2 text-xs flex-wrap">
                  <span className="text-slate-400 font-semibold flex items-center gap-1">
                    <Layers className="w-3.5 h-3.5 text-cyan-400" /> Sessão / Turno:
                  </span>
                  {votesData.sessoes_disponiveis.map((sess, idx) => {
                    const isSelected =
                      selectedSessionId === sess.id ||
                      (!selectedSessionId && votesData.sessao_ativa?.id === sess.id);

                    return (
                      <button
                        key={sess.id}
                        onClick={() => setSelectedSessionId(sess.id)}
                        className={`px-2.5 py-1 rounded-lg text-xs font-semibold border transition-all ${
                          isSelected
                            ? "bg-cyan-500/20 text-cyan-300 border-cyan-500/40"
                            : "bg-slate-900 text-slate-400 border-slate-800 hover:text-slate-200"
                        }`}
                      >
                        {sess.titulo || `Turno ${idx + 1}`}
                      </button>
                    );
                  })}
                </div>
              )}

              {/* Linha de Busca e Badges de Decisão */}
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
                {/* Input de Busca */}
                <div className="relative flex-1">
                  <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    value={modalSearch}
                    onChange={(e) => setModalSearch(e.target.value)}
                    placeholder="Buscar por deputado, senador, partido ou estado..."
                    className="w-full bg-slate-900 border border-slate-800 rounded-xl pl-8.5 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition-colors"
                  />
                </div>

                {/* Filtros de Voto (Todos, Sim, Não, Abstenção) */}
                <div className="flex items-center gap-1 bg-slate-900 p-1 rounded-xl border border-slate-800 flex-shrink-0">
                  <button
                    onClick={() => setModalVoteFilter("TODOS")}
                    className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all ${
                      modalVoteFilter === "TODOS"
                        ? "bg-slate-800 text-slate-100"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    Todos ({votesData?.total || 0})
                  </button>
                  <button
                    onClick={() => setModalVoteFilter("SIM")}
                    className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all ${
                      modalVoteFilter === "SIM"
                        ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    Sim
                  </button>
                  <button
                    onClick={() => setModalVoteFilter("NAO")}
                    className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all ${
                      modalVoteFilter === "NAO"
                        ? "bg-rose-500/20 text-rose-400 border border-rose-500/30"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    Não
                  </button>
                  <button
                    onClick={() => setModalVoteFilter("ABSTENCAO")}
                    className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all ${
                      modalVoteFilter === "ABSTENCAO"
                        ? "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    Abstenção
                  </button>
                </div>
              </div>
            </div>

            {/* Lista dos Votos Nominais */}
            <div className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-2">
              {loadingVotes ? (
                <div className="text-center py-12 text-slate-400 text-xs">
                  Carregando lista nominal de votos...
                </div>
              ) : modalFilteredVotes.length === 0 ? (
                <div className="text-center py-12 text-slate-500 text-xs">
                  Nenhum parlamentar encontrado para o critério pesquisado.
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5">
                  {modalFilteredVotes.map((v) => {
                    const isSim = v.decisao === "SIM";
                    const isNao = v.decisao === "NAO";
                    const isAbst = v.decisao === "ABSTENCAO";

                    return (
                      <div
                        key={v.voto_id}
                        className="bg-slate-950/70 border border-slate-800/80 rounded-xl p-3 flex items-center justify-between gap-2.5"
                      >
                        <div className="flex items-center gap-2.5 min-w-0">
                          {/* Foto do Parlamentar com fallback */}
                          <div className="relative w-9 h-9 rounded-full overflow-hidden bg-slate-800 border border-slate-700 flex-shrink-0 flex items-center justify-center">
                            {v.foto_url ? (
                              <img
                                src={v.foto_url}
                                alt={v.nome_eleitoral}
                                referrerPolicy="no-referrer"
                                className="w-full h-full object-cover"
                                onError={(e) => {
                                  (e.target as HTMLImageElement).style.display = "none";
                                }}
                              />
                            ) : null}
                            <span className="absolute text-[10px] font-bold text-slate-400 -z-10">
                              {v.partido_sigla.slice(0, 2)}
                            </span>
                          </div>

                          <div className="min-w-0">
                            <h4
                              onClick={() => {
                                if (v.politico_id && onSelectPolitician) {
                                  setModalProp(null);
                                  onSelectPolitician(v.politico_id);
                                }
                              }}
                              className={`text-xs font-bold text-slate-100 truncate ${
                                v.politico_id && onSelectPolitician ? "cursor-pointer hover:text-cyan-300 transition-colors" : ""
                              }`}
                              title={v.politico_id && onSelectPolitician ? "Clique para abrir o Raio-X" : undefined}
                            >
                              {v.nome_eleitoral}
                            </h4>
                            <span className="text-[11px] text-slate-400 font-medium">
                              <strong
                                onClick={(e) => {
                                  if (onSelectParty && v.partido_sigla) {
                                    e.stopPropagation();
                                    setModalProp(null);
                                    onSelectParty(v.partido_sigla);
                                  }
                                }}
                                className={`text-cyan-400 ${
                                  onSelectParty ? "cursor-pointer hover:underline" : ""
                                }`}
                                title={onSelectParty ? `Ver bancada do ${v.partido_sigla}` : undefined}
                              >
                                {v.partido_sigla}
                              </strong>{" "}
                              • {v.uf}
                            </span>
                          </div>
                        </div>

                        {/* Badge de Decisão */}
                        <span
                          className={`text-xs font-extrabold px-2.5 py-1 rounded-lg border flex-shrink-0 font-mono ${
                            isSim
                              ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                              : isNao
                              ? "bg-rose-500/15 text-rose-400 border-rose-500/30"
                              : isAbst
                              ? "bg-amber-500/15 text-amber-400 border-amber-500/30"
                              : "bg-slate-800 text-slate-400 border-slate-700"
                          }`}
                        >
                          {v.decisao}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Rodapé do Modal com Informações Auditáveis */}
            <div className="p-3.5 bg-slate-950/80 border-t border-slate-800 flex items-center justify-between text-[11px] text-slate-400">
              <span className="flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                Votos oficiais extraídos dos registros nominais em Plenário
              </span>
              <span className="font-mono text-slate-400">
                Mostrando {modalFilteredVotes.length} de {votesData?.total || 0} votos
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
