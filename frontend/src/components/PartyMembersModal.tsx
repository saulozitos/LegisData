"use client";

import React, { useState, useEffect, useMemo } from "react";
import {
  X,
  Search,
  Users,
  Landmark,
  ArrowRight,
  Filter,
  Sparkles,
  ExternalLink,
} from "lucide-react";
import {
  searchPoliticians,
  getParties,
  PoliticoBuscaItem,
  PartidoCatalogoItem,
} from "@/services/api";
import { PartyLogoBadge } from "./PartiesPanel";

interface PartyMembersModalProps {
  partySigla: string | null;
  isOpen: boolean;
  onClose: () => void;
  onSelectPolitician: (politicianId: string) => void;
}

export default function PartyMembersModal({
  partySigla,
  isOpen,
  onClose,
  onSelectPolitician,
}: PartyMembersModalProps) {
  const [politicians, setPoliticians] = useState<PoliticoBuscaItem[]>([]);
  const [partyInfo, setPartyInfo] = useState<PartidoCatalogoItem | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [houseFilter, setHouseFilter] = useState<"TODOS" | "DEPUTADO_FEDERAL" | "SENADOR">("TODOS");
  const [searchTerm, setSearchTerm] = useState<string>("");

  // Carregar dados do partido e parlamentares
  useEffect(() => {
    if (!isOpen || !partySigla) {
      setPoliticians([]);
      setPartyInfo(null);
      setSearchTerm("");
      return;
    }

    async function loadData() {
      setLoading(true);
      try {
        const [partiesRes, polsRes] = await Promise.all([
          getParties(),
          searchPoliticians(
            undefined,
            houseFilter === "TODOS" ? undefined : houseFilter,
            partySigla!,
            undefined,
            300
          ),
        ]);

        if (partiesRes) {
          const found = partiesRes.find(
            (p) => p.sigla.toUpperCase() === partySigla!.toUpperCase()
          );
          setPartyInfo(found || null);
        }

        if (polsRes) {
          setPoliticians(polsRes.politicos);
        }
      } catch (err) {
        console.error("Erro ao carregar bancada do partido:", err);
      } finally {
        setLoading(false);
      }
    }

    loadData();
  }, [isOpen, partySigla, houseFilter]);

  // Tecla Esc para fechar
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  // Filtragem local por busca
  const filteredPoliticians = useMemo(() => {
    if (!searchTerm.trim()) return politicians;
    const term = searchTerm.toLowerCase();
    return politicians.filter(
      (p) =>
        p.nome_eleitoral.toLowerCase().includes(term) ||
        p.nome_civil.toLowerCase().includes(term) ||
        p.uf.toLowerCase().includes(term)
    );
  }, [politicians, searchTerm]);

  if (!isOpen || !partySigla) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 md:p-6 overflow-y-auto">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-slate-950/80 backdrop-blur-md transition-opacity animate-in fade-in duration-200"
        onClick={onClose}
      />

      {/* Conteúdo do Modal */}
      <div className="relative bg-slate-900 border border-slate-800 rounded-3xl shadow-2xl max-w-5xl w-full max-h-[90vh] flex flex-col z-10 overflow-hidden animate-in zoom-in-95 duration-200">
        {/* Faixa decorativa com a cor do partido */}
        <div
          className="h-2 w-full flex-shrink-0"
          style={{ backgroundColor: partyInfo?.cor_hex || "#06b6d4" }}
        />

        {/* Topo / Cabeçalho */}
        <div className="p-5 sm:p-6 border-b border-slate-800/80 flex flex-col sm:flex-row sm:items-center justify-between gap-4 flex-shrink-0 bg-slate-950/40">
          <div className="flex items-start sm:items-center gap-3.5">
            <PartyLogoBadge
              sigla={partySigla || ""}
              logoUrl={partyInfo?.logo_url}
              corHex={partyInfo?.cor_hex}
              size="md"
            />

            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="text-xl font-black text-white">
                  Bancada: {partySigla}
                </h3>
                {partyInfo?.nome_completo && (
                  <span className="text-xs text-slate-400 font-medium">
                    ({partyInfo.nome_completo})
                  </span>
                )}
                {partyInfo?.numero_eleitoral && (
                  <span className="text-[11px] font-mono font-bold px-2 py-0.5 rounded-lg bg-slate-900 text-slate-300 border border-slate-800">
                    Nº {partyInfo.numero_eleitoral}
                  </span>
                )}
              </div>

              {partyInfo && (
                <div className="flex items-center gap-3 mt-1 text-xs text-slate-400 flex-wrap">
                  {partyInfo.ideologia && (
                    <span className="text-cyan-400 font-medium">
                      {partyInfo.ideologia}
                    </span>
                  )}
                  {partyInfo.lema && (
                    <span className="italic text-slate-400">
                      &ldquo;{partyInfo.lema}&rdquo;
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>

          <button
            onClick={onClose}
            aria-label="Fechar modal"
            className="self-end sm:self-center p-2 rounded-xl bg-slate-800/80 hover:bg-slate-700 text-slate-400 hover:text-white transition-colors border border-slate-700/60"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Filtros e Busca Interna */}
        <div className="p-4 sm:p-5 bg-slate-950/60 border-b border-slate-800/80 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 flex-shrink-0">
          <div className="flex items-center gap-1.5 bg-slate-900 p-1 rounded-xl border border-slate-800 max-w-fit">
            <button
              onClick={() => setHouseFilter("TODOS")}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                houseFilter === "TODOS"
                  ? "bg-slate-800 text-white shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Todos ({politicians.length})
            </button>
            <button
              onClick={() => setHouseFilter("DEPUTADO_FEDERAL")}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                houseFilter === "DEPUTADO_FEDERAL"
                  ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Deputados Federais
            </button>
            <button
              onClick={() => setHouseFilter("SENADOR")}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                houseFilter === "SENADOR"
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Senadores
            </button>
          </div>

          <div className="relative flex-1 max-w-md">
            <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder={`Filtrar parlamentares do ${partySigla} por nome ou UF...`}
              className="w-full bg-slate-900 border border-slate-700/80 rounded-xl pl-9 pr-4 py-2 text-xs sm:text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-400 transition-colors shadow-inner"
            />
          </div>
        </div>

        {/* Grade de Parlamentares */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 custom-scrollbar">
          {loading ? (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3 animate-pulse">
              {Array.from({ length: 10 }).map((_, i) => (
                <div
                  key={i}
                  className="bg-slate-950/50 border border-slate-800 rounded-2xl p-4 h-44 flex flex-col items-center justify-center space-y-2"
                >
                  <div className="w-16 h-16 rounded-xl bg-slate-800" />
                  <div className="h-4 bg-slate-800 rounded w-3/4" />
                  <div className="h-3 bg-slate-800/60 rounded w-1/2" />
                </div>
              ))}
            </div>
          ) : filteredPoliticians.length === 0 ? (
            <div className="text-center py-16 space-y-2">
              <Users className="w-10 h-10 text-slate-600 mx-auto" />
              <p className="text-sm font-semibold text-slate-300">
                Nenhum parlamentar encontrado para o filtro selecionado.
              </p>
              <p className="text-xs text-slate-500">
                {searchTerm
                  ? "Tente buscar por outro nome ou estado."
                  : `Nenhum membro ativo cadastrado no ${partySigla} para esta Casa.`}
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3.5">
              {filteredPoliticians.map((pol) => (
                <div
                  key={pol.id}
                  onClick={() => onSelectPolitician(pol.id)}
                  title={`Clique para abrir o Raio-X de ${pol.nome_eleitoral}`}
                  className="bg-slate-950/70 border border-slate-800 hover:border-cyan-400/90 rounded-2xl p-3 flex flex-col items-center text-center transition-all duration-200 hover:scale-[1.03] hover:bg-slate-900 group shadow-md cursor-pointer hover:shadow-cyan-950/40 relative"
                >
                  {/* Avatar do Político */}
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

                  {/* Badges */}
                  <div className="mt-auto pt-2 w-full flex items-center justify-center gap-1 text-[10px]">
                    <span className="px-1.5 py-0.5 rounded bg-slate-900 text-slate-400 font-semibold border border-slate-800">
                      {pol.cargo === "SENADOR" ? "Senador" : "Deputado"}
                    </span>
                    <span className="text-slate-500 font-bold">{pol.uf}</span>
                  </div>

                  {/* Botão de Dossiê */}
                  <div className="mt-2 text-[10px] font-semibold text-cyan-400/80 group-hover:text-cyan-300 flex items-center gap-1 transition-colors">
                    <span>Abrir Raio-X</span>
                    <ArrowRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Rodapé Informativo */}
        <div className="p-4 bg-slate-950/70 border-t border-slate-800/80 flex flex-col sm:flex-row items-center justify-between text-xs text-slate-400 gap-2 flex-shrink-0">
          <div>
            Exibindo <strong className="text-white">{filteredPoliticians.length}</strong> de{" "}
            <strong className="text-white">{politicians.length}</strong> parlamentares da bancada do{" "}
            <strong className="text-cyan-400">{partySigla}</strong>
          </div>
          <span className="text-slate-500 text-[11px]">
            Clique em qualquer parlamentar para abrir o dossiê no Raio-X
          </span>
        </div>
      </div>
    </div>
  );
}
