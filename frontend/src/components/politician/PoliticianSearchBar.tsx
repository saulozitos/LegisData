"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  Search,
  Sparkles,
} from "lucide-react";
import type { PoliticoBuscaItem } from "@/services/api";
import { safeExternalUrl } from "@/lib/safeUrl";

const QUICK_PICKS = [
  { label: "Baleia Rossi", search: "Baleia" },
  { label: "Arthur Lira", search: "Lira" },
  { label: "Rodrigo Pacheco", search: "Pacheco" },
  { label: "Luiz Inácio Lula da Silva", search: "Lula" },
  { label: "Jair Bolsonaro", search: "Bolsonaro" },
  { label: "Eduardo Braga", search: "Braga" },
];

interface PoliticianSearchBarProps {
  searchTerm: string;
  setSearchTerm: (value: string) => void;
  officeFilter: string;
  setOfficeFilter: (value: string) => void;
  searchResults: PoliticoBuscaItem[];
  isSearching: boolean;
  onSelect: (pol: PoliticoBuscaItem) => void;
  onSelectParty?: (sigla: string) => void;
}

export default function PoliticianSearchBar({
  searchTerm,
  setSearchTerm,
  officeFilter,
  setOfficeFilter,
  searchResults,
  isSearching,
  onSelect,
}: PoliticianSearchBarProps) {
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const searchBoxRef = useRef<HTMLDivElement>(null);

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

  return (
      <div className="bg-slate-900/70 border border-slate-800/90 rounded-2xl p-5 backdrop-blur-md shadow-xl shadow-cyan-950/10 space-y-4 relative z-50">
        <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="p-2 rounded-xl bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                <Search className="w-5 h-5" aria-hidden="true" />
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
              aria-pressed={officeFilter === "TODOS"}
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
              aria-pressed={officeFilter === "DEPUTADO_FEDERAL"}
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
              aria-pressed={officeFilter === "SENADOR"}
              onClick={() => setOfficeFilter("SENADOR")}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                officeFilter === "SENADOR"
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Senadores
            </button>
            <button
              aria-pressed={officeFilter === "PRESIDENTE"}
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
            <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" aria-hidden="true" />
            <input
              type="text"
              value={searchTerm}
              role="combobox"
              aria-expanded={isDropdownOpen && searchResults.length > 0}
              aria-controls="politician-search-results"
              aria-autocomplete="list"
              aria-label="Buscar político pelo nome"
              onChange={(e) => {
                setSearchTerm(e.target.value);
                setIsDropdownOpen(true);
              }}
              onFocus={() => setIsDropdownOpen(true)}
              onKeyDown={(e) => {
                if (e.key === "Escape") setIsDropdownOpen(false);
              }}
              placeholder="Digite o nome de um político para abrir o Raio-X (ex: Baleia Rossi, Arthur Lira, Lula, Pacheco)..."
              className="w-full bg-slate-950 border border-slate-700/80 rounded-xl pl-10 pr-4 py-2.5 text-sm text-slate-100 placeholder-slate-400 focus:outline-none focus:border-cyan-400 transition-colors shadow-inner"
            />
            {isSearching && (
              <span role="status" className="absolute right-3.5 top-1/2 -translate-y-1/2 text-xs text-slate-400 animate-pulse">
                Buscando...
              </span>
            )}
          </div>

          {/* Dropdown de Sugestões em Tempo Real com Alta Prioridade de Sobreposição */}
          {isDropdownOpen && searchResults.length > 0 && (
            <ul id="politician-search-results" role="listbox" aria-label="Sugestões de políticos" className="absolute left-0 right-0 top-full mt-2 bg-slate-950 border border-slate-800 rounded-xl max-h-72 overflow-y-auto shadow-2xl z-[100] divide-y divide-slate-900 list-none p-0 m-0">
              {searchResults.map((pol) => (
                <li key={pol.id} role="option" aria-selected={false}>
                <button
                  type="button"
                  onClick={() => {
                    setIsDropdownOpen(false);
                    onSelect(pol);
                  }}
                  className="w-full text-left p-3 hover:bg-slate-900/90 focus:bg-slate-900/90 focus:outline-none cursor-pointer transition-colors flex items-center justify-between gap-3"
                >
                  <div className="flex items-center gap-3">
                    <div className="relative w-8 h-8 rounded-full overflow-hidden bg-slate-800 border border-slate-700 flex-shrink-0 flex items-center justify-center">
                      {safeExternalUrl(pol.foto_url) ? (
                        <img
                          src={safeExternalUrl(pol.foto_url)}
                          alt=""
                          referrerPolicy="no-referrer"
                          className="w-full h-full object-cover"
                          onError={(e) => {
                            e.currentTarget.style.display = "none";
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
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 font-mono">
                      {pol.partido_sigla}
                    </span>
                    <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
                      {pol.uf}
                    </span>
                    <span className="text-[10px] font-semibold text-slate-400">
                      {pol.cargo === "PRESIDENTE" ? "Presidente" : pol.cargo === "SENADOR" ? "Senador" : "Deputado"}
                    </span>
                  </div>
                </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Atalhos Rápidos */}
        <div className="flex items-center gap-1.5 flex-wrap pt-1 text-xs">
          <span className="text-slate-400 font-semibold mr-1 flex items-center gap-1">
            <Sparkles className="w-3.5 h-3.5 text-amber-400" aria-hidden="true" /> Consultas rápidas:
          </span>
          {QUICK_PICKS.map((item) => (
            <button
              type="button"
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
  );
}
