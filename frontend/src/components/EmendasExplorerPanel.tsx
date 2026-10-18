"use client";

import React, { useState } from "react";
import {
  Coins,
  Search,
  Building2,
  Users2,
  Scale,
  HeartPulse,
  GraduationCap,
  HelpCircle,
  ChevronDown,
  ChevronUp,
  MapPin,
  Info
} from "lucide-react";
import {
  getEmendasResumo,
  getEmendasPorLocalidade,
  getEmendasPorAutor
} from "@/services/api";
import { useApi } from "@/hooks/useApi";
import { useDebounce } from "@/hooks/useDebounce";
import { fmtBRL, fmtNum, fmtPct } from "@/lib/format";
import { EmptyState, ErrorState, LoadingState } from "@/components/StateViews";

interface EmendasExplorerPanelProps {
  onSelectPolitician?: (politicianId: string) => void;
}

type ExplorerTab = "geral" | "localidade" | "institucional";

const AUTORES_SUGESTOES = [
  { id: "RELATOR GERAL", label: "Relator-Geral (RP9)", icone: Scale, cor: "border-amber-500/40 text-amber-300 bg-amber-500/10" },
  { id: "BANCADA DA BAHIA", label: "Bancada da Bahia", icone: Users2, cor: "border-emerald-500/40 text-emerald-300 bg-emerald-500/10" },
  { id: "BANCADA DE SAO PAULO", label: "Bancada de São Paulo", icone: Users2, cor: "border-cyan-500/40 text-cyan-300 bg-cyan-500/10" },
  { id: "BANCADA DE MINAS GERAIS", label: "Bancada de Minas Gerais", icone: Users2, cor: "border-indigo-500/40 text-indigo-300 bg-indigo-500/10" },
  { id: "COMISSAO DE SAUDE", label: "Comissão de Saúde", icone: HeartPulse, cor: "border-rose-500/40 text-rose-300 bg-rose-500/10" },
  { id: "COMISSAO DE EDUCACAO", label: "Comissão de Educação", icone: GraduationCap, cor: "border-blue-500/40 text-blue-300 bg-blue-500/10" },
];

// a API exige ao menos 2 caracteres (um termo curto casaria quase tudo)
const TERMO_MINIMO = 2;
// Mesmo limite do backend (a busca com mais de 100 caracteres volta 422)
const TERMO_MAXIMO = 100;

const LOCALIDADES_SUGESTOES = [
  "Campinas", "Recife", "Salvador", "Belo Horizonte", "Curitiba", "Manaus", "PA", "MA", "AL"
];

export default function EmendasExplorerPanel({ onSelectPolitician }: EmendasExplorerPanelProps) {
  const [activeTab, setActiveTab] = useState<ExplorerTab>("geral");

  // Busca por Localidade
  const [localidadeInput, setLocalidadeInput] = useState("Campinas");
  const debouncedLocalidade = useDebounce(localidadeInput.trim(), 400);

  // Busca por Autor Institucional (Bancadas / Relator)
  const [autorInput, setAutorInput] = useState("RELATOR GERAL");
  const debouncedAutor = useDebounce(autorInput.trim(), 400);

  // Controle do Dicionário Cidadão
  const [dicionarioAberto, setDicionarioAberto] = useState(false);

  // Queries
  const resumoQuery = useApi("emendas:resumo", (signal) => getEmendasResumo(signal));

  const localidadeQuery = useApi(
    `emendas:loc:${debouncedLocalidade}`,
    (signal) => getEmendasPorLocalidade(debouncedLocalidade, 50, signal),
    debouncedLocalidade.length >= TERMO_MINIMO && activeTab === "localidade"
  );

  const autorQuery = useApi(
    `emendas:autor:${debouncedAutor}`,
    (signal) => getEmendasPorAutor(debouncedAutor, 50, signal),
    debouncedAutor.length >= TERMO_MINIMO && activeTab === "institucional"
  );

  if (resumoQuery.loading && !resumoQuery.data) {
    return <LoadingState label="Carregando acervo de emendas orçamentárias da União..." />;
  }

  if (resumoQuery.error || !resumoQuery.data) {
    return (
      <ErrorState
        title="Falha ao carregar emendas orçamentárias"
        message="Não foi possível carregar os dados consolidados do orçamento. Verifique sua conexão e tente novamente."
        onRetry={resumoQuery.retry}
      />
    );
  }

  const resumo = resumoQuery.data;
  const { estatisticas_gerais, por_tipo_autor, por_area_tematica, top_ufs, dicionario } = resumo;

  return (
    <div className="space-y-8 animate-in fade-in duration-300">
      {/* ─── CABEÇALHO DO PAINEL ──────────────────────────────────────────────── */}
      <div className="bg-gradient-to-br from-slate-900 via-slate-900/90 to-amber-950/20 border border-slate-800 rounded-3xl p-6 sm:p-8 shadow-2xl relative overflow-hidden">
        <div className="absolute top-0 right-0 w-96 h-96 bg-amber-500/5 rounded-full blur-3xl pointer-events-none" />

        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6 pb-6 border-b border-slate-800/80">
          <div className="space-y-2">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs font-semibold uppercase tracking-wider">
              <Coins className="w-3.5 h-3.5" />
              Transparência Orçamentária • Ponto 2.7
            </div>
            <h2 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
              Explorador Nacional de Emendas Orçamentárias
            </h2>
            <p className="text-sm text-slate-400 max-w-3xl leading-relaxed">
              Rastreamento de todas as emendas ao Orçamento Geral da União (2019–2026). Rastreabilidade oficial
              segregada entre <strong className="text-slate-200">Individuais</strong>,{" "}
              <strong className="text-slate-200">Bancadas Estaduais</strong>,{" "}
              <strong className="text-slate-200">Comissões Temáticas</strong> e{" "}
              <strong className="text-slate-200">Relator-Geral</strong>.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2 self-stretch md:self-auto">
            <button
              type="button"
              onClick={() => setDicionarioAberto(!dicionarioAberto)}
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-slate-800/80 hover:bg-slate-700/80 text-amber-300 text-xs font-medium border border-slate-700 transition shadow-sm"
              aria-expanded={dicionarioAberto}
            >
              <HelpCircle className="w-4 h-4 text-amber-400" />
              <span>Dicionário Cidadão</span>
              {dicionarioAberto ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </button>
          </div>
        </div>

        {/* ─── CARDS DE KPIS NACIONAIS ────────────────────────────────────────── */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 pt-6">
          <div className="bg-slate-950/50 border border-slate-800/80 rounded-2xl p-4 sm:p-5 flex flex-col justify-between">
            <span className="text-xs text-slate-400 uppercase tracking-wider font-semibold">Total Reservado (Empenhado)</span>
            <div className="mt-2">
              <span className="text-xl sm:text-2xl font-black text-amber-300">
                {fmtBRL(estatisticas_gerais.total_reservado_empenhado_brl, 0)}
              </span>
              <p className="text-[11px] text-slate-500 mt-1">Garantido pelo Governo Federal</p>
            </div>
          </div>

          <div className="bg-slate-950/50 border border-slate-800/80 rounded-2xl p-4 sm:p-5 flex flex-col justify-between">
            <span className="text-xs text-slate-400 uppercase tracking-wider font-semibold">Total Entregue (Pago)</span>
            <div className="mt-2">
              <span className="text-xl sm:text-2xl font-black text-emerald-400">
                {fmtBRL(estatisticas_gerais.total_entregue_pago_brl, 0)}
              </span>
              <p className="text-[11px] text-emerald-500/80 mt-1 font-medium">Depositado nas contas públicas</p>
            </div>
          </div>

          <div className="bg-slate-950/50 border border-slate-800/80 rounded-2xl p-4 sm:p-5 flex flex-col justify-between">
            <span className="text-xs text-slate-400 uppercase tracking-wider font-semibold">Taxa de Execução Média</span>
            <div className="mt-2">
              <div className="flex items-baseline gap-2">
                <span className="text-xl sm:text-2xl font-black text-cyan-300">
                  {fmtPct(estatisticas_gerais.taxa_execucao_pago_pct, 1)}
                </span>
                <span className="text-xs text-slate-500">do empenhado</span>
              </div>
              <div className="w-full bg-slate-800 h-1.5 rounded-full mt-2 overflow-hidden">
                <div
                  className="bg-cyan-400 h-full rounded-full"
                  style={{ width: `${Math.min(100, estatisticas_gerais.taxa_execucao_pago_pct)}%` }}
                />
              </div>
            </div>
          </div>

          <div className="bg-slate-950/50 border border-slate-800/80 rounded-2xl p-4 sm:p-5 flex flex-col justify-between">
            <span className="text-xs text-slate-400 uppercase tracking-wider font-semibold">Acervo de Emendas</span>
            <div className="mt-2">
              <span className="text-xl sm:text-2xl font-black text-slate-200">
                {fmtNum(estatisticas_gerais.total_emendas, 0)}
              </span>
              <p className="text-[11px] text-slate-500 mt-1">Cadastradas e auditadas</p>
            </div>
          </div>
        </div>

        {/* ─── DICIONÁRIO CIDADÃO EXPANSÍVEL ──────────────────────────────────── */}
        {dicionarioAberto && (
          <div className="mt-6 pt-6 border-t border-slate-800 animate-in fade-in slide-in-from-top-2 duration-200">
            <div className="bg-slate-950/70 border border-amber-500/20 rounded-2xl p-5 space-y-4">
              <div className="flex items-center gap-2 text-amber-400 font-semibold text-sm">
                <Info className="w-4 h-4" />
                <span>Glossário Cidadão: Entendendo o Ciclo das Emendas</span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs text-slate-300">
                {dicionario?.termos_orcamentarios &&
                  Object.entries(dicionario.termos_orcamentarios).map(([chave, termo]) => (
                    <div key={chave} className="bg-slate-900/60 p-3.5 rounded-xl border border-slate-800/80 space-y-1.5">
                      <div className="flex items-center justify-between text-amber-300 font-bold">
                        <span>{termo.traducao || chave}</span>
                        <span className="text-[10px] text-slate-500 uppercase font-mono">({termo.termo_tecnico || chave})</span>
                      </div>
                      <p className="text-slate-400 leading-relaxed">{termo.explicacao}</p>
                    </div>
                  ))}
              </div>

              {dicionario?.linha_do_tempo && (
                <div className="pt-2 border-t border-slate-800/60">
                  <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-2">
                    Linha do Tempo Oficial da Verba Pública:
                  </span>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
                    {dicionario.linha_do_tempo.map((etapa) => (
                      <div key={etapa.etapa} className="flex items-start gap-2 text-slate-400 bg-slate-900/40 p-2.5 rounded-lg">
                        <span className="w-5 h-5 rounded-full bg-slate-800 text-amber-400 font-bold text-center leading-5 flex-shrink-0 text-[11px]">
                          {etapa.etapa}
                        </span>
                        <div>
                          <strong className="text-slate-200 block">{etapa.nome}</strong>
                          <span className="text-[11px] text-slate-400">{etapa.descricao}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* ─── 4 CATEGORIAS DE AUTORES (DICIONÁRIO INSTITUCIONAL DO 2.7) ──────── */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-bold text-slate-200 flex items-center gap-2">
            <Users2 className="w-4 h-4 text-amber-400" />
            <span>Classificação Institucional das Emendas (Ponto 2.7)</span>
          </h3>
          <span className="text-xs text-slate-500">Auditoria das 54.362 emendas do acervo</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {por_tipo_autor &&
            Object.entries(por_tipo_autor).map(([tipo, dados]) => {
              const pct = dados.total_empenhado > 0 ? (dados.total_pago / dados.total_empenhado) * 100 : 0;
              return (
                <div
                  key={tipo}
                  className="bg-slate-900/80 border border-slate-800 hover:border-slate-700 transition rounded-2xl p-5 space-y-3 shadow-lg"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-2.5">
                      <span className="text-2xl p-2 rounded-xl bg-slate-800/80 border border-slate-700/60">
                        {dados.icone}
                      </span>
                      <div>
                        <h4 className="font-bold text-slate-200 text-sm leading-tight">{dados.categoria}</h4>
                        <span className="text-[11px] text-slate-400 font-mono">{fmtNum(dados.quantidade, 0)} emendas</span>
                      </div>
                    </div>
                  </div>

                  <p className="text-xs text-slate-400 leading-relaxed line-clamp-2" title={dados.descricao}>
                    {dados.descricao}
                  </p>

                  <div className="pt-3 border-t border-slate-800/80 space-y-1.5 text-xs">
                    <div className="flex justify-between items-baseline">
                      <span className="text-slate-500">Pago:</span>
                      <strong className="text-emerald-400 font-bold">{fmtBRL(dados.total_pago, 0)}</strong>
                    </div>
                    <div className="flex justify-between items-baseline text-[11px]">
                      <span className="text-slate-500">Empenhado:</span>
                      <span className="text-slate-400 font-medium">{fmtBRL(dados.total_empenhado, 0)}</span>
                    </div>
                    <div className="w-full bg-slate-800 h-1 rounded-full overflow-hidden mt-1">
                      <div className="bg-emerald-400 h-full rounded-full" style={{ width: `${Math.min(100, pct)}%` }} />
                    </div>
                  </div>
                </div>
              );
            })}
        </div>
      </div>

      {/* ─── ABAS INTERNAS DE NAVEGAÇÃO ─────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-2 p-1.5 bg-slate-900/90 border border-slate-800 rounded-2xl max-w-xl">
        <button
          type="button"
          onClick={() => setActiveTab("geral")}
          className={`flex-1 min-w-[140px] px-4 py-2.5 rounded-xl text-xs sm:text-sm font-semibold transition flex items-center justify-center gap-2 ${
            activeTab === "geral"
              ? "bg-amber-400 text-slate-950 shadow-md shadow-amber-400/20"
              : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
          }`}
        >
          <Building2 className="w-4 h-4" />
          <span>Visão Geral & Áreas</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("localidade")}
          className={`flex-1 min-w-[140px] px-4 py-2.5 rounded-xl text-xs sm:text-sm font-semibold transition flex items-center justify-center gap-2 ${
            activeTab === "localidade"
              ? "bg-amber-400 text-slate-950 shadow-md shadow-amber-400/20"
              : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
          }`}
        >
          <MapPin className="w-4 h-4" />
          <span>Busca por Cidade/UF</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("institucional")}
          className={`flex-1 min-w-[140px] px-4 py-2.5 rounded-xl text-xs sm:text-sm font-semibold transition flex items-center justify-center gap-2 ${
            activeTab === "institucional"
              ? "bg-amber-400 text-slate-950 shadow-md shadow-amber-400/20"
              : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
          }`}
        >
          <Scale className="w-4 h-4" />
          <span>Bancadas & Relator</span>
        </button>
      </div>

      {/* ─── ABA 1: VISÃO GERAL & ÁREAS TEMÁTICAS ───────────────────────────── */}
      {activeTab === "geral" && (
        <div className="space-y-6 animate-in fade-in duration-200">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Distribuição por Áreas Temáticas */}
            <div className="lg:col-span-2 bg-slate-900/80 border border-slate-800 rounded-3xl p-6 shadow-xl space-y-4">
              <div className="flex items-center justify-between pb-4 border-b border-slate-800">
                <div>
                  <h3 className="text-base font-bold text-slate-200 flex items-center gap-2">
                    <HeartPulse className="w-4 h-4 text-rose-400" />
                    <span>Destinação por Área Temática</span>
                  </h3>
                  <p className="text-xs text-slate-500">Valores pagos vs reservados por área prioritária</p>
                </div>
                <span className="text-xs text-slate-400 font-mono">Top Áreas</span>
              </div>

              <div className="space-y-3.5 pt-2">
                {por_area_tematica?.slice(0, 7).map((area) => {
                  const pct = area.total_empenhado > 0 ? (area.total_pago / area.total_empenhado) * 100 : 0;
                  return (
                    <div key={area.area} className="bg-slate-950/40 p-3.5 rounded-2xl border border-slate-800/60 space-y-2">
                      <div className="flex items-center justify-between text-xs">
                        <div className="flex items-center gap-2">
                          <span className="text-base">{area.icone}</span>
                          <strong className="text-slate-200 font-bold">{area.rotulo}</strong>
                          <span className="text-[11px] text-slate-500 font-mono">({fmtNum(area.quantidade, 0)} emendas)</span>
                        </div>
                        <div className="text-right">
                          <strong className="text-emerald-400 font-bold block">{fmtBRL(area.total_pago, 0)}</strong>
                          <span className="text-[10px] text-slate-500">de {fmtBRL(area.total_empenhado, 0)}</span>
                        </div>
                      </div>

                      <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                        <div
                          className="bg-gradient-to-r from-emerald-500 to-cyan-400 h-full rounded-full transition-all"
                          style={{ width: `${Math.min(100, pct)}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Top UFs Destinatárias */}
            <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-6 shadow-xl space-y-4">
              <div className="flex items-center justify-between pb-4 border-b border-slate-800">
                <div>
                  <h3 className="text-base font-bold text-slate-200 flex items-center gap-2">
                    <MapPin className="w-4 h-4 text-cyan-400" />
                    <span>Top Estados Receptores</span>
                  </h3>
                  <p className="text-xs text-slate-500">UFs com maior montante pago</p>
                </div>
              </div>

              <div className="space-y-2.5 pt-2">
                {top_ufs?.slice(0, 8).map((ufItem, idx) => (
                  <div
                    key={ufItem.uf}
                    className="flex items-center justify-between p-3 rounded-xl bg-slate-950/40 border border-slate-800/60 text-xs"
                  >
                    <div className="flex items-center gap-3">
                      <span className="w-6 h-6 rounded-lg bg-slate-800 text-amber-400 font-bold flex items-center justify-center text-[11px]">
                        {idx + 1}º
                      </span>
                      <div>
                        <strong className="text-slate-200 font-bold block">Estado do {ufItem.uf}</strong>
                        <span className="text-[11px] text-slate-500 font-mono">{fmtNum(ufItem.quantidade, 0)} emendas</span>
                      </div>
                    </div>
                    <div className="text-right">
                      <strong className="text-emerald-400 font-bold block">{fmtBRL(ufItem.total_pago, 0)}</strong>
                      <span className="text-[10px] text-slate-500">{fmtBRL(ufItem.total_empenhado, 0)} emp.</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ─── ABA 2: BUSCA TERRITORIAL POR CIDADE OU UF ──────────────────────── */}
      {activeTab === "localidade" && (
        <div className="space-y-6 animate-in fade-in duration-200">
          <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-6 shadow-xl space-y-4">
            <div className="space-y-1">
              <h3 className="text-lg font-bold text-slate-200 flex items-center gap-2">
                <MapPin className="w-5 h-5 text-amber-400" />
                <span>Pesquisa Territorial de Recursos Públicos</span>
              </h3>
              <p className="text-xs text-slate-400">
                Digite o nome de qualquer município brasileiro ou a sigla de um estado para auditar as emendas destinadas à região.
              </p>
            </div>

            {/* Input de Busca */}
            <div className="relative max-w-xl">
              <Search className="w-5 h-5 text-slate-400 absolute left-4 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                type="text"
                value={localidadeInput}
                maxLength={TERMO_MAXIMO}
                onChange={(e) => setLocalidadeInput(e.target.value)}
                placeholder="Ex: Campinas, Belo Horizonte, Recife, SP, Bahia..."
                className="w-full pl-11 pr-4 py-3 bg-slate-950/80 border border-slate-700 rounded-2xl text-slate-100 placeholder-slate-500 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500 transition shadow-inner"
                aria-label="Pesquisar por município ou estado"
              />
            </div>

            {/* Badges de Sugestão */}
            <div className="flex flex-wrap items-center gap-1.5 pt-1">
              <span className="text-xs text-slate-500 font-medium mr-1">Sugestões rápidas:</span>
              {LOCALIDADES_SUGESTOES.map((loc) => (
                <button
                  key={loc}
                  type="button"
                  onClick={() => setLocalidadeInput(loc)}
                  className={`text-xs px-2.5 py-1 rounded-lg border transition ${
                    localidadeInput.toLowerCase() === loc.toLowerCase()
                      ? "bg-amber-400 text-slate-950 font-bold border-amber-400"
                      : "bg-slate-800/80 text-slate-400 hover:text-slate-200 border-slate-700/80 hover:bg-slate-700/80"
                  }`}
                >
                  {loc}
                </button>
              ))}
            </div>
          </div>

          {/* Resultado da Busca Territorial */}
          {debouncedLocalidade.length < TERMO_MINIMO ? (
            <EmptyState
              title={`Digite ao menos ${TERMO_MINIMO} letras`}
              message="Informe o nome de um município ou o estado, pela sigla ou por extenso (ex: SP, Minas Gerais, Recife)."
            />
          ) : localidadeQuery.loading ? (
            <LoadingState label={`Buscando emendas destinadas a "${debouncedLocalidade}"...`} />
          ) : localidadeQuery.error ? (
            <ErrorState
              title="Erro ao consultar localidade"
              message="Não foi possível carregar as emendas para a localidade solicitada."
              onRetry={localidadeQuery.retry}
            />
          ) : !localidadeQuery.data || localidadeQuery.data.total_emendas_encontradas === 0 ? (
            <EmptyState
              title={`Nenhuma emenda encontrada para "${debouncedLocalidade}"`}
              message="Tente pesquisar por outro município ou pela sigla do estado correspondente (ex: SP, MG, RJ)."
            />
          ) : (
            <div className="space-y-6">
              {/* KPIs Locais */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4">
                  <span className="text-xs text-slate-400 font-semibold uppercase">Localidade</span>
                  <p className="text-lg font-bold text-amber-300 mt-1 truncate">
                    {localidadeQuery.data.localidade_pesquisada}
                  </p>
                </div>
                <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4">
                  <span className="text-xs text-slate-400 font-semibold uppercase">Emendas Encontradas</span>
                  <p className="text-lg font-bold text-slate-200 mt-1">
                    {localidadeQuery.data.total_emendas_encontradas}
                  </p>
                </div>
                <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4">
                  <span className="text-xs text-slate-400 font-semibold uppercase">Total Pago na Região</span>
                  <p className="text-lg font-bold text-emerald-400 mt-1">
                    {fmtBRL(localidadeQuery.data.total_entregue_pago_brl, 0)}
                  </p>
                </div>
                <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4">
                  <span className="text-xs text-slate-400 font-semibold uppercase">Taxa de Execução</span>
                  <p className="text-lg font-bold text-cyan-300 mt-1">
                    {fmtPct(localidadeQuery.data.taxa_execucao_pct, 1)}
                  </p>
                </div>
              </div>

              {/* Tabela de Emendas da Localidade */}
              <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-6 shadow-xl space-y-4">
                <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                  <h4 className="font-bold text-slate-200 text-sm flex items-center gap-2">
                    <Coins className="w-4 h-4 text-amber-400" />
                    <span>Emendas Destinadas à Região ({localidadeQuery.data.emendas.length})</span>
                  </h4>
                  <span className="text-xs text-slate-500">Ordenadas por valor entregue</span>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-slate-800 text-slate-400 font-semibold">
                        <th className="pb-3 pl-2">Ano</th>
                        <th className="pb-3">Autor da Emenda</th>
                        <th className="pb-3">Tipo / Categoria</th>
                        <th className="pb-3">Área Temática</th>
                        <th className="pb-3 text-right">Valor Empenhado</th>
                        <th className="pb-3 text-right">Valor Pago</th>
                        <th className="pb-3 text-center">Estágio</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60">
                      {localidadeQuery.data.emendas.map((e, idx) => (
                        <tr key={`${e.codigo_emenda || idx}-${e.ano}`} className="hover:bg-slate-800/40 transition">
                          <td className="py-3 pl-2 font-mono text-slate-400 font-bold">{e.ano}</td>
                          <td className="py-3">
                            <div className="flex items-center gap-2">
                              <span className="text-base">{e.autor?.icone || "👤"}</span>
                              <div>
                                <strong className="text-slate-200 block leading-tight">
                                  {onSelectPolitician && e.autor?.tipo_autor === "INDIVIDUAL" ? (
                                    <button
                                      type="button"
                                      onClick={() => onSelectPolitician(e.autor.nome_tecnico)}
                                      className="text-amber-400 hover:text-amber-300 hover:underline text-left"
                                      title={e.autor?.nome_amigavel || e.autor?.nome_tecnico || "Ver parlamentar"}
                                    >
                                      {e.autor?.nome_amigavel || e.autor?.nome_tecnico}
                                    </button>
                                  ) : (
                                    e.autor?.nome_amigavel || e.autor?.nome_tecnico
                                  )}
                                </strong>
                                <span className="text-[10px] text-slate-500 font-mono">
                                  {e.codigo_emenda ? `Cód. ${e.codigo_emenda}` : "Emenda sem código"}
                                </span>
                              </div>
                            </div>
                          </td>
                          <td className="py-3">
                            <span className="px-2 py-0.5 rounded-md bg-slate-800 text-[11px] text-slate-300 font-medium">
                              {e.autor?.categoria || e.autor?.tipo_autor}
                            </span>
                          </td>
                          <td className="py-3">
                            <div className="flex items-center gap-1.5">
                              <span>{e.area_icone}</span>
                              <span className="text-slate-300">{e.area_rotulo}</span>
                            </div>
                          </td>
                          <td className="py-3 text-right font-mono text-slate-400">
                            {fmtBRL(e.valor_reservado_empenhado, 2)}
                          </td>
                          <td className="py-3 text-right font-mono font-bold text-emerald-400">
                            {fmtBRL(e.valor_entregue_pago, 2)}
                          </td>
                          <td className="py-3 text-center">
                            <span
                              className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                e.estagio === "Dinheiro Entregue"
                                  ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                                  : "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                              }`}
                            >
                              {e.estagio}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ─── ABA 3: BANCADAS, COMISSÕES E RELATOR-GERAL (PONTO 2.7) ─────────── */}
      {activeTab === "institucional" && (
        <div className="space-y-6 animate-in fade-in duration-200">
          <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-6 shadow-xl space-y-4">
            <div className="space-y-1">
              <h3 className="text-lg font-bold text-slate-200 flex items-center gap-2">
                <Scale className="w-5 h-5 text-amber-400" />
                <span>Auditoria de Autores Coletivos & Relator-Geral</span>
              </h3>
              <p className="text-xs text-slate-400">
                Consulte emendas sem vínculo de parlamentar único: deliberações de bancadas estaduais,
                comissões parlamentares e a cota do Relator-Geral da CMO (antigo RP9 / Orçamento Secreto).
              </p>
            </div>

            {/* Sugestões de Autores Institucionais */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 pt-2">
              {AUTORES_SUGESTOES.map((item) => {
                const Icon = item.icone;
                const isSelected = autorInput.toUpperCase() === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setAutorInput(item.id)}
                    className={`p-3 rounded-2xl border text-left transition flex flex-col justify-between gap-2 ${
                      isSelected
                        ? "bg-amber-400 text-slate-950 font-bold border-amber-400 shadow-md shadow-amber-400/20"
                        : "bg-slate-950/60 hover:bg-slate-800/80 text-slate-300 border-slate-800"
                    }`}
                  >
                    <Icon className={`w-4 h-4 ${isSelected ? "text-slate-950" : "text-amber-400"}`} />
                    <span className="text-xs font-semibold leading-tight">{item.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Resultado da Consulta Institucional */}
          {debouncedAutor.length < TERMO_MINIMO ? (
            <EmptyState
              title={`Digite ao menos ${TERMO_MINIMO} letras`}
              message="Selecione um dos autores sugeridos acima ou informe o nome de uma bancada ou comissão."
            />
          ) : autorQuery.loading ? (
            <LoadingState label={`Consultando emendas do autor institucional "${debouncedAutor}"...`} />
          ) : autorQuery.error ? (
            <ErrorState
              title="Erro ao consultar autor institucional"
              message="Não foi possível carregar os dados para este autor institucional."
              onRetry={autorQuery.retry}
            />
          ) : !autorQuery.data ? (
            <EmptyState
              title="Nenhuma informação institucional encontrada"
              message="Selecione um dos autores sugeridos acima ou pesquise por outra bancada."
            />
          ) : (
            <div className="space-y-6">
              {/* Card de Perfil do Autor Institucional */}
              <div className="bg-slate-900/90 border border-slate-800 rounded-3xl p-6 shadow-xl relative overflow-hidden">
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
                  <div className="flex items-center gap-3.5">
                    <span className="text-3xl p-3 bg-slate-800/90 rounded-2xl border border-slate-700/80">
                      {autorQuery.data.perfil_autor?.icone || "🏛️"}
                    </span>
                    <div>
                      <div className="flex items-center gap-2">
                        <h4 className="text-xl font-bold text-white">
                          {autorQuery.data.perfil_autor?.nome_amigavel || autorQuery.data.autor_pesquisado}
                        </h4>
                        <span className="px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30 text-[10px] font-bold uppercase">
                          {autorQuery.data.perfil_autor?.categoria}
                        </span>
                      </div>
                      <p className="text-xs text-slate-400 mt-1 max-w-2xl">
                        {autorQuery.data.perfil_autor?.descricao_amigavel}
                      </p>
                      {autorQuery.data.quantidade_autores > 1 && (
                        <p className="text-xs text-amber-300 mt-2 max-w-2xl">
                          Esta busca reuniu {autorQuery.data.quantidade_autores} autores (
                          {autorQuery.data.autores_encontrados.map((a) => a.nome_amigavel).join(", ")}
                          {autorQuery.data.quantidade_autores > autorQuery.data.autores_encontrados.length
                            ? " e outros"
                            : ""}
                          ). Os totais abaixo somam todos eles.
                        </p>
                      )}
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 pt-4 text-xs">
                  <div>
                    <span className="text-slate-500 block">Total Empenhado:</span>
                    <strong className="text-slate-200 text-base font-bold">
                      {fmtBRL(autorQuery.data.total_reservado_empenhado_brl, 0)}
                    </strong>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Total Entregue (Pago):</span>
                    <strong className="text-emerald-400 text-base font-bold">
                      {fmtBRL(autorQuery.data.total_entregue_pago_brl, 0)}
                    </strong>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Taxa de Execução:</span>
                    <strong className="text-cyan-300 text-base font-bold">
                      {fmtPct(autorQuery.data.taxa_execucao_pct, 1)}
                    </strong>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Emendas Auditadas:</span>
                    <strong className="text-slate-200 text-base font-bold">
                      {fmtNum(autorQuery.data.total_emendas_enviadas, 0)}
                    </strong>
                  </div>
                </div>
              </div>

              {/* Top Destinos e Áreas */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Destinos */}
                <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-6 shadow-xl space-y-3">
                  <h4 className="font-bold text-slate-200 text-sm flex items-center gap-2">
                    <MapPin className="w-4 h-4 text-amber-400" />
                    <span>Principais Municípios Destinatários</span>
                  </h4>
                  <div className="space-y-2 pt-1">
                    {autorQuery.data.top_destinos?.slice(0, 6).map((dest) => (
                      <div
                        key={dest.localidade}
                        className="flex items-center justify-between p-2.5 rounded-xl bg-slate-950/40 border border-slate-800/60 text-xs"
                      >
                        <span className="text-slate-200 font-medium truncate" title={dest.localidade}>
                          {dest.localidade}
                        </span>
                        <div className="text-right flex-shrink-0">
                          <strong className="text-emerald-400 font-bold block">{fmtBRL(dest.total_pago, 0)}</strong>
                          <span className="text-[10px] text-slate-500">{fmtNum(dest.quantidade, 0)} emendas</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Áreas */}
                <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-6 shadow-xl space-y-3">
                  <h4 className="font-bold text-slate-200 text-sm flex items-center gap-2">
                    <HeartPulse className="w-4 h-4 text-rose-400" />
                    <span>Divisão por Área de Atuação</span>
                  </h4>
                  <div className="space-y-2 pt-1">
                    {autorQuery.data.por_area_tematica?.slice(0, 6).map((area) => (
                      <div
                        key={area.area}
                        className="flex items-center justify-between p-2.5 rounded-xl bg-slate-950/40 border border-slate-800/60 text-xs"
                      >
                        <div className="flex items-center gap-2 truncate">
                          <span>{area.icone}</span>
                          <span className="text-slate-200 font-medium truncate">{area.rotulo}</span>
                        </div>
                        <div className="text-right flex-shrink-0">
                          <strong className="text-emerald-400 font-bold block">{fmtBRL(area.total_pago, 0)}</strong>
                          <span className="text-[10px] text-slate-500">{fmtNum(area.quantidade, 0)} emendas</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Lista Detalhada */}
              <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-6 shadow-xl space-y-4">
                <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                  <h4 className="font-bold text-slate-200 text-sm flex items-center gap-2">
                    <Coins className="w-4 h-4 text-amber-400" />
                    <span>Emendas deste Autor ({autorQuery.data.emendas.length})</span>
                  </h4>
                  <span className="text-xs text-slate-500">Rastreamento da destinação</span>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-slate-800 text-slate-400 font-semibold">
                        <th className="pb-3 pl-2">Ano</th>
                        <th className="pb-3">Localidade de Destino</th>
                        <th className="pb-3">Área Temática</th>
                        <th className="pb-3 text-right">Valor Empenhado</th>
                        <th className="pb-3 text-right">Valor Pago</th>
                        <th className="pb-3 text-center">Estágio</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60">
                      {autorQuery.data.emendas.map((e, idx) => (
                        <tr key={`${e.codigo_emenda || idx}-${e.ano}`} className="hover:bg-slate-800/40 transition">
                          <td className="py-3 pl-2 font-mono text-slate-400 font-bold">{e.ano}</td>
                          <td className="py-3">
                            <strong className="text-slate-200 block">{e.localidade_destino || "Nacional"}</strong>
                            <span className="text-[10px] text-slate-500 font-mono">
                              {e.codigo_emenda ? `Cód. ${e.codigo_emenda}` : "Emenda Geral"}
                            </span>
                          </td>
                          <td className="py-3">
                            <div className="flex items-center gap-1.5">
                              <span>{e.area_icone}</span>
                              <span className="text-slate-300">{e.area_rotulo}</span>
                            </div>
                          </td>
                          <td className="py-3 text-right font-mono text-slate-400">
                            {fmtBRL(e.valor_reservado_empenhado, 2)}
                          </td>
                          <td className="py-3 text-right font-mono font-bold text-emerald-400">
                            {fmtBRL(e.valor_entregue_pago, 2)}
                          </td>
                          <td className="py-3 text-center">
                            <span
                              className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                e.estagio === "Dinheiro Entregue"
                                  ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                                  : "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                              }`}
                            >
                              {e.estagio}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
