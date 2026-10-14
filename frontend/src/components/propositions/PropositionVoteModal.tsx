"use client";

import React, { useState, useMemo } from "react";
import {
  ParlamentarVotoNominalItem,
  getPropositionNominalVotesSplit,
  DeliberacaoItem,
} from "@/services/api";
import {
  X,
  Vote,
  Check,
  Ban,
  Search,
  ExternalLink,
  FileText,
  Landmark,
  Users,
  Info,
  Calendar,
  ShieldCheck,
  FileCheck,
} from "lucide-react";
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

function getOrientacaoBadge(orientacao: string) {
  const norm = orientacao.toUpperCase();
  if (norm === "SIM") {
    return {
      bg: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
      icon: <Check className="w-3.5 h-3.5 text-emerald-400" aria-hidden="true" />,
    };
  }
  if (norm === "NAO" || norm === "NÃO") {
    return {
      bg: "bg-rose-500/20 text-rose-300 border-rose-500/30",
      icon: <Ban className="w-3.5 h-3.5 text-rose-400" aria-hidden="true" />,
    };
  }
  if (norm === "LIBERADO") {
    return {
      bg: "bg-sky-500/20 text-sky-300 border-sky-500/30",
      icon: <ShieldCheck className="w-3.5 h-3.5 text-sky-400" aria-hidden="true" />,
    };
  }
  if (norm === "OBSTRUCAO" || norm === "OBSTRUÇÃO") {
    return {
      bg: "bg-purple-500/20 text-purple-300 border-purple-500/30",
      icon: <Ban className="w-3.5 h-3.5 text-purple-400" aria-hidden="true" />,
    };
  }
  return {
    bg: "bg-amber-500/20 text-amber-300 border-amber-500/30",
    icon: <Vote className="w-3.5 h-3.5 text-amber-400" aria-hidden="true" />,
  };
}

export default function PropositionVoteModal({
  propId,
  onClose,
  onSelectPolitician,
  onSelectParty,
}: PropositionVoteModalProps) {
  const [modalSearch, setModalSearch] = useState<string>("");
  const [activeModalTab, setActiveModalTab] = useState<ModalTab>("lado_a_lado");
  const [selectedDeliberacaoId, setSelectedDeliberacaoId] = useState<string | null>(null);

  const debouncedSearch = useDebounce(modalSearch, 300);

  const votes = useApi(`nominal-votes:${propId}`, (signal) =>
    getPropositionNominalVotesSplit(propId, undefined, signal)
  );
  const modalData = votes.data ?? null;
  const isLoadingModal = votes.loading;

  const deliberacoes: DeliberacaoItem[] = useMemo(() => modalData?.deliberacoes ?? [], [modalData?.deliberacoes]);

  const activeDeliberacao: DeliberacaoItem | null = useMemo(() => {
    if (deliberacoes.length === 0) return null;
    if (selectedDeliberacaoId) {
      const found = deliberacoes.find((d) => d.id === selectedDeliberacaoId);
      if (found) return found;
    }
    const nominal = deliberacoes.find((d) => d.tipo_deliberacao === "NOMINAL");
    return nominal || deliberacoes[0];
  }, [deliberacoes, selectedDeliberacaoId]);

  const activeTipoDeliberacao = activeDeliberacao?.tipo_deliberacao ?? "NOMINAL";

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
                  className="inline-flex items-center gap-1.5 text-xs text-cyan-400 hover:text-cyan-300 bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/20 px-2.5 py-1 rounded-lg transition-colors font-medium"
                >
                  <span>Ler na Íntegra</span>
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

      {/* SELETOR DE HISTÓRICO DE DELIBERAÇÕES (MÓDULO 3) */}
      {deliberacoes.length > 0 && (
        <div className="px-6 py-3 bg-slate-950/50 border-b border-slate-800">
          <div className="flex items-center justify-between gap-3 mb-2 flex-wrap">
            <span className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
              <Calendar className="w-3.5 h-3.5 text-cyan-400" aria-hidden="true" />
              Histórico de Deliberações ({deliberacoes.length})
            </span>
            <span className="text-[11px] text-slate-400">
              Selecione uma deliberação para auditar o quórum e a metodologia regimental
            </span>
          </div>

          <div className="flex items-center gap-2 overflow-x-auto pb-1">
            {deliberacoes.map((d) => {
              const isSelected = activeDeliberacao?.id === d.id;
              const isSimbolica = d.tipo_deliberacao === "SIMBOLICA";
              const isNominal = d.tipo_deliberacao === "NOMINAL";

              return (
                <button
                  type="button"
                  key={d.id}
                  onClick={() => setSelectedDeliberacaoId(d.id)}
                  className={`px-3 py-1.5 rounded-xl text-xs font-semibold flex items-center gap-2 transition-all shrink-0 border ${
                    isSelected
                      ? isNominal
                        ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/50 shadow-md shadow-emerald-950/40"
                        : isSimbolica
                        ? "bg-amber-500/20 text-amber-300 border-amber-500/50 shadow-md shadow-amber-950/40"
                        : "bg-sky-500/20 text-sky-300 border-sky-500/50 shadow-md shadow-sky-950/40"
                      : "bg-slate-900/80 text-slate-400 hover:text-slate-200 border-slate-800 hover:border-slate-700"
                  }`}
                >
                  {isNominal ? (
                    <Vote className="w-3.5 h-3.5 text-emerald-400" aria-hidden="true" />
                  ) : isSimbolica ? (
                    <Users className="w-3.5 h-3.5 text-amber-400" aria-hidden="true" />
                  ) : (
                    <Landmark className="w-3.5 h-3.5 text-sky-400" aria-hidden="true" />
                  )}
                  <span>
                    {isNominal
                      ? "Votação Nominal"
                      : isSimbolica
                      ? "Votação Simbólica"
                      : "Deliberação em Comissão"}
                  </span>
                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-950/70 text-slate-300 border border-slate-700/60 font-mono">
                    {d.local_deliberacao.split("-")[0].trim()}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}

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
        ) : activeTipoDeliberacao === "SIMBOLICA" ? (
          /* ========================================================================= */
          /* REGRA 6.3: SE tipo_deliberacao = 'SIMBOLICA'                              */
          /* Ocultar busca nominal individual e renderizar obrigatoriamente a matriz   */
          /* de orientacoes_partidarias com aviso educativo ao usuário.                */
          /* ========================================================================= */
          <div className="space-y-6" data-testid="simbolica-view">
            {/* AVISO EDUCATIVO DE VOTAÇÃO SIMBÓLICA */}
            <div className="p-4 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex items-start gap-3.5">
              <div className="p-2 rounded-xl bg-amber-500/20 text-amber-400 shrink-0 mt-0.5">
                <Info className="w-5 h-5" aria-hidden="true" />
              </div>
              <div className="space-y-1">
                <h4 className="text-sm font-bold text-amber-300">
                  Como funciona a Votação Simbólica no Congresso Nacional?
                </h4>
                <p className="text-xs text-amber-200/90 leading-relaxed">
                  No regime de deliberação simbólica, a matéria é decidida no Plenário por acordo visual e aclamação entre as bancadas partidárias, <strong>sem acionamento do painel eletrônico e sem registro de voto individual dos parlamentares</strong>. O Presidente da sessão proclama: <em>&quot;Os senhores parlamentares que aprovam permaneçam como se encontram&quot;</em>.
                </p>
                <p className="text-xs text-amber-300/80 font-medium pt-1">
                  💡 Para transparência cívica e conferência democrática, a expressão política é auditada formalmente através da <strong>matriz de orientação de bancada</strong> abaixo.
                </p>
              </div>
            </div>

            {/* RESUMO DA DECISÃO */}
            {activeDeliberacao?.resumo_decisao && (
              <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-300">
                <span className="font-bold text-white block mb-0.5">Decisão Proclamada em Plenário:</span>
                <span>{activeDeliberacao.resumo_decisao}</span>
              </div>
            )}

            {/* MATRIZ OBRIGATÓRIA DE ORIENTAÇÕES PARTIDÁRIAS */}
            <div className="space-y-3">
              <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                <h4 className="text-sm font-bold text-white flex items-center gap-2">
                  <Users className="w-4 h-4 text-cyan-400" aria-hidden="true" />
                  Matriz de Orientações Partidárias de Bancada
                </h4>
                <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700">
                  {activeDeliberacao?.orientacoes_partidarias?.length || 0} bancadas orientadas
                </span>
              </div>

              {(!activeDeliberacao?.orientacoes_partidarias || activeDeliberacao.orientacoes_partidarias.length === 0) ? (
                <p className="text-xs text-slate-400 italic py-6 text-center">
                  Orientações de bancada não formalizadas em ata para esta deliberação simbólica.
                </p>
              ) : (
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                  {activeDeliberacao.orientacoes_partidarias.map((op) => {
                    const badge = getOrientacaoBadge(op.orientacao);
                    return (
                      <div
                        key={op.partido_bancada}
                        className="p-3 rounded-xl bg-slate-950/70 border border-slate-800 hover:border-slate-700 transition-colors flex items-center justify-between gap-2"
                      >
                        <span className="text-xs font-black text-slate-100 truncate" title={op.partido_bancada}>
                          {op.partido_bancada}
                        </span>
                        <span
                          className={`text-[11px] font-bold px-2 py-0.5 rounded-lg border flex items-center gap-1 shrink-0 ${badge.bg}`}
                        >
                          {badge.icon}
                          {op.orientacao}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        ) : activeTipoDeliberacao === "COMISSAO" ? (
          /* ========================================================================= */
          /* REGRA 6.3: SE tipo_deliberacao = 'COMISSAO'                               */
          /* Exibir o nome da comissão, o link para a ata da reunião e os dados do     */
          /* parecer do relator associado.                                             */
          /* ========================================================================= */
          <div className="space-y-6" data-testid="comissao-view">
            {/* CARTÃO DA COMISSÃO TEMÁTICA PERMANENTE */}
            <div className="p-5 rounded-2xl bg-sky-950/20 border border-sky-500/30 space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 rounded-xl bg-sky-500/20 text-sky-400 shrink-0">
                    <Landmark className="w-6 h-6" aria-hidden="true" />
                  </div>
                  <div>
                    <span className="text-[10px] font-bold text-sky-400 uppercase tracking-wider block">
                      Comissão Permanente com Poder Conclusivo / Terminativo
                    </span>
                    <h4 className="text-base font-black text-white">
                      {activeDeliberacao?.nome_comissao || activeDeliberacao?.local_deliberacao}
                    </h4>
                  </div>
                </div>

                {/* LINK PARA A ATA DA REUNIÃO DELIBERATIVA */}
                {activeDeliberacao?.link_ata_reuniao && safeExternalUrl(activeDeliberacao.link_ata_reuniao) && (
                  <a
                    href={safeExternalUrl(activeDeliberacao.link_ata_reuniao)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold bg-sky-500/20 hover:bg-sky-500/30 text-sky-300 border border-sky-500/40 transition-colors shrink-0"
                  >
                    <FileText className="w-3.5 h-3.5" aria-hidden="true" />
                    <span>Acessar Ata Oficial da Reunião</span>
                    <ExternalLink className="w-3 h-3" aria-hidden="true" />
                  </a>
                )}
              </div>

              {activeDeliberacao?.resumo_decisao && (
                <div className="p-3 rounded-xl bg-slate-950/70 border border-sky-500/20 text-xs text-slate-200">
                  <span className="font-bold text-sky-300 block mb-0.5">Deliberação da Comissão:</span>
                  <span>{activeDeliberacao.resumo_decisao}</span>
                </div>
              )}
            </div>

            {/* DADOS DO PARECER DO RELATOR ASSOCIADO */}
            <div className="p-5 rounded-2xl bg-slate-950/70 border border-slate-800 space-y-4">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3 flex-wrap gap-2">
                <h4 className="text-sm font-bold text-white flex items-center gap-2">
                  <FileCheck className="w-4 h-4 text-emerald-400" aria-hidden="true" />
                  Parecer do Relator Associado
                </h4>
                {activeDeliberacao?.parecer_relator_numero && (
                  <span className="text-xs font-mono font-bold px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-300 border border-emerald-500/30">
                    {activeDeliberacao.parecer_relator_numero}
                  </span>
                )}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-1">
                  <span className="text-[11px] font-semibold text-slate-400 block">Relator Designado:</span>
                  <p className="text-sm font-bold text-slate-100 flex items-center gap-1.5">
                    <Users className="w-4 h-4 text-slate-400" aria-hidden="true" />
                    {activeDeliberacao?.relator_nome || "Relatoria da Comissão"}
                  </p>
                </div>

                {activeDeliberacao?.link_parecer_relator && safeExternalUrl(activeDeliberacao.link_parecer_relator) && (
                  <div className="flex sm:justify-end items-center">
                    <a
                      href={safeExternalUrl(activeDeliberacao.link_parecer_relator)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-300 border border-emerald-500/30 transition-colors"
                    >
                      <FileText className="w-3.5 h-3.5" aria-hidden="true" />
                      <span>Ver Íntegra do Parecer Técnico</span>
                      <ExternalLink className="w-3 h-3" aria-hidden="true" />
                    </a>
                  </div>
                )}
              </div>

              {activeDeliberacao?.parecer_relator_texto && (
                <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800/80 text-xs text-slate-300 leading-relaxed">
                  <span className="font-bold text-slate-200 block mb-1">Fundamentação e Conclusão do Parecer:</span>
                  <p>{activeDeliberacao.parecer_relator_texto}</p>
                </div>
              )}
            </div>
          </div>
        ) : !hasNominalVotes ? (
          /* ========================================================================= */
          /* CASO SEM VOTOS NOMINAIS REGISTRADOS                                       */
          /* ========================================================================= */
          <div role="status" className="p-12 text-center text-slate-400 space-y-3 bg-slate-950/50 rounded-2xl border border-slate-800">
            <Vote className="w-10 h-10 text-slate-400 mx-auto" aria-hidden="true" />
            <h4 className="text-base font-bold text-slate-200">Sem votação nominal registrada</h4>
            <p className="text-xs text-slate-400 max-w-md mx-auto">
              Não há votação nominal em plenário registrada para esta matéria na base de dados. Ela pode ter sido deliberada em comissões ou votada de forma simbólica.
            </p>
          </div>
        ) : (
          /* ========================================================================= */
          /* REGRA 6.3: SE tipo_deliberacao = 'NOMINAL'                                */
          /* Renderizar a lista explícita de votos_nominais com busca e abas           */
          /* ========================================================================= */
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

            {/* COLUNAS DE VOTOS NOMINAIS */}
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
          Dados oficiais abertos da Câmara dos Deputados e do Senado Federal (Módulo 3 - Histórico de Deliberações)
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
