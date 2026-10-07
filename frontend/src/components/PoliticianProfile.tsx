"use client";

import React, { useState, useEffect, useMemo, useRef } from "react";
import {
  PoliticoBuscaItem,
  PoliticoDossier,
  searchPoliticians,
  getPoliticianDossier,
  getParties,
  PartidoCatalogoItem,
} from "@/services/api";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Cell,
  PieChart as RechartsPieChart,
  Pie,
} from "recharts";
import {
  Search,
  User,
  Users,
  Calendar,
  Building,
  Building2,
  DollarSign,
  FileText,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Award,
  Landmark,
  ShieldAlert,
  ShieldCheck,
  TrendingUp,
  MapPin,
  Clock,
  Sparkles,
  ChevronDown,
  Layers,
  ArrowRight,
  ArrowLeft,
  Filter,
  ExternalLink,
  Mail,
  Phone,
  Receipt,
  Scale,
  Gavel,
  Briefcase,
  FileCheck,
  Gauge,
  Coins,
  PieChart as LucidePieChart,
} from "lucide-react";

interface PoliticianProfileProps {
  selectedPoliticianId?: string | null;
  onSelectParty?: (sigla: string) => void;
}

function formatCpfCnpj(doc: string | null | undefined): string {
  if (!doc) return "Não informado";
  const clean = doc.replace(/\D/g, "");
  if (clean.length === 11) {
    return `***.${clean.slice(3, 6)}.${clean.slice(6, 9)}-**`;
  }
  if (clean.length === 14) {
    return `**.${clean.slice(2, 5)}.${clean.slice(5, 8)}/${clean.slice(8, 12)}-**`;
  }
  return doc;
}

export default function PoliticianProfile({
  selectedPoliticianId: initialPoliticianId,
  onSelectParty,
}: PoliticianProfileProps = {}) {
  const [searchTerm, setSearchTerm] = useState("");
  const [officeFilter, setOfficeFilter] = useState<string>("TODOS");
  const [searchResults, setSearchResults] = useState<PoliticoBuscaItem[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);

  const [selectedPoliticianId, setSelectedPoliticianId] = useState<string | null>(initialPoliticianId || null);
  const [dossier, setDossier] = useState<PoliticoDossier | null>(null);
  const [isLoadingDossier, setIsLoadingDossier] = useState(false);
  const [activeTab, setActiveTab] = useState<
    "visao_geral" | "proposicoes" | "financiamento" | "ceap" | "emendas" | "justica" | "assiduidade" | "remuneracao" | "votacoes"
  >("visao_geral");
  const [voteSearchTerm, setVoteSearchTerm] = useState<string>("");
  const [proposicaoFilter, setProposicaoFilter] = useState<"TODAS" | "IMPACTO" | "SIMBOLICO">("TODAS");
  const [proposicaoSearch, setProposicaoSearch] = useState<string>("");
  const [doacaoSearch, setDoacaoSearch] = useState<string>("");

  // Estados específicos da "Home do Raio-X" (quando nenhum político estiver selecionado)
  const [homeParty, setHomeParty] = useState<string>("TODOS");
  const [homeOffice, setHomeOffice] = useState<string>("TODOS");
  const [homeSearchTerm, setHomeSearchTerm] = useState<string>("");
  const [homePoliticians, setHomePoliticians] = useState<PoliticoBuscaItem[]>([]);
  const [isHomeLoading, setIsHomeLoading] = useState<boolean>(false);
  const [partiesList, setPartiesList] = useState<PartidoCatalogoItem[]>([]);

  const searchBoxRef = useRef<HTMLDivElement>(null);

  // Sincronizar quando prop externa mudar (ex: drill-down do painel de bancadas)
  useEffect(() => {
    if (initialPoliticianId) {
      setSelectedPoliticianId(initialPoliticianId);
    }
  }, [initialPoliticianId]);

  // Carregar catálogo de partidos para o Select da Home
  useEffect(() => {
    async function loadPartiesData() {
      try {
        const parties = await getParties();
        if (parties) {
          setPartiesList(parties);
        }
      } catch (err) {
        console.error("Erro ao carregar lista de partidos:", err);
      }
    }
    loadPartiesData();
  }, []);

  // Carregar políticos da Home do Raio-X quando selectedPoliticianId for nulo
  useEffect(() => {
    if (selectedPoliticianId) return;

    let isCancelled = false;
    async function loadHomePols() {
      setIsHomeLoading(true);
      try {
        const officeParam = homeOffice === "TODOS" ? undefined : homeOffice;
        const partyParam = homeParty === "TODOS" ? undefined : homeParty;
        const limitParam = homeParty === "TODOS" ? 500 : 300;
        const res = await searchPoliticians(undefined, officeParam, partyParam, undefined, limitParam);
        if (!isCancelled && res) {
          setHomePoliticians(res.politicos);
        }
      } catch (err) {
        console.error("Erro ao carregar políticos para a Home do Raio-X:", err);
      } finally {
        if (!isCancelled) setIsHomeLoading(false);
      }
    }

    loadHomePols();
    return () => {
      isCancelled = true;
    };
  }, [selectedPoliticianId, homeParty, homeOffice]);

  // Filtragem da grade da Home em memória
  const filteredHomePoliticians = useMemo(() => {
    if (!homeSearchTerm.trim()) return homePoliticians;
    const term = homeSearchTerm.toLowerCase();
    return homePoliticians.filter(
      (p) =>
        p.nome_eleitoral.toLowerCase().includes(term) ||
        p.nome_civil.toLowerCase().includes(term) ||
        p.uf.toLowerCase().includes(term) ||
        p.partido_sigla.toLowerCase().includes(term)
    );
  }, [homePoliticians, homeSearchTerm]);

  // Agrupamento por partido quando 'TODOS' estiver selecionado
  const groupedPoliticians = useMemo(() => {
    const groups: Record<string, PoliticoBuscaItem[]> = {};
    for (const pol of filteredHomePoliticians) {
      const sigla = pol.partido_sigla || "OUTROS";
      if (!groups[sigla]) groups[sigla] = [];
      groups[sigla].push(pol);
    }
    return Object.entries(groups).sort((a, b) => b[1].length - a[1].length);
  }, [filteredHomePoliticians]);

  // Mapa rápido de informações dos partidos
  const partyMetaMap = useMemo(() => {
    const map = new Map<string, PartidoCatalogoItem>();
    partiesList.forEach((p) => map.set(p.sigla.toUpperCase(), p));
    return map;
  }, [partiesList]);

  // Políticos em destaque para atalho rápido
  const quickPickList = [
    { label: "Baleia Rossi (MDB/SP)", search: "Baleia" },
    { label: "Arthur Lira (PP/AL)", search: "Lira" },
    { label: "Rodrigo Pacheco (PSD/MG)", search: "Pacheco" },
    { label: "Luiz Inácio Lula da Silva", search: "Lula" },
    { label: "Jair Bolsonaro", search: "Bolsonaro" },
    { label: "Eduardo Braga (MDB/AM)", search: "Braga" },
  ];

  // Buscar lista de políticos para autocomplete no campo superior
  useEffect(() => {
    const delayDebounce = setTimeout(async () => {
      setIsSearching(true);
      try {
        const officeParam = officeFilter === "TODOS" ? undefined : officeFilter;
        const res = await searchPoliticians(searchTerm || undefined, officeParam, undefined, undefined, 40);
        if (res) {
          setSearchResults(res.politicos);
        }
      } catch (err) {
        console.error("Erro na busca de políticos:", err);
      } finally {
        setIsSearching(false);
      }
    }, 250);

    return () => clearTimeout(delayDebounce);
  }, [searchTerm, officeFilter]);

  // Carregar Dossiê quando selectedPoliticianId mudar
  useEffect(() => {
    if (!selectedPoliticianId) return;

    async function loadDossier() {
      setIsLoadingDossier(true);
      try {
        const res = await getPoliticianDossier(selectedPoliticianId!);
        if (res) {
          setDossier(res);
          if (res.perfil?.nome_eleitoral) {
            setSearchTerm(res.perfil.nome_eleitoral);
          }
        }
      } catch (err) {
        console.error("Erro ao carregar dossiê do político:", err);
      } finally {
        setIsLoadingDossier(false);
      }
    }

    loadDossier();
  }, [selectedPoliticianId]);

  // Fechar dropdown ao clicar fora
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (searchBoxRef.current && !searchBoxRef.current.contains(event.target as Node)) {
        setIsDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSelectPolitician = (pol: PoliticoBuscaItem) => {
    setSelectedPoliticianId(pol.id);
    setSearchTerm(pol.nome_eleitoral);
    setIsDropdownOpen(false);
  };

  const perfil = dossier?.perfil;
  const assiduidade = dossier?.assiduidade;
  const remuneracao = dossier?.remuneracao;

  return (
    <div className="space-y-6">
      {/* ======================================================== */}
      {/* BARRA DE PESQUISA & AUTOCOMPLETE DO RAIO-X */}
      {/* ======================================================== */}
      <div className="bg-slate-900/70 border border-slate-800/90 rounded-2xl p-5 backdrop-blur-md shadow-xl shadow-cyan-950/10 space-y-4 relative z-50">
        <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="p-2 rounded-xl bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                <Search className="w-5 h-5" />
              </span>
              <h2 className="text-base sm:text-lg font-bold text-slate-100">
                Raio-X do Político: Dossiê e Transparência Individual
              </h2>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Consulte trajetória eletiva, fidelidade partidária, assiduidade regimental, remuneração e histórico de votações nominais
            </p>
          </div>

          {/* Filtro de Esfera / Cargo */}
          <div className="flex items-center gap-1.5 bg-slate-950 p-1 rounded-xl border border-slate-800">
            <button
              onClick={() => setOfficeFilter("TODOS")}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                officeFilter === "TODOS"
                  ? "bg-slate-800 text-slate-100"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Todos
            </button>
            <button
              onClick={() => setOfficeFilter("DEPUTADO_FEDERAL")}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                officeFilter === "DEPUTADO_FEDERAL"
                  ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Deputados
            </button>
            <button
              onClick={() => setOfficeFilter("SENADOR")}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                officeFilter === "SENADO"
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Senadores
            </button>
            <button
              onClick={() => setOfficeFilter("PRESIDENTE")}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                officeFilter === "PRESIDENTE"
                  ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Presidentes
            </button>
          </div>
        </div>

        {/* Input de Autocomplete Pesquisável */}
        <div ref={searchBoxRef} className="relative z-50 w-full">
          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => {
                setSearchTerm(e.target.value);
                setIsDropdownOpen(true);
              }}
              onFocus={() => setIsDropdownOpen(true)}
              placeholder="Digite o nome de um político para abrir o Raio-X (ex: Baleia Rossi, Arthur Lira, Lula, Pacheco)..."
              className="w-full bg-slate-950 border border-slate-700/80 rounded-xl pl-10 pr-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-400 transition-colors shadow-inner"
            />
            {isSearching && (
              <span className="absolute right-3.5 top-1/2 -translate-y-1/2 text-xs text-slate-500 animate-pulse">
                Buscando...
              </span>
            )}
          </div>

          {/* Dropdown de Sugestões em Tempo Real com Alta Prioridade de Sobreposição */}
          {isDropdownOpen && searchResults.length > 0 && (
            <div className="absolute left-0 right-0 top-full mt-2 bg-slate-950 border border-slate-800 rounded-xl max-h-72 overflow-y-auto shadow-2xl z-[100] divide-y divide-slate-900">
              {searchResults.map((pol) => (
                <div
                  key={pol.id}
                  onClick={() => handleSelectPolitician(pol)}
                  className="p-3 hover:bg-slate-900/90 cursor-pointer transition-colors flex items-center justify-between gap-3"
                >
                  <div className="flex items-center gap-3">
                    <div className="relative w-8 h-8 rounded-full overflow-hidden bg-slate-800 border border-slate-700 flex-shrink-0 flex items-center justify-center">
                      {pol.foto_url ? (
                        <img
                          src={pol.foto_url}
                          alt={pol.nome_eleitoral}
                          referrerPolicy="no-referrer"
                          className="w-full h-full object-cover"
                          onError={(e) => {
                            (e.target as HTMLImageElement).style.display = "none";
                          }}
                        />
                      ) : null}
                      <span className="text-[10px] font-bold text-slate-400 -z-10">
                        {pol.partido_sigla.slice(0, 2)}
                      </span>
                    </div>

                    <div>
                      <h4 className="text-xs font-bold text-slate-100">
                        {pol.nome_eleitoral}
                      </h4>
                      <p className="text-[11px] text-slate-400">
                        {pol.nome_civil}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    <span
                      onClick={(e) => {
                        if (onSelectParty && pol.partido_sigla) {
                          e.stopPropagation();
                          onSelectParty(pol.partido_sigla);
                        }
                      }}
                      className={`text-[10px] font-bold px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 font-mono ${
                        onSelectParty ? "cursor-pointer hover:underline hover:border-cyan-400" : ""
                      }`}
                      title={onSelectParty ? `Ver bancada do ${pol.partido_sigla}` : undefined}
                    >
                      {pol.partido_sigla}
                    </span>
                    <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
                      {pol.uf}
                    </span>
                    <span className="text-[10px] font-semibold text-slate-500">
                      {pol.cargo === "PRESIDENTE" ? "Presidente" : pol.cargo === "SENADOR" ? "Senador" : "Deputado"}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Atalhos Rápidos */}
        <div className="flex items-center gap-1.5 flex-wrap pt-1 text-xs">
          <span className="text-slate-500 font-semibold mr-1 flex items-center gap-1">
            <Sparkles className="w-3.5 h-3.5 text-amber-400" /> Consultas rápidas:
          </span>
          {quickPickList.map((item) => (
            <button
              key={item.label}
              onClick={() => {
                setSearchTerm(item.search);
                setIsDropdownOpen(true);
              }}
              className="px-2.5 py-1 rounded-lg bg-slate-950 border border-slate-800 hover:border-slate-700 text-slate-300 hover:text-cyan-300 text-xs transition-colors"
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {/* ======================================================== */}
      {/* DOSSIÊ COMPLETO DO POLÍTICO */}
      {/* ======================================================== */}
      {isLoadingDossier ? (
        <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-12 text-center animate-pulse space-y-4">
          <div className="w-20 h-20 bg-slate-800 rounded-full mx-auto" />
          <div className="h-6 bg-slate-800 rounded w-1/3 mx-auto" />
          <div className="h-32 bg-slate-800/40 rounded-xl w-full" />
        </div>
      ) : !dossier ? (
        /* ======================================================== */
        /* HOME DO RAIO-X: CATÁLOGO GERAL DE PARLAMENTARES */
        /* ======================================================== */
        <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-6 backdrop-blur-md shadow-2xl space-y-6">
          {/* Cabeçalho da Home */}
          <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 pb-6 border-b border-slate-800">
            <div className="flex items-center gap-3.5">
              <div className="p-3 rounded-2xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 flex-shrink-0">
                <Users className="w-6 h-6" />
              </div>
              <div>
                <h2 className="text-lg sm:text-xl font-black text-white">
                  Catálogo de Parlamentares: Home do Raio-X
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  Selecione um partido para explorar sua bancada ou clique em qualquer político para abrir o dossiê individual completo.
                </p>
              </div>
            </div>

            <div className="px-3.5 py-1.5 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono text-slate-300">
              Total exibido: <strong className="text-cyan-400">{filteredHomePoliticians.length}</strong> parlamentares
            </div>
          </div>

          {/* Barra de Filtros: Select de Partidos + Casa Legislativa + Busca Rápida */}
          <div className="grid grid-cols-1 md:grid-cols-12 gap-3.5 bg-slate-950/80 p-4 rounded-2xl border border-slate-800/80">
            {/* Select / Combobox de Partidos */}
            <div className="md:col-span-5 space-y-1.5">
              <label className="text-[11px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                <Filter className="w-3.5 h-3.5 text-cyan-400" /> Bancada Partidária
              </label>
              <select
                value={homeParty}
                onChange={(e) => setHomeParty(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700/80 rounded-xl px-3 py-2 text-xs font-semibold text-slate-100 focus:outline-none focus:border-cyan-400 transition-colors shadow-inner"
              >
                <option value="TODOS">Todos os Partidos (Agrupados por Bancada)</option>
                {partiesList.map((p) => (
                  <option key={p.id} value={p.sigla}>
                    {p.sigla} - {p.nome_completo} ({p.total_parlamentares} membros)
                  </option>
                ))}
              </select>
            </div>

            {/* Filtro de Cargo / Casa */}
            <div className="md:col-span-4 space-y-1.5">
              <label className="text-[11px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                <Landmark className="w-3.5 h-3.5 text-emerald-400" /> Casa Legislativa
              </label>
              <div className="flex items-center gap-1 bg-slate-900 p-1 rounded-xl border border-slate-700/80">
                <button
                  onClick={() => setHomeOffice("TODOS")}
                  className={`flex-1 py-1.5 rounded-lg text-[11px] font-semibold transition-all ${
                    homeOffice === "TODOS"
                      ? "bg-slate-800 text-white shadow-sm"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  Todos
                </button>
                <button
                  onClick={() => setHomeOffice("DEPUTADO_FEDERAL")}
                  className={`flex-1 py-1.5 rounded-lg text-[11px] font-semibold transition-all ${
                    homeOffice === "DEPUTADO_FEDERAL"
                      ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  Deputados
                </button>
                <button
                  onClick={() => setHomeOffice("SENADOR")}
                  className={`flex-1 py-1.5 rounded-lg text-[11px] font-semibold transition-all ${
                    homeOffice === "SENADOR"
                      ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  Senadores
                </button>
              </div>
            </div>

            {/* Busca Rápida na Grade */}
            <div className="md:col-span-3 space-y-1.5">
              <label className="text-[11px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                <Search className="w-3.5 h-3.5 text-amber-400" /> Filtrar Parlamentares
              </label>
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={homeSearchTerm}
                  onChange={(e) => setHomeSearchTerm(e.target.value)}
                  placeholder="Nome ou UF (ex: SP, RJ)..."
                  className="w-full bg-slate-900 border border-slate-700/80 rounded-xl pl-8 pr-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-400 transition-colors shadow-inner"
                />
              </div>
            </div>
          </div>

          {/* Grade de Parlamentares */}
          {isHomeLoading ? (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3.5 animate-pulse py-4">
              {Array.from({ length: 12 }).map((_, i) => (
                <div
                  key={i}
                  className="bg-slate-950/60 border border-slate-800 rounded-2xl p-4 h-48 flex flex-col items-center justify-center space-y-2.5"
                >
                  <div className="w-16 h-16 rounded-xl bg-slate-800" />
                  <div className="h-3.5 bg-slate-800 rounded w-3/4" />
                  <div className="h-3 bg-slate-800/60 rounded w-1/2" />
                </div>
              ))}
            </div>
          ) : filteredHomePoliticians.length === 0 ? (
            <div className="text-center py-16 space-y-3">
              <Users className="w-12 h-12 text-slate-600 mx-auto" />
              <p className="text-sm font-semibold text-slate-300">
                Nenhum parlamentar encontrado para o filtro selecionado.
              </p>
              <button
                onClick={() => {
                  setHomeParty("TODOS");
                  setHomeOffice("TODOS");
                  setHomeSearchTerm("");
                }}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-cyan-300 transition-colors"
              >
                Limpar Filtros da Home
              </button>
            </div>
          ) : homeParty !== "TODOS" ? (
            /* VISÃO DE PARTIDO ÚNICO SELECIONADO */
            <div className="space-y-4">
              {/* Cabeçalho do Partido Específico */}
              {(() => {
                const meta = partyMetaMap.get(homeParty.toUpperCase());
                return (
                  <div className="bg-slate-950/90 border border-slate-800 rounded-2xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <div
                        className="w-10 h-10 rounded-xl flex items-center justify-center font-black text-sm text-white shadow-md border border-white/10"
                        style={{ backgroundColor: meta?.cor_hex || "#1e293b" }}
                      >
                        {homeParty}
                      </div>
                      <div>
                        <h3 className="text-sm font-black text-white">
                          Bancada do {homeParty} {meta?.nome_completo ? `• ${meta.nome_completo}` : ""}
                        </h3>
                        <p className="text-xs text-slate-400">
                          {meta?.ideologia && <span className="text-cyan-400">{meta.ideologia}</span>}
                          {meta?.lema && <span className="italic ml-2">&ldquo;{meta.lema}&rdquo;</span>}
                        </p>
                      </div>
                    </div>
                    <div className="text-xs text-slate-400 font-medium">
                      Total: <strong className="text-white">{filteredHomePoliticians.length}</strong> parlamentares
                    </div>
                  </div>
                );
              })()}

              {/* Grade de Avatares do Partido */}
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3.5">
                {filteredHomePoliticians.map((pol) => (
                  <div
                    key={pol.id}
                    onClick={() => setSelectedPoliticianId(pol.id)}
                    title={`Clique para abrir o Raio-X de ${pol.nome_eleitoral}`}
                    className="bg-slate-950/70 border border-slate-800/90 hover:border-cyan-400/90 rounded-2xl p-3 flex flex-col items-center text-center transition-all duration-200 hover:scale-[1.03] hover:bg-slate-900 group shadow-md cursor-pointer hover:shadow-cyan-950/40 relative"
                  >
                    {/* Foto / Avatar */}
                    <div className="relative mb-2.5">
                      {pol.foto_url ? (
                        <img
                          src={pol.foto_url}
                          alt={pol.nome_eleitoral}
                          referrerPolicy="no-referrer"
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
                    <span
                      className="text-[10px] text-slate-400 mt-0.5 line-clamp-1"
                      title={pol.nome_civil}
                    >
                      {pol.nome_civil}
                    </span>

                    <div className="mt-auto pt-2 w-full flex items-center justify-center gap-1 text-[10px]">
                      <span className="px-1.5 py-0.5 rounded bg-slate-900 text-slate-400 font-semibold border border-slate-800">
                        {pol.cargo === "SENADOR" ? "Senador" : pol.cargo === "PRESIDENTE" ? "Presidente" : "Deputado"}
                      </span>
                      <span className="text-slate-500 font-bold">{pol.uf}</span>
                    </div>

                    <div className="mt-2 text-[10px] font-semibold text-cyan-400/80 group-hover:text-cyan-300 flex items-center gap-1 transition-colors">
                      <span>Raio-X</span>
                      <ArrowRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            /* VISÃO AGRUPADA POR PARTIDO (TODOS OS PARTIDOS) */
            <div className="space-y-8">
              {groupedPoliticians.map(([sigla, pols]) => {
                const meta = partyMetaMap.get(sigla.toUpperCase());
                return (
                  <div key={sigla} className="space-y-3">
                    {/* Header do Grupo Partidário */}
                    <div className="flex items-center justify-between pb-2 border-b border-slate-800/80">
                      <div className="flex items-center gap-2.5">
                        <div
                          className="w-7 h-7 rounded-lg flex items-center justify-center font-bold text-xs text-white shadow-sm border border-white/10"
                          style={{ backgroundColor: meta?.cor_hex || "#1e293b" }}
                        >
                          {sigla}
                        </div>
                        <h3 className="text-sm font-bold text-white flex items-center gap-2">
                          <span>Bancada do {sigla}</span>
                          {meta?.nome_completo && (
                            <span className="text-xs text-slate-400 font-normal hidden sm:inline">
                              ({meta.nome_completo})
                            </span>
                          )}
                        </h3>
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-800 text-cyan-300 font-semibold">
                          {pols.length} parlamentares
                        </span>
                      </div>

                      <button
                        onClick={() => setHomeParty(sigla)}
                        className="text-[11px] font-semibold text-cyan-400 hover:text-cyan-300 flex items-center gap-1 transition-colors"
                      >
                        <span>Ver só {sigla}</span>
                        <ArrowRight className="w-3 h-3" />
                      </button>
                    </div>

                    {/* Grade de Avatares daquele Partido */}
                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3.5">
                      {pols.map((pol) => (
                        <div
                          key={pol.id}
                          onClick={() => setSelectedPoliticianId(pol.id)}
                          title={`Clique para abrir o Raio-X de ${pol.nome_eleitoral}`}
                          className="bg-slate-950/70 border border-slate-800/90 hover:border-cyan-400/90 rounded-2xl p-3 flex flex-col items-center text-center transition-all duration-200 hover:scale-[1.03] hover:bg-slate-900 group shadow-md cursor-pointer hover:shadow-cyan-950/40 relative"
                        >
                          {/* Foto / Avatar */}
                          <div className="relative mb-2.5">
                            {pol.foto_url ? (
                              <img
                                src={pol.foto_url}
                                alt={pol.nome_eleitoral}
                                referrerPolicy="no-referrer"
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
                          <span
                            className="text-[10px] text-slate-400 mt-0.5 line-clamp-1"
                            title={pol.nome_civil}
                          >
                            {pol.nome_civil}
                          </span>

                          <div className="mt-auto pt-2 w-full flex items-center justify-center gap-1 text-[10px]">
                            <span className="px-1.5 py-0.5 rounded bg-slate-900 text-slate-400 font-semibold border border-slate-800">
                              {pol.cargo === "SENADOR" ? "Senador" : pol.cargo === "PRESIDENTE" ? "Presidente" : "Deputado"}
                            </span>
                            <span className="text-slate-500 font-bold">{pol.uf}</span>
                          </div>

                          <div className="mt-2 text-[10px] font-semibold text-cyan-400/80 group-hover:text-cyan-300 flex items-center gap-1 transition-colors">
                            <span>Raio-X</span>
                            <ArrowRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-6">
          {/* Barra Superior de Retorno à Home do Raio-X */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 bg-slate-900/60 border border-slate-800 rounded-2xl">
            <button
              onClick={() => {
                setSelectedPoliticianId(null);
                setDossier(null);
                setSearchTerm("");
              }}
              className="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl bg-slate-950 hover:bg-slate-800 text-slate-300 hover:text-cyan-300 border border-slate-700/80 transition-all text-xs font-semibold shadow-md group max-w-fit"
            >
              <ArrowLeft className="w-4 h-4 group-hover:-translate-x-1 transition-transform text-cyan-400" />
              <span>← Voltar ao Catálogo Geral (Home do Raio-X)</span>
            </button>

            <div className="text-xs text-slate-400">
              Visualizando dossiê de <strong className="text-white">{perfil?.nome_eleitoral}</strong>{" "}
              <span className="font-mono text-cyan-400 font-bold">
                (
                <span
                  onClick={() => onSelectParty && perfil?.partido_atual && onSelectParty(perfil.partido_atual)}
                  className={onSelectParty ? "cursor-pointer hover:underline" : ""}
                  title={onSelectParty ? `Ver bancada do ${perfil?.partido_atual}` : undefined}
                >
                  {perfil?.partido_atual}
                </span>
                /{perfil?.uf})
              </span>
            </div>
          </div>

          {/* Card Principal do Perfil */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 backdrop-blur-md relative overflow-hidden shadow-xl">
            <div className="absolute top-0 right-0 w-80 h-80 bg-cyan-500/5 rounded-full blur-3xl pointer-events-none" />

            <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6 pb-6 border-b border-slate-800">
              <div className="flex items-center gap-4.5">
                {/* Foto Oficial */}
                <div className="relative w-20 h-20 sm:w-24 sm:h-24 rounded-2xl overflow-hidden bg-slate-800 border-2 border-cyan-500/40 shadow-lg flex-shrink-0 flex items-center justify-center">
                  {perfil?.foto_url ? (
                    <img
                      src={perfil.foto_url}
                      alt={perfil.nome_eleitoral}
                      referrerPolicy="no-referrer"
                      className="w-full h-full object-cover object-top"
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = "none";
                      }}
                    />
                  ) : null}
                  <div className="absolute inset-0 bg-slate-800 -z-10 flex items-center justify-center font-bold text-cyan-400 text-lg">
                    {perfil?.partido_atual?.slice(0, 2) || "PL"}
                  </div>
                </div>

                {/* Identificação */}
                <div className="space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span
                      onClick={() => onSelectParty && perfil?.partido_atual && onSelectParty(perfil.partido_atual)}
                      className={`text-xs font-mono font-bold px-2.5 py-0.5 rounded-lg bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 ${
                        onSelectParty ? "cursor-pointer hover:underline hover:border-cyan-400" : ""
                      }`}
                      title={onSelectParty ? `Ver bancada do ${perfil?.partido_atual}` : undefined}
                    >
                      {perfil?.partido_atual}
                    </span>
                    <span className="text-xs font-semibold px-2 py-0.5 rounded-lg bg-slate-800 text-slate-300">
                      {perfil?.cargo_atual === "PRESIDENTE" ? "Presidente da República" : perfil?.cargo_atual === "SENADOR" ? "Senador Federal" : "Deputado Federal"}
                    </span>
                    <span className="text-xs font-semibold px-2 py-0.5 rounded-lg bg-slate-800 text-slate-400">
                      {perfil?.uf}
                    </span>
                  </div>

                  <h1 className="text-xl sm:text-2xl font-black text-slate-100">
                    {perfil?.nome_eleitoral}
                  </h1>
                  <p className="text-xs text-slate-400">
                    Nome Civil: <strong className="text-slate-300">{perfil?.nome_civil}</strong>
                  </p>
                  <p className="text-xs text-slate-500 flex items-center gap-1.5 pt-0.5">
                    <MapPin className="w-3.5 h-3.5 text-slate-400" />
                    Naturalidade: {perfil?.naturalidade}
                    {perfil?.data_nascimento && ` • Nascido em ${perfil.data_nascimento}`}
                  </p>
                </div>
              </div>

              {/* Badges de Atividade Parlamentar e Ficha Limpa */}
              <div className="flex flex-col sm:flex-row md:flex-col items-start md:items-end gap-2 text-xs">
                {/* Badge Ficha/Certidões Judicial */}
                <button
                  type="button"
                  onClick={() => setActiveTab("justica")}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-bold transition-all shadow-sm ${
                    dossier?.ficha_limpa?.possui_processos_declarados
                      ? "bg-rose-500/15 border-rose-500/40 text-rose-300 hover:bg-rose-500/25 ring-1 ring-rose-500/20"
                      : "bg-emerald-500/15 border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/25 ring-1 ring-emerald-500/20"
                  }`}
                  title="Clique para inspecionar as certidões judiciais no Raio-X"
                >
                  {dossier?.ficha_limpa?.possui_processos_declarados ? (
                    <>
                      <ShieldAlert className="w-4 h-4 text-rose-400 shrink-0" />
                      <span>Ficha/Certidões: Possui Processos Declarados</span>
                      {dossier.ficha_limpa.orgaos_declarados && dossier.ficha_limpa.orgaos_declarados.length > 0 && (
                        <span className="font-mono text-[10px] bg-rose-950/90 px-1.5 py-0.5 rounded text-rose-200 border border-rose-500/40">
                          {dossier.ficha_limpa.orgaos_declarados.join(", ")}
                        </span>
                      )}
                    </>
                  ) : (
                    <>
                      <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
                      <span>Ficha/Certidões: Nada Consta</span>
                      <span className="text-[10px] text-emerald-400/90 font-mono">(Ficha Limpa)</span>
                    </>
                  )}
                </button>

                <div className="flex items-center gap-2">
                  {perfil?.camara_id && (
                    <span className="px-3 py-1 rounded-xl bg-slate-950 border border-slate-800 text-slate-400">
                      Câmara ID: <strong className="text-cyan-400 font-mono">{perfil.camara_id}</strong>
                    </span>
                  )}
                  {perfil?.senado_id && (
                    <span className="px-3 py-1 rounded-xl bg-slate-950 border border-slate-800 text-slate-400">
                      Senado ID: <strong className="text-cyan-400 font-mono">{perfil.senado_id}</strong>
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* O BASÔMETRO: TAXA DE ALINHAMENTO COM O GOVERNO */}
            <div className="mt-6 bg-gradient-to-r from-slate-900/95 via-slate-950/95 to-slate-900/95 border border-cyan-500/30 hover:border-cyan-500/50 rounded-2xl p-4.5 shadow-xl transition-all relative overflow-hidden backdrop-blur-sm">
              <div className="absolute top-0 right-0 w-80 h-80 bg-cyan-500/5 rounded-full blur-3xl -z-10 pointer-events-none" />

              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-800/80">
                <div className="flex items-center gap-2.5">
                  <span className="p-2 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 shadow-inner">
                    <Gauge className="w-5 h-5" />
                  </span>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-cyan-400 uppercase tracking-wider">
                        O Basômetro (Alinhamento Governista)
                      </span>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 font-bold">
                        Radar de Votações
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-400">
                      Cruzamento das deliberações com a orientação do governo federal no Congresso Nacional
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-xs text-slate-400">Classificação:</span>
                  <span
                    className={`text-xs font-extrabold px-2.5 py-1 rounded-xl border font-mono ${
                      (dossier?.basometro?.taxa_governismo_pct ?? 0) >= 70
                        ? "bg-emerald-500/15 border-emerald-500/40 text-emerald-300 ring-1 ring-emerald-500/20"
                        : (dossier?.basometro?.taxa_governismo_pct ?? 0) <= 35
                        ? "bg-rose-500/15 border-rose-500/40 text-rose-300 ring-1 ring-rose-500/20"
                        : "bg-amber-500/15 border-amber-500/40 text-amber-300 ring-1 ring-amber-500/20"
                    }`}
                  >
                    {dossier?.basometro?.classificacao || "Em análise"}
                  </span>
                </div>
              </div>

              {/* Barra de Progresso Horizontal: Taxa de Governismo */}
              <div className="pt-3.5 space-y-2">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs sm:text-sm font-bold text-slate-200">
                      Taxa de Governismo:
                    </span>
                    <span className="text-lg sm:text-2xl font-black font-mono text-cyan-400">
                      {dossier?.basometro?.taxa_governismo_pct ?? 0}%
                    </span>
                    <span className="text-xs text-slate-400">de alinhamento nas votações</span>
                  </div>
                  <span className="text-xs text-slate-400 font-mono">
                    {dossier?.basometro?.votos_alinhados ?? 0} favoráveis / {dossier?.basometro?.votos_divergentes ?? 0} contrários
                  </span>
                </div>

                {/* Barra Estilizada com Gradiente e Marcador */}
                <div className="w-full bg-slate-950 rounded-full h-3.5 relative overflow-hidden border border-slate-800 p-0.5">
                  <div
                    className={`h-full rounded-full transition-all duration-700 ease-out ${
                      (dossier?.basometro?.taxa_governismo_pct ?? 0) >= 70
                        ? "bg-gradient-to-r from-teal-500 via-cyan-400 to-emerald-400 shadow-lg shadow-emerald-500/20"
                        : (dossier?.basometro?.taxa_governismo_pct ?? 0) <= 35
                        ? "bg-gradient-to-r from-rose-600 via-rose-500 to-orange-400 shadow-lg shadow-rose-500/20"
                        : "bg-gradient-to-r from-amber-500 via-yellow-400 to-cyan-400 shadow-lg shadow-cyan-500/20"
                    }`}
                    style={{ width: `${Math.min(100, Math.max(0, dossier?.basometro?.taxa_governismo_pct ?? 0))}%` }}
                  />
                </div>

                {/* Régua de Orientação Política */}
                <div className="flex justify-between items-center text-[10px] text-slate-400 font-mono pt-0.5">
                  <span className="text-rose-400 font-semibold">0% Oposição</span>
                  <span className="text-slate-400">50% Independente</span>
                  <span className="text-emerald-400 font-semibold">100% Base Aliada</span>
                </div>

                {/* Sub-indicadores rápidos */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 pt-2">
                  <div className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-2.5 flex items-center justify-between text-xs">
                    <span className="text-slate-400">Votos com o Governo:</span>
                    <span className="font-mono font-bold text-emerald-400">
                      {dossier?.basometro?.votos_alinhados ?? 0}
                    </span>
                  </div>
                  <div className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-2.5 flex items-center justify-between text-xs">
                    <span className="text-slate-400">Votos Divergentes:</span>
                    <span className="font-mono font-bold text-rose-400">
                      {dossier?.basometro?.votos_divergentes ?? 0}
                    </span>
                  </div>
                  <div className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-2.5 flex items-center justify-between text-xs">
                    <span className="text-slate-400">Total Analisado:</span>
                    <button
                      type="button"
                      onClick={() => setActiveTab("votacoes")}
                      className="font-mono font-bold text-cyan-400 hover:underline flex items-center gap-1"
                      title="Ver histórico nominal de votos"
                    >
                      {dossier?.basometro?.total_votacoes_analisadas ?? 0} votos
                      <ArrowRight className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* PAINÉIS DE DESTAQUE NO TOPO: SALÁRIO & REMUNERAÇÃO E ASSIDUIDADE & FALTAS */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 pt-4">
              {/* PAINEL 1: SALÁRIO E REMUNERAÇÃO OFICIAL */}
              <div className="bg-gradient-to-br from-slate-900/90 via-slate-950/90 to-emerald-950/20 border border-emerald-500/30 hover:border-emerald-500/50 rounded-2xl p-4.5 space-y-3 shadow-lg transition-all">
                <div className="flex items-center justify-between pb-2 border-b border-slate-800/80">
                  <span className="flex items-center gap-2 text-xs font-bold text-emerald-400 uppercase tracking-wider">
                    <span className="p-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
                      <DollarSign className="w-4 h-4" />
                    </span>
                    Remuneração & Subsídio Oficial
                  </span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 font-bold">
                    Transparência Pública
                  </span>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  <div className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-3">
                    <span className="text-[10px] font-medium text-slate-400 block mb-1">
                      Salário Bruto
                    </span>
                    <span className="text-base sm:text-lg font-black font-mono text-cyan-400 block leading-tight">
                      R$ {remuneracao?.resumo?.salario_bruto_atual?.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                    </span>
                    <span className="text-[10px] text-slate-500 mt-1 block">
                      Subsídio mensal
                    </span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-3">
                    <span className="text-[10px] font-medium text-slate-400 block mb-1">
                      Salário Líquido
                    </span>
                    <span className="text-base sm:text-lg font-black font-mono text-emerald-400 block leading-tight">
                      R$ {remuneracao?.resumo?.salario_liquido_atual?.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                    </span>
                    <span className="text-[10px] text-emerald-500/90 mt-1 block font-medium">
                      Após deduções oficiais
                    </span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-3 col-span-2 sm:col-span-1">
                    <span className="text-[10px] font-medium text-slate-400 block mb-1">
                      Cota CEAP (Média)
                    </span>
                    <span className="text-base sm:text-lg font-black font-mono text-amber-400 block leading-tight">
                      R$ {remuneracao?.resumo?.media_ceap_mensal?.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                    </span>
                    <span className="text-[10px] text-slate-500 mt-1 block">
                      Gasto atividade / mês
                    </span>
                  </div>
                </div>
              </div>

              {/* PAINEL 2: ASSIDUIDADE E CONTROLE DE FALTAS */}
              <div className="bg-gradient-to-br from-slate-900/90 via-slate-950/90 to-rose-950/20 border border-rose-500/30 hover:border-rose-500/50 rounded-2xl p-4.5 space-y-3 shadow-lg transition-all">
                <div className="flex items-center justify-between pb-2 border-b border-slate-800/80">
                  <span className="flex items-center gap-2 text-xs font-bold text-rose-400 uppercase tracking-wider">
                    <span className="p-1.5 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400">
                      <AlertTriangle className="w-4 h-4" />
                    </span>
                    Assiduidade & Faltas no Plenário
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setActiveTab("justica")}
                      className={`text-[10px] font-mono px-2 py-0.5 rounded border font-bold flex items-center gap-1 transition-all ${
                        dossier?.ficha_limpa?.possui_processos_declarados
                          ? "bg-rose-500/15 text-rose-300 border-rose-500/30 hover:bg-rose-500/25"
                          : "bg-emerald-500/15 text-emerald-300 border-emerald-500/30 hover:bg-emerald-500/25"
                      }`}
                      title="Ver certidões judiciais do parlamentar"
                    >
                      {dossier?.ficha_limpa?.possui_processos_declarados ? (
                        <>
                          <ShieldAlert className="w-3 h-3 text-rose-400 shrink-0" />
                          <span>Processos Declarados</span>
                        </>
                      ) : (
                        <>
                          <ShieldCheck className="w-3 h-3 text-emerald-400 shrink-0" />
                          <span>Ficha Limpa</span>
                        </>
                      )}
                    </button>
                    <span className={`text-[10px] font-mono px-2 py-0.5 rounded border font-bold ${
                      (assiduidade?.taxa_presenca_pct || 0) >= 90
                        ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/20"
                        : "bg-amber-500/10 text-amber-300 border-amber-500/20"
                    }`}>
                      {assiduidade?.taxa_presenca_pct}% de Presença
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-2.5">
                  {/* Total de Faltas */}
                  <div className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-3">
                    <span className="text-[10px] font-medium text-slate-400 block mb-1">
                      Total de Faltas
                    </span>
                    <span className="text-base sm:text-lg font-black font-mono text-slate-100 block leading-tight">
                      {((assiduidade?.faltas_justificadas || 0) + (assiduidade?.faltas_nao_justificadas || 0))}
                    </span>
                    <span className="text-[10px] text-slate-500 mt-1 block">
                      Em {assiduidade?.total_sessoes} sessões
                    </span>
                  </div>

                  {/* Faltas Justificadas */}
                  <div className="bg-slate-950/70 border border-amber-500/20 rounded-xl p-3">
                    <span className="text-[10px] font-medium text-amber-400/90 block mb-1">
                      Justificadas
                    </span>
                    <span className="text-base sm:text-lg font-black font-mono text-amber-400 block leading-tight">
                      {assiduidade?.faltas_justificadas || 0}
                    </span>
                    <span className="text-[10px] text-amber-500/80 mt-1 block">
                      Motivo formal
                    </span>
                  </div>

                  {/* Faltas Não Justificadas */}
                  <div className="bg-slate-950/70 border border-rose-500/30 rounded-xl p-3">
                    <span className="text-[10px] font-medium text-rose-400/90 block mb-1">
                      Não Justificadas
                    </span>
                    <span className="text-base sm:text-lg font-black font-mono text-rose-400 block leading-tight">
                      {assiduidade?.faltas_nao_justificadas || 0}
                    </span>
                    <span className="text-[10px] text-rose-500/80 mt-1 block font-medium">
                      Sem justificativa
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Mini-resumo de Mandatos & Legendas */}
            <div className="mt-3.5 bg-slate-950/50 border border-slate-800/80 rounded-xl p-3 flex flex-wrap items-center justify-between text-xs text-slate-400 gap-3">
              <div className="flex items-center gap-2">
                <Award className="w-4 h-4 text-purple-400" />
                <span>Atuação Parlamentar: <strong>{dossier?.trajetoria_mandatos?.length}</strong> mandato(s) registrado(s)</span>
              </div>
              <div className="flex items-center gap-4">
                <span><strong>{dossier?.filiacoes_partidarias?.length}</strong> partido(s) no histórico</span>
                <span>•</span>
                <span><strong>{dossier?.materias_propostas?.length}</strong> proposição(ões) de autoria</span>
                <span>•</span>
                <span><strong>{assiduidade?.total_presencas}</strong> presenças registradas</span>
              </div>
            </div>
          </div>

          {/* Sistema de Abas Internas do Dossiê */}
          <div className="flex items-center gap-2 border-b border-slate-800 pb-2 overflow-x-auto">
            <button
              onClick={() => setActiveTab("visao_geral")}
              className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 whitespace-nowrap ${
                activeTab === "visao_geral"
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Layers className="w-3.5 h-3.5" /> Visão Geral & Trajetória
            </button>

            <button
              onClick={() => setActiveTab("proposicoes")}
              className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 whitespace-nowrap ${
                activeTab === "proposicoes"
                  ? "bg-purple-500/20 text-purple-300 border border-purple-500/40"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <LucidePieChart className="w-3.5 h-3.5" /> Proposições & Relevância ({dossier?.materias_propostas?.length || 0})
              {dossier?.relevancia_legislativa ? (
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-purple-500/20 text-purple-300">
                  {dossier.relevancia_legislativa.percentual_impacto}% Impacto
                </span>
              ) : null}
            </button>

            <button
              onClick={() => setActiveTab("financiamento")}
              className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 whitespace-nowrap ${
                activeTab === "financiamento"
                  ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Coins className="w-3.5 h-3.5" /> Quem Paga a Conta?
              {dossier?.financiamento_campanha?.total_arrecadado ? (
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-emerald-500/20 text-emerald-300">
                  R$ {(dossier.financiamento_campanha.total_arrecadado / 1000000).toFixed(1)}M
                </span>
              ) : null}
            </button>

            <button
              onClick={() => setActiveTab("ceap")}
              className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 whitespace-nowrap ${
                activeTab === "ceap"
                  ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Receipt className="w-3.5 h-3.5" /> Custos do Mandato (CEAP)
              {dossier?.custos_ceap?.gasto_total_recente ? (
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-300">
                  R$ {(dossier.custos_ceap.gasto_total_recente / 1000).toFixed(0)}k
                </span>
              ) : null}
            </button>

            <button
              onClick={() => setActiveTab("emendas")}
              className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 whitespace-nowrap ${
                activeTab === "emendas"
                  ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Landmark className="w-3.5 h-3.5" /> Destino das Emendas
              {dossier?.emendas_parlamentares?.total_pago ? (
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-emerald-500/20 text-emerald-300">
                  R$ {(dossier.emendas_parlamentares.total_pago / 1000000).toFixed(1)}M
                </span>
              ) : null}
            </button>

            <button
              onClick={() => setActiveTab("justica")}
              className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 whitespace-nowrap ${
                activeTab === "justica"
                  ? (dossier?.ficha_limpa?.possui_processos_declarados
                      ? "bg-rose-500/20 text-rose-300 border border-rose-500/40"
                      : "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40")
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Scale className="w-3.5 h-3.5" /> Justiça & Ficha Limpa
              <span className={`text-[10px] font-mono px-1.5 py-0.2 rounded ${
                dossier?.ficha_limpa?.possui_processos_declarados
                  ? "bg-rose-500/20 text-rose-300"
                  : "bg-emerald-500/20 text-emerald-300"
              }`}>
                {dossier?.ficha_limpa?.possui_processos_declarados ? "Alerta" : "Limpa"}
              </span>
            </button>

            <button
              onClick={() => setActiveTab("assiduidade")}
              className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 whitespace-nowrap ${
                activeTab === "assiduidade"
                  ? "bg-blue-500/20 text-blue-300 border border-blue-500/40"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <CheckCircle className="w-3.5 h-3.5" /> Presenças ({assiduidade?.taxa_presenca_pct}%)
            </button>

            <button
              onClick={() => setActiveTab("remuneracao")}
              className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 whitespace-nowrap ${
                activeTab === "remuneracao"
                  ? "bg-teal-500/20 text-teal-300 border border-teal-500/40"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <DollarSign className="w-3.5 h-3.5" /> Remuneração
            </button>

            <button
              onClick={() => setActiveTab("votacoes")}
              className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 whitespace-nowrap ${
                activeTab === "votacoes"
                  ? "bg-purple-500/20 text-purple-300 border border-purple-500/40"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <FileText className="w-3.5 h-3.5" /> Votações Nominais ({dossier?.votacoes_principais?.length})
            </button>
          </div>

          {/* ======================================================== */}
          {/* CONTEÚDO DA ABA 1: VISÃO GERAL & TRAJETÓRIA */}
          {/* ======================================================== */}
          {activeTab === "visao_geral" && (
            <div className="space-y-6">
              {/* CARD DE CONTATO E GABINETE PARLAMENTAR */}
              <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 backdrop-blur-md shadow-lg">
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 pb-4 border-b border-slate-800">
                  <div className="flex items-center gap-2">
                    <span className="p-1.5 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
                      <Building2 className="w-4 h-4" />
                    </span>
                    <h3 className="text-sm font-bold text-slate-100">
                      Contato Oficial & Gabinete Parlamentar
                    </h3>
                  </div>
                  <span className="text-[11px] font-mono text-cyan-400 bg-cyan-500/10 border border-cyan-500/20 px-2.5 py-1 rounded-full">
                    {perfil?.cargo_atual === "SENADOR" ? "Senado Federal" : "Câmara dos Deputados"} • Brasília/DF
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5 pt-4">
                  {/* E-mail Oficial */}
                  <div className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-3.5 flex flex-col justify-between space-y-2">
                    <div className="flex items-center gap-2 text-xs text-slate-400">
                      <Mail className="w-4 h-4 text-cyan-400" />
                      <span className="font-semibold text-slate-300">E-mail Institucional</span>
                    </div>
                    <div className="text-xs font-mono text-cyan-300 break-all select-all font-semibold">
                      {perfil?.email || `dep.${perfil?.camara_id || "contato"}@camara.leg.br`}
                    </div>
                    {perfil?.email && (
                      <a
                        href={`mailto:${perfil.email}`}
                        className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-cyan-400 hover:text-cyan-300 transition-colors pt-1"
                      >
                        <span>Enviar mensagem</span>
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    )}
                  </div>

                  {/* Sala do Gabinete */}
                  <div className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-3.5 flex flex-col justify-between space-y-2">
                    <div className="flex items-center gap-2 text-xs text-slate-400">
                      <MapPin className="w-4 h-4 text-emerald-400" />
                      <span className="font-semibold text-slate-300">Gabinete / Localização</span>
                    </div>
                    <div className="text-xs font-semibold text-slate-100">
                      {perfil?.gabinete_sala || "Congresso Nacional - Edifício Principal"}
                    </div>
                    <span className="text-[11px] text-slate-500">
                      Atendimento e protocolo presencial
                    </span>
                  </div>

                  {/* Telefone do Gabinete */}
                  <div className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-3.5 flex flex-col justify-between space-y-2">
                    <div className="flex items-center gap-2 text-xs text-slate-400">
                      <Phone className="w-4 h-4 text-amber-400" />
                      <span className="font-semibold text-slate-300">Telefone Oficial</span>
                    </div>
                    <div className="text-xs font-mono font-bold text-amber-300">
                      {perfil?.gabinete_telefone || "(61) 3215-5000"}
                    </div>
                    {perfil?.gabinete_telefone && (
                      <a
                        href={`tel:${perfil.gabinete_telefone.replace(/\D/g, "")}`}
                        className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-amber-400 hover:text-amber-300 transition-colors pt-1"
                      >
                        <span>Ligar para o gabinete</span>
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    )}
                  </div>
                </div>
              </div>

              {/* CARD DE EVOLUÇÃO PATRIMONIAL DECLARADA (TSE DIVULGACAND) */}
              {dossier.evolucao_patrimonial?.resumo?.possui_dados && (
                <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 backdrop-blur-md shadow-lg space-y-5">
                  <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-4 border-b border-slate-800">
                    <div className="flex items-center gap-2.5">
                      <span className="p-2 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
                        <TrendingUp className="w-5 h-5" />
                      </span>
                      <div>
                        <h3 className="text-sm sm:text-base font-bold text-slate-100 flex items-center gap-2">
                          Evolução Patrimonial Declarada
                          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                            TSE DivulgaCand
                          </span>
                        </h3>
                        <p className="text-xs text-slate-400">
                          Histórico oficial de bens declarados à Justiça Eleitoral em eleições disputadas
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="text-xs text-slate-400">
                        Crescimento Total:
                      </span>
                      <span className={`text-xs font-mono font-bold px-2.5 py-1 rounded-full border ${
                        dossier.evolucao_patrimonial.resumo.crescimento_pct >= 0
                          ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                          : "bg-rose-500/10 text-rose-400 border-rose-500/30"
                      }`}>
                        {dossier.evolucao_patrimonial.resumo.crescimento_pct >= 0 ? "+" : ""}
                        {dossier.evolucao_patrimonial.resumo.crescimento_pct.toFixed(1)}%
                      </span>
                    </div>
                  </div>

                  {/* Métricas Resumidas em Destaque */}
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5">
                    <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5 space-y-1">
                      <div className="text-[11px] font-semibold text-slate-400">
                        Primeira Declaração ({dossier.evolucao_patrimonial.resumo.primeiro_ano})
                      </div>
                      <div className="text-base font-black font-mono text-slate-200">
                        {dossier.evolucao_patrimonial.resumo.primeiro_valor_formatado}
                      </div>
                      <div className="text-[10px] text-slate-500">
                        Registro eleitoral inicial documentado
                      </div>
                    </div>

                    <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5 space-y-1">
                      <div className="text-[11px] font-semibold text-slate-400">
                        Última Declaração ({dossier.evolucao_patrimonial.resumo.ultimo_ano})
                      </div>
                      <div className="text-base font-black font-mono text-emerald-400">
                        {dossier.evolucao_patrimonial.resumo.ultimo_valor_formatado}
                      </div>
                      <div className="text-[10px] text-slate-500">
                        Valor atualizado informado ao TSE
                      </div>
                    </div>

                    <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5 space-y-1">
                      <div className="text-[11px] font-semibold text-slate-400">
                        Variação Absoluta
                      </div>
                      <div className={`text-base font-black font-mono ${
                        dossier.evolucao_patrimonial.resumo.crescimento_absoluto >= 0 ? "text-cyan-400" : "text-rose-400"
                      }`}>
                        {dossier.evolucao_patrimonial.resumo.crescimento_absoluto >= 0 ? "+" : ""}
                        {new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(
                          dossier.evolucao_patrimonial.resumo.crescimento_absoluto
                        )}
                      </div>
                      <div className="text-[10px] text-slate-500">
                        {dossier.evolucao_patrimonial.resumo.total_declaracoes} ciclos eleitorais analisados
                      </div>
                    </div>
                  </div>

                  {/* Gráfico Recharts de Barras */}
                  <div className="bg-slate-950/50 border border-slate-800/80 rounded-xl p-4 space-y-2">
                    <div className="flex items-center justify-between text-xs text-slate-400 px-1 pb-2">
                      <span className="font-semibold text-slate-300">Gráfico de Patrimônio Declarado por Ano Eleitoral</span>
                      <span className="text-[11px] font-mono text-slate-500">Valores em R$ nominais</span>
                    </div>
                    <div className="h-56 w-full">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                          data={dossier.evolucao_patrimonial.historico}
                          margin={{ top: 10, right: 10, left: 10, bottom: 5 }}
                        >
                          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                          <XAxis
                            dataKey="ano"
                            stroke="#64748b"
                            fontSize={11}
                            tickLine={false}
                            axisLine={{ stroke: "#334155" }}
                          />
                          <YAxis
                            stroke="#64748b"
                            fontSize={10}
                            tickLine={false}
                            axisLine={{ stroke: "#334155" }}
                            tickFormatter={(val) => {
                              if (val >= 1000000) return `R$ ${(val / 1000000).toFixed(1)}M`;
                              if (val >= 1000) return `R$ ${(val / 1000).toFixed(0)}k`;
                              return `R$ ${val}`;
                            }}
                          />
                          <Tooltip
                            content={({ active, payload }) => {
                              if (active && payload && payload.length) {
                                const data = payload[0].payload as any;
                                return (
                                  <div className="bg-slate-900 border border-slate-700 p-3 rounded-xl shadow-2xl text-xs space-y-1 max-w-xs">
                                    <div className="font-bold text-cyan-300">Eleição {data.ano}</div>
                                    <div className="text-emerald-400 font-mono font-bold text-sm">
                                      {data.valor_formatado}
                                    </div>
                                    <div className="text-slate-400 text-[11px] pt-1 border-t border-slate-800 leading-snug">
                                      {data.detalhes}
                                    </div>
                                  </div>
                                );
                              }
                              return null;
                            }}
                          />
                          <Bar dataKey="valor" radius={[6, 6, 0, 0]}>
                            {dossier.evolucao_patrimonial.historico.map((entry, index) => (
                              <Cell
                                key={`cell-${index}`}
                                fill={index === dossier.evolucao_patrimonial!.historico.length - 1 ? "#10b981" : "#06b6d4"}
                              />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>

                  {/* Histórico Discriminado das Eleições */}
                  <div className="space-y-2">
                    <div className="text-xs font-bold text-slate-300 flex items-center gap-1.5 px-1">
                      <FileText className="w-3.5 h-3.5 text-cyan-400" />
                      Detalhamento dos Bens Informados ao TSE
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                      {dossier.evolucao_patrimonial.historico.map((item) => (
                        <div
                          key={item.ano}
                          className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-3 flex flex-col justify-between space-y-1.5"
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                              Eleição {item.ano}
                            </span>
                            <span className="text-xs font-mono font-extrabold text-emerald-400">
                              {item.valor_formatado}
                            </span>
                          </div>
                          <p className="text-[11px] text-slate-400 leading-snug">
                            {item.detalhes}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Linha do Tempo dos Mandatos */}
              <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-4">
                <div className="flex items-center gap-2 pb-2 border-b border-slate-800">
                  <Award className="w-4 h-4 text-cyan-400" />
                  <h3 className="text-sm font-bold text-slate-100">
                    Trajetória de Mandatos Eletivos
                  </h3>
                </div>

                <div className="space-y-3">
                  {dossier.trajetoria_mandatos.map((m) => (
                    <div
                      key={m.id}
                      className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5 flex items-start justify-between gap-3"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold text-slate-100">
                            {m.cargo.replace("_", " ")}
                          </span>
                          <span
                            onClick={() => onSelectParty && m.partido_sigla && onSelectParty(m.partido_sigla)}
                            className={`text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 ${
                              onSelectParty ? "cursor-pointer hover:underline hover:border-cyan-400" : ""
                            }`}
                            title={onSelectParty ? `Ver bancada do ${m.partido_sigla}` : undefined}
                          >
                            {m.partido_sigla}
                          </span>
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
                            {m.uf}
                          </span>
                        </div>
                        <p className="text-xs text-slate-400">
                          Eleição {m.ano_eleicao} • Mandato nº {m.numero_mandato} ({m.esfera})
                        </p>
                        {m.coligacao && (
                          <p className="text-[11px] text-slate-500">
                            Coligação: {m.coligacao}
                          </p>
                        )}
                      </div>

                      <span className="text-[10px] font-bold px-2 py-1 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        {m.status.replace("_", " ")}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Histórico Completo de Partidos (TSE) */}
              <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-4">
                <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                  <div className="flex items-center gap-2">
                    <Building className="w-4 h-4 text-amber-400" />
                    <h3 className="text-sm font-bold text-slate-100">
                      Histórico Partidário (TSE)
                    </h3>
                  </div>
                  <span className="text-xs text-slate-400">
                    Total: <strong className="text-amber-400">{dossier.filiacoes_partidarias.length}</strong> legendas
                  </span>
                </div>

                <div className="space-y-2.5">
                  {dossier.filiacoes_partidarias.map((f) => (
                    <div
                      key={f.id}
                      className="bg-slate-950/70 border border-slate-800 rounded-xl p-3 flex items-center justify-between gap-3"
                    >
                      <div className="flex items-center gap-3">
                        <span
                          onClick={() => onSelectParty && f.partido_sigla && onSelectParty(f.partido_sigla)}
                          className={`text-xs font-mono font-bold px-2.5 py-1 rounded-lg bg-slate-900 text-cyan-400 border border-slate-800 ${
                            onSelectParty ? "cursor-pointer hover:underline hover:border-cyan-400" : ""
                          }`}
                          title={onSelectParty ? `Ver bancada do ${f.partido_sigla}` : undefined}
                        >
                          {f.partido_sigla}
                        </span>
                        <div>
                          <h4 className="text-xs font-bold text-slate-200">
                            {f.partido_nome}
                          </h4>
                          <span className="text-[11px] text-slate-500">
                            Filiado em {f.data_filiacao || "Data não registrada"}
                            {f.data_desfiliacao && ` até ${f.data_desfiliacao}`}
                          </span>
                        </div>
                      </div>

                      {f.is_atual ? (
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                          Atual
                        </span>
                      ) : (
                        <span className="text-[10px] text-slate-500">
                          {f.motivo_desfiliacao?.replace("_", " ") || "Desfiliação"}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* CARD: QUEM PAGA A CONTA? (FINANCIAMENTO DE CAMPANHA) */}
              <div className="bg-gradient-to-br from-slate-900/90 via-slate-950/90 to-emerald-950/20 border border-emerald-500/30 rounded-2xl p-5 space-y-4 lg:col-span-2 shadow-lg">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-800 gap-2">
                  <div className="flex items-center gap-2.5">
                    <span className="p-2 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
                      <Coins className="w-5 h-5" />
                    </span>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-sm font-bold text-slate-100 uppercase tracking-wide">
                          Quem Paga a Conta? (Financiadores de Campanha)
                        </h3>
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 font-bold">
                          TSE DivulgaCand
                        </span>
                      </div>
                      <p className="text-xs text-slate-400">
                        Top doadores e recursos arrecadados na última campanha eleitoral ({dossier?.financiamento_campanha?.ano_eleicao || 2022})
                      </p>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => setActiveTab("financiamento")}
                    className="inline-flex items-center gap-1.5 text-xs font-bold text-emerald-400 hover:text-emerald-300 transition-colors bg-emerald-500/10 border border-emerald-500/25 px-3 py-1.5 rounded-xl hover:bg-emerald-500/20 self-start sm:self-auto"
                  >
                    <span>Ver Todas as Doações</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>

                {/* Métricas do Financiamento */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                    <span className="text-[10px] font-medium text-slate-400 block mb-1">
                      Total Arrecadado na Campanha
                    </span>
                    <span className="text-lg sm:text-xl font-black font-mono text-emerald-400 block leading-tight">
                      R$ {(dossier?.financiamento_campanha?.total_arrecadado || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                    </span>
                    <span className="text-[10px] text-slate-500 mt-1 block">
                      Receita total declarada à Justiça Eleitoral
                    </span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                    <span className="text-[10px] font-medium text-slate-400 block mb-1">
                      Total de Doadores Registrados
                    </span>
                    <span className="text-lg sm:text-xl font-black font-mono text-cyan-400 block leading-tight">
                      {dossier?.financiamento_campanha?.total_doadores || 0} doações
                    </span>
                    <span className="text-[10px] text-slate-500 mt-1 block">
                      Partidos, pessoas físicas e recursos próprios
                    </span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                    <span className="text-[10px] font-medium text-slate-400 block mb-1">
                      Maior Doador Individual
                    </span>
                    <span className="text-lg sm:text-xl font-black font-mono text-amber-400 block leading-tight">
                      {dossier?.financiamento_campanha?.top_doadores?.[0]?.percentual || 0}%
                    </span>
                    <span className="text-[10px] text-slate-500 mt-1 block truncate">
                      {dossier?.financiamento_campanha?.top_doadores?.[0]?.nome_doador || "Sem registros"}
                    </span>
                  </div>
                </div>

                {/* Lista / Gráfico dos Top 5 Maiores Doadores */}
                <div className="space-y-2.5 pt-1">
                  <div className="text-xs font-bold text-slate-300 flex items-center justify-between">
                    <span className="flex items-center gap-1.5">
                      <Award className="w-3.5 h-3.5 text-emerald-400" />
                      Top 5 Maiores Doadores da Eleição
                    </span>
                    <span className="text-[11px] text-slate-500 font-mono">
                      Concentração de receita eleitoral
                    </span>
                  </div>

                  {(!dossier?.financiamento_campanha?.top_doadores || dossier.financiamento_campanha.top_doadores.length === 0) ? (
                    <p className="text-xs text-slate-500 py-3 text-center">
                      Nenhum registro de doação eleitoral localizado nesta base de dados do TSE.
                    </p>
                  ) : (
                    <div className="space-y-2">
                      {dossier.financiamento_campanha.top_doadores.slice(0, 5).map((doador, idx) => (
                        <div
                          key={idx}
                          className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-3 hover:border-slate-700 transition-colors space-y-1.5"
                        >
                          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                            <div className="flex items-center gap-2">
                              <span className="w-5 h-5 rounded-full bg-emerald-500/15 text-emerald-400 font-mono font-bold text-xs flex items-center justify-center shrink-0 border border-emerald-500/30">
                                #{idx + 1}
                              </span>
                              <div>
                                <span className="text-xs font-bold text-slate-200 block">
                                  {doador.nome_doador}
                                </span>
                                <div className="flex items-center gap-2 text-[10px] text-slate-500 font-mono">
                                  <span>Doc: {formatCpfCnpj(doador.cpf_cnpj_doador)}</span>
                                  {doador.tipo_receita && (
                                    <>
                                      <span>•</span>
                                      <span className="text-emerald-400/90">{doador.tipo_receita}</span>
                                    </>
                                  )}
                                </div>
                              </div>
                            </div>

                            <div className="text-left sm:text-right shrink-0">
                              <span className="text-xs font-mono font-black text-emerald-400 block">
                                R$ {doador.valor_doado.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                              </span>
                              <span className="text-[10px] font-mono text-slate-400">
                                {doador.percentual}% do total
                              </span>
                            </div>
                          </div>

                          {/* Barra de Proporção Visual */}
                          <div className="w-full bg-slate-900 rounded-full h-1.5 overflow-hidden">
                            <div
                              className="bg-gradient-to-r from-emerald-500 to-teal-400 h-full rounded-full transition-all duration-500"
                              style={{ width: `${Math.min(100, Math.max(2, doador.percentual))}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* PAINEL: DETECTOR DE LEIS INÚTEIS (TAXA DE RELEVÂNCIA LEGISLATIVA) */}
              <div className="bg-gradient-to-br from-slate-900/90 via-slate-950/90 to-purple-950/20 border border-purple-500/30 rounded-2xl p-5 space-y-4 lg:col-span-2 shadow-lg">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-800 gap-2">
                  <div className="flex items-center gap-2.5">
                    <span className="p-2 rounded-xl bg-purple-500/10 border border-purple-500/20 text-purple-400">
                      <LucidePieChart className="w-5 h-5" />
                    </span>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-sm font-bold text-slate-100 uppercase tracking-wide">
                          Detector de Leis Inúteis (Taxa de Relevância)
                        </h3>
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-500/10 text-purple-300 border border-purple-500/20 font-bold">
                          Arsenal Antidesinformação
                        </span>
                      </div>
                      <p className="text-xs text-slate-400">
                        Classificação semântica de ementas: Projetos Estruturais vs Homenagens Simbólicas
                      </p>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => setActiveTab("proposicoes")}
                    className="inline-flex items-center gap-1.5 text-xs font-bold text-purple-400 hover:text-purple-300 transition-colors bg-purple-500/10 border border-purple-500/25 px-3 py-1.5 rounded-xl hover:bg-purple-500/20 self-start sm:self-auto"
                  >
                    <span>Painel Completo de Leis</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>

                {/* Gráfico de Pizza + Métricas de Relevância */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-center">
                  {/* Gráfico de Pizza (Recharts PieChart) */}
                  <div className="bg-slate-950/70 border border-slate-800/90 rounded-xl p-3 flex flex-col items-center justify-center">
                    <span className="text-[11px] font-bold text-slate-300 mb-1">
                      Projetos de Impacto vs Simbólicos
                    </span>
                    <div className="w-full h-44">
                      <ResponsiveContainer width="100%" height="100%">
                        <RechartsPieChart>
                          <Pie
                            data={[
                              {
                                name: "Projetos de Impacto",
                                value: dossier?.relevancia_legislativa?.projetos_impacto || 0,
                                color: "#10b981",
                                pct: dossier?.relevancia_legislativa?.percentual_impacto || 0,
                              },
                              {
                                name: "Projetos Simbólicos",
                                value: dossier?.relevancia_legislativa?.projetos_simbolicos || 0,
                                color: "#f59e0b",
                                pct: dossier?.relevancia_legislativa?.percentual_simbolico || 0,
                              },
                            ]}
                            dataKey="value"
                            nameKey="name"
                            cx="50%"
                            cy="50%"
                            innerRadius={42}
                            outerRadius={68}
                            paddingAngle={3}
                          >
                            <Cell fill="#10b981" />
                            <Cell fill="#f59e0b" />
                          </Pie>
                          <Tooltip
                            content={({ active, payload }) => {
                              if (!active || !payload || !payload.length) return null;
                              const d = payload[0].payload;
                              return (
                                <div className="bg-slate-900 border border-slate-700 p-2 rounded-lg text-xs shadow-xl">
                                  <span className="font-bold text-slate-200 block">{d.name}</span>
                                  <span className="font-mono text-cyan-400 font-bold">{d.value} matérias ({d.pct}%)</span>
                                </div>
                              );
                            }}
                          />
                        </RechartsPieChart>
                      </ResponsiveContainer>
                    </div>
                    <div className="flex items-center gap-3 text-[11px] font-mono pt-1">
                      <span className="flex items-center gap-1 text-emerald-400">
                        <span className="w-2 h-2 rounded-full bg-emerald-400" />
                        Impacto ({dossier?.relevancia_legislativa?.percentual_impacto || 0}%)
                      </span>
                      <span className="flex items-center gap-1 text-amber-400">
                        <span className="w-2 h-2 rounded-full bg-amber-400" />
                        Simbólico ({dossier?.relevancia_legislativa?.percentual_simbolico || 0}%)
                      </span>
                    </div>
                  </div>

                  {/* Diagnóstico e Estatísticas */}
                  <div className="md:col-span-2 space-y-3">
                    <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5 space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="text-[11px] font-medium text-slate-400">Diagnóstico de Produtividade</span>
                        <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border ${
                          (dossier?.relevancia_legislativa?.percentual_impacto || 0) >= 60
                            ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/30"
                            : "bg-amber-500/10 text-amber-300 border-amber-500/30"
                        }`}>
                          {dossier?.relevancia_legislativa?.diagnostico || "Em análise"}
                        </span>
                      </div>
                      <p className="text-xs text-slate-300 leading-relaxed">
                        De um total de <strong className="text-cyan-400">{dossier?.relevancia_legislativa?.total_proposicoes || 0} proposições</strong> analisadas,{" "}
                        <strong className="text-emerald-400">{dossier?.relevancia_legislativa?.projetos_impacto || 0} ({dossier?.relevancia_legislativa?.percentual_impacto || 0}%)</strong> versam sobre matérias substanciais (Economia, Saúde, Código Penal, Educação) e{" "}
                        <strong className="text-amber-400">{dossier?.relevancia_legislativa?.projetos_simbolicos || 0} ({dossier?.relevancia_legislativa?.percentual_simbolico || 0}%)</strong> são projetos simbólicos (Dias Nacionais, Homenagens e Denominações).
                      </p>
                    </div>

                    <div className="grid grid-cols-2 gap-2.5">
                      <div className="bg-slate-950/70 border border-emerald-500/20 rounded-xl p-2.5">
                        <span className="text-[10px] text-emerald-400 font-medium block">Projetos de Impacto</span>
                        <span className="text-base font-black font-mono text-emerald-400">
                          {dossier?.relevancia_legislativa?.projetos_impacto || 0}
                        </span>
                        <span className="text-[10px] text-slate-500 block">Reformas e políticas públicas</span>
                      </div>
                      <div className="bg-slate-950/70 border border-amber-500/20 rounded-xl p-2.5">
                        <span className="text-[10px] text-amber-400 font-medium block">Projetos Simbólicos</span>
                        <span className="text-base font-black font-mono text-amber-400">
                          {dossier?.relevancia_legislativa?.projetos_simbolicos || 0}
                        </span>
                        <span className="text-[10px] text-slate-500 block">Homenagens e datas festivas</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Amostra recente de matérias com badges */}
                <div className="space-y-2 pt-2">
                  <div className="text-xs font-bold text-slate-300 flex items-center justify-between">
                    <span>Amostra Recente de Proposições</span>
                    <button
                      type="button"
                      onClick={() => setActiveTab("proposicoes")}
                      className="text-[11px] font-mono text-purple-400 hover:underline flex items-center gap-1"
                    >
                      Ver todas as {dossier?.materias_propostas?.length || 0} matérias
                      <ArrowRight className="w-3 h-3" />
                    </button>
                  </div>

                  {(!dossier?.materias_propostas || dossier.materias_propostas.length === 0) ? (
                    <p className="text-xs text-slate-500 py-3 text-center">
                      Nenhuma matéria de autoria individual registrada nesta base legislativa estrutural.
                    </p>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {dossier.materias_propostas.slice(0, 4).map((p) => {
                        const isImpacto = p.classificacao_relevancia === "IMPACTO";
                        return (
                          <div
                            key={p.id}
                            className="bg-slate-950/70 border border-slate-800 rounded-xl p-3 space-y-2"
                          >
                            <div className="flex items-center justify-between gap-2">
                              <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-purple-500/10 text-purple-300 border border-purple-500/20">
                                {p.tipo} {p.numero}/{p.ano}
                              </span>
                              <span
                                className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border ${
                                  isImpacto
                                    ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                                    : "bg-amber-500/15 text-amber-300 border-amber-500/30"
                                }`}
                              >
                                {isImpacto ? "Impacto / Substancial" : "Simbólico / Homenagem"}
                              </span>
                            </div>

                            <div className="flex items-start justify-between gap-2">
                              <h4 className="text-xs font-bold text-slate-100 leading-snug line-clamp-1">
                                {p.titulo}
                              </h4>
                              {p.url_oficial && (
                                <a
                                  href={p.url_oficial}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1 text-[10px] font-semibold text-cyan-400 hover:text-cyan-300 transition-colors shrink-0 bg-cyan-500/10 border border-cyan-500/20 px-2 py-0.5 rounded"
                                >
                                  <span>Íntegra</span>
                                  <ExternalLink className="w-2.5 h-2.5" />
                                </a>
                              )}
                            </div>
                            <p className="text-xs text-slate-400 line-clamp-2">
                              {p.ementa}
                            </p>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            </div>
            </div>
          )}

          {/* ======================================================== */}
          {/* CONTEÚDO DA ABA DEDICADA: PROPOSIÇÕES & RELEVÂNCIA */}
          {/* ======================================================== */}
          {activeTab === "proposicoes" && (
            <div className="space-y-6">
              {/* Header do Detector de Leis Inúteis */}
              <div className="bg-gradient-to-br from-slate-900/90 via-slate-950/90 to-purple-950/30 border border-purple-500/30 rounded-2xl p-5 sm:p-6 backdrop-blur-md shadow-lg space-y-4">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-800">
                  <div className="flex items-center gap-3">
                    <div className="p-3 rounded-2xl bg-purple-500/10 border border-purple-500/20 text-purple-400 shadow-inner">
                      <LucidePieChart className="w-7 h-7" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h2 className="text-lg font-black text-slate-100">
                          Detector de Leis Inúteis & Relevância Legislativa
                        </h2>
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-500/15 text-purple-300 border border-purple-500/30 font-bold">
                          Arsenal Antidesinformação
                        </span>
                      </div>
                      <p className="text-xs text-slate-400">
                        Classificação automatizada por processamento de linguagem natural: Leis Estruturais vs Homenagens Simbólicas
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-400">Diagnóstico:</span>
                    <span className={`text-xs font-mono font-bold px-3 py-1.5 rounded-xl border ${
                      (dossier?.relevancia_legislativa?.percentual_impacto || 0) >= 60
                        ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/40"
                        : "bg-amber-500/15 text-amber-300 border-amber-500/40"
                    }`}>
                      {dossier?.relevancia_legislativa?.diagnostico || "Em análise"}
                    </span>
                  </div>
                </div>

                {/* Grid Analítico: Gráfico de Pizza + Estatísticas Detalhadas */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-center pt-2">
                  {/* Painel do Gráfico de Pizza */}
                  <div className="bg-slate-950/80 border border-slate-800 rounded-2xl p-4 flex flex-col items-center justify-center">
                    <span className="text-xs font-bold text-slate-200 mb-1">
                      Proporção de Relevância Legislativa
                    </span>
                    <span className="text-[10px] text-slate-500 font-mono mb-2">
                      Gráfico de Pizza: Projetos de Impacto ({dossier?.relevancia_legislativa?.percentual_impacto || 0}%) vs Simbólicos ({dossier?.relevancia_legislativa?.percentual_simbolico || 0}%)
                    </span>

                    <div className="w-full h-52">
                      <ResponsiveContainer width="100%" height="100%">
                        <RechartsPieChart>
                          <Pie
                            data={[
                              {
                                name: "Projetos de Impacto / Substanciais",
                                value: dossier?.relevancia_legislativa?.projetos_impacto || 0,
                                pct: dossier?.relevancia_legislativa?.percentual_impacto || 0,
                              },
                              {
                                name: "Projetos Simbólicos / Homenagens",
                                value: dossier?.relevancia_legislativa?.projetos_simbolicos || 0,
                                pct: dossier?.relevancia_legislativa?.percentual_simbolico || 0,
                              },
                            ]}
                            dataKey="value"
                            nameKey="name"
                            cx="50%"
                            cy="50%"
                            innerRadius={50}
                            outerRadius={80}
                            paddingAngle={4}
                          >
                            <Cell fill="#10b981" />
                            <Cell fill="#f59e0b" />
                          </Pie>
                          <Tooltip
                            content={({ active, payload }) => {
                              if (!active || !payload || !payload.length) return null;
                              const d = payload[0].payload;
                              return (
                                <div className="bg-slate-900 border border-slate-700 p-2.5 rounded-xl text-xs shadow-xl space-y-1">
                                  <span className="font-bold text-slate-200 block">{d.name}</span>
                                  <div className="flex items-center gap-2">
                                    <span className="font-mono text-cyan-400 font-bold">{d.value} matérias</span>
                                    <span className="text-slate-400 font-mono">({d.pct}%)</span>
                                  </div>
                                </div>
                              );
                            }}
                          />
                        </RechartsPieChart>
                      </ResponsiveContainer>
                    </div>

                    <div className="grid grid-cols-2 gap-2 w-full pt-2 text-[11px] font-mono">
                      <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg p-2 text-center">
                        <span className="text-emerald-400 font-bold block">
                          Impacto ({dossier?.relevancia_legislativa?.percentual_impacto || 0}%)
                        </span>
                        <span className="text-slate-400 text-[10px]">
                          {dossier?.relevancia_legislativa?.projetos_impacto || 0} projetos
                        </span>
                      </div>
                      <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-2 text-center">
                        <span className="text-amber-400 font-bold block">
                          Simbólico ({dossier?.relevancia_legislativa?.percentual_simbolico || 0}%)
                        </span>
                        <span className="text-slate-400 text-[10px]">
                          {dossier?.relevancia_legislativa?.projetos_simbolicos || 0} projetos
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Informações Metodológicas & Explicativas */}
                  <div className="lg:col-span-2 space-y-3">
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                      <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                        <span className="text-[10px] text-slate-400 font-medium block mb-1">Total de Proposições</span>
                        <span className="text-xl font-black font-mono text-cyan-400 block">
                          {dossier?.relevancia_legislativa?.total_proposicoes || 0}
                        </span>
                        <span className="text-[10px] text-slate-500 mt-1 block">Projetos de autoria cadastrados</span>
                      </div>
                      <div className="bg-slate-950/70 border border-emerald-500/30 rounded-xl p-3.5">
                        <span className="text-[10px] text-emerald-400 font-medium block mb-1">Impacto / Estrutural</span>
                        <span className="text-xl font-black font-mono text-emerald-400 block">
                          {dossier?.relevancia_legislativa?.projetos_impacto || 0} ({dossier?.relevancia_legislativa?.percentual_impacto || 0}%)
                        </span>
                        <span className="text-[10px] text-slate-500 mt-1 block">Economia, Saúde, Código Penal</span>
                      </div>
                      <div className="bg-slate-950/70 border border-amber-500/30 rounded-xl p-3.5">
                        <span className="text-[10px] text-amber-400 font-medium block mb-1">Simbólico / Homenagem</span>
                        <span className="text-xl font-black font-mono text-amber-400 block">
                          {dossier?.relevancia_legislativa?.projetos_simbolicos || 0} ({dossier?.relevancia_legislativa?.percentual_simbolico || 0}%)
                        </span>
                        <span className="text-[10px] text-slate-500 mt-1 block">Títulos, Homenagens e Datas</span>
                      </div>
                    </div>

                    <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5 space-y-2 text-xs">
                      <span className="font-bold text-slate-200 block">Como funciona o algoritmo de classificação?</span>
                      <p className="text-slate-400 leading-relaxed text-[11px]">
                        O detector analisa a ementa de cada proposição em busca de marcadores semânticos honoríficos (como <em>&quot;Dia Nacional&quot;</em>, <em>&quot;Homenagem&quot;</em>, <em>&quot;Denomina&quot;</em>, <em>&quot;Cidadão Honorário&quot;</em> e <em>&quot;Título&quot;</em>). Matérias com essas características são categorizadas como <strong>Simbólicas</strong>, enquanto as demais são classificadas como <strong>Impacto/Substancial</strong>.
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Filtros e Barra de Busca */}
              <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-slate-900/60 border border-slate-800 p-3.5 rounded-2xl">
                <div className="flex items-center gap-1.5 w-full sm:w-auto overflow-x-auto">
                  <button
                    type="button"
                    onClick={() => setProposicaoFilter("TODAS")}
                    className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all whitespace-nowrap ${
                      proposicaoFilter === "TODAS"
                        ? "bg-purple-500/20 text-purple-300 border border-purple-500/40"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    Todas ({dossier?.materias_propostas?.length || 0})
                  </button>
                  <button
                    type="button"
                    onClick={() => setProposicaoFilter("IMPACTO")}
                    className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all whitespace-nowrap ${
                      proposicaoFilter === "IMPACTO"
                        ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    Impacto ({dossier?.relevancia_legislativa?.projetos_impacto || 0})
                  </button>
                  <button
                    type="button"
                    onClick={() => setProposicaoFilter("SIMBOLICO")}
                    className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all whitespace-nowrap ${
                      proposicaoFilter === "SIMBOLICO"
                        ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    Simbólicas ({dossier?.relevancia_legislativa?.projetos_simbolicos || 0})
                  </button>
                </div>

                <div className="relative w-full sm:w-72">
                  <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
                  <input
                    type="text"
                    value={proposicaoSearch}
                    onChange={(e) => setProposicaoSearch(e.target.value)}
                    placeholder="Buscar ementa, tipo ou número..."
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-purple-500/50"
                  />
                </div>
              </div>

              {/* Lista Detalhada de Proposições */}
              {(() => {
                const proposicoesExibidas = (dossier?.materias_propostas || []).filter((p) => {
                  const matchFilter =
                    proposicaoFilter === "TODAS"
                      ? true
                      : proposicaoFilter === "IMPACTO"
                      ? p.classificacao_relevancia === "IMPACTO"
                      : p.classificacao_relevancia === "SIMBOLICO";
                  const matchSearch =
                    !proposicaoSearch.trim() ||
                    p.titulo.toLowerCase().includes(proposicaoSearch.toLowerCase()) ||
                    p.ementa.toLowerCase().includes(proposicaoSearch.toLowerCase()) ||
                    `${p.tipo} ${p.numero}`.toLowerCase().includes(proposicaoSearch.toLowerCase());
                  return matchFilter && matchSearch;
                });

                if (proposicoesExibidas.length === 0) {
                  return (
                    <div className="bg-slate-900/40 border border-slate-800 rounded-2xl p-8 text-center text-xs text-slate-500">
                      Nenhuma proposição encontrada para os filtros selecionados.
                    </div>
                  );
                }

                return (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {proposicoesExibidas.map((p) => {
                      const isImpacto = p.classificacao_relevancia === "IMPACTO";
                      return (
                        <div
                          key={p.id}
                          className={`bg-slate-900/70 border rounded-2xl p-4.5 space-y-3 transition-all ${
                            isImpacto
                              ? "border-emerald-500/20 hover:border-emerald-500/40"
                              : "border-amber-500/20 hover:border-amber-500/40"
                          }`}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-xs font-mono font-bold px-2.5 py-1 rounded-lg bg-slate-950 text-purple-300 border border-purple-500/20">
                              {p.tipo} {p.numero}/{p.ano}
                            </span>
                            <span
                              className={`text-[10px] font-mono font-bold px-2.5 py-1 rounded-lg border flex items-center gap-1 ${
                                isImpacto
                                  ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/40"
                                  : "bg-amber-500/15 text-amber-300 border-amber-500/40"
                              }`}
                            >
                              {isImpacto ? (
                                <>
                                  <CheckCircle className="w-3 h-3 text-emerald-400" />
                                  <span>Impacto / Estrutural</span>
                                </>
                              ) : (
                                <>
                                  <AlertTriangle className="w-3 h-3 text-amber-400" />
                                  <span>Simbólico / Homenagem</span>
                                </>
                              )}
                            </span>
                          </div>

                          <div>
                            <div className="flex items-start justify-between gap-2">
                              <h4 className="text-xs font-bold text-slate-100 leading-snug">
                                {p.titulo}
                              </h4>
                              {p.url_oficial && (
                                <a
                                  href={p.url_oficial}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1 text-[11px] font-semibold text-cyan-400 hover:text-cyan-300 transition-colors shrink-0 bg-cyan-500/10 border border-cyan-500/20 px-2 py-0.5 rounded-lg"
                                >
                                  <span>Íntegra</span>
                                  <ExternalLink className="w-3 h-3" />
                                </a>
                              )}
                            </div>
                            <span className="text-[10px] text-slate-500 font-mono mt-1 block">
                              Apresentado em {p.data_apresentacao || "Data não registrada"}
                            </span>
                          </div>

                          <p className="text-xs text-slate-300 leading-relaxed bg-slate-950/60 p-3 rounded-xl border border-slate-800/80">
                            {p.ementa}
                          </p>

                          {p.justificativa_relevancia && (
                            <div className="flex items-center gap-1.5 text-[10px] text-slate-400 font-mono pt-1">
                              <Sparkles className="w-3 h-3 text-purple-400 shrink-0" />
                              <span>{p.justificativa_relevancia}</span>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                );
              })()}
            </div>
          )}

          {/* ======================================================== */}
          {/* CONTEÚDO DA ABA DEDICADA: FINANCIAMENTO DE CAMPANHA */}
          {/* ======================================================== */}
          {activeTab === "financiamento" && (
            <div className="space-y-6">
              {/* Header de Financiamento */}
              <div className="bg-gradient-to-br from-slate-900/90 via-slate-950/90 to-emerald-950/30 border border-emerald-500/30 rounded-2xl p-5 sm:p-6 backdrop-blur-md shadow-lg space-y-4">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-800">
                  <div className="flex items-center gap-3">
                    <div className="p-3 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 shadow-inner">
                      <Coins className="w-7 h-7" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h2 className="text-lg font-black text-slate-100">
                          Quem Paga a Conta? (Financiamento Eleitoral)
                        </h2>
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 font-bold">
                          TSE DivulgaCand
                        </span>
                      </div>
                      <p className="text-xs text-slate-400">
                        Prestação de contas oficial da campanha de {dossier?.financiamento_campanha?.ano_eleicao || 2022} declarada à Justiça Eleitoral
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-400">Total Arrecadado:</span>
                    <span className="text-base font-black font-mono text-emerald-400 px-3 py-1 rounded-xl bg-emerald-500/10 border border-emerald-500/30">
                      R$ {(dossier?.financiamento_campanha?.total_arrecadado || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                </div>

                {/* Resumo de KPIs do Financiamento */}
                <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 pt-2">
                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                    <span className="text-[10px] text-slate-400 font-medium block mb-1">Receita Total de Campanha</span>
                    <span className="text-lg font-black font-mono text-emerald-400 block">
                      R$ {(dossier?.financiamento_campanha?.total_arrecadado || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                    </span>
                    <span className="text-[10px] text-slate-500 mt-1 block">Ano Eleitoral: {dossier?.financiamento_campanha?.ano_eleicao || 2022}</span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                    <span className="text-[10px] text-slate-400 font-medium block mb-1">Total de Doadores</span>
                    <span className="text-lg font-black font-mono text-cyan-400 block">
                      {dossier?.financiamento_campanha?.total_doadores || 0}
                    </span>
                    <span className="text-[10px] text-slate-500 mt-1 block">Registros na prestação de contas</span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                    <span className="text-[10px] text-slate-400 font-medium block mb-1">Maior Doador Individual</span>
                    <span className="text-lg font-black font-mono text-amber-400 block">
                      {dossier?.financiamento_campanha?.top_doadores?.[0]?.percentual || 0}%
                    </span>
                    <span className="text-[10px] text-slate-500 mt-1 block truncate">
                      {dossier?.financiamento_campanha?.top_doadores?.[0]?.nome_doador || "Sem registros"}
                    </span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                    <span className="text-[10px] text-slate-400 font-medium block mb-1">Ticket Médio por Doador</span>
                    <span className="text-lg font-black font-mono text-purple-400 block">
                      R$ {((dossier?.financiamento_campanha?.total_arrecadado || 0) / Math.max(1, dossier?.financiamento_campanha?.total_doadores || 1)).toLocaleString("pt-BR", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                    </span>
                    <span className="text-[10px] text-slate-500 mt-1 block">Valor médio por doação</span>
                  </div>
                </div>
              </div>

              {/* Seção dos Top 5 Doadores */}
              <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-4">
                <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                  <div className="flex items-center gap-2">
                    <Award className="w-4 h-4 text-emerald-400" />
                    <h3 className="text-sm font-bold text-slate-100">
                      Top 5 Maiores Financiadores da Campanha
                    </h3>
                  </div>
                  <span className="text-xs text-slate-400 font-mono">
                    Concentração de recursos
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                  {(dossier?.financiamento_campanha?.top_doadores || []).slice(0, 5).map((d, idx) => (
                    <div
                      key={idx}
                      className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5 space-y-2 hover:border-slate-700 transition-colors"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className="w-6 h-6 rounded-lg bg-emerald-500/15 text-emerald-400 font-mono font-bold text-xs flex items-center justify-center shrink-0 border border-emerald-500/30">
                            #{idx + 1}
                          </span>
                          <div>
                            <h4 className="text-xs font-bold text-slate-200 leading-snug">
                              {d.nome_doador}
                            </h4>
                            <span className="text-[10px] text-slate-500 font-mono">
                              Doc: {formatCpfCnpj(d.cpf_cnpj_doador)}
                            </span>
                          </div>
                        </div>

                        <div className="text-right shrink-0">
                          <span className="text-xs font-mono font-black text-emerald-400 block">
                            R$ {d.valor_doado.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                          </span>
                          <span className="text-[10px] font-mono text-slate-400">
                            {d.percentual}% da campanha
                          </span>
                        </div>
                      </div>

                      <div className="w-full bg-slate-900 rounded-full h-2 overflow-hidden">
                        <div
                          className="bg-gradient-to-r from-emerald-500 to-teal-400 h-full rounded-full transition-all duration-500"
                          style={{ width: `${Math.min(100, Math.max(3, d.percentual))}%` }}
                        />
                      </div>

                      {d.tipo_receita && (
                        <div className="text-[10px] font-mono text-slate-400 flex items-center gap-1.5 pt-0.5">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                          <span>Tipo de Receita: {d.tipo_receita}</span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Tabela de Todas as Doações Declaradas */}
              <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-800 gap-3">
                  <div className="flex items-center gap-2">
                    <FileText className="w-4 h-4 text-cyan-400" />
                    <h3 className="text-sm font-bold text-slate-100">
                      Relação de Doações Declaradas
                    </h3>
                  </div>

                  <div className="relative w-full sm:w-72">
                    <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
                    <input
                      type="text"
                      value={doacaoSearch}
                      onChange={(e) => setDoacaoSearch(e.target.value)}
                      placeholder="Filtrar por nome ou CPF/CNPJ..."
                      className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-emerald-500/50"
                    />
                  </div>
                </div>

                {(() => {
                  const doacoesExibidas = (dossier?.financiamento_campanha?.todas_doacoes || []).filter((d) => {
                    if (!doacaoSearch.trim()) return true;
                    const term = doacaoSearch.toLowerCase();
                    return (
                      d.nome_doador.toLowerCase().includes(term) ||
                      (d.cpf_cnpj_doador && d.cpf_cnpj_doador.includes(term)) ||
                      (d.tipo_receita && d.tipo_receita.toLowerCase().includes(term))
                    );
                  });

                  if (doacoesExibidas.length === 0) {
                    return (
                      <p className="text-xs text-slate-500 py-6 text-center">
                        Nenhuma doação encontrada para o termo pesquisado.
                      </p>
                    );
                  }

                  return (
                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-xs border-collapse">
                        <thead>
                          <tr className="border-b border-slate-800 text-slate-400 text-[11px] font-mono uppercase">
                            <th className="py-2.5 px-3">Nome do Doador</th>
                            <th className="py-2.5 px-3">CPF / CNPJ</th>
                            <th className="py-2.5 px-3">Tipo de Receita</th>
                            <th className="py-2.5 px-3 text-right">Valor Doado</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/60 font-mono">
                          {doacoesExibidas.map((d, idx) => (
                            <tr key={d.id || idx} className="hover:bg-slate-900/60 transition-colors">
                              <td className="py-2.5 px-3 text-slate-200 font-sans font-medium">
                                {d.nome_doador}
                              </td>
                              <td className="py-2.5 px-3 text-slate-400 text-[11px]">
                                {formatCpfCnpj(d.cpf_cnpj_doador)}
                              </td>
                              <td className="py-2.5 px-3 text-slate-400 text-[11px]">
                                {d.tipo_receita || "Recurso Financeiro"}
                              </td>
                              <td className="py-2.5 px-3 text-right font-black text-emerald-400">
                                R$ {d.valor_doado.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  );
                })()}
              </div>
            </div>
          )}

          {/* ======================================================== */}
          {/* CONTEÚDO DA NOVA ABA: CUSTOS DO MANDATO (CEAP) */}
          {/* ======================================================== */}
          {activeTab === "ceap" && (
            <div className="space-y-6">
              {/* Header do Painel CEAP */}
              <div className="bg-slate-900/80 border border-amber-500/30 rounded-2xl p-5 sm:p-6 backdrop-blur-md shadow-lg space-y-5">
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-4 border-b border-slate-800">
                  <div className="flex items-center gap-2.5">
                    <span className="p-2 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400">
                      <Receipt className="w-5 h-5" />
                    </span>
                    <div>
                      <h3 className="text-base sm:text-lg font-bold text-slate-100 flex items-center gap-2">
                        Custos do Mandato &amp; Cota Parlamentar (CEAP)
                      </h3>
                      <p className="text-xs text-slate-400 mt-0.5">
                        Cota para o Exercício da Atividade Parlamentar (gastos públicos de gabinete auditados)
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-mono text-amber-300 bg-amber-500/10 border border-amber-500/20 px-3 py-1 rounded-full font-bold">
                      Legislatura 2023–2026
                    </span>
                    <span className="text-[11px] font-mono text-slate-400 bg-slate-950 px-2.5 py-1 rounded-lg border border-slate-800">
                      {dossier?.custos_ceap?.total_notas || 0} comprovantes fiscais
                    </span>
                  </div>
                </div>

                {/* 4 Cards de Resumo Executivo */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                    <span className="text-[11px] font-medium text-slate-400 block mb-1">
                      Gasto Total Auditado
                    </span>
                    <span className="text-lg sm:text-xl font-black font-mono text-amber-400 block leading-tight">
                      R$ {(dossier?.custos_ceap?.gasto_total_recente || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                    </span>
                    <span className="text-[10px] text-slate-500 mt-1 block">
                      Reembolsos oficiais na legislatura
                    </span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                    <span className="text-[11px] font-medium text-slate-400 block mb-1">
                      Média de Gasto Mensal
                    </span>
                    <span className="text-lg sm:text-xl font-black font-mono text-cyan-400 block leading-tight">
                      R$ {remuneracao?.resumo?.media_ceap_mensal?.toLocaleString("pt-BR", { minimumFractionDigits: 2 }) || "0,00"}
                    </span>
                    <span className="text-[10px] text-slate-500 mt-1 block">
                      Média calculada por mês ativo
                    </span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                    <span className="text-[11px] font-medium text-slate-400 block mb-1">
                      Maior Categoria de Custo
                    </span>
                    <span className="text-xs sm:text-sm font-bold text-slate-200 block truncate leading-tight" title={dossier?.custos_ceap?.gastos_por_tipo?.[0]?.tipo_despesa || "Nenhum gasto"}>
                      {dossier?.custos_ceap?.gastos_por_tipo?.[0]?.tipo_despesa || "Sem lançamentos"}
                    </span>
                    <span className="text-[10px] font-mono text-amber-400/90 mt-1 block">
                      R$ {(dossier?.custos_ceap?.gastos_por_tipo?.[0]?.total_gasto || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                    </span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                    <span className="text-[11px] font-medium text-slate-400 block mb-1">
                      Maior Fornecedor Único
                    </span>
                    <span className="text-xs sm:text-sm font-bold text-slate-200 block truncate leading-tight" title={dossier?.custos_ceap?.maiores_fornecedores?.[0]?.nome_fornecedor || "Nenhum"}>
                      {dossier?.custos_ceap?.maiores_fornecedores?.[0]?.nome_fornecedor || "Nenhum"}
                    </span>
                    <span className="text-[10px] font-mono text-emerald-400 mt-1 block">
                      R$ {(dossier?.custos_ceap?.maiores_fornecedores?.[0]?.total_recebido || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                </div>
              </div>

              {/* Grid 2 colunas: Gráfico/Barras por Tipo de Despesa + Mini-tabela Maiores Fornecedores */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Gastos por Tipo de Despesa (Barras de Distribuição) */}
                <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-4">
                  <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                    <div className="flex items-center gap-2">
                      <TrendingUp className="w-4 h-4 text-amber-400" />
                      <h4 className="text-sm font-bold text-slate-100">
                        Gastos por Tipo de Despesa
                      </h4>
                    </div>
                    <span className="text-xs text-slate-400">
                      {dossier?.custos_ceap?.gastos_por_tipo?.length || 0} categorias
                    </span>
                  </div>

                  {(!dossier?.custos_ceap?.gastos_por_tipo || dossier.custos_ceap.gastos_por_tipo.length === 0) ? (
                    <p className="text-xs text-slate-500 py-6 text-center">
                      Nenhum registro de cota parlamentar detalhado encontrado para este período.
                    </p>
                  ) : (
                    <div className="space-y-3 pt-1">
                      {dossier.custos_ceap.gastos_por_tipo.map((g, idx) => (
                        <div key={idx} className="space-y-1">
                          <div className="flex items-center justify-between text-xs">
                            <span className="text-slate-300 font-medium truncate max-w-[240px] sm:max-w-[320px]" title={g.tipo_despesa}>
                              {g.tipo_despesa}
                            </span>
                            <div className="flex items-center gap-2 shrink-0 font-mono">
                              <span className="text-amber-400 font-bold">
                                R$ {g.total_gasto.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                              </span>
                              <span className="text-slate-500 text-[11px] w-12 text-right">
                                {g.percentual}%
                              </span>
                            </div>
                          </div>
                          <div className="h-2 w-full bg-slate-950 rounded-full overflow-hidden border border-slate-800">
                            <div
                              className="h-full bg-gradient-to-r from-amber-500 to-amber-300 rounded-full transition-all duration-500"
                              style={{ width: `${Math.min(100, Math.max(2, g.percentual))}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Mini-Tabela: Maiores Fornecedores */}
                <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-4">
                  <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                    <div className="flex items-center gap-2">
                      <Building2 className="w-4 h-4 text-cyan-400" />
                      <h4 className="text-sm font-bold text-slate-100">
                        Maiores Fornecedores &amp; Prestadores
                      </h4>
                    </div>
                    <span className="text-xs text-slate-400">
                      Top 10 beneficiários
                    </span>
                  </div>

                  {(!dossier?.custos_ceap?.maiores_fornecedores || dossier.custos_ceap.maiores_fornecedores.length === 0) ? (
                    <p className="text-xs text-slate-500 py-6 text-center">
                      Nenhum fornecedor registrado.
                    </p>
                  ) : (
                    <div className="overflow-x-auto rounded-xl border border-slate-800/80 bg-slate-950/60 shadow-inner">
                      <table className="w-full text-left text-xs">
                        <thead className="bg-slate-950 text-slate-400 uppercase tracking-wider text-[10px] font-bold border-b border-slate-800">
                          <tr>
                            <th className="py-2.5 px-3">Empresa / Fornecedor</th>
                            <th className="py-2.5 px-2 text-center whitespace-nowrap">Notas</th>
                            <th className="py-2.5 px-3 text-right whitespace-nowrap">Total Pago</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/50">
                          {dossier.custos_ceap.maiores_fornecedores.map((f, idx) => (
                            <tr key={idx} className="hover:bg-slate-900/80 transition-colors">
                              <td className="py-2.5 px-3">
                                <p className="font-semibold text-slate-200 line-clamp-1 max-w-[220px]" title={f.nome_fornecedor}>
                                  {f.nome_fornecedor}
                                </p>
                                {f.cnpj_cpf && (
                                  <p className="font-mono text-[10px] text-slate-500">
                                    CNPJ/CPF: {f.cnpj_cpf}
                                  </p>
                                )}
                              </td>
                              <td className="py-2.5 px-2 text-center font-mono text-slate-400">
                                <span className="px-1.5 py-0.5 rounded bg-slate-800 text-[10px]">
                                  {f.num_notas}
                                </span>
                              </td>
                              <td className="py-2.5 px-3 text-right font-mono font-bold text-amber-400 whitespace-nowrap">
                                R$ {f.total_recebido.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </div>

              {/* Feed de Despesas e Notas Fiscais Recentes com Link Oficial */}
              {dossier?.custos_ceap?.despesas_recentes && dossier.custos_ceap.despesas_recentes.length > 0 && (
                <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-4">
                  <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                    <div className="flex items-center gap-2">
                      <FileCheck className="w-4 h-4 text-emerald-400" />
                      <h4 className="text-sm font-bold text-slate-100">
                        Últimos Comprovantes Fiscais Auditados
                      </h4>
                    </div>
                    <span className="text-xs text-slate-400">
                      Exibindo últimas {dossier.custos_ceap.despesas_recentes.length} notas emitidas
                    </span>
                  </div>

                  <div className="overflow-x-auto rounded-xl border border-slate-800/80 bg-slate-950/60">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-slate-950 text-slate-400 uppercase tracking-wider text-[10px] font-bold border-b border-slate-800">
                        <tr>
                          <th className="py-2.5 px-3 whitespace-nowrap">Mês/Ano</th>
                          <th className="py-2.5 px-3">Rubrica / Tipo de Despesa</th>
                          <th className="py-2.5 px-3">Prestador / Fornecedor</th>
                          <th className="py-2.5 px-3 text-right whitespace-nowrap">Valor da Nota</th>
                          <th className="py-2.5 px-3 text-center whitespace-nowrap">Documento</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/50">
                        {dossier.custos_ceap.despesas_recentes.map((d, idx) => (
                          <tr key={idx} className="hover:bg-slate-900/80 transition-colors">
                            <td className="py-2.5 px-3 font-mono text-slate-300 whitespace-nowrap">
                              {d.mes ? String(d.mes).padStart(2, "0") : "--"}/{d.ano}
                            </td>
                            <td className="py-2.5 px-3 text-slate-300 font-medium">
                              {d.tipo_despesa}
                            </td>
                            <td className="py-2.5 px-3 text-slate-400">
                              <span className="line-clamp-1" title={d.nome_fornecedor}>
                                {d.nome_fornecedor}
                              </span>
                            </td>
                            <td className="py-2.5 px-3 text-right font-mono font-bold text-cyan-400 whitespace-nowrap">
                              R$ {d.valor_liquido.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                            </td>
                            <td className="py-2.5 px-3 text-center whitespace-nowrap">
                              {d.documento_url ? (
                                <a
                                  href={d.documento_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1 text-[11px] font-semibold text-cyan-400 hover:text-cyan-300 bg-cyan-500/10 border border-cyan-500/20 px-2 py-0.5 rounded-lg"
                                  title="Ver nota original no portal oficial"
                                >
                                  <span>NF-e</span>
                                  <ExternalLink className="w-3 h-3" />
                                </a>
                              ) : (
                                <span className="text-[10px] text-slate-500">Registrado</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ======================================================== */}
          {/* CONTEÚDO DA NOVA ABA: A TRILHA DO DINHEIRO (EMENDAS) */}
          {/* ======================================================== */}
          {activeTab === "emendas" && (
            <div className="space-y-6">
              {/* Header do Painel Emendas */}
              <div className="bg-slate-900/80 border border-emerald-500/30 rounded-2xl p-5 sm:p-6 backdrop-blur-md shadow-lg space-y-5">
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-4 border-b border-slate-800">
                  <div className="flex items-center gap-2.5">
                    <span className="p-2 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
                      <Landmark className="w-5 h-5" />
                    </span>
                    <div>
                      <h3 className="text-base sm:text-lg font-bold text-slate-100 flex items-center gap-2">
                        A Trilha do Dinheiro &amp; Emendas Parlamentares
                      </h3>
                      <p className="text-xs text-slate-400 mt-0.5">
                        Rastreamento de verbas públicas direcionadas por este parlamentar aos municípios e estados
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-mono text-emerald-300 bg-emerald-500/10 border border-emerald-500/20 px-3 py-1 rounded-full font-bold">
                      Orçamento Geral da União
                    </span>
                    <span className="text-[11px] font-mono text-slate-400 bg-slate-950 px-2.5 py-1 rounded-lg border border-slate-800">
                      {dossier?.emendas_parlamentares?.lista_emendas?.length || 0} emendas cadastradas
                    </span>
                  </div>
                </div>

                {/* 4 Cards de Resumo Executivo */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                    <span className="text-[11px] font-medium text-slate-400 block mb-1">
                      Total Efetivamente Pago
                    </span>
                    <span className="text-lg sm:text-xl font-black font-mono text-emerald-400 block leading-tight">
                      R$ {(dossier?.emendas_parlamentares?.total_pago || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                    </span>
                    <span className="text-[10px] text-slate-500 mt-1 block">
                      Recursos depositados nos destinos
                    </span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                    <span className="text-[11px] font-medium text-slate-400 block mb-1">
                      Total Empenhado no OGU
                    </span>
                    <span className="text-lg sm:text-xl font-black font-mono text-cyan-400 block leading-tight">
                      R$ {(dossier?.emendas_parlamentares?.total_empenhado || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                    </span>
                    <span className="text-[10px] text-slate-500 mt-1 block">
                      Compromisso orçamentário aprovado
                    </span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                    <span className="text-[11px] font-medium text-slate-400 block mb-1">
                      Taxa de Execução
                    </span>
                    <span className="text-lg sm:text-xl font-black font-mono text-purple-400 block leading-tight">
                      {dossier?.emendas_parlamentares?.percentual_execucao || 0}%
                    </span>
                    <span className="text-[10px] text-slate-500 mt-1 block">
                      Razão entre pago e empenhado
                    </span>
                  </div>

                  <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5">
                    <span className="text-[11px] font-medium text-slate-400 block mb-1">
                      Principal Destino
                    </span>
                    <span className="text-xs sm:text-sm font-bold text-slate-200 block truncate leading-tight" title={dossier?.emendas_parlamentares?.destinos_principais?.[0]?.localidade || "Nenhum"}>
                      {dossier?.emendas_parlamentares?.destinos_principais?.[0]?.localidade || "Sem dados"}
                    </span>
                    <span className="text-[10px] font-mono text-emerald-400 mt-1 block">
                      R$ {(dossier?.emendas_parlamentares?.destinos_principais?.[0]?.valor_pago || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                </div>
              </div>

              {/* Grid 2 colunas: Ranking de Cidades/Estados Destino + Tipos & Áreas Temáticas */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Ranking de Cidades/Estados */}
                <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-4">
                  <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                    <div className="flex items-center gap-2">
                      <MapPin className="w-4 h-4 text-emerald-400" />
                      <h4 className="text-sm font-bold text-slate-100">
                        Localidades &amp; Municípios Mais Beneficiados
                      </h4>
                    </div>
                    <span className="text-xs text-slate-400">
                      {dossier?.emendas_parlamentares?.destinos_principais?.length || 0} localidades
                    </span>
                  </div>

                  {(!dossier?.emendas_parlamentares?.destinos_principais || dossier.emendas_parlamentares.destinos_principais.length === 0) ? (
                    <p className="text-xs text-slate-500 py-6 text-center">
                      Nenhum repasse de emenda registrado.
                    </p>
                  ) : (
                    <div className="space-y-3 pt-1">
                      {dossier.emendas_parlamentares.destinos_principais.map((dest, idx) => (
                        <div key={idx} className="space-y-1">
                          <div className="flex items-center justify-between text-xs">
                            <span className="text-slate-300 font-medium truncate max-w-[240px] sm:max-w-[320px]">
                              {dest.localidade}
                            </span>
                            <div className="flex items-center gap-2 shrink-0 font-mono">
                              <span className="text-emerald-400 font-bold">
                                R$ {dest.valor_pago.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                              </span>
                              <span className="text-slate-500 text-[11px] w-12 text-right">
                                {dest.percentual}%
                              </span>
                            </div>
                          </div>
                          <div className="h-2 w-full bg-slate-950 rounded-full overflow-hidden border border-slate-800">
                            <div
                              className="h-full bg-gradient-to-r from-emerald-500 to-teal-400 rounded-full transition-all duration-500"
                              style={{ width: `${Math.min(100, Math.max(2, dest.percentual))}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Distribuição por Tipo de Emenda e Função */}
                <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-5">
                  <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                    <div className="flex items-center gap-2">
                      <Briefcase className="w-4 h-4 text-purple-400" />
                      <h4 className="text-sm font-bold text-slate-100">
                        Modalidades &amp; Funções Orçamentárias
                      </h4>
                    </div>
                    <span className="text-xs text-slate-400">
                      Critérios de Alocação
                    </span>
                  </div>

                  {/* Por Tipo de Emenda */}
                  <div className="space-y-2.5">
                    <span className="text-xs font-bold text-slate-300 uppercase tracking-wider block">
                      Por Modalidade de Emenda
                    </span>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                      {dossier?.emendas_parlamentares?.distribuicao_por_tipo?.map((t, idx) => (
                        <div key={idx} className="bg-slate-950/70 border border-slate-800 rounded-xl p-3">
                          <span className="text-[11px] text-slate-400 block font-medium truncate">
                            {t.tipo || "Modalidade"}
                          </span>
                          <span className="text-sm font-bold font-mono text-purple-400 block mt-0.5">
                            R$ {t.valor_pago.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                          </span>
                          <span className="text-[10px] text-slate-500 font-mono">
                            {t.percentual}% do total
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Por Área Temática */}
                  <div className="space-y-2.5 pt-2 border-t border-slate-800/80">
                    <span className="text-xs font-bold text-slate-300 uppercase tracking-wider block">
                      Por Área de Aplicação dos Recursos
                    </span>
                    <div className="space-y-2">
                      {dossier?.emendas_parlamentares?.distribuicao_por_area?.map((a, idx) => (
                        <div key={idx} className="flex items-center justify-between text-xs bg-slate-950/50 p-2 rounded-lg border border-slate-800/60">
                          <span className="text-slate-300 font-medium">
                            {a.area || "Geral"}
                          </span>
                          <div className="flex items-center gap-2 font-mono">
                            <span className="text-cyan-400 font-bold">
                              R$ {a.valor_pago.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                            </span>
                            <span className="text-slate-500 text-[10px]">
                              ({a.percentual}%)
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              {/* Tabela das Emendas Parlamentares Registradas */}
              {dossier?.emendas_parlamentares?.lista_emendas && dossier.emendas_parlamentares.lista_emendas.length > 0 && (
                <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-4">
                  <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                    <div className="flex items-center gap-2">
                      <FileText className="w-4 h-4 text-emerald-400" />
                      <h4 className="text-sm font-bold text-slate-100">
                        Detalhamento das Emendas no OGU
                      </h4>
                    </div>
                    <span className="text-xs text-slate-400">
                      Rastreabilidade completa de cada repasse
                    </span>
                  </div>

                  <div className="overflow-x-auto rounded-xl border border-slate-800/80 bg-slate-950/60">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-slate-950 text-slate-400 uppercase tracking-wider text-[10px] font-bold border-b border-slate-800">
                        <tr>
                          <th className="py-2.5 px-3">Código / Ano</th>
                          <th className="py-2.5 px-3">Modalidade</th>
                          <th className="py-2.5 px-3">Localidade Destino</th>
                          <th className="py-2.5 px-3">Função / Área</th>
                          <th className="py-2.5 px-3 text-right">Empenhado</th>
                          <th className="py-2.5 px-3 text-right">Efetivamente Pago</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/50">
                        {dossier.emendas_parlamentares.lista_emendas.map((e, idx) => (
                          <tr key={idx} className="hover:bg-slate-900/80 transition-colors">
                            <td className="py-2.5 px-3 font-mono font-bold text-cyan-300 whitespace-nowrap">
                              {e.codigo_emenda || "--"} ({e.ano})
                            </td>
                            <td className="py-2.5 px-3 text-slate-300">
                              <span className="px-2 py-0.5 rounded bg-slate-800 text-[10px] font-medium">
                                {e.tipo_emenda}
                              </span>
                            </td>
                            <td className="py-2.5 px-3 text-slate-200 font-semibold">
                              {e.localidade_destino}
                            </td>
                            <td className="py-2.5 px-3 text-slate-400">
                              {e.funcao || "Geral"}
                            </td>
                            <td className="py-2.5 px-3 text-right font-mono text-slate-300 whitespace-nowrap">
                              R$ {e.valor_empenhado.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                            </td>
                            <td className="py-2.5 px-3 text-right font-mono font-bold text-emerald-400 whitespace-nowrap">
                              R$ {e.valor_pago.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ======================================================== */}
          {/* CONTEÚDO DA NOVA ABA: RAIO-X JUDICIAL & FICHA LIMPA */}
          {/* ======================================================== */}
          {activeTab === "justica" && (
            <div className="space-y-6">
              {/* Header do Painel Judicial */}
              <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 sm:p-6 backdrop-blur-md shadow-lg space-y-5">
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-4 border-b border-slate-800">
                  <div className="flex items-center gap-2.5">
                    <span className="p-2 rounded-xl bg-purple-500/10 border border-purple-500/20 text-purple-400">
                      <Scale className="w-5 h-5" />
                    </span>
                    <div>
                      <h3 className="text-base sm:text-lg font-bold text-slate-100 flex items-center gap-2">
                        Raio-X Judicial &amp; Certidões de Ficha Limpa
                      </h3>
                      <p className="text-xs text-slate-400 mt-0.5">
                        Conformidade com a Lei Complementar nº 135/2010 (Lei da Ficha Limpa) e certidões registradas na Justiça Eleitoral
                      </p>
                    </div>
                  </div>
                  <span className="text-[11px] font-mono text-purple-300 bg-purple-500/10 border border-purple-500/20 px-3 py-1 rounded-full font-bold">
                    TSE DivulgaCandContas &amp; Tribunais
                  </span>
                </div>

                {/* Banner Hero do Status da Ficha Limpa */}
                {dossier?.ficha_limpa?.possui_processos_declarados ? (
                  <div className="bg-gradient-to-r from-rose-950/60 via-slate-950 to-rose-950/30 border border-rose-500/40 rounded-2xl p-5 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 shadow-xl">
                    <div className="flex items-start gap-3.5">
                      <div className="p-2.5 rounded-xl bg-rose-500/20 text-rose-400 border border-rose-500/30 shrink-0">
                        <ShieldAlert className="w-6 h-6" />
                      </div>
                      <div className="space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h4 className="text-base font-extrabold text-rose-300">
                            Possui Processos Declarados na Justiça
                          </h4>
                          <span className="text-[11px] font-mono font-bold bg-rose-500/20 text-rose-200 border border-rose-500/30 px-2 py-0.5 rounded-lg">
                            Atenção do Eleitor
                          </span>
                        </div>
                        <p className="text-xs text-slate-300 leading-relaxed max-w-2xl">
                          Foram identificadas certidões judiciais positivas ou procedimentos protocolados perante os órgãos informados à Justiça Eleitoral. Veja abaixo o detalhamento por tribunal.
                        </p>
                        {dossier.ficha_limpa.orgaos_declarados && dossier.ficha_limpa.orgaos_declarados.length > 0 && (
                          <div className="flex items-center gap-2 pt-1 flex-wrap">
                            <span className="text-[11px] font-bold text-rose-400">Órgãos com declaração:</span>
                            {dossier.ficha_limpa.orgaos_declarados.map((org, i) => (
                              <span key={i} className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-rose-900/50 text-rose-200 border border-rose-500/40">
                                {org}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="bg-gradient-to-r from-emerald-950/60 via-slate-950 to-emerald-950/30 border border-emerald-500/40 rounded-2xl p-5 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 shadow-xl">
                    <div className="flex items-start gap-3.5">
                      <div className="p-2.5 rounded-xl bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 shrink-0">
                        <ShieldCheck className="w-6 h-6" />
                      </div>
                      <div className="space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h4 className="text-base font-extrabold text-emerald-300">
                            Certidões Judiciais: Nada Consta (Ficha Limpa)
                          </h4>
                          <span className="text-[11px] font-mono font-bold bg-emerald-500/20 text-emerald-200 border border-emerald-500/30 px-2 py-0.5 rounded-lg">
                            Situação Regular
                          </span>
                        </div>
                        <p className="text-xs text-slate-300 leading-relaxed max-w-2xl">
                          O parlamentar apresentou certidões negativas em todos os órgãos competentes perante a Justiça Eleitoral (STF, TSE, TRF e Tribunais de Justiça), cumprindo integralmente os requisitos da Lei da Ficha Limpa (LC 135/2010).
                        </p>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Grid de Certidões por Tribunal */}
              <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-4">
                <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                  <div className="flex items-center gap-2">
                    <Gavel className="w-4 h-4 text-purple-400" />
                    <h4 className="text-sm font-bold text-slate-100">
                      Certidões Oficiais Registradas no TSE
                    </h4>
                  </div>
                  <span className="text-xs text-slate-400">
                    Total: <strong className="text-purple-400">{dossier?.ficha_limpa?.certidoes?.length || 0}</strong> certidões
                  </span>
                </div>

                {(!dossier?.ficha_limpa?.certidoes || dossier.ficha_limpa.certidoes.length === 0) ? (
                  <p className="text-xs text-slate-500 py-6 text-center">
                    Nenhuma certidão individual cadastrada no repositório para este mandato.
                  </p>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                    {dossier.ficha_limpa.certidoes.map((c) => {
                      const isPositiva = c.status_ficha.toLowerCase().includes("positiva") || c.status_ficha.toLowerCase().includes("declarada");
                      return (
                        <div
                          key={c.id}
                          className={`bg-slate-950/80 rounded-xl p-4 border space-y-2 transition-all ${
                            isPositiva
                              ? "border-rose-500/30 hover:border-rose-500/50"
                              : "border-slate-800 hover:border-emerald-500/30"
                          }`}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-xs font-mono font-black text-slate-100 px-2 py-0.5 rounded bg-slate-900 border border-slate-700">
                              {c.orgao}
                            </span>
                            <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border ${
                              isPositiva
                                ? "bg-rose-500/15 text-rose-300 border-rose-500/30"
                                : "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                            }`}>
                              {c.status_ficha}
                            </span>
                          </div>

                          <div className="text-xs font-semibold text-slate-300">
                            Tipo: <span className="text-slate-100">{c.tipo_certidao}</span>
                          </div>

                          {c.detalhes && (
                            <p className="text-[11px] text-slate-400 leading-relaxed bg-slate-900/50 p-2.5 rounded-lg border border-slate-800/60">
                              {c.detalhes}
                            </p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Box Informativo Legal Antidesinformação */}
              <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-4 text-xs text-slate-400 space-y-1.5">
                <span className="font-bold text-slate-200 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-amber-400" />
                  Marco Legal e Critério Técnico de Ficha Limpa
                </span>
                <p className="leading-relaxed">
                  A Lei Complementar nº 135/2010 estabelece a inelegibilidade de candidatos condenados por órgãos colegiados em crimes contra a administração pública, eleitorais e de lavagem de dinheiro. A mera existência de procedimentos investigatórios ou ações em andamento sem trânsito em julgado ou decisão colegiada respeita a presunção constitucional de inocência. As informações acima são transcritas fielmente das certidões do TSE.
                </p>
              </div>
            </div>
          )}

          {/* ======================================================== */}
          {/* CONTEÚDO DA ABA 2: ASSIDUIDADE & PRESENÇAS */}
          {/* ======================================================== */}
          {activeTab === "assiduidade" && (
            <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 sm:p-6 space-y-6">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
                <div>
                  <h3 className="text-sm sm:text-base font-bold text-slate-100 flex items-center gap-2">
                    <CheckCircle className="w-4 h-4 text-emerald-400" />
                    Balanço Oficial de Assiduidade em Plenário
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Contabilização de sessões deliberativas ordinárias e extraordinárias na Legislatura
                  </p>
                </div>

                <div className="px-3.5 py-1.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-300 font-mono font-bold">
                  Taxa de Presença: {assiduidade?.taxa_presenca_pct}%
                </div>
              </div>

              {/* Indicadores de Presença */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="bg-slate-950/70 border border-emerald-500/20 rounded-xl p-4 space-y-1">
                  <span className="text-xs text-slate-400">Presenças Confirmadas</span>
                  <div className="text-2xl font-black text-emerald-400 font-mono">
                    {assiduidade?.total_presencas}
                  </div>
                  <span className="text-[11px] text-slate-500">
                    Sessões deliberativas registradas
                  </span>
                </div>

                <div className="bg-slate-950/70 border border-amber-500/20 rounded-xl p-4 space-y-1">
                  <span className="text-xs text-slate-400">Faltas Justificadas</span>
                  <div className="text-2xl font-black text-amber-400 font-mono">
                    {assiduidade?.faltas_justificadas}
                  </div>
                  <span className="text-[11px] text-slate-500">
                    Licenças médicas e missões oficiais
                  </span>
                </div>

                <div className="bg-slate-950/70 border border-rose-500/20 rounded-xl p-4 space-y-1">
                  <span className="text-xs text-slate-400">Faltas Não Justificadas</span>
                  <div className="text-2xl font-black text-rose-400 font-mono">
                    {assiduidade?.faltas_nao_justificadas}
                  </div>
                  <span className="text-[11px] text-slate-500">
                    Ausências sem protocolo prévio
                  </span>
                </div>
              </div>

              {/* Tabela de Justificativas / Ocorrências de Ausência */}
              <div className="space-y-3 pt-2">
                <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
                  Histórico Detalhado de Ausências e Justificativas Regimentais
                </h4>

                {assiduidade?.amostra_faltas?.length === 0 ? (
                  <div className="p-4 rounded-xl bg-emerald-500/5 border border-emerald-500/20 text-xs text-emerald-300 text-center">
                    Nenhuma ausência registrada neste período. O parlamentar atingiu 100% de assiduidade!
                  </div>
                ) : (
                  <div className="space-y-2">
                    {assiduidade?.amostra_faltas?.map((f, idx) => (
                      <div
                        key={idx}
                        className="bg-slate-950/80 border border-slate-800 rounded-xl p-3 flex items-start justify-between gap-3 text-xs"
                      >
                        <div className="space-y-0.5">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-slate-300 font-bold">
                              {f.data}
                            </span>
                            <span
                              className={`text-[10px] font-bold px-2 py-0.2 rounded ${
                                f.tipo.includes("JUSTIFICADA") || f.tipo.includes("LICENCA") || f.tipo.includes("MISSAO")
                                  ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                                  : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                              }`}
                            >
                              {f.tipo.replace("_", " ")}
                            </span>
                          </div>
                          <p className="text-[11px] text-slate-400">
                            {f.justificativa || "Sem justificativa formal protocolada"}
                          </p>
                        </div>

                        <span className="text-[10px] text-slate-500 font-semibold flex-shrink-0">
                          {f.casa === "CAMARA_DOS_DEPUTADOS" ? "Câmara" : "Senado"}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ======================================================== */}
          {/* CONTEÚDO DA ABA 3: REMUNERAÇÃO & COTA CEAP */}
          {/* ======================================================== */}
          {activeTab === "remuneracao" && (
            <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 sm:p-6 space-y-6">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
                <div>
                  <h3 className="text-sm sm:text-base font-bold text-slate-100 flex items-center gap-2">
                    <DollarSign className="w-4 h-4 text-cyan-400" />
                    Transparência Remuneratória e Benefícios Oficiais
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Dados obtidos via Portal da Transparência da Câmara dos Deputados e Senado Federal
                  </p>
                </div>

                <div className="text-xs text-slate-400">
                  Total Bruto 2023: <strong className="text-cyan-400 font-mono">R$ {remuneracao?.resumo?.total_bruto_2023?.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}</strong>
                </div>
              </div>

              {/* Tabela de Folha Mensal */}
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400 bg-slate-950/60">
                      <th className="py-2.5 px-3">Mês/Ano</th>
                      <th className="py-2.5 px-3">Salário Bruto</th>
                      <th className="py-2.5 px-3">Salário Líquido</th>
                      <th className="py-2.5 px-3">Cota CEAP (Gastos)</th>
                      <th className="py-2.5 px-3">Auxílios / Moradia</th>
                      <th className="py-2.5 px-3">Fonte dos Dados</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {remuneracao?.historico?.map((r, idx) => (
                      <tr key={idx} className="hover:bg-slate-900/80 transition-colors">
                        <td className="py-2.5 px-3 font-mono font-bold text-slate-200">
                          {String(r.mes).padStart(2, "0")}/{r.ano}
                        </td>
                        <td className="py-2.5 px-3 font-mono text-cyan-400 font-bold">
                          R$ {r.salario_bruto.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                        </td>
                        <td className="py-2.5 px-3 font-mono text-slate-300">
                          R$ {r.salario_liquido.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                        </td>
                        <td className="py-2.5 px-3 font-mono text-amber-400">
                          R$ {r.cota_ceap.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                        </td>
                        <td className="py-2.5 px-3 font-mono text-slate-400">
                          R$ {(r.auxilio_moradia + r.outros_beneficios).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                        </td>
                        <td className="py-2.5 px-3 text-slate-500 text-[11px]">
                          {r.fonte}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ======================================================== */}
          {/* CONTEÚDO DA ABA 4: VOTAÇÕES NOMINAIS */}
          {/* ======================================================== */}
          {activeTab === "votacoes" && (
            <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 sm:p-6 space-y-5">
              <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                <div className="flex items-center gap-2">
                  <FileText className="w-4 h-4 text-purple-400" />
                  <h3 className="text-sm sm:text-base font-bold text-slate-100">
                    Posicionamento nas Leis Estruturantes
                  </h3>
                </div>
                <span className="text-xs text-slate-400">
                  {dossier.votacoes_principais.length} deliberações nominais registradas
                </span>
              </div>

              {/* Alinhamento Temático por Eixo de Impacto */}
              {dossier.alinhamento_tematico && dossier.alinhamento_tematico.length > 0 && (
                <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-4.5 space-y-3.5">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5 text-amber-400" />
                      <span>Alinhamento Temático por Categoria de Lei</span>
                    </h4>
                    <span className="text-[11px] text-slate-400">Classificação Técnica e Neutra</span>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {dossier.alinhamento_tematico.map((al, idx) => (
                      <div
                        key={idx}
                        className="bg-slate-900/70 border border-slate-800/80 rounded-xl p-3.5 space-y-2"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-slate-200 text-xs">{al.eixo}</span>
                          <span className={`text-xs font-mono font-extrabold ${
                            al.percentual_favoravel >= 60
                              ? "text-emerald-400"
                              : al.percentual_favoravel <= 40
                              ? "text-rose-400"
                              : "text-amber-400"
                          }`}>
                            {al.percentual_favoravel.toFixed(1)}% a favor
                          </span>
                        </div>

                        {/* Barra de Progresso do Alinhamento */}
                        <div className="w-full bg-slate-950 h-2 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all duration-500 ${
                              al.percentual_favoravel >= 60
                                ? "bg-emerald-500"
                                : al.percentual_favoravel <= 40
                                ? "bg-rose-500"
                                : "bg-amber-500"
                            }`}
                            style={{ width: `${al.percentual_favoravel}%` }}
                          />
                        </div>

                        <div className="flex justify-between text-[10px] text-slate-500">
                          <span>{al.votos_sim} a favor • {al.votos_nao} contra</span>
                          <span>{al.total_votacoes} votações</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Campo de Busca Simples na Capivara de Votos */}
              {(() => {
                const rawVotes =
                  dossier.historico_votos && dossier.historico_votos.length > 0
                    ? dossier.historico_votos
                    : dossier.votacoes_principais.map((v) => ({
                        proposicao_id: v.proposicao_id,
                        proposicao_titulo: v.proposicao_titulo,
                        proposicao_numero: `${v.proposicao_tipo} ${v.proposicao_numero}/${v.proposicao_ano}`,
                        proposicao_tipo: v.proposicao_tipo,
                        tema: (v as any).eixo_impacto || "Geral",
                        setor: (v as any).eixo_impacto || "Geral",
                        data: v.sessao_data ? v.sessao_data.slice(0, 10).split("-").reverse().join("/") : "-",
                        data_iso: v.sessao_data,
                        voto: v.decisao === "SIM" ? "Sim" : v.decisao === "NAO" ? "Não" : "Abstenção",
                        decisao: v.decisao,
                        sessao_titulo: v.sessao_titulo,
                        sessao_aprovada: v.sessao_aprovada,
                        casa_legislativa: v.casa_legislativa,
                        url_oficial: (v as any).url_oficial || null,
                      }));

                const filteredVotes = rawVotes.filter((v) => {
                  if (!voteSearchTerm.trim()) return true;
                  const term = voteSearchTerm.toLowerCase();
                  return (
                    v.proposicao_titulo.toLowerCase().includes(term) ||
                    v.proposicao_numero.toLowerCase().includes(term) ||
                    (v.tema && v.tema.toLowerCase().includes(term)) ||
                    (v.setor && v.setor.toLowerCase().includes(term)) ||
                    (v.sessao_titulo && v.sessao_titulo.toLowerCase().includes(term)) ||
                    v.voto.toLowerCase().includes(term)
                  );
                });

                if (rawVotes.length === 0) {
                  return (
                    <div className="text-center py-10 text-slate-500 text-xs">
                      Nenhum voto nominal registrado para este parlamentar nas matérias cadastradas.
                    </div>
                  );
                }

                return (
                  <div className="space-y-4">
                    {/* Barra de Pesquisa de Votos */}
                    <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-slate-950/70 border border-slate-800 rounded-xl p-3">
                      <div className="relative flex-1">
                        <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                        <input
                          type="text"
                          placeholder="Pesquisar por matéria, número, tema ou palavra-chave..."
                          value={voteSearchTerm}
                          onChange={(e) => setVoteSearchTerm(e.target.value)}
                          className="w-full bg-slate-900 border border-slate-800/80 rounded-lg pl-9 pr-3 py-1.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-400 transition-colors"
                        />
                      </div>
                      <div className="text-xs text-slate-400 px-1 whitespace-nowrap">
                        Exibindo <strong className="text-cyan-400 font-mono">{filteredVotes.length}</strong> de{" "}
                        <span className="font-mono">{rawVotes.length}</span> deliberações
                      </div>
                    </div>

                    {/* Tabela de Histórico de Votos */}
                    <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/50 shadow-inner">
                      <table className="w-full text-left text-xs">
                        <thead className="bg-slate-950 text-slate-400 uppercase tracking-wider text-[11px] font-bold border-b border-slate-800">
                          <tr>
                            <th className="py-3 px-4">Matéria / Proposição</th>
                            <th className="py-3 px-4 w-32 whitespace-nowrap">Data</th>
                            <th className="py-3 px-4 w-36 text-center whitespace-nowrap">Voto Registrado</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/60">
                          {filteredVotes.length === 0 ? (
                            <tr>
                              <td colSpan={3} className="py-8 text-center text-slate-500 text-xs">
                                Nenhuma deliberação encontrada para &ldquo;{voteSearchTerm}&rdquo;.
                              </td>
                            </tr>
                          ) : (
                            filteredVotes.map((v, idx) => {
                              const vLower = (v.voto || v.decisao || "").toLowerCase();
                              const isSim = vLower === "sim";
                              const isNao = vLower === "não" || vLower === "nao";
                              const isAbst = vLower.includes("abst") || vLower.includes("obst");

                              const badgeColor = isSim
                                ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                                : isNao
                                ? "bg-rose-500/15 text-rose-400 border-rose-500/30"
                                : isAbst
                                ? "bg-amber-500/15 text-amber-400 border-amber-500/30"
                                : "bg-slate-700/30 text-slate-400 border-slate-700/50";

                              const labelVoto = isSim ? "Sim" : isNao ? "Não" : isAbst ? "Abstenção" : "Ausente";
                              const temaLabel = v.tema || v.setor || "Geral";

                              return (
                                <tr key={idx} className="hover:bg-slate-900/60 transition-colors">
                                  {/* Coluna 1: Matéria/Proposição com Tema/Setor */}
                                  <td className="py-3 px-4">
                                    <div className="space-y-1">
                                      <div className="flex flex-wrap items-center gap-2">
                                        <span className="font-mono font-bold text-xs text-cyan-300 bg-cyan-500/10 border border-cyan-500/20 px-2 py-0.5 rounded">
                                          {v.proposicao_numero}
                                        </span>
                                        <span className="text-[10px] font-semibold text-purple-300 bg-purple-500/10 border border-purple-500/20 px-2 py-0.5 rounded">
                                          {temaLabel}
                                        </span>
                                        <span className="text-[10px] text-slate-500">
                                          {v.casa_legislativa === "CAMARA_DOS_DEPUTADOS" ? "Câmara" : "Senado"}
                                        </span>
                                      </div>
                                      <div className="font-semibold text-slate-200 leading-snug flex items-start justify-between gap-2">
                                        <span>{v.proposicao_titulo}</span>
                                        {v.url_oficial && (
                                          <a
                                            href={v.url_oficial}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="inline-flex items-center gap-1 text-[11px] font-semibold text-cyan-400 hover:text-cyan-300 transition-colors shrink-0 bg-cyan-500/10 border border-cyan-500/20 px-2 py-0.5 rounded-lg"
                                            title="Ler íntegra no site oficial"
                                          >
                                            <span>Íntegra</span>
                                            <ExternalLink className="w-3 h-3" />
                                          </a>
                                        )}
                                      </div>
                                      {v.sessao_titulo && (
                                        <p className="text-[11px] text-slate-400 line-clamp-1">
                                          {v.sessao_titulo}
                                        </p>
                                      )}
                                    </div>
                                  </td>

                                  {/* Coluna 2: Data */}
                                  <td className="py-3 px-4 whitespace-nowrap text-slate-400 font-mono text-[11px]">
                                    {v.data}
                                  </td>

                                  {/* Coluna 3: Voto (Badge Colorido) */}
                                  <td className="py-3 px-4 text-center whitespace-nowrap">
                                    <span
                                      className={`inline-block font-mono font-black text-xs px-3 py-1 rounded-xl border ${badgeColor}`}
                                    >
                                      {labelVoto}
                                    </span>
                                  </td>
                                </tr>
                              );
                            })
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                );
              })()}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
