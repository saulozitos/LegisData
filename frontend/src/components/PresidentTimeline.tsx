"use client";

import React, { useRef, useEffect, useMemo } from "react";
import { PresidenteHistorico } from "@/services/api";
import { Calendar, Sparkles } from "lucide-react";

interface PresidentTimelineProps {
  presidents: PresidenteHistorico[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

export function getPresidentPhotoUrl(idReferencia?: string, fotoUrl?: string): string {
  if (fotoUrl && fotoUrl.startsWith("/presidents/")) return fotoUrl;
  if (idReferencia) {
    if (idReferencia.includes("itamar")) return "/presidents/itamar-franco.jpg";
    if (idReferencia.includes("fhc")) return "/presidents/fhc.jpg";
    if (idReferencia.includes("lula")) return "/presidents/lula.jpg";
    if (idReferencia.includes("dilma")) return "/presidents/dilma.jpg";
    if (idReferencia.includes("temer")) return "/presidents/temer.jpg";
    if (idReferencia.includes("bolsonaro")) return "/presidents/bolsonaro.jpg";
  }
  return fotoUrl || "/presidents/lula.jpg";
}

export default function PresidentTimeline({
  presidents,
  selectedId,
  onSelect,
}: PresidentTimelineProps) {
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const selectedButtonRef = useRef<HTMLButtonElement>(null);

  // Identifica dinamicamente o presidente atual em exercício
  const currentPresident = useMemo(() => {
    if (!presidents || presidents.length === 0) return null;
    return (
      presidents.find(
        (p) =>
          p.status_mandato === "TITULAR_ATIVO" ||
          p.status_mandato === "EM_EXERCICIO" ||
          p.status_mandato === "ATIVO" ||
          !p.data_fim
      ) || presidents[presidents.length - 1]
    );
  }, [presidents]);

  // Cores por partido
  const getPartyColor = (party: string) => {
    switch (party.toUpperCase()) {
      case "PT":
        return "bg-red-500/10 text-red-400 border-red-500/20";
      case "PSDB":
        return "bg-blue-500/10 text-blue-400 border-blue-500/20";
      case "PMDB":
      case "MDB":
        return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
      case "PL":
      case "PSL":
        return "bg-amber-500/10 text-amber-400 border-amber-500/20";
      default:
        return "bg-slate-500/10 text-slate-400 border-slate-500/20";
    }
  };

  const selectedPresident = presidents.find((p) => p.id_referencia === selectedId);

  // Centraliza o presidente selecionado automaticamente no carrossel horizontal
  useEffect(() => {
    const scrollToSelected = () => {
      if (selectedButtonRef.current && scrollContainerRef.current) {
        const container = scrollContainerRef.current;
        const button = selectedButtonRef.current;
        const buttonLeft = button.offsetLeft;
        const buttonWidth = button.offsetWidth;
        const containerWidth = container.offsetWidth;

        if (containerWidth > 0) {
          const targetScrollLeft = buttonLeft - containerWidth / 2 + buttonWidth / 2;
          container.scrollTo({
            left: Math.max(0, targetScrollLeft),
            behavior: "smooth",
          });
        }
      }
    };

    scrollToSelected();
    const timer = setTimeout(scrollToSelected, 150);
    return () => clearTimeout(timer);
  }, [selectedId, presidents]);

  return (
    <div className="w-full">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 mb-3">
        <div className="flex items-center gap-2 flex-wrap">
          <Calendar className="w-4 h-4 text-emerald-400" />
          <h2 className="text-sm font-semibold tracking-wider uppercase text-slate-300">
            Linha do Tempo Presidencial (1992 - 2026)
          </h2>
          {selectedPresident ? (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              {selectedPresident.id_referencia === currentPresident?.id_referencia ? (
                <>Presidente Atual (Padrão): {selectedPresident.nome_eleitoral}</>
              ) : (
                <>Filtrando: {selectedPresident.nome_eleitoral}</>
              )}
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-medium bg-slate-800 text-slate-300 border border-slate-700">
              Visão Histórica Completa (Todos os Mandatos)
            </span>
          )}
        </div>

        <div className="flex items-center gap-2.5 flex-wrap">
          {/* Botão para restaurar o Presidente Atual sempre que outro mandato ou Todos estiver ativo */}
          {selectedId !== currentPresident?.id_referencia && currentPresident && (
            <button
              onClick={() => onSelect(currentPresident.id_referencia)}
              className="inline-flex items-center gap-1.5 px-3 py-1 rounded-xl text-xs font-bold bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-300 border border-emerald-500/40 hover:border-emerald-500/60 transition-all cursor-pointer shadow-sm shadow-emerald-500/10 active:scale-95"
              title="Restaurar o presidente atual em exercício como filtro padrão"
            >
              <Sparkles className="w-3.5 h-3.5 text-emerald-400" />
              Presidente Atual ({currentPresident.nome_eleitoral.split(" ")[0]})
            </button>
          )}

          {selectedId !== null && (
            <button
              onClick={() => onSelect(null)}
              className="text-[11px] font-medium text-slate-400 hover:text-slate-200 underline underline-offset-2 transition-all cursor-pointer"
              title="Exibir dados consolidados de todos os mandatos desde 1992"
            >
              Ver todos
            </button>
          )}

          <span className="text-xs text-slate-500 hidden xl:inline">
            Clique no presidente para filtrar abas
          </span>
        </div>
      </div>

      {/* Carrossel de botões horizontais com scroll suave e barra de rolagem estilizada */}
      <div
        ref={scrollContainerRef}
        className="flex gap-2.5 overflow-x-auto pb-3 pt-1 scrollbar-thin scrollbar-thumb-slate-800 scrollbar-track-transparent scroll-smooth"
      >
        {/* Botão de Visão Geral / Todos os Mandatos */}
        <button
          ref={selectedId === null ? selectedButtonRef : null}
          onClick={() => onSelect(null)}
          className={`flex-shrink-0 flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl text-left border transition-all duration-200 cursor-pointer ${
            selectedId === null
              ? "bg-slate-900 border-emerald-500 shadow-md shadow-emerald-500/10 ring-1 ring-emerald-500/30 scale-[1.02]"
              : "bg-slate-950/60 border-slate-800/80 hover:bg-slate-900/60 hover:border-slate-700 text-slate-400"
          }`}
        >
          <div className="w-10 h-10 rounded-full bg-slate-800 border border-slate-700/80 flex items-center justify-center text-emerald-400 font-extrabold text-xs">
            TODOS
          </div>
          <div className="flex flex-col">
            <span
              className={`text-xs font-bold leading-tight ${
                selectedId === null ? "text-slate-100" : "text-slate-300"
              }`}
            >
              Visão Geral
            </span>
            <span className="text-[11px] text-slate-500 font-medium">1992 - 2026</span>
          </div>
        </button>

        {presidents.map((p) => {
          const isSelected = p.id_referencia === selectedId;
          const isCurrent = currentPresident?.id_referencia === p.id_referencia;
          const anos = `${p.data_inicio.slice(0, 4)} - ${
            p.data_fim ? p.data_fim.slice(0, 4) : "Atual"
          }`;

          return (
            <button
              key={p.id_referencia}
              ref={isSelected ? selectedButtonRef : null}
              onClick={() => {
                if (isSelected) {
                  // Se desmarcar um presidente histórico, restaura o atual por padrão;
                  // Se desmarcar o atual, vai para a visão geral consolidada
                  if (isCurrent) {
                    onSelect(null);
                  } else if (currentPresident) {
                    onSelect(currentPresident.id_referencia);
                  } else {
                    onSelect(null);
                  }
                } else {
                  onSelect(p.id_referencia);
                }
              }}
              className={`flex-shrink-0 flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-left border transition-all duration-200 cursor-pointer ${
                isSelected
                  ? "bg-slate-900 border-emerald-500 shadow-md shadow-emerald-500/10 ring-1 ring-emerald-500/30 scale-[1.02]"
                  : isCurrent
                  ? "bg-slate-950/80 border-emerald-500/40 hover:bg-slate-900/70 hover:border-emerald-500/70 text-slate-300"
                  : "bg-slate-950/60 border-slate-800/80 hover:bg-slate-900/60 hover:border-slate-700 text-slate-400"
              }`}
            >
              {/* Avatar do Presidente */}
              <div
                className={`relative w-10 h-10 rounded-full overflow-hidden bg-slate-800 flex-shrink-0 border flex items-center justify-center ${
                  isCurrent
                    ? "border-emerald-500/60 ring-2 ring-emerald-500/30"
                    : "border-slate-700/80"
                }`}
              >
                <img
                  src={getPresidentPhotoUrl(p.id_referencia, p.foto_url)}
                  alt={p.nome_eleitoral}
                  referrerPolicy="no-referrer"
                  className="w-full h-full object-cover object-top"
                  onError={(e) => {
                    const target = e.target as HTMLImageElement;
                    if (!target.src.includes("/presidents/")) {
                      target.src = getPresidentPhotoUrl(p.id_referencia);
                    } else {
                      target.style.display = "none";
                    }
                  }}
                />
                <div className="absolute inset-0 bg-slate-800 -z-10 flex items-center justify-center text-xs font-bold text-slate-300">
                  {p.partido_sigla.slice(0, 2)}
                </div>
              </div>

              {/* Informações */}
              <div className="flex flex-col">
                <div className="flex items-center gap-1.5">
                  <span
                    className={`text-xs font-bold leading-tight ${
                      isSelected ? "text-slate-100" : "text-slate-300"
                    }`}
                  >
                    {p.nome_eleitoral}
                  </span>
                  <span
                    className={`text-[9px] font-bold px-1.5 py-0.2 rounded border ${getPartyColor(
                      p.partido_sigla
                    )}`}
                  >
                    {p.partido_sigla}
                  </span>
                  {isCurrent && (
                    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[9px] font-extrabold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                      Atual
                    </span>
                  )}
                </div>
                <span className="text-[11px] text-slate-500 font-medium">
                  {isCurrent ? `${p.data_inicio.slice(0, 4)} - Em Exercício` : anos}
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
