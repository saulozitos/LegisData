"use client";

import React, { useEffect, useState, useMemo } from "react";
import Header from "@/components/Header";
import { getConsultasPublicas, ConsultaPublicaItem } from "@/services/api";
import {
  Vote,
  ExternalLink,
  Search,
  CheckCircle2,
  XCircle,
  HelpCircle,
  ShieldCheck,
  Building2,
  Landmark,
  Sparkles,
  Flame,
  Users,
  RefreshCw,
  Info,
  Calendar,
  Share2,
  Check,
  Radio,
  FileCheck2,
} from "lucide-react";

export default function CidadaniaPage() {
  const [consultas, setConsultas] = useState<ConsultaPublicaItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [selectedCasa, setSelectedCasa] = useState<"TODAS" | "Senado" | "Câmara">("TODAS");
  const [selectedStatus, setSelectedStatus] = useState<"TODAS" | "ABERTAS" | "ENCERRADAS">("TODAS");
  const [onlyWithVotes, setOnlyWithVotes] = useState<boolean>(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const carregarConsultas = async (forceRefresh: boolean = false) => {
    if (forceRefresh) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
    }
    try {
      const data = await getConsultasPublicas();
      setConsultas(data);
    } catch (err) {
      console.error("Erro ao carregar consultas públicas:", err);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    carregarConsultas();
  }, []);

  // Estatísticas resumidas
  const stats = useMemo(() => {
    const total = consultas.length;
    const senadoCount = consultas.filter((c) => c.casa === "Senado").length;
    const camaraCount = consultas.filter((c) => c.casa === "Câmara").length;
    const abertasCount = consultas.filter((c) => c.em_votacao_aberta === true).length;
    const encerradasCount = consultas.filter((c) => c.em_votacao_aberta === false).length;
    const totalVotosColetados = consultas.reduce(
      (acc, c) => acc + (c.total_votos || 0),
      0
    );
    return { total, senadoCount, camaraCount, abertasCount, encerradasCount, totalVotosColetados };
  }, [consultas]);

  // Filtros combinados
  const filteredConsultas = useMemo(() => {
    return consultas.filter((item) => {
      // Filtro por Casa
      if (selectedCasa !== "TODAS" && item.casa !== selectedCasa) {
        return false;
      }
      // Filtro por Status da Votação
      if (selectedStatus === "ABERTAS" && item.em_votacao_aberta !== true) {
        return false;
      }
      if (selectedStatus === "ENCERRADAS" && item.em_votacao_aberta === true) {
        return false;
      }
      // Filtro por placar existente
      if (onlyWithVotes && (item.votos_sim === null || item.votos_nao === null)) {
        return false;
      }
      // Filtro por texto
      if (searchTerm.trim() !== "") {
        const query = searchTerm.toLowerCase();
        const matchSigla = item.sigla_projeto.toLowerCase().includes(query);
        const matchEmenta = item.ementa.toLowerCase().includes(query);
        const matchTema = item.tema ? item.tema.toLowerCase().includes(query) : false;
        const matchAutor = item.autor ? item.autor.toLowerCase().includes(query) : false;
        return matchSigla || matchEmenta || matchTema || matchAutor;
      }
      return true;
    });
  }, [consultas, selectedCasa, selectedStatus, onlyWithVotes, searchTerm]);

  const handleShare = (item: ConsultaPublicaItem) => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(item.link_oficial_votacao);
      setCopiedId(item.id_externo);
      setTimeout(() => setCopiedId(null), 2500);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      <Header />

      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {/* Banner Hero Principal */}
        <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-amber-500/10 via-slate-900 to-emerald-950/30 border border-slate-800 p-6 sm:p-10 shadow-2xl">
          <div className="absolute top-0 right-0 -mt-8 -mr-8 w-64 h-64 bg-amber-500/10 rounded-full blur-3xl pointer-events-none" />
          <div className="absolute bottom-0 left-0 -mb-8 -ml-8 w-64 h-64 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none" />

          <div className="relative z-10 max-w-3xl space-y-4">
            <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-bold uppercase tracking-wider bg-amber-500/15 text-amber-300 border border-amber-500/30">
              <Vote className="w-4 h-4 text-amber-400" />
              <span>Democracia Direta & Participação Cívica</span>
            </div>

            <h1 className="text-3xl sm:text-5xl font-extrabold tracking-tight text-white leading-tight">
              Cidadania Ativa:{" "}
              <span className="bg-gradient-to-r from-amber-400 via-orange-300 to-emerald-400 bg-clip-text text-transparent">
                O que o Congresso está decidindo hoje?
              </span>
            </h1>

            <p className="text-sm sm:text-base text-slate-300 leading-relaxed">
              Não basta apenas fiscalizar: exerça seu papel soberano no debate legislativo.
              Consulte os Projetos de Lei e PECs em discussão pública e registre seu voto popular
              diretamente nas consultas ativas do <strong>Senado Federal (e-Cidadania)</strong> e da <strong>Câmara dos Deputados (e-Democracia)</strong>.
            </p>

            {/* Aviso de Transparência e Validade Governamental */}
            <div className="flex items-start gap-3 p-4 rounded-2xl bg-slate-900/90 border border-slate-800/80 text-xs text-slate-300 shadow-sm">
              <ShieldCheck className="w-5 h-5 text-emerald-400 flex-shrink-0 mt-0.5" />
              <div>
                <strong className="text-emerald-400 font-semibold block mb-0.5">
                  Votação Oficial e Segura nos Portais do Governo
                </strong>
                O LegisData monitora em tempo real as matérias abertas para participação popular.
                Para consultas ativas, ao clicar em <em>&quot;Votar no Site Oficial&quot;</em>, você vota diretamente
                na plataforma governamental. Para matérias cuja votação já encerrou (como a PEC 45 da Reforma Tributária ou o Marco de IA),
                disponibilizamos o resultado histórico e o link permanente de tramitação oficial.
              </div>
            </div>
          </div>
        </section>

        {/* Estatísticas Rápidas */}
        <section className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4 sm:p-5 backdrop-blur-sm">
            <div className="flex items-center justify-between text-slate-400 text-xs mb-2">
              <span>Votação Aberta Agora</span>
              <Radio className="w-4 h-4 text-emerald-400 animate-pulse" />
            </div>
            <div className="text-2xl sm:text-3xl font-extrabold text-emerald-400">
              {stats.abertasCount}
            </div>
            <p className="text-[11px] text-slate-400 mt-1">Consultas públicas recebendo votos</p>
          </div>

          <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4 sm:p-5 backdrop-blur-sm">
            <div className="flex items-center justify-between text-slate-400 text-xs mb-2">
              <span>Encerradas / Históricas</span>
              <FileCheck2 className="w-4 h-4 text-amber-400" />
            </div>
            <div className="text-2xl sm:text-3xl font-extrabold text-amber-300">
              {stats.encerradasCount}
            </div>
            <p className="text-[11px] text-slate-400 mt-1">Tramitação e resultados preservados</p>
          </div>

          <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4 sm:p-5 backdrop-blur-sm">
            <div className="flex items-center justify-between text-slate-400 text-xs mb-2">
              <span>Proposições Listadas</span>
              <Sparkles className="w-4 h-4 text-cyan-400" />
            </div>
            <div className="text-2xl sm:text-3xl font-extrabold text-white">
              {stats.total}
            </div>
            <p className="text-[11px] text-slate-400 mt-1">Senado ({stats.senadoCount}) e Câmara ({stats.camaraCount})</p>
          </div>

          <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4 sm:p-5 backdrop-blur-sm">
            <div className="flex items-center justify-between text-slate-400 text-xs mb-2">
              <span>Votos Populares</span>
              <Users className="w-4 h-4 text-purple-400" />
            </div>
            <div className="text-2xl sm:text-3xl font-extrabold text-purple-400">
              {stats.totalVotosColetados > 0
                ? `${(stats.totalVotosColetados / 1000).toFixed(0)}k+`
                : "Milhares"}
            </div>
            <p className="text-[11px] text-slate-400 mt-1">Manifestações de cidadãos apuradas</p>
          </div>
        </section>

        {/* Barra de Filtros e Busca */}
        <section className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 sm:p-5 space-y-4">
          <div className="flex flex-col md:flex-row gap-4 justify-between items-stretch md:items-center">
            {/* Campo de Busca */}
            <div className="relative flex-1">
              <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Buscar por tema (ex.: Imposto de Renda, Escala 6x1, Inteligência Artificial, Reforma Tributária)..."
                className="w-full pl-10 pr-4 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-amber-500/50 transition-colors"
              />
              {searchTerm && (
                <button
                  onClick={() => setSearchTerm("")}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-400 hover:text-slate-200"
                >
                  Limpar
                </button>
              )}
            </div>

            {/* Ações e Atualização */}
            <div className="flex items-center gap-2 flex-wrap">
              {/* Filtro por Status da Votação */}
              <div className="inline-flex p-1 bg-slate-950 border border-slate-800 rounded-xl text-xs font-medium">
                <button
                  onClick={() => setSelectedStatus("TODAS")}
                  className={`px-3 py-1.5 rounded-lg transition-all ${
                    selectedStatus === "TODAS"
                      ? "bg-slate-800 text-white font-bold shadow-sm"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  Todas ({stats.total})
                </button>
                <button
                  onClick={() => setSelectedStatus("ABERTAS")}
                  className={`px-3 py-1.5 rounded-lg transition-all flex items-center gap-1.5 ${
                    selectedStatus === "ABERTAS"
                      ? "bg-emerald-600/30 text-emerald-300 font-bold border border-emerald-500/40"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <span className="w-2 h-2 rounded-full bg-emerald-400 inline-block animate-pulse"></span>
                  Votação Aberta ({stats.abertasCount})
                </button>
                <button
                  onClick={() => setSelectedStatus("ENCERRADAS")}
                  className={`px-3 py-1.5 rounded-lg transition-all ${
                    selectedStatus === "ENCERRADAS"
                      ? "bg-amber-600/30 text-amber-300 font-bold border border-amber-500/40"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  Encerradas ({stats.encerradasCount})
                </button>
              </div>

              {/* Filtro por Casa */}
              <div className="inline-flex p-1 bg-slate-950 border border-slate-800 rounded-xl text-xs font-medium">
                <button
                  onClick={() => setSelectedCasa("TODAS")}
                  className={`px-3 py-1.5 rounded-lg transition-all ${
                    selectedCasa === "TODAS"
                      ? "bg-slate-800 text-white font-bold shadow-sm"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  Casas
                </button>
                <button
                  onClick={() => setSelectedCasa("Senado")}
                  className={`px-3 py-1.5 rounded-lg transition-all ${
                    selectedCasa === "Senado"
                      ? "bg-blue-600/30 text-blue-300 font-bold border border-blue-500/40"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  Senado
                </button>
                <button
                  onClick={() => setSelectedCasa("Câmara")}
                  className={`px-3 py-1.5 rounded-lg transition-all ${
                    selectedCasa === "Câmara"
                      ? "bg-emerald-600/30 text-emerald-300 font-bold border border-emerald-500/40"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  Câmara
                </button>
              </div>

              {/* Botão de Atualização Forçada */}
              <button
                onClick={() => carregarConsultas(true)}
                disabled={isRefreshing}
                className="flex items-center gap-2 px-3 py-2 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-300 hover:text-white hover:bg-slate-800/60 transition-all disabled:opacity-50"
                title="Renovar cache oficial das consultas"
              >
                <RefreshCw
                  className={`w-3.5 h-3.5 text-amber-400 ${
                    isRefreshing ? "animate-spin" : ""
                  }`}
                />
                <span className="hidden sm:inline">Atualizar</span>
              </button>
            </div>
          </div>
        </section>

        {/* Listagem de Cards de Votação */}
        {isLoading ? (
          <div className="py-20 flex flex-col items-center justify-center space-y-4 text-center">
            <div className="w-12 h-12 rounded-full border-4 border-amber-400/20 border-t-amber-400 animate-spin" />
            <p className="text-slate-400 text-sm font-medium">
              Conectando em tempo real com as APIs do Senado Federal e da Câmara dos Deputados...
            </p>
          </div>
        ) : filteredConsultas.length === 0 ? (
          <div className="bg-slate-900/40 border border-slate-800/80 rounded-3xl p-12 text-center space-y-3">
            <HelpCircle className="w-10 h-10 text-slate-500 mx-auto" />
            <h3 className="text-lg font-bold text-white">Nenhuma consulta encontrada</h3>
            <p className="text-sm text-slate-400 max-w-md mx-auto">
              Nenhum projeto corresponde aos filtros aplicados. Tente buscar por outros termos ou redefinir os filtros.
            </p>
            <button
              onClick={() => {
                setSearchTerm("");
                setSelectedCasa("TODAS");
                setSelectedStatus("TODAS");
                setOnlyWithVotes(false);
              }}
              className="mt-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-xs font-semibold rounded-xl text-white transition-colors"
            >
              Limpar todos os filtros
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {filteredConsultas.map((item) => {
              const temPlacar =
                item.votos_sim !== null && item.votos_nao !== null && (item.total_votos ?? 0) > 0;
              const isSenado = item.casa === "Senado";
              const isAberta = item.em_votacao_aberta === true;

              return (
                <div
                  key={`${item.casa}-${item.id_externo}-${item.sigla_projeto}`}
                  className="flex flex-col justify-between bg-slate-900/70 border border-slate-800/90 rounded-2xl p-6 hover:border-slate-700 transition-all duration-200 shadow-lg hover:shadow-xl hover:shadow-black/40 group relative overflow-hidden"
                >
                  {/* Barra de destaque superior se for tema de alta relevância */}
                  {item.destaque && (
                    <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-amber-400 via-orange-500 to-emerald-400" />
                  )}

                  <div className="space-y-4">
                    {/* Topo do Card: Casa, Sigla, Status e Destaque */}
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-center gap-2 flex-wrap">
                        {/* Badge de Status da Votação */}
                        {isAberta ? (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-bold uppercase tracking-wider bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                            <span className="relative flex h-2 w-2">
                              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                            </span>
                            Votação Aberta Agora
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold bg-slate-800/90 text-slate-300 border border-slate-700/80">
                            <CheckCircle2 className="w-3.5 h-3.5 text-amber-400" />
                            {item.status?.includes("Promulgada") ? "Matéria Promulgada" : "Consulta Encerrada"}
                          </span>
                        )}

                        {/* Badge da Casa */}
                        <span
                          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-bold uppercase tracking-wider ${
                            isSenado
                              ? "bg-blue-500/15 text-blue-300 border border-blue-500/30"
                              : "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                          }`}
                        >
                          {isSenado ? (
                            <Landmark className="w-3.5 h-3.5 text-blue-400" />
                          ) : (
                            <Building2 className="w-3.5 h-3.5 text-emerald-400" />
                          )}
                          <span>{item.casa}</span>
                        </span>

                        {/* Badge de Tema */}
                        {item.tema && (
                          <span className="px-2.5 py-1 rounded-lg text-xs font-medium bg-slate-800/80 text-slate-300 border border-slate-700/60">
                            {item.tema}
                          </span>
                        )}

                        {/* Badge de Destaque Popular */}
                        {item.destaque && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-black uppercase tracking-wider bg-amber-500/20 text-amber-300 border border-amber-500/40">
                            <Flame className="w-3 h-3 text-amber-400" />
                            Alta Relevância
                          </span>
                        )}
                      </div>

                      {/* Botão de Compartilhar Link */}
                      <button
                        onClick={() => handleShare(item)}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
                        title="Copiar link oficial da consulta"
                      >
                        {copiedId === item.id_externo ? (
                          <Check className="w-4 h-4 text-emerald-400" />
                        ) : (
                          <Share2 className="w-4 h-4" />
                        )}
                      </button>
                    </div>

                    {/* Título do Projeto */}
                    <div>
                      <h2 className="text-xl font-bold text-white group-hover:text-amber-300 transition-colors">
                        {item.sigla_projeto}
                      </h2>
                      {item.autor && (
                        <p className="text-xs text-slate-400 mt-1 flex items-center gap-1">
                          <span className="font-semibold text-slate-300">Autoria:</span> {item.autor}
                        </p>
                      )}
                    </div>

                    {/* Ementa do Projeto */}
                    <p className="text-xs sm:text-sm text-slate-300 leading-relaxed line-clamp-4">
                      {item.ementa}
                    </p>

                    {/* Placar Popular (Se Disponível) */}
                    {temPlacar ? (
                      <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-4 space-y-2.5">
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-semibold text-slate-300 flex items-center gap-1.5">
                            <Users className="w-3.5 h-3.5 text-purple-400" />
                            {isAberta ? "Placar Parcial em Tempo Real:" : "Placar Final Apurado:"}
                          </span>
                          <span className="text-[11px] text-slate-400 font-mono">
                            {(item.total_votos ?? 0).toLocaleString("pt-BR")} votos computados
                          </span>
                        </div>

                        {/* Barra de Progresso Bipolar (SIM vs NÃO) */}
                        <div className="h-3 w-full bg-slate-800 rounded-full overflow-hidden flex shadow-inner">
                          <div
                            style={{ width: `${item.percentual_sim ?? 50}%` }}
                            className="h-full bg-gradient-to-r from-emerald-500 to-teal-400 transition-all duration-500"
                            title={`SIM: ${item.percentual_sim}%`}
                          />
                          <div
                            style={{ width: `${item.percentual_nao ?? 50}%` }}
                            className="h-full bg-gradient-to-r from-rose-500 to-red-600 transition-all duration-500"
                            title={`NÃO: ${item.percentual_nao}%`}
                          />
                        </div>

                        {/* Legenda de Porcentagens */}
                        <div className="flex items-center justify-between text-xs font-semibold pt-1">
                          <div className="flex items-center gap-1 text-emerald-400">
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            <span>
                              SIM: {item.percentual_sim}%{" "}
                              <span className="text-[10px] text-slate-400 font-normal">
                                ({item.votos_sim?.toLocaleString("pt-BR")})
                              </span>
                            </span>
                          </div>
                          <div className="flex items-center gap-1 text-rose-400">
                            <XCircle className="w-3.5 h-3.5" />
                            <span>
                              NÃO: {item.percentual_nao}%{" "}
                              <span className="text-[10px] text-slate-400 font-normal">
                                ({item.votos_nao?.toLocaleString("pt-BR")})
                              </span>
                            </span>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="bg-slate-950/50 border border-slate-800/80 rounded-xl p-3 flex items-center gap-2.5 text-xs text-slate-400">
                        <Info className="w-4 h-4 text-cyan-400 flex-shrink-0" />
                        <span>
                          {isAberta
                            ? "Consulta pública aberta no portal governamental. Acesse para registrar sua manifestação."
                            : "Matéria em tramitação legislativa no Congresso Nacional."}
                        </span>
                      </div>
                    )}
                  </div>

                  {/* Rodapé do Card com CTA Oficial */}
                  <div className="pt-5 mt-5 border-t border-slate-800/80 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
                    <div className="text-[11px] text-slate-400 flex flex-col gap-0.5">
                      <span className="flex items-center gap-1">
                        <Calendar className="w-3.5 h-3.5 text-slate-500" />
                        {item.data_apresentacao
                          ? `Apresentado em ${item.data_apresentacao}`
                          : item.status || "Em tramitação"}
                      </span>
                      {item.link_tramitacao_oficial && isAberta && (
                        <a
                          href={item.link_tramitacao_oficial}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[10px] text-amber-400/80 hover:text-amber-300 flex items-center gap-1 underline pt-0.5"
                        >
                          <span>Ficha de Tramitação no Congresso</span>
                          <ExternalLink className="w-2.5 h-2.5" />
                        </a>
                      )}
                    </div>

                    {/* Botão de Ação: Diferenciado para Aberta vs Concluída */}
                    {isAberta ? (
                      <a
                        href={item.link_oficial_votacao}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold text-slate-950 bg-gradient-to-r from-emerald-400 via-teal-300 to-emerald-300 hover:from-emerald-300 hover:to-teal-200 shadow-md shadow-emerald-500/20 hover:shadow-emerald-500/40 transition-all hover:scale-[1.02] active:scale-[0.98]"
                      >
                        <span>Votar no Site Oficial</span>
                        <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                    ) : (
                      <a
                        href={item.link_tramitacao_oficial || item.link_oficial_votacao}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold text-slate-200 bg-slate-800 hover:bg-slate-700 hover:text-white border border-slate-700 shadow transition-all hover:scale-[1.02] active:scale-[0.98]"
                      >
                        <span>Ver Tramitação & Resultado</span>
                        <ExternalLink className="w-3.5 h-3.5 text-slate-400" />
                      </a>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Seção Informativa de Apoio ao Cidadão */}
        <section className="bg-slate-900/40 border border-slate-800/80 rounded-3xl p-6 sm:p-8 space-y-4">
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-emerald-400" />
            <span>Como funciona o impacto dos votos populares no Congresso?</span>
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 text-xs text-slate-300 leading-relaxed">
            <div className="space-y-1.5 p-4 rounded-xl bg-slate-950/60 border border-slate-800/60">
              <strong className="text-white block font-semibold">1. Relatórios de Opinião Pública</strong>
              Tanto no e-Cidadania quanto no e-Democracia, os votos coletados são compilados em relatórios periódicos entregues aos relatores de cada matéria nas comissões temáticas.
            </div>
            <div className="space-y-1.5 p-4 rounded-xl bg-slate-950/60 border border-slate-800/60">
              <strong className="text-white block font-semibold">2. Audiências e Emendas Populares</strong>
              Matérias com alta adesão popular ganham prioridade nas pautas de votação dos colégios de líderes e costumam gerar audiências públicas transmitidas ao vivo pela TV Senado e TV Câmara.
            </div>
            <div className="space-y-1.5 p-4 rounded-xl bg-slate-950/60 border border-slate-800/60">
              <strong className="text-white block font-semibold">3. Integridade e Autenticidade</strong>
              Ao votar no portal oficial, o Governo valida a autenticidade através da conta Gov.br, garantindo que o placar popular seja protegido contra ataques de bots e manipulações.
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
