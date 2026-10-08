"use client";

import React, { useEffect, useState } from "react";
import Header from "@/components/Header";
import {
  PresidentialMandate,
  MandateIndicatorData,
  getPresidentialMandates,
  getMandateIndicators,
} from "@/services/api";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { Award, Briefcase, TrendingUp, Users } from "lucide-react";
import { getPresidentPhotoUrl } from "@/components/PresidentTimeline";

export default function ExecutivoDashboard() {
  const [mandates, setMandates] = useState<PresidentialMandate[]>([]);
  const [selectedMandateId, setSelectedMandateId] = useState<string>("");
  const [indicators, setIndicators] = useState<MandateIndicatorData[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const m = await getPresidentialMandates();
        setMandates(m);
        if (m.length > 0) {
          setSelectedMandateId(m[0].id);
        }
      } catch (err) {
        console.error("Erro ao carregar mandatos", err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  useEffect(() => {
    async function loadIndicators() {
      if (!selectedMandateId) return;
      try {
        const data = await getMandateIndicators(selectedMandateId);
        setIndicators(data);
      } catch (err) {
        console.error("Erro ao carregar indicadores", err);
      }
    }
    loadIndicators();
  }, [selectedMandateId]);

  if (loading) {
    return (
      <main className="min-h-screen bg-slate-950 text-slate-50 flex items-center justify-center font-sans">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-cyan-500"></div>
      </main>
    );
  }

  const selectedMandate = mandates.find((m) => m.id === selectedMandateId);

  return (
    <main className="min-h-screen bg-slate-950 text-slate-50 font-sans selection:bg-cyan-500/30">
      <Header />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        <header className="space-y-4">
          <div className="flex items-center gap-3">
            <span className="p-2 rounded-xl bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 shadow-lg shadow-cyan-500/10">
              <Briefcase className="w-6 h-6" />
            </span>
            <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-slate-100 to-slate-400">
              Raio-X do Executivo
            </h1>
          </div>
          <p className="text-lg text-slate-400 max-w-3xl">
            Acompanhe indicadores-chave de desempenho (KPIs) Econômicos, Sociais e de Governabilidade para cada mandato presidencial.
          </p>
        </header>

        {/* Seletor de Mandatos */}
        <section className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-6 backdrop-blur-md">
          <label className="block text-sm font-medium text-slate-400 mb-2">Selecione um Mandato Presidencial</label>
          <div className="flex flex-wrap gap-4">
            {mandates.map((m) => (
              <button
                key={m.id}
                onClick={() => setSelectedMandateId(m.id)}
                className={`flex items-center gap-3 px-4 py-2 rounded-xl border transition-all ${
                  selectedMandateId === m.id
                    ? "bg-cyan-500/20 border-cyan-500/40 text-cyan-300 shadow-sm shadow-cyan-500/10"
                    : "bg-slate-950 border-slate-800 text-slate-300 hover:border-slate-700"
                }`}
              >
                {m.foto_url && (
                  <img src={getPresidentPhotoUrl(m.nome.toLowerCase(), m.foto_url)} alt={m.nome} className="w-8 h-8 rounded-full object-cover" />
                )}
                <div className="text-left">
                  <p className="font-bold text-sm">{m.nome}</p>
                  <p className="text-xs text-slate-500">{m.partido}</p>
                </div>
              </button>
            ))}
          </div>
        </section>

        {selectedMandate && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            {/* Gráfico 1: Aprovação Popular vs. Inflação (IPCA) */}
            <section className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-6 backdrop-blur-md flex flex-col space-y-6">
              <div className="flex items-center gap-2 border-b border-slate-800 pb-4">
                <Users className="w-5 h-5 text-emerald-400" />
                <h2 className="text-xl font-bold text-slate-100">Aprovação Popular vs Inflação</h2>
              </div>
              <div className="h-80 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={indicators} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                    <XAxis dataKey="data" stroke="#64748b" tick={{ fill: "#94a3b8", fontSize: 12 }} />
                    <YAxis yAxisId="left" stroke="#64748b" tick={{ fill: "#94a3b8", fontSize: 12 }} />
                    <YAxis yAxisId="right" orientation="right" stroke="#64748b" tick={{ fill: "#94a3b8", fontSize: 12 }} />
                    <Tooltip
                      contentStyle={{ backgroundColor: "#020617", borderColor: "#1e293b", borderRadius: "0.5rem" }}
                      itemStyle={{ color: "#f8fafc" }}
                      labelStyle={{ color: "#94a3b8", marginBottom: "0.5rem" }}
                    />
                    <Legend />
                    <Line
                      yAxisId="left"
                      type="monotone"
                      dataKey="aprovacao_popular"
                      name="Aprovação (%)"
                      stroke="#10b981"
                      strokeWidth={3}
                      dot={false}
                    />
                    <Line
                      yAxisId="right"
                      type="monotone"
                      dataKey="inflacao_ipca"
                      name="Inflação IPCA (%)"
                      stroke="#f43f5e"
                      strokeWidth={3}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </section>

            {/* Gráfico 2: Taxa de Sucesso no Congresso vs. Volume de Emendas Liberadas */}
            <section className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-6 backdrop-blur-md flex flex-col space-y-6">
              <div className="flex items-center gap-2 border-b border-slate-800 pb-4">
                <TrendingUp className="w-5 h-5 text-amber-400" />
                <h2 className="text-xl font-bold text-slate-100">Sucesso no Congresso vs Emendas</h2>
              </div>
              <div className="h-80 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={indicators} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                    <XAxis dataKey="data" stroke="#64748b" tick={{ fill: "#94a3b8", fontSize: 12 }} />
                    <YAxis yAxisId="left" stroke="#64748b" tick={{ fill: "#94a3b8", fontSize: 12 }} />
                    <YAxis yAxisId="right" orientation="right" stroke="#64748b" tick={{ fill: "#94a3b8", fontSize: 12 }} />
                    <Tooltip
                      contentStyle={{ backgroundColor: "#020617", borderColor: "#1e293b", borderRadius: "0.5rem" }}
                      itemStyle={{ color: "#f8fafc" }}
                      labelStyle={{ color: "#94a3b8", marginBottom: "0.5rem" }}
                    />
                    <Legend />
                    <Line
                      yAxisId="left"
                      type="stepAfter"
                      dataKey="taxa_sucesso_congresso"
                      name="Sucesso Congresso (%)"
                      stroke="#fbbf24"
                      strokeWidth={3}
                      dot={false}
                    />
                    <Line
                      yAxisId="right"
                      type="monotone"
                      dataKey="volume_emendas"
                      name="Volume Emendas (R$ Mi)"
                      stroke="#38bdf8"
                      strokeWidth={3}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </section>
          </div>
        )}
      </div>
    </main>
  );
}
