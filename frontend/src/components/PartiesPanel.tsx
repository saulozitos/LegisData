"use client";

import React, { useState, useEffect, useMemo } from "react";
import { getParties, PartidoCatalogoItem } from "@/services/api";
import {
  Users,
  Search,
  Filter,
  Landmark,
  Compass,
  Sparkles,
  ArrowRight,
  Shield,
  Layers,
  Award,
} from "lucide-react";

interface PartiesPanelProps {
  onSelectParty?: (sigla: string) => void;
  targetParty?: string | null;
  mandateId?: string | null;
}

const SPECTRUM_BADGE_CONFIG: Record<string, { label: string; bg: string; text: string; border: string }> = {
  ESQUERDA: {
    label: "Esquerda",
    bg: "bg-red-500/15",
    text: "text-red-400",
    border: "border-red-500/30",
  },
  CENTRO_ESQUERDA: {
    label: "Centro-Esquerda",
    bg: "bg-rose-500/15",
    text: "text-rose-300",
    border: "border-rose-500/30",
  },
  CENTRO: {
    label: "Centro",
    bg: "bg-amber-500/15",
    text: "text-amber-300",
    border: "border-amber-500/30",
  },
  CENTRO_DIREITA: {
    label: "Centro-Direita",
    bg: "bg-sky-500/15",
    text: "text-sky-300",
    border: "border-sky-500/30",
  },
  DIREITA: {
    label: "Direita",
    bg: "bg-blue-600/15",
    text: "text-blue-400",
    border: "border-blue-600/30",
  },
};

export function PartyLogoBadge({
  sigla,
  logoUrl,
  corHex,
  size = "md",
}: {
  sigla: string;
  logoUrl?: string | null;
  corHex?: string;
  size?: "sm" | "md" | "lg";
}) {
  const [hasError, setHasError] = useState(false);
  const color = corHex || "#3b82f6";
  const showImage = Boolean(logoUrl && !hasError);

  const sizeClasses = {
    sm: "w-10 h-10 rounded-xl p-1 text-xs",
    md: "w-14 h-14 rounded-2xl p-1.5 text-base",
    lg: "w-16 h-16 rounded-2xl p-2 text-lg",
  }[size];

  return (
    <div
      className={`${sizeClasses} flex items-center justify-center shadow-md border border-white/10 relative overflow-hidden flex-shrink-0 transition-transform duration-200 group-hover:scale-105`}
      style={{
        backgroundColor: showImage ? `${color}18` : color,
      }}
    >
      {showImage ? (
        <img
          src={logoUrl!}
          alt={`Logo ${sigla}`}
          onError={() => setHasError(true)}
          className="object-contain w-full h-full filter drop-shadow-sm transition-transform duration-300 group-hover:scale-105"
          loading="lazy"
        />
      ) : (
        <span className="font-black text-white tracking-wider">
          {sigla}
        </span>
      )}
    </div>
  );
}

export default function PartiesPanel({ onSelectParty, targetParty }: PartiesPanelProps) {
  const [parties, setParties] = useState<PartidoCatalogoItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState(targetParty || "");
  const [spectrumFilter, setSpectrumFilter] = useState("TODOS");

  useEffect(() => {
    if (targetParty) {
      setSearchTerm(targetParty);
    }
  }, [targetParty]);

  useEffect(() => {
    async function loadParties() {
      setLoading(true);
      try {
        const data = await getParties();
        setParties(data);
      } catch (err) {
        console.error("Erro ao carregar catálogo de partidos:", err);
      } finally {
        setLoading(false);
      }
    }
    loadParties();
  }, []);

  const filteredParties = useMemo(() => {
    return parties.filter((p) => {
      const matchSearch =
        !searchTerm.trim() ||
        p.sigla.toLowerCase().includes(searchTerm.toLowerCase()) ||
        p.nome_completo.toLowerCase().includes(searchTerm.toLowerCase()) ||
        p.ideologia.toLowerCase().includes(searchTerm.toLowerCase()) ||
        p.lema.toLowerCase().includes(searchTerm.toLowerCase());

      const matchSpectrum =
        spectrumFilter === "TODOS" || p.espectro_politico === spectrumFilter;

      return matchSearch && matchSpectrum;
    });
  }, [parties, searchTerm, spectrumFilter]);

  // Estatísticas rápidas
  const totalBancada = useMemo(
    () => parties.reduce((acc, curr) => acc + curr.total_parlamentares, 0),
    [parties]
  );

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      {/* CABEÇALHO DO PAINEL */}
      <div className="bg-gradient-to-r from-slate-900 via-indigo-950/40 to-slate-900 border border-indigo-500/20 rounded-3xl p-6 sm:p-8 backdrop-blur-xl relative overflow-hidden shadow-2xl">
        <div className="absolute top-0 right-0 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="relative z-10 space-y-3">
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
            <Compass className="w-3.5 h-3.5 text-indigo-400" />
            Guia do Espectro Partidário Nacional
          </div>
          <h2 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
            Catálogo de Partidos Políticos Brasileiros
          </h2>
          <p className="text-sm sm:text-base text-slate-300 max-w-3xl leading-relaxed">
            Consulte a ideologia doutrinária, os lemas oficiais, o espectro político
            e o tamanho atual das bancadas parlamentares (Câmara e Senado) de cada legenda registrada no TSE.
          </p>
        </div>
      </div>

      {/* BARRA DE CONTROLES: BUSCA & FILTRO POR ESPECTRO */}
      <div className="bg-slate-900/70 border border-slate-800/90 rounded-2xl p-4 sm:p-5 backdrop-blur-md flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4 shadow-lg">
        {/* Campo de Busca */}
        <div className="relative flex-1">
          <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Buscar por sigla, nome do partido, ideologia ou lema..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-10 pr-4 py-2.5 text-xs sm:text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition-colors shadow-inner"
          />
        </div>

        {/* Filtro por Espectro Político */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0 scrollbar-none">
          <span className="text-xs font-semibold text-slate-400 mr-1 flex items-center gap-1 flex-shrink-0">
            <Filter className="w-3.5 h-3.5" /> Espectro:
          </span>
          {[
            { id: "TODOS", label: "Todos" },
            { id: "ESQUERDA", label: "Esquerda" },
            { id: "CENTRO_ESQUERDA", label: "Centro-Esq." },
            { id: "CENTRO", label: "Centro" },
            { id: "CENTRO_DIREITA", label: "Centro-Dir." },
            { id: "DIREITA", label: "Direita" },
          ].map((item) => (
            <button
              key={item.id}
              onClick={() => setSpectrumFilter(item.id)}
              className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all whitespace-nowrap ${
                spectrumFilter === item.id
                  ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/30"
                  : "bg-slate-950 border border-slate-800 text-slate-400 hover:text-slate-200 hover:bg-slate-900"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {/* GRADE DE CARDS DOS PARTIDOS */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 animate-pulse">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="h-64 bg-slate-900/60 border border-slate-800 rounded-3xl p-5"
            />
          ))}
        </div>
      ) : filteredParties.length === 0 ? (
        <div className="bg-slate-900/40 border border-slate-800 rounded-3xl p-12 text-center text-slate-400 space-y-2">
          <Compass className="w-8 h-8 text-slate-600 mx-auto" />
          <p className="text-sm font-semibold text-slate-300">
            Nenhum partido encontrado para os termos da busca.
          </p>
          <p className="text-xs text-slate-500">
            Tente remover os filtros ou buscar por outra sigla.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {filteredParties.map((p) => {
            const spectrumStyle =
              SPECTRUM_BADGE_CONFIG[p.espectro_politico] || {
                label: p.espectro_politico,
                bg: "bg-slate-800",
                text: "text-slate-300",
                border: "border-slate-700",
              };

            const isTarget = Boolean(targetParty && p.sigla.toUpperCase() === targetParty.toUpperCase());

            return (
              <div
                key={p.id}
                onClick={() => onSelectParty?.(p.sigla)}
                className={`bg-slate-900/80 border hover:border-cyan-400/80 rounded-3xl p-5 sm:p-6 flex flex-col justify-between transition-all duration-300 hover:scale-[1.02] hover:bg-slate-900 group shadow-xl cursor-pointer hover:shadow-cyan-950/30 relative overflow-hidden ${
                  isTarget ? "ring-2 ring-cyan-400 border-cyan-400 shadow-cyan-950/50 scale-[1.02]" : "border-slate-800/90"
                }`}
              >
                {/* Faixa sutil no topo com a cor do partido */}
                <div
                  className="absolute top-0 left-0 right-0 h-1.5 opacity-80 group-hover:opacity-100 transition-opacity"
                  style={{ backgroundColor: p.cor_hex || "#3b82f6" }}
                />

                <div className="space-y-4 pt-1">
                  {/* Cabeçalho do Card: Sigla, Número Eleitoral e Espectro */}
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <PartyLogoBadge
                        sigla={p.sigla}
                        logoUrl={p.logo_url}
                        corHex={p.cor_hex}
                        size="md"
                      />

                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="text-lg font-black text-white group-hover:text-cyan-300 transition-colors">
                            {p.sigla}
                          </h3>
                          {p.numero_eleitoral && (
                            <span className="text-[11px] font-mono font-bold px-2 py-0.5 rounded-lg bg-slate-950 text-slate-300 border border-slate-800">
                              Nº {p.numero_eleitoral}
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-slate-400 line-clamp-1" title={p.nome_completo}>
                          {p.nome_completo}
                        </p>
                      </div>
                    </div>

                    <span
                      className={`text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-xl border ${spectrumStyle.bg} ${spectrumStyle.text} ${spectrumStyle.border}`}
                    >
                      {spectrumStyle.label}
                    </span>
                  </div>

                  {/* Ideologia Doutrinária */}
                  <div className="bg-slate-950/70 border border-slate-800/80 rounded-xl p-3 space-y-1">
                    <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider block">
                      Ideologia Política
                    </span>
                    <p className="text-xs font-semibold text-slate-200">
                      {p.ideologia}
                    </p>
                  </div>

                  {/* Lema Oficial */}
                  <div className="px-1">
                    <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider block mb-1">
                      Lema da Legenda
                    </span>
                    <p className="text-xs italic text-slate-300 leading-relaxed">
                      &ldquo;{p.lema}&rdquo;
                    </p>
                  </div>
                </div>

                {/* Rodapé do Card: Bancada Parlamentar e Ação de Ver Membros */}
                <div className="mt-5 pt-4 border-t border-slate-800/80 flex items-center justify-between text-xs">
                  <div className="flex items-center gap-3 text-[11px]">
                    <span className="text-slate-400" title="Deputados Federais">
                      Dep: <strong className="text-slate-200">{p.total_deputados}</strong>
                    </span>
                    <span className="text-slate-600">•</span>
                    <span className="text-slate-400" title="Senadores">
                      Sen: <strong className="text-slate-200">{p.total_senadores}</strong>
                    </span>
                    <span className="text-slate-600">•</span>
                    <span className="text-cyan-400 font-bold" title="Total no Congresso Nacional">
                      Total: {p.total_parlamentares}
                    </span>
                  </div>

                  <div className="inline-flex items-center gap-1 text-[11px] font-bold text-cyan-400 group-hover:text-cyan-300 transition-colors">
                    <span>Ver Bancada</span>
                    <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
