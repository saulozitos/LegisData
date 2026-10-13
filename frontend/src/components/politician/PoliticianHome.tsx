"use client";

import React, { useMemo, useState } from "react";
import {
  Search,
  Users,
  Landmark,
  ArrowRight,
  Filter,
} from "lucide-react";
import { getParties, searchPoliticians } from "@/services/api";
import type { PartidoCatalogoItem } from "@/services/api";
import { useApi } from "@/hooks/useApi";
import { safeExternalUrl } from "@/lib/safeUrl";
import { ErrorState } from "@/components/StateViews";

interface PoliticianHomeProps {
  onSelectPolitician: (id: string) => void;
}

const PAGE_SIZE = 120;

/** Catálogo geral de parlamentares exibido enquanto nenhum político está selecionado. */
export default function PoliticianHome({ onSelectPolitician }: PoliticianHomeProps) {
  const [homeParty, setHomeParty] = useState<string>("TODOS");
  const [homeOffice, setHomeOffice] = useState<string>("TODOS");
  const [homeSearchTerm, setHomeSearchTerm] = useState<string>("");

  const partiesQuery = useApi("parties", (signal) => getParties(signal));
  const partiesList = useMemo(() => partiesQuery.data ?? [], [partiesQuery.data]);

  // Sem partido escolhido, limita o volume; com partido, traz a bancada.
  const homeQuery = useApi(`home-politicians:${homeOffice}:${homeParty}`, (signal) =>
    searchPoliticians(
      undefined,
      homeOffice === "TODOS" ? undefined : homeOffice,
      homeParty === "TODOS" ? undefined : homeParty,
      undefined,
      homeParty === "TODOS" ? 500 : 300,
      signal
    )
  );
  const homePoliticians = useMemo(() => homeQuery.data?.politicos ?? [], [homeQuery.data]);
  const isHomeLoading = homeQuery.loading;

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

  // Renderização incremental: evita montar centenas de cartões de uma vez. O limite volta ao inicial ao mudar filtros.
  const filtersKey = `${homeOffice}|${homeParty}|${homeSearchTerm}`;
  const [visible, setVisible] = useState<{ key: string; count: number }>({ key: filtersKey, count: PAGE_SIZE });
  const visibleCount = visible.key === filtersKey ? visible.count : PAGE_SIZE;
  const visiblePoliticians = useMemo(
    () => filteredHomePoliticians.slice(0, visibleCount),
    [filteredHomePoliticians, visibleCount]
  );
  const hasMore = filteredHomePoliticians.length > visiblePoliticians.length;

  const sentinelRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    if (!hasMore || isHomeLoading) return;
    if (typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          setVisible((prev) => ({ key: prev.key, count: prev.count + PAGE_SIZE }));
        }
      },
      { rootMargin: "300px" }
    );
    const el = sentinelRef.current;
    if (el) observer.observe(el);
    return () => {
      if (el) observer.unobserve(el);
    };
  }, [hasMore, isHomeLoading, filtersKey]);

  // Agrupamento por partido quando 'TODOS' estiver selecionado
  const groupedPoliticians = useMemo(() => {
    const groups: Record<string, typeof homePoliticians> = {};
    for (const pol of visiblePoliticians) {
      const sigla = pol.partido_sigla || "OUTROS";
      if (!groups[sigla]) groups[sigla] = [];
      groups[sigla].push(pol);
    }
    return Object.entries(groups).sort((a, b) => b[1].length - a[1].length);
  }, [visiblePoliticians]);

  // Mapa rápido de informações dos partidos
  const partyMetaMap = useMemo(() => {
    const map = new Map<string, PartidoCatalogoItem>();
    partiesList.forEach((p) => map.set(p.sigla.toUpperCase(), p));
    return map;
  }, [partiesList]);

  return (
        <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-6 backdrop-blur-md shadow-2xl space-y-6">
          {/* Cabeçalho da Home */}
          <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 pb-6 border-b border-slate-800">
            <div className="flex items-center gap-3.5">
              <div className="p-3 rounded-2xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 flex-shrink-0">
                <Users className="w-6 h-6" aria-hidden="true" />
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
              <label htmlFor="home-party-select" className="text-[11px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                <Filter className="w-3.5 h-3.5 text-cyan-400" aria-hidden="true" /> Bancada Partidária
              </label>
              <select
                id="home-party-select"
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
                <Landmark className="w-3.5 h-3.5 text-emerald-400" aria-hidden="true" /> Casa Legislativa
              </label>
              <div className="flex items-center gap-1 bg-slate-900 p-1 rounded-xl border border-slate-700/80">
                <button
                  aria-pressed={homeOffice === "TODOS"}
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
                  aria-pressed={homeOffice === "DEPUTADO_FEDERAL"}
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
                  aria-pressed={homeOffice === "SENADOR"}
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
              <label htmlFor="home-filter-input" className="text-[11px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                <Search className="w-3.5 h-3.5 text-amber-400" aria-hidden="true" /> Filtrar Parlamentares
              </label>
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" aria-hidden="true" />
                <input
                  id="home-filter-input"
                  type="text"
                  value={homeSearchTerm}
                  onChange={(e) => setHomeSearchTerm(e.target.value)}
                  placeholder="Nome ou UF (ex: SP, RJ)..."
                  className="w-full bg-slate-900 border border-slate-700/80 rounded-xl pl-8 pr-3 py-2 text-xs text-slate-100 placeholder-slate-400 focus:outline-none focus:border-cyan-400 transition-colors shadow-inner"
                />
              </div>
            </div>
          </div>

          {/* Grade de Parlamentares */}
          {homeQuery.error ? (
            <ErrorState onRetry={homeQuery.retry} />
          ) : isHomeLoading ? (
            <div role="status" aria-live="polite" className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3.5 animate-pulse py-4">
              <span className="sr-only">Carregando parlamentares...</span>
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
            <div role="status" className="text-center py-16 space-y-3">
              <Users className="w-12 h-12 text-slate-400 mx-auto" aria-hidden="true" />
              <p className="text-sm font-semibold text-slate-300">
                Nenhum parlamentar encontrado para o filtro selecionado.
              </p>
              <button
                type="button"
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
                {visiblePoliticians.map((pol) => (
                  <button
                    type="button"
                    key={pol.id}
                    onClick={() => onSelectPolitician(pol.id)}
                    title={`Clique para abrir o Raio-X de ${pol.nome_eleitoral}`}
                    className="bg-slate-950/70 border border-slate-800/90 hover:border-cyan-400/90 rounded-2xl p-3 flex flex-col items-center text-center transition-all duration-200 hover:scale-[1.03] hover:bg-slate-900 group shadow-md cursor-pointer hover:shadow-cyan-950/40 relative focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400"
                  >
                    {/* Foto / Avatar */}
                    <div className="relative mb-2.5">
                      {safeExternalUrl(pol.foto_url) ? (
                        <img
                          src={safeExternalUrl(pol.foto_url)}
                          alt=""
                          referrerPolicy="no-referrer"
                          className="w-16 h-16 rounded-xl object-cover border border-slate-700 group-hover:border-cyan-400 transition-colors shadow-sm"
                          onError={(e) => {
                            e.currentTarget.style.display = "none";
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
                      <span className="text-slate-400 font-bold">{pol.uf}</span>
                    </div>

                    <div className="mt-2 text-[10px] font-semibold text-cyan-400/80 group-hover:text-cyan-300 flex items-center gap-1 transition-colors">
                      <span>Raio-X</span>
                      <ArrowRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" aria-hidden="true" />
                    </div>
                  </button>
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
                        type="button"
                        onClick={() => setHomeParty(sigla)}
                        className="text-[11px] font-semibold text-cyan-400 hover:text-cyan-300 flex items-center gap-1 transition-colors"
                      >
                        <span>Ver só {sigla}</span>
                        <ArrowRight className="w-3 h-3" aria-hidden="true" />
                      </button>
                    </div>

                    {/* Grade de Avatares daquele Partido */}
                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3.5">
                      {pols.map((pol) => (
                        <button
                          type="button"
                          key={pol.id}
                          onClick={() => onSelectPolitician(pol.id)}
                          title={`Clique para abrir o Raio-X de ${pol.nome_eleitoral}`}
                          className="bg-slate-950/70 border border-slate-800/90 hover:border-cyan-400/90 rounded-2xl p-3 flex flex-col items-center text-center transition-all duration-200 hover:scale-[1.03] hover:bg-slate-900 group shadow-md cursor-pointer hover:shadow-cyan-950/40 relative focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400"
                        >
                          {/* Foto / Avatar */}
                          <div className="relative mb-2.5">
                            {safeExternalUrl(pol.foto_url) ? (
                              <img
                                src={safeExternalUrl(pol.foto_url)}
                                alt=""
                                referrerPolicy="no-referrer"
                                className="w-16 h-16 rounded-xl object-cover border border-slate-700 group-hover:border-cyan-400 transition-colors shadow-sm"
                                onError={(e) => {
                                  e.currentTarget.style.display = "none";
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
                            <span className="text-slate-400 font-bold">{pol.uf}</span>
                          </div>

                          <div className="mt-2 text-[10px] font-semibold text-cyan-400/80 group-hover:text-cyan-300 flex items-center gap-1 transition-colors">
                            <span>Raio-X</span>
                            <ArrowRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" aria-hidden="true" />
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {hasMore && !isHomeLoading && (
            <div className="flex flex-col items-center gap-2 pt-2">
              <div ref={sentinelRef} className="h-1 w-full pointer-events-none" aria-hidden="true" />
              <button
                type="button"
                onClick={() => setVisible({ key: filtersKey, count: visibleCount + PAGE_SIZE })}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-cyan-300 transition-colors"
              >
                Mostrar mais ({filteredHomePoliticians.length - visiblePoliticians.length} restantes)
              </button>
            </div>
          )}
        </div>
  );
}
