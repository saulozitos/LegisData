"use client";

import React, { useState, useMemo } from "react";
import {
  ProposicaoLegislativa,
  PlacarVotos,
  getPropositionVotes,
} from "@/services/api";
import { useApi } from "@/hooks/useApi";
import { safeExternalUrl } from "@/lib/safeUrl";
import { voteLabel } from "@/lib/votes";
import { EmptyState, ErrorState } from "@/components/StateViews";
import PartyLink from "@/components/PartyLink";
import Modal from "@/components/Modal";
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

  // Votos nominais: a resposta só vale para a proposição/casa/sessão atuais (sem sobrescrita por resposta antiga).
  const votes = useApi(
    `proposition-votes:${modalProp?.id}:${activeHouse}:${selectedSessionId ?? "default"}`,
    (signal) => getPropositionVotes(modalProp!.id, activeHouse, selectedSessionId || undefined, undefined, undefined, signal),
    Boolean(modalProp)
  );
  const votesData = votes.data ?? null;
  const loadingVotes = votes.loading;

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
    setSelectedSessionId(null);
    setModalSearch("");
    setModalVoteFilter("TODOS");
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
            <FileText className="w-5 h-5 text-cyan-400" aria-hidden="true" />
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
            type="button"
            aria-pressed={activeHouse === "CAMARA"}
            onClick={() => setActiveHouse("CAMARA")}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeHouse === "CAMARA"
                ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-sm shadow-emerald-500/10"
                : "text-slate-300 hover:text-slate-100"
            }`}
          >
            <Users className="w-3.5 h-3.5 text-emerald-400" aria-hidden="true" />
            <span>Câmara dos Deputados</span>
          </button>

          <button
            type="button"
            aria-pressed={activeHouse === "SENADO"}
            onClick={() => setActiveHouse("SENADO")}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeHouse === "SENADO"
                ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm shadow-cyan-500/10"
                : "text-slate-300 hover:text-slate-100"
            }`}
          >
            <Landmark className="w-3.5 h-3.5 text-cyan-400" aria-hidden="true" />
            <span>Senado Federal</span>
          </button>
        </div>
      </div>

      {/* Barra de Filtros (Comboboxes de Tema, Ano e Reformas) */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-3 rounded-xl bg-slate-950/70 border border-slate-800/80">
        <div className="flex flex-wrap items-center gap-2.5">
          <div className="flex items-center gap-1.5 text-xs text-slate-400 font-medium">
            <Filter className="w-3.5 h-3.5 text-cyan-400" aria-hidden="true" />
            <span>Filtrar por:</span>
          </div>

          {/* Combobox Tema */}
          <select
            aria-label="Filtrar por tema"
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
            aria-label="Filtrar por ano"
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
            type="button"
            aria-pressed={filterOnlyReforms}
            onClick={() => setFilterOnlyReforms(!filterOnlyReforms)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all ${
              filterOnlyReforms
                ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
                : "bg-slate-900 text-slate-300 border-slate-800 hover:text-slate-100"
            }`}
          >
            <Sparkles className="w-3 h-3 text-amber-400" aria-hidden="true" />
            <span>Apenas Reformas</span>
          </button>
        </div>

        <div className="text-[11px] text-slate-400 self-end sm:self-auto">
          Exibindo <strong className="text-cyan-400">{filteredProps.length}</strong> matérias com votação nominal auditada
        </div>
      </div>

      {/* Grid de Cards de Proposição (Clicáveis) */}
      {propositions.length === 0 ? (
        <EmptyState
          title="Proposições indisponíveis"
          message="Nenhuma proposição com votação nominal foi retornada pela API."
        />
      ) : filteredProps.length === 0 ? (
        <div role="status" className="text-center py-12 bg-slate-950/40 border border-slate-800/60 rounded-xl space-y-2">
          <Clock className="w-8 h-8 text-slate-400 mx-auto" aria-hidden="true" />
          <p className="text-sm font-semibold text-slate-300">
            Nenhuma proposição com votação registrada encontrada para este filtro.
          </p>
          <p className="text-xs text-slate-400">
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

            // O resultado oficial é o da sessão; sem ele, não se infere aprovação pela maioria simples
            // (PEC, quórum qualificado e destaques tornam essa inferência incorreta).
            const resultado: boolean | null = typeof sessao?.aprovada === "boolean" ? sessao.aprovada : null;

            return (
              <article
                key={prop.id}
                className="group relative bg-slate-950/80 border border-slate-800/90 hover:border-cyan-500/60 rounded-2xl p-5 transition-all duration-200 hover:shadow-lg hover:shadow-cyan-500/5 flex flex-col justify-between space-y-4 focus-within:ring-2 focus-within:ring-cyan-400"
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
                          <Sparkles className="w-3 h-3 text-amber-400" aria-hidden="true" />
                          Reforma Estrutural
                        </span>
                      )}
                    </div>

                    <span className="text-[11px] text-slate-400 font-mono">
                      {prop.data_apresentacao}
                    </span>
                  </div>

                  {/* Título com Link Oficial */}
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="text-sm font-bold text-slate-100 group-hover:text-cyan-300 transition-colors leading-snug">
                      <button
                        type="button"
                        onClick={() => handleOpenModal(prop)}
                        className="text-left cursor-pointer focus:outline-none after:absolute after:inset-0 after:content-['']"
                      >
                        {prop.titulo}
                      </button>
                    </h3>
                    {safeExternalUrl(prop.url_oficial) && (
                      <a
                        href={safeExternalUrl(prop.url_oficial)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="relative inline-flex items-center gap-1 text-[11px] font-semibold text-cyan-400 hover:text-cyan-300 transition-colors shrink-0 bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/20 px-2 py-0.5 rounded-lg z-10"
                        title="Ler íntegra no site oficial"
                      >
                        <span>Íntegra</span>
                        <ExternalLink className="w-3 h-3" aria-hidden="true" />
                      </a>
                    )}
                  </div>

                  {/* Autor / Propositor */}
                  <div className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-800/80 text-slate-300">
                    <User className="w-3.5 h-3.5 text-cyan-400 flex-shrink-0" aria-hidden="true" />
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
                        <Users className="w-3.5 h-3.5 text-emerald-400" aria-hidden="true" />
                      ) : (
                        <Landmark className="w-3.5 h-3.5 text-cyan-400" aria-hidden="true" />
                      )}
                      {isCamara ? "Placar na Câmara" : "Placar no Senado"} ({total} votos):
                    </span>

                    <span className="font-semibold text-xs">
                      {resultado === true ? (
                        <span className="text-emerald-400 flex items-center gap-1">
                          <CheckCircle2 className="w-3.5 h-3.5" aria-hidden="true" /> Aprovada
                        </span>
                      ) : resultado === false ? (
                        <span className="text-rose-400 flex items-center gap-1">
                          <XCircle className="w-3.5 h-3.5" aria-hidden="true" /> Rejeitada
                        </span>
                      ) : (
                        <span className="text-slate-300 flex items-center gap-1">
                          <Clock className="w-3.5 h-3.5" aria-hidden="true" /> Resultado indisponível
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

                    <div className="flex items-center gap-1 text-[11px] font-bold text-cyan-400 group-hover:text-cyan-300" aria-hidden="true">
                      <span>Ver Votos Nominais</span>
                      <ChevronRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
                    </div>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}

      {/* ======================================================== */}
      {/* MODAL DETALHADO DE VOTOS NOMINAIS */}
      {/* ======================================================== */}
      {modalProp && (
        <Modal
          isOpen
          onClose={handleCloseModal}
          titleId="legislative-modal-title"
          overlayClassName="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5 bg-slate-950/80 backdrop-blur-md"
          className="bg-slate-900 border border-slate-700/80 rounded-2xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl shadow-cyan-950/30 overflow-hidden"
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
                  <h2 id="legislative-modal-title" className="text-base sm:text-lg font-bold text-slate-100">
                    {modalProp.titulo}
                  </h2>
                  {safeExternalUrl(modalProp.url_oficial) && (
                    <a
                      href={safeExternalUrl(modalProp.url_oficial)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 text-xs font-semibold text-cyan-400 hover:text-cyan-300 bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/30 px-2.5 py-1 rounded-lg transition-colors shadow-sm"
                      title="Abrir página oficial do Congresso"
                    >
                      <span>Ler na Íntegra (Site Oficial)</span>
                      <ExternalLink className="w-3.5 h-3.5" aria-hidden="true" />
                    </a>
                  )}
                </div>
                <div className="flex items-center gap-2 text-xs text-slate-400 pt-0.5">
                  <span className="text-slate-400">Autor:</span>
                  <strong className="text-slate-300 font-semibold">
                    {modalProp.autor_nome || (modalProp.iniciativa_executivo ? "Poder Executivo Federal" : "Parlamentar")}
                  </strong>
                </div>
              </div>

              <button
                type="button"
                onClick={handleCloseModal}
                aria-label="Fechar"
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors"
                title="Fechar"
              >
                <X className="w-5 h-5" aria-hidden="true" />
              </button>
            </div>

            {/* Controles do Modal: Sessão, Busca e Filtro de Voto */}
            <div className="p-4 border-b border-slate-800/80 bg-slate-950/40 space-y-3">
              {/* Seletor de Sessões/Turnos caso haja mais de uma */}
              {votesData?.sessoes_disponiveis && votesData.sessoes_disponiveis.length > 1 && (
                <div className="flex items-center gap-2 text-xs flex-wrap">
                  <span className="text-slate-400 font-semibold flex items-center gap-1">
                    <Layers className="w-3.5 h-3.5 text-cyan-400" aria-hidden="true" /> Sessão / Turno:
                  </span>
                  {votesData.sessoes_disponiveis.map((sess, idx) => {
                    const isSelected =
                      selectedSessionId === sess.id ||
                      (!selectedSessionId && votesData.sessao_ativa?.id === sess.id);

                    return (
                      <button
                        type="button"
                        key={sess.id}
                        aria-pressed={isSelected}
                        onClick={() => setSelectedSessionId(sess.id)}
                        className={`px-2.5 py-1 rounded-lg text-xs font-semibold border transition-all ${
                          isSelected
                            ? "bg-cyan-500/20 text-cyan-300 border-cyan-500/40"
                            : "bg-slate-900 text-slate-300 border-slate-800 hover:text-slate-100"
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
                  <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" aria-hidden="true" />
                  <input
                    type="text"
                    aria-label="Buscar parlamentar, partido ou estado"
                    value={modalSearch}
                    onChange={(e) => setModalSearch(e.target.value)}
                    placeholder="Buscar por deputado, senador, partido ou estado..."
                    className="w-full bg-slate-900 border border-slate-800 rounded-xl pl-8.5 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-400 focus:outline-none focus:border-cyan-500 transition-colors"
                  />
                </div>

                {/* Filtros de Voto (Todos, Sim, Não, Abstenção) */}
                <div className="flex items-center gap-1 bg-slate-900 p-1 rounded-xl border border-slate-800 flex-shrink-0">
                  <button
                    type="button"
                    aria-pressed={modalVoteFilter === "TODOS"}
                    onClick={() => setModalVoteFilter("TODOS")}
                    className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all ${
                      modalVoteFilter === "TODOS"
                        ? "bg-slate-800 text-slate-100"
                        : "text-slate-300 hover:text-slate-100"
                    }`}
                  >
                    Todos ({votesData?.total || 0})
                  </button>
                  <button
                    type="button"
                    aria-pressed={modalVoteFilter === "SIM"}
                    onClick={() => setModalVoteFilter("SIM")}
                    className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all ${
                      modalVoteFilter === "SIM"
                        ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                        : "text-slate-300 hover:text-slate-100"
                    }`}
                  >
                    Sim
                  </button>
                  <button
                    type="button"
                    aria-pressed={modalVoteFilter === "NAO"}
                    onClick={() => setModalVoteFilter("NAO")}
                    className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all ${
                      modalVoteFilter === "NAO"
                        ? "bg-rose-500/20 text-rose-400 border border-rose-500/30"
                        : "text-slate-300 hover:text-slate-100"
                    }`}
                  >
                    Não
                  </button>
                  <button
                    type="button"
                    aria-pressed={modalVoteFilter === "ABSTENCAO"}
                    onClick={() => setModalVoteFilter("ABSTENCAO")}
                    className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all ${
                      modalVoteFilter === "ABSTENCAO"
                        ? "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                        : "text-slate-300 hover:text-slate-100"
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
                <div role="status" aria-live="polite" className="text-center py-12 text-slate-400 text-xs">
                  Carregando lista nominal de votos...
                </div>
              ) : votes.error ? (
                <ErrorState
                  title="Não foi possível carregar os votos"
                  message="A lista nominal não pôde ser obtida. Isso não significa que a matéria não tenha sido votada."
                  onRetry={votes.retry}
                />
              ) : modalFilteredVotes.length === 0 ? (
                <div role="status" className="text-center py-12 text-slate-400 text-xs">
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
                            {safeExternalUrl(v.foto_url) ? (
                              <img
                                src={safeExternalUrl(v.foto_url)}
                                alt=""
                                referrerPolicy="no-referrer"
                                className="w-full h-full object-cover"
                                onError={(e) => {
                                  e.currentTarget.style.display = "none";
                                }}
                              />
                            ) : null}
                            <span className="absolute text-[10px] font-bold text-slate-300 -z-10">
                              {v.partido_sigla.slice(0, 2)}
                            </span>
                          </div>

                          <div className="min-w-0">
                            <h4 className="text-xs font-bold text-slate-100 truncate">
                              {v.politico_id && onSelectPolitician ? (
                                <button
                                  type="button"
                                  onClick={() => {
                                    setModalProp(null);
                                    onSelectPolitician(v.politico_id);
                                  }}
                                  className="cursor-pointer hover:text-cyan-300 transition-colors text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 rounded"
                                  title="Clique para abrir o Raio-X"
                                >
                                  {v.nome_eleitoral}
                                </button>
                              ) : (
                                v.nome_eleitoral
                              )}
                            </h4>
                            <span className="text-[11px] text-slate-400 font-medium">
                              <PartyLink
                                sigla={v.partido_sigla}
                                onSelectParty={
                                  onSelectParty
                                    ? (sigla) => {
                                        setModalProp(null);
                                        onSelectParty(sigla);
                                      }
                                    : undefined
                                }
                                className="text-cyan-400 font-bold"
                              />{" "}
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
                              : "bg-slate-800 text-slate-300 border-slate-700"
                          }`}
                        >
                          {voteLabel(v.decisao)}
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
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" aria-hidden="true" />
                Votos oficiais extraídos dos registros nominais em Plenário
              </span>
              <span className="font-mono text-slate-400">
                Mostrando {modalFilteredVotes.length} de {votesData?.total || 0} votos
              </span>
            </div>
        </Modal>
      )}
    </div>
  );
}
