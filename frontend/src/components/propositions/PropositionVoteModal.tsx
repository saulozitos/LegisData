import React, { useState, useEffect, useMemo } from 'react';
import { PropositionNominalVotesSplitResponse, getPropositionNominalVotesSplit } from '@/services/api';
import { X, Vote, Check, Ban, Search, ExternalLink, FileText } from 'lucide-react';
import ParlamentarCard from './ParlamentarCard';
import { useDebounce } from '@/hooks/useDebounce';

interface PropositionVoteModalProps {
  propId: string;
  onClose: () => void;
  onSelectPolitician?: (id: string) => void;
  onSelectParty?: (sigla: string) => void;
}

export default function PropositionVoteModal({
  propId,
  onClose,
  onSelectPolitician,
  onSelectParty
}: PropositionVoteModalProps) {
  const [modalData, setModalData] = useState<PropositionNominalVotesSplitResponse | null>(null);
  const [isLoadingModal, setIsLoadingModal] = useState<boolean>(true);
  const [modalSearch, setModalSearch] = useState<string>("");
  const [activeModalTab, setActiveModalTab] = useState<"lado_a_lado" | "sim" | "nao">("lado_a_lado");

  const debouncedSearch = useDebounce(modalSearch, 300);

  useEffect(() => {
    let isMounted = true;
    const fetchModalVotes = async () => {
      setIsLoadingModal(true);
      try {
        const data = await getPropositionNominalVotesSplit(propId);
        if (isMounted) {
          setModalData(data);
        }
      } catch (err) {
        console.error("Erro ao carregar votos nominais da proposição:", err);
      } finally {
        if (isMounted) setIsLoadingModal(false);
      }
    };
    fetchModalVotes();
    return () => {
      isMounted = false;
    };
  }, [propId]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const filteredVotosSim = useMemo(() => {
    if (!modalData?.votos_sim) return [];
    if (!debouncedSearch.trim()) return modalData.votos_sim;
    const s = debouncedSearch.toLowerCase();
    return modalData.votos_sim.filter(
      (v) =>
        v.nome_eleitoral.toLowerCase().includes(s) ||
        v.partido_sigla.toLowerCase().includes(s) ||
        v.uf.toLowerCase().includes(s)
    );
  }, [modalData, debouncedSearch]);

  const filteredVotosNao = useMemo(() => {
    if (!modalData?.votos_nao) return [];
    if (!debouncedSearch.trim()) return modalData.votos_nao;
    const s = debouncedSearch.toLowerCase();
    return modalData.votos_nao.filter(
      (v) =>
        v.nome_eleitoral.toLowerCase().includes(s) ||
        v.partido_sigla.toLowerCase().includes(s) ||
        v.uf.toLowerCase().includes(s)
    );
  }, [modalData, debouncedSearch]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div
        className="bg-slate-900 border border-slate-700 rounded-3xl w-full max-w-5xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden relative"
        onClick={(e) => e.stopPropagation()}
      >
        {/* CABEÇALHO DO MODAL */}
        <div className="p-6 border-b border-slate-800 bg-slate-950/80 relative">
          <button
            onClick={onClose}
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
                {modalData.proposicao.url_oficial && (
                  <a
                    href={modalData.proposicao.url_oficial}
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
                          <ParlamentarCard 
                            key={parl.politico_id}
                            parl={parl}
                            borderColor="border-emerald-500/20"
                            onSelectPolitician={onSelectPolitician}
                            onSelectParty={onSelectParty}
                            onCloseModal={onClose}
                          />
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
                          <ParlamentarCard 
                            key={parl.politico_id}
                            parl={parl}
                            borderColor="border-rose-500/20"
                            onSelectPolitician={onSelectPolitician}
                            onSelectParty={onSelectParty}
                            onCloseModal={onClose}
                          />
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
            onClick={onClose}
            className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-semibold transition-colors"
          >
            Fechar
          </button>
        </div>
      </div>
    </div>
  );
}
