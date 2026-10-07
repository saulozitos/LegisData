"use client";

import React, { useState, useEffect, useMemo } from "react";
import {
  CalendarioVotacoesResponse,
  DiaVotacaoItem,
  SessaoCalendarioItem,
  getVotingCalendar,
} from "@/services/api";
import {
  CalendarDays,
  Calendar,
  CheckCircle2,
  XCircle,
  ExternalLink,
  Users,
  Landmark,
  FileText,
  Clock,
  Sparkles,
  Filter,
  Layers,
  ChevronRight,
  TrendingUp,
  Award,
  Vote,
} from "lucide-react";

interface VotingCalendarPanelProps {
  onSelectPolitician?: (id: string) => void;
}

const MESES_NOMES = [
  "Janeiro",
  "Fevereiro",
  "Março",
  "Abril",
  "Maio",
  "Junho",
  "Julho",
  "Agosto",
  "Setembro",
  "Outubro",
  "Novembro",
  "Dezembro",
];

export default function VotingCalendarPanel({
  onSelectPolitician,
}: VotingCalendarPanelProps = {}) {
  const [selectedYear, setSelectedYear] = useState<number | undefined>(undefined);
  const [data, setData] = useState<CalendarioVotacoesResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [selectedDateStr, setSelectedDateStr] = useState<string | null>(null);
  const [monthFilter, setMonthFilter] = useState<number | "TODOS">("TODOS");

  useEffect(() => {
    let isCancelled = false;
    async function loadCalendar() {
      setIsLoading(true);
      try {
        const res = await getVotingCalendar(selectedYear);
        if (!isCancelled && res) {
          setData(res);
          if (!selectedDateStr && res.dias.length > 0) {
            setSelectedDateStr(res.dias[0].data);
          } else if (res.dias.length > 0 && !res.dias.some((d) => d.data === selectedDateStr)) {
            setSelectedDateStr(res.dias[0].data);
          }
        }
      } catch (err) {
        console.error("Erro ao carregar calendário legislativo:", err);
      } finally {
        if (!isCancelled) {
          setIsLoading(false);
        }
      }
    }
    loadCalendar();
    return () => {
      isCancelled = true;
    };
  }, [selectedYear]);

  // Filtrar dias exibidos pelo mês selecionado
  const filteredDays = useMemo(() => {
    if (!data) return [];
    if (monthFilter === "TODOS") return data.dias;
    return data.dias.filter((d) => d.mes === monthFilter);
  }, [data, monthFilter]);

  // Dia atualmente selecionado
  const activeDay = useMemo(() => {
    if (!data || !data.dias) return null;
    return data.dias.find((d) => d.data === selectedDateStr) || data.dias[0] || null;
  }, [data, selectedDateStr]);

  return (
    <div className="space-y-6">
      {/* ======================================================== */}
      {/* 1. CABEÇALHO & SELETOR DE ANO */}
      {/* ======================================================== */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-6 backdrop-blur-md shadow-2xl space-y-6">
        <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4 pb-6 border-b border-slate-800">
          <div className="flex items-center gap-3.5">
            <div className="p-3 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 flex-shrink-0">
              <CalendarDays className="w-6 h-6" />
            </div>
            <div>
              <h2 className="text-xl sm:text-2xl font-black text-white flex items-center gap-2">
                Diário do Congresso Nacional
                <span className="text-xs font-mono px-2.5 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                  Calendário de Votações
                </span>
              </h2>
              <p className="text-xs sm:text-sm text-slate-400 mt-1">
                Acompanhe as datas em que o Congresso realizou deliberações em plenário e consulte todas as matérias votadas.
              </p>
            </div>
          </div>

          {/* Seletor de Ano */}
          {data && data.anos_disponiveis.length > 0 && (
            <div className="flex items-center gap-2 bg-slate-950 p-1.5 rounded-2xl border border-slate-800">
              <span className="text-xs font-semibold text-slate-400 px-2 flex items-center gap-1.5">
                <Calendar className="w-3.5 h-3.5 text-cyan-400" />
                Ano:
              </span>
              {data.anos_disponiveis.map((ano) => (
                <button
                  key={ano}
                  onClick={() => setSelectedYear(ano)}
                  className={`px-3.5 py-1.5 rounded-xl text-xs font-bold font-mono transition-all ${
                    (selectedYear === ano || (!selectedYear && data.ano_selecionado === ano))
                      ? "bg-emerald-500 text-slate-950 shadow-md shadow-emerald-500/20"
                      : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
                  }`}
                >
                  {ano}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* ======================================================== */}
        {/* 2. ESTATÍSTICA GLOBAL ANUAL (REQUISITO OFICIAL) */}
        {/* ======================================================== */}
        {data && (
          <div className="space-y-4">
            {/* Banner Educativo de Destaque */}
            <div className="bg-gradient-to-r from-emerald-950/40 via-cyan-950/30 to-slate-950/60 border border-emerald-500/30 rounded-2xl p-5 shadow-inner">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                <div className="space-y-1">
                  <div className="flex items-center gap-2 text-xs font-bold text-emerald-400 uppercase tracking-wider">
                    <Sparkles className="w-4 h-4" />
                    Transparência de Atividade Deliberativa
                  </div>
                  <h3 className="text-base sm:text-lg font-black text-slate-100">
                    &ldquo;{data.estatisticas_anuais.texto_estatistica}&rdquo;
                  </h3>
                  <p className="text-xs text-slate-400">
                    Contabilização rigorosa de dias com sessões de votação nominal com quórum verificado no plenário da Câmara e do Senado.
                  </p>
                </div>

                <div className="flex-shrink-0 text-right sm:border-l sm:border-slate-800 sm:pl-6">
                  <div className="text-2xl sm:text-3xl font-black font-mono text-emerald-400">
                    {data.estatisticas_anuais.percentual_dias_ativos}%
                  </div>
                  <div className="text-[11px] font-semibold text-slate-400">
                    Frequência anual em plenário
                  </div>
                </div>
              </div>

              {/* Barra de Progresso Visual de Dias Ativos */}
              <div className="mt-4 space-y-1.5">
                <div className="flex justify-between text-[11px] text-slate-400 font-mono">
                  <span>{data.estatisticas_anuais.dias_com_votacao} dias com votação</span>
                  <span>{data.estatisticas_anuais.total_dias_ano - data.estatisticas_anuais.dias_com_votacao} dias sem votações nominais</span>
                </div>
                <div className="w-full bg-slate-950/80 h-3 rounded-full overflow-hidden border border-slate-800">
                  <div
                    className="h-full bg-gradient-to-r from-emerald-500 to-cyan-400 rounded-full transition-all duration-700"
                    style={{ width: `${Math.max(2, data.estatisticas_anuais.percentual_dias_ativos)}%` }}
                  />
                </div>
              </div>
            </div>

            {/* Três Cards de Resumo */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5">
              <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 space-y-1">
                <div className="text-xs text-slate-400 font-semibold flex items-center gap-1.5">
                  <Calendar className="w-4 h-4 text-emerald-400" />
                  Dias com Sessão Nominal
                </div>
                <div className="text-2xl font-black font-mono text-slate-100">
                  {data.estatisticas_anuais.dias_com_votacao}{" "}
                  <span className="text-xs font-normal text-slate-500 font-sans">
                    de {data.estatisticas_anuais.total_dias_ano} dias
                  </span>
                </div>
                <div className="text-[11px] text-slate-500">
                  Sessões deliberativas registradas no ano
                </div>
              </div>

              <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 space-y-1">
                <div className="text-xs text-slate-400 font-semibold flex items-center gap-1.5">
                  <Layers className="w-4 h-4 text-cyan-400" />
                  Total de Deliberações Nominais
                </div>
                <div className="text-2xl font-black font-mono text-cyan-300">
                  {data.estatisticas_anuais.total_sessoes_ano}{" "}
                  <span className="text-xs font-normal text-slate-500 font-sans">votações</span>
                </div>
                <div className="text-[11px] text-slate-500">
                  Placar nominal registrado na Câmara e no Senado
                </div>
              </div>

              <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 space-y-1">
                <div className="text-xs text-slate-400 font-semibold flex items-center gap-1.5">
                  <Vote className="w-4 h-4 text-amber-400" />
                  Média de Matérias por Dia de Sessão
                </div>
                <div className="text-2xl font-black font-mono text-amber-300">
                  {data.estatisticas_anuais.dias_com_votacao > 0
                    ? (data.estatisticas_anuais.total_sessoes_ano / data.estatisticas_anuais.dias_com_votacao).toFixed(1)
                    : "0.0"}
                </div>
                <div className="text-[11px] text-slate-500">
                  Densidade de deliberação nas datas convocadas
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ======================================================== */}
        {/* 3. FILTRO POR MÊS */}
        {/* ======================================================== */}
        <div className="space-y-2 pt-2 border-t border-slate-800">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span className="font-semibold flex items-center gap-1.5">
              <Filter className="w-3.5 h-3.5 text-cyan-400" />
              Filtrar por Mês:
            </span>
            <span>
              Mostrando <strong className="text-cyan-400 font-mono">{filteredDays.length}</strong> dia(s) com votação
            </span>
          </div>

          <div className="flex items-center gap-1.5 overflow-x-auto pb-2 scrollbar-thin">
            <button
              onClick={() => setMonthFilter("TODOS")}
              className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all whitespace-nowrap ${
                monthFilter === "TODOS"
                  ? "bg-slate-800 text-white border border-slate-700 shadow-sm"
                  : "bg-slate-950 text-slate-400 border border-slate-800 hover:text-slate-200"
              }`}
            >
              Todos os Meses
            </button>
            {MESES_NOMES.map((nome, idx) => {
              const mesNum = idx + 1;
              const hasVotes = data?.dias.some((d) => d.mes === mesNum);
              return (
                <button
                  key={mesNum}
                  onClick={() => setMonthFilter(mesNum)}
                  className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-all whitespace-nowrap flex items-center gap-1.5 ${
                    monthFilter === mesNum
                      ? "bg-emerald-500 text-slate-950 font-bold shadow-md shadow-emerald-500/20"
                      : hasVotes
                      ? "bg-slate-950 text-slate-300 border border-emerald-500/30 hover:border-emerald-500/60"
                      : "bg-slate-950/50 text-slate-600 border border-slate-900 cursor-not-allowed"
                  }`}
                  disabled={!hasVotes}
                >
                  <span>{nome.slice(0, 3)}</span>
                  {hasVotes && <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* ======================================================== */}
      {/* 4. GRADE DE DIAS & LISTA DE MATÉRIAS VOTADAS */}
      {/* ======================================================== */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* COLUNA ESQUERDA: LISTA INTERATIVA DE DATAS COM SESSÃO */}
        <div className="lg:col-span-5 bg-slate-900/80 border border-slate-800 rounded-3xl p-5 backdrop-blur-md shadow-xl space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-800">
            <div className="flex items-center gap-2">
              <Calendar className="w-4 h-4 text-emerald-400" />
              <h3 className="text-sm font-bold text-slate-100">
                Datas com Votação Registrada
              </h3>
            </div>
            <span className="text-xs text-slate-400 font-mono">
              {filteredDays.length} dias
            </span>
          </div>

          {isLoading ? (
            <div className="space-y-2.5 animate-pulse">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="h-16 bg-slate-950/80 rounded-2xl border border-slate-800" />
              ))}
            </div>
          ) : filteredDays.length === 0 ? (
            <div className="py-12 text-center text-slate-500 text-xs">
              Nenhuma sessão de votação nominal registrada para o filtro selecionado.
            </div>
          ) : (
            <div className="space-y-2.5 max-h-[600px] overflow-y-auto pr-1 scrollbar-thin">
              {filteredDays.map((dia) => {
                const isSelected = dia.data === selectedDateStr;
                return (
                  <div
                    key={dia.data}
                    onClick={() => setSelectedDateStr(dia.data)}
                    className={`p-4 rounded-2xl border transition-all cursor-pointer flex items-center justify-between gap-3 ${
                      isSelected
                        ? "bg-slate-800/90 border-emerald-500/80 shadow-lg shadow-emerald-500/10 ring-1 ring-emerald-500/40"
                        : "bg-slate-950/70 border-slate-800 hover:border-slate-700 hover:bg-slate-900/60"
                    }`}
                  >
                    <div className="flex items-center gap-3.5">
                      {/* Ponto indicador de votação ativa */}
                      <div className="relative flex items-center justify-center">
                        <span className="w-3 h-3 rounded-full bg-emerald-400" />
                        <span className="w-3 h-3 rounded-full bg-emerald-400 animate-ping absolute opacity-75" />
                      </div>

                      <div className="space-y-0.5">
                        <div className="text-xs font-bold text-slate-100 flex items-center gap-2">
                          <span>{dia.data_formatada}</span>
                        </div>
                        <div className="text-[11px] text-slate-400 flex items-center gap-2">
                          <span>{dia.dia_semana}</span>
                          {dia.camara_count > 0 && (
                            <span className="text-[10px] font-mono text-emerald-400 bg-emerald-500/10 px-1.5 py-0.2 rounded">
                              {dia.camara_count} Câmara
                            </span>
                          )}
                          {dia.senado_count > 0 && (
                            <span className="text-[10px] font-mono text-cyan-400 bg-cyan-500/10 px-1.5 py-0.2 rounded">
                              {dia.senado_count} Senado
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 flex-shrink-0">
                      <span className="text-xs font-mono font-bold text-slate-300 bg-slate-900 border border-slate-800 px-2.5 py-1 rounded-xl">
                        {dia.total_votacoes} matéria{dia.total_votacoes > 1 ? "s" : ""}
                      </span>
                      <ChevronRight className={`w-4 h-4 transition-transform ${isSelected ? "text-emerald-400 translate-x-1" : "text-slate-600"}`} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* COLUNA DIREITA: MATÉRIAS VOTADAS NA DATA SELECIONADA */}
        <div className="lg:col-span-7 space-y-4">
          {activeDay ? (
            <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-6 backdrop-blur-md shadow-2xl space-y-6">
              {/* Cabeçalho do Dia */}
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-4 border-b border-slate-800">
                <div className="space-y-0.5">
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
                    <span className="text-xs font-bold text-emerald-400 uppercase tracking-wider">
                      Deliberações Registradas
                    </span>
                  </div>
                  <h3 className="text-lg sm:text-xl font-black text-white">
                    {activeDay.data_formatada}
                  </h3>
                  <p className="text-xs text-slate-400">
                    {activeDay.dia_semana} • {activeDay.total_votacoes} matéria(s) apreciada(s) em plenário
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  {activeDay.camara_count > 0 && (
                    <span className="text-xs font-mono font-semibold px-2.5 py-1 rounded-xl bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                      Câmara: {activeDay.camara_count}
                    </span>
                  )}
                  {activeDay.senado_count > 0 && (
                    <span className="text-xs font-mono font-semibold px-2.5 py-1 rounded-xl bg-cyan-500/15 text-cyan-300 border border-cyan-500/30">
                      Senado: {activeDay.senado_count}
                    </span>
                  )}
                </div>
              </div>

              {/* Lista de Sessões e Proposições Deliberadas */}
              <div className="space-y-4">
                {activeDay.sessoes.map((sess, idx) => {
                  const isCamara = sess.casa === "CAMARA_DOS_DEPUTADOS";
                  return (
                    <div
                      key={sess.sessao_id || idx}
                      className="bg-slate-950/80 border border-slate-800/90 rounded-2xl p-5 space-y-4 shadow-lg hover:border-slate-700 transition-colors"
                    >
                      {/* Topo da Sessão: Casa Legislativa, Horário e Status */}
                      <div className="flex items-center justify-between gap-2 flex-wrap pb-3 border-b border-slate-800/60">
                        <div className="flex items-center gap-2">
                          <span className={`inline-flex items-center gap-1.5 text-xs font-bold px-2.5 py-1 rounded-xl border ${
                            isCamara
                              ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                              : "bg-cyan-500/15 text-cyan-300 border-cyan-500/30"
                          }`}>
                            {isCamara ? <Users className="w-3.5 h-3.5" /> : <Landmark className="w-3.5 h-3.5" />}
                            <span>{sess.casa_nome}</span>
                          </span>

                          <span className="text-xs font-mono text-slate-400 flex items-center gap-1">
                            <Clock className="w-3.5 h-3.5 text-slate-500" />
                            {sess.hora}
                          </span>
                        </div>

                        <span className={`inline-flex items-center gap-1.5 text-xs font-bold px-2.5 py-0.5 rounded-full border ${
                          sess.aprovada
                            ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                            : "bg-rose-500/20 text-rose-300 border-rose-500/40"
                        }`}>
                          {sess.aprovada ? (
                            <>
                              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                              <span>Aprovada</span>
                            </>
                          ) : (
                            <>
                              <XCircle className="w-3.5 h-3.5 text-rose-400" />
                              <span>Rejeitada</span>
                            </>
                          )}
                        </span>
                      </div>

                      {/* Título da Pauta & Descrição */}
                      <div className="space-y-1.5">
                        <h4 className="text-sm sm:text-base font-bold text-slate-100 leading-snug">
                          {sess.titulo}
                        </h4>
                        {sess.descricao && sess.descricao !== sess.titulo && (
                          <p className="text-xs text-slate-400 leading-relaxed">
                            {sess.descricao}
                          </p>
                        )}
                      </div>

                      {/* Dados da Proposição com LINK OFICIAL NA ÍNTEGRA */}
                      <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4 space-y-2.5">
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-purple-500/10 text-purple-300 border border-purple-500/20">
                              {sess.proposicao.tipo} {sess.proposicao.numero}/{sess.proposicao.ano}
                            </span>
                            <span className="text-[11px] text-slate-400 font-semibold">
                              {sess.proposicao.setor}
                            </span>
                          </div>

                          {/* LINK OFICIAL NA ÍNTEGRA (REQUISITO 2 e 4) */}
                          {sess.proposicao.url_oficial && (
                            <a
                              href={sess.proposicao.url_oficial}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1.5 text-xs font-semibold text-cyan-400 hover:text-cyan-300 bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/30 px-3 py-1 rounded-xl transition-all shadow-sm"
                              title="Ler texto da lei na íntegra no portal oficial"
                            >
                              <span>Ler Proposição na Íntegra</span>
                              <ExternalLink className="w-3.5 h-3.5" />
                            </a>
                          )}
                        </div>

                        <div className="font-semibold text-xs text-slate-200">
                          {sess.proposicao.titulo}
                        </div>

                        <p className="text-xs text-slate-400 line-clamp-3 leading-relaxed">
                          {sess.proposicao.ementa}
                        </p>

                        <div className="text-[11px] text-slate-500 pt-1 border-t border-slate-800/80">
                          Autor da iniciativa: <strong className="text-slate-400 font-medium">{sess.proposicao.autor_nome}</strong>
                        </div>
                      </div>

                      {/* Placar de Votação Nominal */}
                      {sess.placar && sess.placar.total > 0 && (
                        <div className="space-y-2 pt-1">
                          <div className="flex justify-between items-center text-xs">
                            <span className="font-semibold text-slate-400">Placar da Deliberação:</span>
                            <span className="font-mono text-slate-400 font-semibold">
                              Total: <strong className="text-slate-200">{sess.placar.total}</strong> votos
                            </span>
                          </div>

                          <div className="grid grid-cols-3 gap-2 text-center text-xs">
                            <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-2">
                              <span className="text-[11px] text-emerald-400 font-semibold block">Sim</span>
                              <strong className="text-sm font-mono font-bold text-emerald-300">
                                {sess.placar.sim}
                              </strong>
                            </div>
                            <div className="bg-rose-500/10 border border-rose-500/20 rounded-xl p-2">
                              <span className="text-[11px] text-rose-400 font-semibold block">Não</span>
                              <strong className="text-sm font-mono font-bold text-rose-300">
                                {sess.placar.nao}
                              </strong>
                            </div>
                            <div className="bg-amber-500/10 border border-amber-500/20 rounded-xl p-2">
                              <span className="text-[11px] text-amber-400 font-semibold block">Abstenção</span>
                              <strong className="text-sm font-mono font-bold text-amber-300">
                                {sess.placar.abstencao}
                              </strong>
                            </div>
                          </div>

                          {/* Barra do Placar */}
                          <div className="w-full bg-slate-900 h-2 rounded-full overflow-hidden flex">
                            <div
                              style={{ width: `${(sess.placar.sim / sess.placar.total) * 100}%` }}
                              className="bg-emerald-500 h-full"
                              title={`Sim: ${sess.placar.sim}`}
                            />
                            <div
                              style={{ width: `${(sess.placar.nao / sess.placar.total) * 100}%` }}
                              className="bg-rose-500 h-full"
                              title={`Não: ${sess.placar.nao}`}
                            />
                            <div
                              style={{ width: `${(sess.placar.abstencao / sess.placar.total) * 100}%` }}
                              className="bg-amber-500 h-full"
                              title={`Abstenção: ${sess.placar.abstencao}`}
                            />
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="bg-slate-900/60 border border-slate-800 rounded-3xl p-12 text-center text-slate-500 text-xs">
              Selecione uma data à esquerda para visualizar as deliberações e links na íntegra.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
