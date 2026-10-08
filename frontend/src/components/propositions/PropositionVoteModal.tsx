"use client";

import React, { useState, useMemo } from "react";
import { ParlamentarVotoNominalItem, getPropositionNominalVotesSplit } from "@/services/api";
import { X, Vote, Check, Ban, Search, ExternalLink, FileText } from "lucide-react";
import ParlamentarCard from "./ParlamentarCard";
import Modal from "@/components/Modal";
import { ErrorState } from "@/components/StateViews";
import { useDebounce } from "@/hooks/useDebounce";
import { useApi } from "@/hooks/useApi";
import { safeExternalUrl } from "@/lib/safeUrl";

interface PropositionVoteModalProps {
  propId: string;
  onClose: () => void;
  onSelectPolitician?: (id: string) => void;
  onSelectParty?: (sigla: string) => void;
}

type ModalTab = "lado_a_lado" | "sim" | "nao" | "abstencao" | "obstrucao";

function matchesSearch(v: ParlamentarVotoNominalItem, term: string): boolean {
  return (
    v.nome_eleitoral.toLowerCase().includes(term) ||
    v.partido_sigla.toLowerCase().includes(term) ||
    v.uf.toLowerCase().includes(term)
  );
}

export default function PropositionVoteModal({
  propId,
  onClose,
  onSelectPolitician,
  onSelectParty,
}: PropositionVoteModalProps) {
  const [modalSearch, setModalSearch] = useState<string>("");
  const [activeModalTab, setActiveModalTab] = useState<ModalTab>("lado_a_lado");

  const debouncedSearch = useDebounce(modalSearch, 300);

  const votes = useApi(`nominal-votes:${propId}`, (signal) =>
    getPropositionNominalVotesSplit(propId, undefined, signal)
  );
  const modalData = votes.data ?? null;
  const isLoadingModal = votes.loading;

  const filterByTerm = useMemo(() => {
    const term = debouncedSearch.trim().toLowerCase();
    return (list: ParlamentarVotoNominalItem[] | undefined) => {
      if (!list) return [];
      return term ? list.filter((v) => matchesSearch(v, term)) : list;
    };
  }, [debouncedSearch]);

  const filteredVotosSim = useMemo(() => filterByTerm(modalData?.votos_sim), [modalData, filterByTerm]);
  const filteredVotosNao = useMemo(() => filterByTerm(modalData?.votos_nao), [modalData, filterByTerm]);
  const filteredVotosAbstencao = useMemo(() => filterByTerm(modalData?.votos_abstencao), [modalData, filterByTerm]);
  const filteredVotosObstrucao = useMemo(() => filterByTerm(modalData?.votos_obstrucao), [modalData, filterByTerm]);

  const hasNominalVotes =
    Boolean(modalData) &&
    ((modalData?.placar?.total ?? 0) > 0 ||
      (modalData?.votos_sim?.length ?? 0) > 0 ||
      (modalData?.votos_nao?.length ?? 0) > 0 ||
      (modalData?.votos_abstencao?.length ?? 0) > 0 ||
      (modalData?.votos_obstrucao?.length ?? 0) > 0);

  const officialUrl = safeExternalUrl(modalData?.proposicao?.url_oficial);

  const tabs: Array<{ id: ModalTab; label: string; activeClass: string; inactiveClass: string }> = [
    { id: "lado_a_lado", label: "Lado a Lado", activeClass: "bg-slate-800 text-white", inactiveClass: "text-slate-300 hover:text-slate-100" },
    { id: "sim", label: `Apenas SIM (${filteredVotosSim.length})`, activeClass: "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30", inactiveClass: "text-slate-300 hover:text-emerald-400" },
    { id: "nao", label: `Apenas NÃO (${filteredVotosNao.length})`, activeClass: "bg-rose-500/20 text-rose-300 border border-rose-500/30", inactiveClass: "text-slate-300 hover:text-rose-400" },
    { id: "abstencao", label: `Abstenções (${filteredVotosAbstencao.length})`, activeClass: "bg-amber-500/20 text-amber-300 border border-amber-500/30", inactiveClass: "text-slate-300 hover:text-amber-400" },
    { id: "obstrucao", label: `Obstruções (${filteredVotosObstrucao.length})`, activeClass: "bg-purple-500/20 text-purple-300 border border-purple-500/30", inactiveClass: "text-slate-300 hover:text-purple-400" },
  ];

  const renderColumn = (
    title: string,
    icon: React.ReactNode,
    list: ParlamentarVotoNominalItem[],
    palette: { box: string; line: string; title: string; badge: string; border: string },
    emptyText: string
  ) => (
    <div className={`${palette.box} rounded-2xl p-4 space-y-3`}>
      <div className={`flex items-center justify-between border-b ${palette.line} pb-2`}>
        <h4 className={`text-sm font-black ${palette.title} flex items-center gap-2`}>
          {icon}
          {title}
        </h4>
        <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${palette.badge}`}>
          {list.length} parlamentares
        </span>
      </div>

      {list.length === 0 ? (
        <p className="text-xs text-slate-400 italic py-4 text-center">{emptyText}</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 max-h-96 overflow-y-auto pr-1">
          {list.map((parl) => (
            <ParlamentarCard
              key={parl.politico_id}
              parl={parl}
              borderColor={palette.border}
              onSelectPolitician={onSelectPolitician}
              onSelectParty={onSelectParty}
              onCloseModal={onClose}
            />
          ))}
        </div>
      )}
    </div>
  );

  const emerald = { box: "bg-emerald-950/15 border border-emerald-500/30", line: "border-emerald-500/20", title: "text-emerald-400", badge: "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30", border: "border-emerald-500/20" };
  const rose = { box: "bg-rose-950/15 border border-rose-500/30", line: "border-rose-500/20", title: "text-rose-400", badge: "bg-rose-500/20 text-rose-300 border border-rose-500/30", border: "border-rose-500/20" };
  const amber = { box: "bg-amber-950/15 border border-amber-500/30", line: "border-amber-500/20", title: "text-amber-400", badge: "bg-amber-500/20 text-amber-300 border border-amber-500/30", border: "border-amber-500/20" };
  const purple = { box: "bg-purple-950/15 border border-purple-500/30", line: "border-purple-500/20", title: "text-purple-400", badge: "bg-purple-500/20 text-purple-300 border border-purple-500/30", border: "border-purple-500/20" };

  const placar = modalData?.placar;
  const total = Math.max(1, placar?.total ?? 0);

  return (
    <Modal
      isOpen
      onClose={onClose}
      titleId="proposition-vote-title"
      overlayClassName="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-slate-950/80 backdrop-blur-md"
      className="bg-slate-900 border border-slate-700 rounded-3xl w-full max-w-5xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden relative"
    >
      {/* CABEÇALHO DO MODAL */}
      <div className="p-6 border-b border-slate-800 bg-slate-950/80 relative">
        <button
          type="button"
          aria-label="Fechar"
          onClick={onClose}
          className="absolute top-5 right-5 p-2 rounded-xl bg-slate-800/80 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors"
        >
          <X className="w-5 h-5" aria-hidden="true" />
        </button>

        {isLoadingModal ? (
          <div role="status" aria-live="polite" className="space-y-2 animate-pulse">
            <span className="sr-only">Carregando proposição...</span>
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
              {typeof modalData.sessao?.aprovada === "boolean" && (
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
              <h3 id="proposition-vote-title" className="text-xl sm:text-2xl font-black text-white leading-tight">
                {modalData.proposicao.titulo}
              </h3>
              {officialUrl && (
                <a
                  href={officialUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-cyan-400 hover:text-cyan-300 bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/30 px-2.5 py-1 rounded-lg transition-colors shadow-sm"
                  title="Ler íntegra no site oficial"
                >
                  <span>Ler na Íntegra (Site Oficial)</span>
                  <ExternalLink className="w-3.5 h-3.5" aria-hidden="true" />
                </a>
              )}
            </div>

            <p className="text-xs sm:text-sm text-slate-300 leading-relaxed bg-slate-950/60 p-3 rounded-xl border border-slate-800/80 max-h-24 overflow-y-auto">
              {modalData.proposicao.ementa}
            </p>

            <div className="flex flex-wrap items-center justify-between gap-4 pt-1 text-xs text-slate-400">
              <div>
                Autor: <span className="text-slate-200 font-bold">{modalData.proposicao.autor_nome || "Não informado"}</span>
              </div>
              {modalData.sessao?.data_hora && (
                <div>
                  Sessão: <span className="text-slate-200 font-medium">{modalData.sessao.data_hora.slice(0, 10)}</span>
                </div>
              )}
            </div>
          </div>
        ) : (
          <h3 id="proposition-vote-title" className="text-sm text-slate-300 font-semibold">
            Dados da matéria indisponíveis.
          </h3>
        )}
      </div>

      {/* CORPO DO MODAL */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {isLoadingModal ? (
          <div role="status" aria-live="polite" className="p-16 text-center text-slate-400 space-y-3">
            <div className="w-10 h-10 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto" aria-hidden="true" />
            <p className="text-sm">Buscando votos nominais de cada parlamentar...</p>
          </div>
        ) : votes.error ? (
          <ErrorState
            title="Não foi possível carregar os votos"
            message="A API não respondeu. Isso não significa que a matéria não tenha sido votada."
            onRetry={votes.retry}
          />
        ) : !hasNominalVotes ? (
          <div role="status" className="p-12 text-center text-slate-400 space-y-3 bg-slate-950/50 rounded-2xl border border-slate-800">
            <Vote className="w-10 h-10 text-slate-400 mx-auto" aria-hidden="true" />
            <h4 className="text-base font-bold text-slate-200">Sem votação nominal registrada</h4>
            <p className="text-xs text-slate-400 max-w-md mx-auto">
              Não há votação nominal em plenário registrada para esta matéria na base de dados. Ela pode estar em tramitação nas comissões ou ter sido votada de forma simbólica.
            </p>
          </div>
        ) : (
          <>
            {/* BARRA DO PLACAR CONSOLIDADO */}
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
              <div className="bg-emerald-950/30 border border-emerald-500/30 rounded-2xl p-4 text-center">
                <span className="text-2xl sm:text-3xl font-black text-emerald-400 block">{placar?.sim ?? 0}</span>
                <span className="text-xs font-bold text-emerald-300 uppercase tracking-wider flex items-center justify-center gap-1 mt-1">
                  <Check className="w-3.5 h-3.5" aria-hidden="true" />
                  Votos SIM (A Favor)
                </span>
              </div>

              <div className="bg-rose-950/30 border border-rose-500/30 rounded-2xl p-4 text-center">
                <span className="text-2xl sm:text-3xl font-black text-rose-400 block">{placar?.nao ?? 0}</span>
                <span className="text-xs font-bold text-rose-300 uppercase tracking-wider flex items-center justify-center gap-1 mt-1">
                  <Ban className="w-3.5 h-3.5" aria-hidden="true" />
                  Votos NÃO (Contra)
                </span>
              </div>

              <div className="bg-slate-950/60 border border-slate-800 rounded-2xl p-4 text-center">
                <span className="text-2xl sm:text-3xl font-black text-slate-300 block">{placar?.abstencao ?? 0}</span>
                <span className="text-xs font-bold text-slate-400 uppercase tracking-wider block mt-1">Abstenções</span>
              </div>

              <div className="bg-slate-950/60 border border-slate-800 rounded-2xl p-4 text-center">
                <span className="text-2xl sm:text-3xl font-black text-purple-300 block">{placar?.obstrucao ?? 0}</span>
                <span className="text-xs font-bold text-slate-400 uppercase tracking-wider block mt-1">Obstruções</span>
              </div>

              <div className="bg-slate-950/60 border border-slate-800 rounded-2xl p-4 text-center">
                <span className="text-2xl sm:text-3xl font-black text-indigo-400 block">{placar?.total ?? 0}</span>
                <span className="text-xs font-bold text-slate-400 uppercase tracking-wider block mt-1">Total de Votos</span>
              </div>
            </div>

            {/* BARRA DE PROPORÇÃO VISUAL */}
            <div className="w-full bg-slate-950 h-3 rounded-full overflow-hidden flex border border-slate-800" aria-hidden="true">
              <div
                className="bg-emerald-500 h-full transition-all duration-700"
                style={{ width: `${((placar?.sim ?? 0) / total) * 100}%` }}
                title={`Sim: ${placar?.sim ?? 0}`}
              />
              <div
                className="bg-rose-500 h-full transition-all duration-700"
                style={{ width: `${((placar?.nao ?? 0) / total) * 100}%` }}
                title={`Não: ${placar?.nao ?? 0}`}
              />
            </div>

            {/* CAMPO DE BUSCA INTERNO NO MODAL */}
            <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
              <div className="relative flex-1">
                <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" aria-hidden="true" />
                <input
                  type="text"
                  aria-label="Buscar parlamentar por nome, partido ou UF nesta votação"
                  placeholder="Buscar parlamentar por nome, partido ou UF nesta votação..."
                  value={modalSearch}
                  onChange={(e) => setModalSearch(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-xs text-slate-200 placeholder-slate-400 focus:outline-none focus:border-indigo-500"
                />
                {modalSearch && (
                  <button
                    type="button"
                    aria-label="Limpar busca"
                    onClick={() => setModalSearch("")}
                    className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-200"
                  >
                    <X className="w-3.5 h-3.5" aria-hidden="true" />
                  </button>
                )}
              </div>

              {/* SELETOR DE ABA */}
              <div className="inline-flex flex-wrap rounded-xl bg-slate-950 p-1 border border-slate-800 text-xs">
                {tabs.map((tab) => (
                  <button
                    type="button"
                    key={tab.id}
                    aria-pressed={activeModalTab === tab.id}
                    onClick={() => setActiveModalTab(tab.id)}
                    className={`px-3 py-1.5 rounded-lg font-bold transition-colors ${
                      activeModalTab === tab.id ? tab.activeClass : tab.inactiveClass
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
            </div>

            {/* COLUNAS DE VOTOS */}
            <div
              className={`grid gap-6 ${
                activeModalTab === "lado_a_lado" ? "grid-cols-1 md:grid-cols-2" : "grid-cols-1"
              }`}
            >
              {(activeModalTab === "lado_a_lado" || activeModalTab === "sim") &&
                renderColumn(
                  "Quem votou SIM (A Favor)",
                  <Check className="w-4 h-4" aria-hidden="true" />,
                  filteredVotosSim,
                  emerald,
                  "Nenhum voto SIM encontrado para a busca."
                )}
              {(activeModalTab === "lado_a_lado" || activeModalTab === "nao") &&
                renderColumn(
                  "Quem votou NÃO (Contra)",
                  <Ban className="w-4 h-4" aria-hidden="true" />,
                  filteredVotosNao,
                  rose,
                  "Nenhum voto NÃO encontrado para a busca."
                )}
              {activeModalTab === "abstencao" &&
                renderColumn(
                  "Abstenções",
                  <Vote className="w-4 h-4" aria-hidden="true" />,
                  filteredVotosAbstencao,
                  amber,
                  "Nenhuma abstenção encontrada para a busca."
                )}
              {activeModalTab === "obstrucao" &&
                renderColumn(
                  "Obstruções",
                  <Ban className="w-4 h-4" aria-hidden="true" />,
                  filteredVotosObstrucao,
                  purple,
                  "Nenhuma obstrução encontrada para a busca."
                )}
            </div>
          </>
        )}
      </div>

      {/* RODAPÉ DO MODAL */}
      <div className="p-4 bg-slate-950 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400">
        <span className="flex items-center gap-1.5">
          <FileText className="w-4 h-4 text-slate-400" aria-hidden="true" />
          Dados oficiais abertos da Câmara dos Deputados e do Senado Federal
        </span>
        <button
          type="button"
          onClick={onClose}
          className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-semibold transition-colors"
        >
          Fechar
        </button>
      </div>
    </Modal>
  );
}
