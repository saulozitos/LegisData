"use client";

import React, { useState, useEffect, useMemo } from "react";
import {
  Landmark,
  ShieldCheck,
  ShieldAlert,
  Users,
  Award,
  BarChart3,
  CheckCircle2,
  AlertCircle,
  Search,
  X,
  Sparkles,
  MousePointerClick
} from "lucide-react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell
} from "recharts";
import {
  getCongressComposition,
  CongressCompositionResponse,
  LeaderProfile,
  PartySeat,
  searchPoliticians,
  PoliticoSearchResultItem
} from "../services/api";

interface CongressCompositionPanelProps {
  mandateId: string;
  onSelectPolitician?: (id: string) => void;
  onPoliticianSelect?: (id: string) => void;
  onSelectParty?: (partido: string) => void;
}

export default function CongressCompositionPanel({
  mandateId,
  onSelectPolitician,
  onPoliticianSelect,
  onSelectParty,
}: CongressCompositionPanelProps) {
  const [data, setData] = useState<CongressCompositionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeHouse, setActiveHouse] = useState<"camara" | "senado">("camara");

  // Estados do Modal Interativo de Parlamentares da Bancada
  const [selectedParty, setSelectedParty] = useState<string | null>(null);
  const [partyPoliticians, setPartyPoliticians] = useState<PoliticoSearchResultItem[]>([]);
  const [loadingParty, setLoadingParty] = useState<boolean>(false);
  const [partySearch, setPartySearch] = useState<string>("");

  useEffect(() => {
    async function loadComposition() {
      try {
        setLoading(true);
        const res = await getCongressComposition(mandateId);
        if (res) setData(res);
      } catch (err) {
        console.error("Erro ao carregar composição do congresso:", err);
      } finally {
        setLoading(false);
      }
    }
    loadComposition();
  }, [mandateId]);

  // Carregar parlamentares da bancada selecionada
  useEffect(() => {
    if (!selectedParty) {
      setPartyPoliticians([]);
      return;
    }

    async function fetchPartyMembers() {
      setLoadingParty(true);
      try {
        const targetOffice = activeHouse === "camara" ? "DEPUTADO_FEDERAL" : "SENADOR";
        const res = await searchPoliticians(undefined, targetOffice, selectedParty!, undefined, 200);
        setPartyPoliticians(res?.politicos || []);
      } catch (err) {
        console.error("Erro ao carregar parlamentares da bancada:", err);
        setPartyPoliticians([]);
      } finally {
        setLoadingParty(false);
      }
    }

    fetchPartyMembers();
  }, [selectedParty, activeHouse]);

  // Fechar modal com tecla Esc
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSelectedParty(null);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const handlePartyClick = (partido: string) => {
    if (!partido) return;
    if (onSelectParty) {
      onSelectParty(partido);
      return;
    }
    setSelectedParty(partido);
    setPartySearch("");
  };

  // Filtragem interna de parlamentares no modal
  const filteredPoliticians = useMemo(() => {
    if (!partySearch.trim()) return partyPoliticians;
    const s = partySearch.toLowerCase();
    return partyPoliticians.filter(
      (p) =>
        p.nome_eleitoral.toLowerCase().includes(s) ||
        p.nome_civil.toLowerCase().includes(s) ||
        p.uf.toLowerCase().includes(s)
    );
  }, [partyPoliticians, partySearch]);

  if (loading) {
    return (
      <div className="bg-slate-900/50 border border-slate-800 rounded-3xl p-8 text-center animate-pulse">
        <div className="h-6 bg-slate-800 rounded w-1/3 mx-auto mb-4" />
        <div className="h-64 bg-slate-800/40 rounded-2xl w-full" />
      </div>
    );
  }

  if (!data) return null;

  const currentHouse = activeHouse === "camara" ? data.camara : data.senado;
  const houseLabel = activeHouse === "camara" ? "Câmara dos Deputados (513 cadeiras)" : "Senado Federal (81 cadeiras)";
  const quorumPec = activeHouse === "camara" ? 308 : 49;
  const quorumSimples = activeHouse === "camara" ? 257 : 41;

  const { governabilidade } = currentHouse;

  return (
    <div className="space-y-6">
      {/* Cabeçalho de Governabilidade */}
      <div className="bg-slate-900/60 border border-slate-800/80 rounded-3xl p-6 backdrop-blur-md">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="p-2 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
                <Landmark className="w-5 h-5" />
              </span>
              <h2 className="text-xl font-extrabold text-slate-100 tracking-tight">
                Composição do Congresso & Governabilidade Presidencial
              </h2>
            </div>
            <p className="text-xs text-slate-400">
              Mandato de <strong>{data.presidente_republica}</strong> ({data.periodo}) • Presidência das Casas Legislativas e correlação de forças partidárias.
            </p>
          </div>

          {/* Seletor Câmara / Senado */}
          <div className="flex items-center bg-slate-950 p-1.5 rounded-2xl border border-slate-800 self-start md:self-auto">
            <button
              onClick={() => {
                setActiveHouse("camara");
                setSelectedParty(null);
              }}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${
                activeHouse === "camara"
                  ? "bg-cyan-500 text-slate-950 shadow-md"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Câmara dos Deputados
            </button>
            <button
              onClick={() => {
                setActiveHouse("senado");
                setSelectedParty(null);
              }}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${
                activeHouse === "senado"
                  ? "bg-cyan-500 text-slate-950 shadow-md"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Senado Federal
            </button>
          </div>
        </div>

        {/* Barra de Governabilidade Empilhada */}
        <div className="mt-6 bg-slate-950/70 border border-slate-800/90 rounded-2xl p-4">
          <div className="flex items-center justify-between text-xs mb-2.5">
            <span className="font-bold text-slate-300">
              Distribuição de Forças: {houseLabel}
            </span>
            <div className="flex items-center gap-3">
              <span className="flex items-center gap-1.5 text-emerald-400 font-bold">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
                Base ({governabilidade.base_aliada_cadeiras} cad. • {governabilidade.base_aliada_pct.toFixed(1)}%)
              </span>
              <span className="flex items-center gap-1.5 text-amber-400 font-bold">
                <span className="w-2.5 h-2.5 rounded-full bg-amber-500" />
                Centro ({governabilidade.centro_cadeiras} cad. • {governabilidade.centro_pct.toFixed(1)}%)
              </span>
              <span className="flex items-center gap-1.5 text-rose-400 font-bold">
                <span className="w-2.5 h-2.5 rounded-full bg-rose-500" />
                Oposição ({governabilidade.oposicao_cadeiras} cad. • {governabilidade.oposicao_pct.toFixed(1)}%)
              </span>
            </div>
          </div>

          {/* Barra Visual */}
          <div className="w-full h-4 bg-slate-900 rounded-full overflow-hidden flex shadow-inner">
            <div
              style={{ width: `${governabilidade.base_aliada_pct}%` }}
              className="bg-emerald-500 h-full transition-all duration-500"
              title={`Base Aliada: ${governabilidade.base_aliada_cadeiras} cadeiras`}
            />
            <div
              style={{ width: `${governabilidade.centro_pct}%` }}
              className="bg-amber-500 h-full transition-all duration-500"
              title={`Centro/Independente: ${governabilidade.centro_cadeiras} cadeiras`}
            />
            <div
              style={{ width: `${governabilidade.oposicao_pct}%` }}
              className="bg-rose-500 h-full transition-all duration-500"
              title={`Oposição: ${governabilidade.oposicao_cadeiras} cadeiras`}
            />
          </div>

          {/* Quóruns Constitucionais */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-4 pt-3 border-t border-slate-900 text-xs">
            <div className="flex items-center gap-2">
              {governabilidade.maioria_simples_atingida ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
              ) : (
                <AlertCircle className="w-4 h-4 text-amber-400 flex-shrink-0" />
              )}
              <span className="text-slate-300">
                <strong>Maioria Simples ({quorumSimples} votos):</strong>{" "}
                {governabilidade.maioria_simples_atingida
                  ? "Garantida exclusivamente pela bancada governista."
                  : "Dependente de negociação com o Centro/Independente."}
              </span>
            </div>

            <div className="flex items-center gap-2">
              {governabilidade.maioria_pec_atingida ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
              ) : (
                <ShieldAlert className="w-4 h-4 text-rose-400 flex-shrink-0" />
              )}
              <span className="text-slate-300">
                <strong>Quórum de PEC ({quorumPec} votos - 3/5):</strong>{" "}
                {governabilidade.maioria_pec_atingida
                  ? "Alcançado pela coalizão de sustentação."
                  : "Exige composição com partidos de Centro e Oposição moderada."}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Cards dos Presidentes da Casa */}
      <div className="bg-slate-900/60 border border-slate-800/80 rounded-3xl p-6 backdrop-blur-md">
        <div className="flex items-center gap-2 mb-4">
          <Award className="w-4 h-4 text-cyan-400" />
          <h3 className="text-sm font-bold text-slate-200">
            Presidentes da {activeHouse === "camara" ? "Câmara dos Deputados" : "Senado Federal"} no Mandato
          </h3>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {currentHouse.presidentes.map((p, idx) => (
            <div
              key={idx}
              className="bg-slate-950/70 border border-slate-800 hover:border-slate-700 rounded-2xl p-4 flex items-center gap-3.5 transition-all"
            >
              {p.foto_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={p.foto_url}
                  alt={p.nome}
                  referrerPolicy="no-referrer"
                  className="w-14 h-14 rounded-xl object-cover border border-slate-700 flex-shrink-0"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = "none";
                  }}
                />
              ) : (
                <div className="w-14 h-14 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center text-sm font-bold text-cyan-400 flex-shrink-0">
                  {p.partido}
                </div>
              )}
              <div>
                <h4 className="text-sm font-bold text-slate-100">{p.nome}</h4>
                <p className="text-xs text-slate-400 mt-0.5">
                  <span className="font-semibold text-cyan-400">{p.partido}</span> • {p.uf}
                </p>
                <span className="text-[11px] font-mono text-slate-500 block mt-1">
                  {p.periodo}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Gráfico de Bancadas Partidárias (INTERATIVO COM CLIQUE NAS BARRAS) */}
      <div className="bg-slate-900/60 border border-slate-800/80 rounded-3xl p-6 backdrop-blur-md space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-bold text-slate-200">
              Tamanho das Bancadas Partidárias na {activeHouse === "camara" ? "Câmara" : "Senado"}
            </h3>
          </div>
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-cyan-500/10 text-cyan-300 border border-cyan-500/20">
            <MousePointerClick className="w-3.5 h-3.5" />
            <span>Clique em qualquer barra para ver a lista de parlamentares</span>
          </div>
        </div>

        <div className="h-96 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={currentHouse.bancadas}
              layout="vertical"
              margin={{ top: 10, right: 30, left: 90, bottom: 0 }}
            >
              <XAxis type="number" stroke="#64748b" tick={{ fontSize: 11 }} />
              <YAxis
                type="category"
                dataKey="partido"
                stroke="#94a3b8"
                tick={{ fontSize: 11 }}
                width={85}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#090d16",
                  borderColor: "#334155",
                  borderRadius: "12px",
                  fontSize: "12px"
                }}
                formatter={(val: any, _: any, item: any) => [
                  `${val} cadeiras (${item.payload.percentual}%) - ${item.payload.alinhamento.replace("_", " ")} (Clique para abrir)`,
                  "Bancada"
                ]}
              />
              <Bar
                dataKey="cadeiras"
                radius={[0, 6, 6, 0]}
                className="cursor-pointer"
                onClick={(entry: any) => {
                  const sigla = entry?.partido || entry?.payload?.partido;
                  if (sigla) handlePartyClick(sigla);
                }}
              >
                {currentHouse.bancadas.map((entry, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={entry.cor_hex || "#3b82f6"}
                    className="cursor-pointer hover:opacity-80 transition-opacity"
                    onClick={() => handlePartyClick(entry.partido)}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ======================================================== */}
      {/* MODAL / GAVETA: PARLAMENTARES DA BANCADA PARTIDÁRIA      */}
      {/* ======================================================== */}
      {selectedParty && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-200"
          onClick={() => setSelectedParty(null)}
        >
          <div
            className="bg-slate-900 border border-slate-700 rounded-3xl w-full max-w-5xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden relative"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Cabeçalho do Modal */}
            <div className="p-6 border-b border-slate-800 bg-slate-950/90 relative">
              <button
                onClick={() => setSelectedParty(null)}
                className="absolute top-5 right-5 p-2 rounded-xl bg-slate-800/80 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>

              <div className="space-y-3 pr-8">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-black px-3 py-1 rounded-xl bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
                    Bancada: {selectedParty}
                  </span>
                  <span className="text-xs font-semibold px-2.5 py-1 rounded-lg bg-slate-800 text-slate-300 border border-slate-700">
                    {activeHouse === "camara" ? "Câmara dos Deputados" : "Senado Federal"}
                  </span>
                  {!loadingParty && (
                    <span className="text-xs font-bold px-2.5 py-1 rounded-lg bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                      {filteredPoliticians.length} parlamentares
                    </span>
                  )}
                </div>

                <h3 className="text-xl sm:text-2xl font-black text-white">
                  Parlamentares do {selectedParty} no(a) {activeHouse === "camara" ? "Câmara dos Deputados" : "Senado Federal"}
                </h3>

                <p className="text-xs sm:text-sm text-slate-400">
                  Lista nominal dos {activeHouse === "camara" ? "deputados federais" : "senadores"} filiados à legenda nesta legislatura.
                </p>

                {/* Campo de Busca Rápida Dentro do Modal */}
                <div className="relative pt-2">
                  <Search className="w-4 h-4 text-slate-500 absolute left-3 top-5" />
                  <input
                    type="text"
                    placeholder={`Buscar parlamentar do ${selectedParty} por nome ou UF (ex: SP, RJ, MG)...`}
                    value={partySearch}
                    onChange={(e) => setPartySearch(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
                  />
                  {partySearch && (
                    <button
                      onClick={() => setPartySearch("")}
                      className="absolute right-3 top-4.5 text-slate-500 hover:text-slate-300"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>
            </div>

            {/* Conteúdo com Grid de Cards */}
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {loadingParty ? (
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3 animate-pulse">
                  {Array.from({ length: 15 }).map((_, i) => (
                    <div key={i} className="h-44 bg-slate-950/60 border border-slate-800 rounded-2xl p-3" />
                  ))}
                </div>
              ) : filteredPoliticians.length === 0 ? (
                <div className="p-12 text-center text-slate-400 space-y-2 bg-slate-950/40 rounded-2xl border border-slate-800">
                  <Users className="w-8 h-8 text-slate-600 mx-auto" />
                  <p className="text-sm font-semibold text-slate-300">Nenhum parlamentar encontrado</p>
                  <p className="text-xs text-slate-500">
                    {partySearch ? "Tente outro termo de busca." : `Nenhum membro registrado para o ${selectedParty} nesta Casa.`}
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
                  {filteredPoliticians.map((pol) => (
                    <div
                      key={pol.id}
                      onClick={() => {
                        setSelectedParty(null);
                        if (onSelectPolitician) {
                          onSelectPolitician(pol.id);
                        } else if (onPoliticianSelect) {
                          onPoliticianSelect(pol.id);
                        }
                      }}
                      title={`Clique para abrir o Raio-X de ${pol.nome_eleitoral}`}
                      className="bg-slate-950/70 border border-slate-800/90 hover:border-cyan-400/80 rounded-2xl p-3 flex flex-col items-center text-center transition-all duration-200 hover:scale-[1.03] hover:bg-slate-900 group shadow-md cursor-pointer hover:shadow-cyan-950/40 relative"
                    >
                      {/* Foto */}
                      <div className="relative mb-2.5">
                        {pol.foto_url ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={pol.foto_url}
                            alt={pol.nome_eleitoral}
                            className="w-16 h-16 rounded-xl object-cover border border-slate-700 group-hover:border-cyan-400 transition-colors shadow-sm"
                            onError={(e) => {
                              (e.target as HTMLElement).style.display = "none";
                            }}
                          />
                        ) : (
                          <div className="w-16 h-16 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center text-sm font-bold text-slate-300">
                            {pol.nome_eleitoral.slice(0, 2).toUpperCase()}
                          </div>
                        )}
                        <span className="absolute -bottom-1 -right-1 text-[10px] font-black px-1.5 py-0.2 rounded bg-slate-900 text-cyan-300 border border-slate-700 shadow">
                          {pol.uf}
                        </span>
                      </div>

                      {/* Nome & Cargo */}
                      <span className="text-xs font-bold text-white group-hover:text-cyan-300 transition-colors line-clamp-2 leading-tight">
                        {pol.nome_eleitoral}
                      </span>
                      <span className="text-[10px] text-slate-400 mt-1 line-clamp-1" title={pol.nome_civil}>
                        {pol.nome_civil}
                      </span>

                      <div className="mt-auto pt-2 w-full flex items-center justify-center gap-1.5 text-[10px]">
                        <span className="px-2 py-0.5 rounded-md bg-slate-900 font-bold text-slate-300 border border-slate-800">
                          {pol.partido_sigla}
                        </span>
                        <span className="text-slate-500 font-semibold">{pol.uf}</span>
                      </div>

                      <div className="mt-2 text-[10px] font-semibold text-cyan-400/80 group-hover:text-cyan-300 flex items-center gap-1 transition-colors">
                        <span>Raio-X</span>
                        <span>→</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Rodapé do Modal */}
            <div className="p-4 bg-slate-950 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400">
              <span>
                Exibindo <strong>{filteredPoliticians.length}</strong> parlamentares da bancada do <strong>{selectedParty}</strong>
              </span>
              <button
                onClick={() => setSelectedParty(null)}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-semibold transition-colors"
              >
                Fechar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ======================================================== */}
      {/* SEÇÃO DE EDUCAÇÃO CÍVICA: ESTRUTURA E PAPEL DOS PODERES */}
      {/* ======================================================== */}
      <div className="bg-slate-950/70 border border-slate-800/90 rounded-2xl p-5 sm:p-6 space-y-5">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-4 border-b border-slate-900">
          <div className="flex items-center gap-2.5">
            <span className="p-2 rounded-xl bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
              <Landmark className="w-5 h-5" />
            </span>
            <div>
              <h3 className="text-base sm:text-lg font-bold text-slate-100">
                Educação Cívica: Como Funciona a Divisão de Poderes no Brasil?
              </h3>
              <p className="text-xs text-slate-400">
                Guia didático sobre as atribuições constitucionais de cada cargo que compõe a representação pública
              </p>
            </div>
          </div>
          <span className="text-[11px] font-semibold text-slate-500 px-3 py-1 rounded-full bg-slate-900 border border-slate-800">
            Constituição Federal de 1988
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {/* Card 1: Presidente da República */}
          <div className="bg-slate-900/80 border border-emerald-500/20 hover:border-emerald-500/40 rounded-xl p-4.5 space-y-2.5 transition-all">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
                <Users className="w-3.5 h-3.5" /> Poder Executivo Federal
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 font-bold">
                Mandato: 4 anos
              </span>
            </div>
            <h4 className="text-sm font-bold text-slate-100">
              Presidente da República
            </h4>
            <p className="text-xs text-slate-300 leading-relaxed">
              Chefe de Estado e de Governo. Administra o país, executa o orçamento da União, formula diretrizes econômicas, comanda as Forças Armadas, representa o Brasil internacionalmente e sanciona ou veta projetos de lei aprovados pelo Congresso.
            </p>
          </div>

          {/* Card 2: Governador */}
          <div className="bg-slate-900/80 border border-emerald-500/20 hover:border-emerald-500/40 rounded-xl p-4.5 space-y-2.5 transition-all">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
                <Users className="w-3.5 h-3.5" /> Poder Executivo Estadual
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 font-bold">
                Mandato: 4 anos
              </span>
            </div>
            <h4 className="text-sm font-bold text-slate-100">
              Governador de Estado
            </h4>
            <p className="text-xs text-slate-300 leading-relaxed">
              Comanda a administração pública estadual. Responsável primordial pelas políticas e forças de <strong>Segurança Pública</strong> (Polícias Militar e Civil), rede hospitalar e de saúde de alta complexidade estadual, e ensino médio público.
            </p>
          </div>

          {/* Card 3: Senador */}
          <div className="bg-slate-900/80 border border-cyan-500/20 hover:border-cyan-500/40 rounded-xl p-4.5 space-y-2.5 transition-all">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-cyan-400 uppercase tracking-wider flex items-center gap-1.5">
                <Landmark className="w-3.5 h-3.5" /> Congresso Nacional
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 font-bold">
                Mandato: 8 anos
              </span>
            </div>
            <h4 className="text-sm font-bold text-slate-100">
              Senador da República (Senado Federal)
            </h4>
            <p className="text-xs text-slate-300 leading-relaxed">
              Representante paritário dos 26 Estados e do Distrito Federal (3 por ente). Além de legislar, tem atribuição exclusiva de <strong>sabatinar e aprovar ministros do STF</strong>, diretores do Banco Central, embaixadores e julgar processos de impeachment.
            </p>
          </div>

          {/* Card 4: Deputado Federal */}
          <div className="bg-slate-900/80 border border-cyan-500/20 hover:border-cyan-500/40 rounded-xl p-4.5 space-y-2.5 transition-all">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-cyan-400 uppercase tracking-wider flex items-center gap-1.5">
                <Landmark className="w-3.5 h-3.5" /> Câmara dos Deputados
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 font-bold">
                Mandato: 4 anos
              </span>
            </div>
            <h4 className="text-sm font-bold text-slate-100">
              Deputado Federal
            </h4>
            <p className="text-xs text-slate-300 leading-relaxed">
              Representante direto do povo (proporcional à população de cada estado). Propõe e vota <strong>leis nacionais e reformas constitucionais</strong>, define a destinação do Orçamento da União via emendas e autoriza a abertura de processos contra o Presidente da República.
            </p>
          </div>

          {/* Card 5: Deputado Estadual */}
          <div className="bg-slate-900/80 border border-indigo-500/20 hover:border-indigo-500/40 rounded-xl p-4.5 space-y-2.5 transition-all md:col-span-2 lg:col-span-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-indigo-400 uppercase tracking-wider flex items-center gap-1.5">
                <Landmark className="w-3.5 h-3.5" /> Poder Legislativo Estadual
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 font-bold">
                Mandato: 4 anos
              </span>
            </div>
            <h4 className="text-sm font-bold text-slate-100">
              Deputado Estadual (Assembleias Legislativas)
            </h4>
            <p className="text-xs text-slate-300 leading-relaxed">
              Atua nas Assembleias Legislativas (ex: ALESP, ALERJ, ALEMG). Cria e aprova leis de abrangência estadual, fiscaliza os atos e gastos do Governador, aprova o orçamento estadual e acompanha as políticas públicas regionais implementadas pelas secretarias de Estado.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
