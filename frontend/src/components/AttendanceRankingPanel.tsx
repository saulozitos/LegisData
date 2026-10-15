"use client";

import React, { useState } from "react";
import { CalendarX2, Info, Users2, UserX } from "lucide-react";
import {
  getAttendancePartyRanking,
  getAttendanceRanking,
  type AttendanceCasa,
  type AttendanceOrdenacao,
} from "@/services/api";
import { useApi } from "@/hooks/useApi";
import { fmtNum } from "@/lib/format";
import { EmptyState, ErrorState, LoadingState } from "@/components/StateViews";

interface AttendanceRankingPanelProps {
  onSelectPolitician?: (politicianId: string) => void;
  onSelectParty?: (sigla: string) => void;
}

type Visao = "parlamentares" | "partidos";

const CASAS: Array<{ id: AttendanceCasa; label: string }> = [
  { id: "ALL", label: "Congresso (Câmara e Senado)" },
  { id: "CAMARA", label: "Câmara dos Deputados" },
  { id: "SENADO", label: "Senado Federal" },
];

const PERIODOS: Array<{ id: string; label: string; inicio?: number }> = [
  { id: "legislatura", label: "Legislatura atual (2023 em diante)", inicio: 2023 },
  { id: "oficial", label: "Desde 2020 (faltas oficiais da Câmara)", inicio: 2020 },
  { id: "tudo", label: "Todo o período com faltas (2003 em diante)" },
];

const ORDENACOES: Array<{ id: AttendanceOrdenacao; label: string; ajuda: string }> = [
  { id: "faltas", label: "Mais faltas", ajuda: "Total de dias de ausência registrados." },
  { id: "taxa", label: "Maior taxa de ausência", ajuda: "Faltas divididas pelos dias registrados (mínimo de 20 dias)." },
  { id: "nao_justificadas", label: "Faltas sem justificativa", ajuda: "Ausências oficiais sem justificativa (Senado: NCom; Câmara: desde 2020)." },
  {
    id: "baixa_producao",
    label: "Falta muito e produz pouco",
    ajuda: "Taxa de ausência ÷ (100 + pontos IALP). Cresce com as faltas e diminui com a produção legislativa.",
  },
];

export default function AttendanceRankingPanel({ onSelectPolitician, onSelectParty }: AttendanceRankingPanelProps) {
  const [visao, setVisao] = useState<Visao>("parlamentares");
  const [casa, setCasa] = useState<AttendanceCasa>("ALL");
  const [periodoId, setPeriodoId] = useState("legislatura");
  const [ordenar, setOrdenar] = useState<AttendanceOrdenacao>("faltas");
  const inicio = PERIODOS.find((p) => p.id === periodoId)?.inicio;

  const politicos = useApi(
    `attendance-politicians-${casa}-${periodoId}-${ordenar}`,
    (signal) => getAttendanceRanking(casa, ordenar, inicio, undefined, 30, signal),
    visao === "parlamentares"
  );
  const partidos = useApi(
    `attendance-parties-${casa}-${periodoId}`,
    (signal) => getAttendancePartyRanking(casa, inicio, undefined, signal),
    visao === "partidos"
  );
  const consulta = visao === "parlamentares" ? politicos : partidos;
  const ajuda = ORDENACOES.find((o) => o.id === ordenar)?.ajuda;

  return (
    <div className="space-y-6">
      <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-4">
        <div className="flex items-center gap-2">
          <CalendarX2 className="w-5 h-5 text-rose-400" />
          <h2 className="text-lg font-bold text-slate-100">Presença & Faltas no Congresso</h2>
        </div>
        <p className="text-xs text-slate-400">
          Quem mais falta às sessões de plenário e qual partido tem a maior taxa de ausência. A produção legislativa
          (pontos IALP) aparece ao lado para comparar presença e entrega.
        </p>

        <div className="flex flex-wrap gap-2" role="tablist" aria-label="Visão do ranking">
          {(
            [
              ["parlamentares", "Parlamentares", UserX],
              ["partidos", "Partidos", Users2],
            ] as const
          ).map(([id, label, Icon]) => (
            <button
              key={id}
              role="tab"
              aria-selected={visao === id}
              onClick={() => setVisao(id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                visao === id ? "bg-rose-500 text-slate-950" : "bg-slate-800 text-slate-300 hover:bg-slate-700"
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              {label}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
          <label className="space-y-1">
            <span className="text-slate-400">Casa</span>
            <select
              value={casa}
              onChange={(e) => setCasa(e.target.value as AttendanceCasa)}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-2 text-slate-200"
            >
              {CASAS.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1">
            <span className="text-slate-400">Período</span>
            <select
              value={periodoId}
              onChange={(e) => setPeriodoId(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-2 text-slate-200"
            >
              {PERIODOS.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
          {visao === "parlamentares" && (
            <label className="space-y-1">
              <span className="text-slate-400">Ordenar por</span>
              <select
                value={ordenar}
                onChange={(e) => setOrdenar(e.target.value as AttendanceOrdenacao)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-2 text-slate-200"
              >
                {ORDENACOES.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
        {visao === "parlamentares" && ajuda && <p className="text-[11px] text-slate-400">{ajuda}</p>}
      </div>

      {consulta.error ? (
        <ErrorState onRetry={consulta.retry} />
      ) : consulta.loading ? (
        <LoadingState label="Carregando ranking de presença..." />
      ) : visao === "parlamentares" ? (
        !politicos.data || politicos.data.itens.length === 0 ? (
          <EmptyState message="Sem registros de presença para este filtro." />
        ) : (
          <div className="bg-slate-900/60 border border-slate-800 rounded-2xl overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-slate-400 border-b border-slate-800">
                  <th className="p-3">#</th>
                  <th className="p-3">Parlamentar</th>
                  <th className="p-3 text-right">Dias</th>
                  <th className="p-3 text-right">Faltas</th>
                  <th className="p-3 text-right">Justificadas</th>
                  <th className="p-3 text-right">Sem justificativa</th>
                  <th className="p-3 text-right">Inferidas</th>
                  <th className="p-3 text-right">Taxa de ausência</th>
                  <th className="p-3 text-right">Pontos IALP</th>
                </tr>
              </thead>
              <tbody>
                {politicos.data.itens.map((p, i) => (
                  <tr key={p.politico_id} className="border-b border-slate-800/60 hover:bg-slate-800/30">
                    <td className="p-3 font-mono text-slate-400">{i + 1}</td>
                    <td className="p-3">
                      <button
                        type="button"
                        onClick={() => onSelectPolitician?.(p.politico_id)}
                        className="text-left font-bold text-slate-100 hover:text-cyan-300"
                      >
                        {p.nome_eleitoral}
                      </button>
                      <div className="text-[10px] text-slate-400">{p.partido_sigla}</div>
                    </td>
                    <td className="p-3 text-right font-mono">{fmtNum(p.dias_registrados)}</td>
                    <td className="p-3 text-right font-mono font-bold text-rose-300">{fmtNum(p.faltas)}</td>
                    <td className="p-3 text-right font-mono text-amber-300">{fmtNum(p.faltas_justificadas)}</td>
                    <td className="p-3 text-right font-mono text-rose-400">{fmtNum(p.faltas_nao_justificadas)}</td>
                    <td className="p-3 text-right font-mono text-sky-300">{fmtNum(p.faltas_inferidas)}</td>
                    <td className="p-3 text-right font-mono">{p.taxa_ausencia_pct == null ? "n/d" : `${fmtNum(p.taxa_ausencia_pct)}%`}</td>
                    <td className="p-3 text-right font-mono text-emerald-300">{fmtNum(p.pontos_ialp)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      ) : !partidos.data || partidos.data.itens.length === 0 ? (
        <EmptyState message="Sem registros de presença para este filtro." />
      ) : (
        <div className="bg-slate-900/60 border border-slate-800 rounded-2xl overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-slate-400 border-b border-slate-800">
                <th className="p-3">#</th>
                <th className="p-3">Partido</th>
                <th className="p-3 text-right">Parlamentares</th>
                <th className="p-3 text-right">Dias</th>
                <th className="p-3 text-right">Faltas</th>
                <th className="p-3 text-right">Taxa de ausência</th>
              </tr>
            </thead>
            <tbody>
              {partidos.data.itens.map((p, i) => (
                <tr key={p.sigla} className="border-b border-slate-800/60 hover:bg-slate-800/30">
                  <td className="p-3 font-mono text-slate-400">{i + 1}</td>
                  <td className="p-3">
                    <button
                      type="button"
                      onClick={() => onSelectParty?.(p.sigla)}
                      className="font-bold text-slate-100 hover:text-violet-300"
                    >
                      {p.sigla}
                    </button>
                  </td>
                  <td className="p-3 text-right font-mono">{fmtNum(p.parlamentares)}</td>
                  <td className="p-3 text-right font-mono">{fmtNum(p.dias_registrados)}</td>
                  <td className="p-3 text-right font-mono text-rose-300">{fmtNum(p.faltas)}</td>
                  <td className="p-3 text-right font-mono font-bold">
                    {p.taxa_ausencia_pct == null ? "n/d" : `${fmtNum(p.taxa_ausencia_pct)}%`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {(visao === "parlamentares" ? politicos.data?.aviso : partidos.data?.aviso) && (
        <div className="flex gap-2 p-3 rounded-xl bg-sky-500/5 border border-sky-500/20 text-[11px] text-sky-200">
          <Info className="w-4 h-4 flex-shrink-0" />
          <span>{visao === "parlamentares" ? politicos.data?.aviso : partidos.data?.aviso}</span>
        </div>
      )}
    </div>
  );
}
