"use client";

import React, { useMemo, useState } from "react";
import { useApi } from "@/hooks/useApi";
import { getPartyIPPMEvolution, type PartyEvolutionSeries } from "@/services/api";
import { ErrorState, EmptyState } from "@/components/StateViews";

interface PartyEvolutionChartProps {
  casa: string;
}

const LARGURA = 760;
const ALTURA = 320;
const MARGEM = { topo: 16, direita: 20, baixo: 36, esquerda: 48 };
const MAX_SELECIONADOS = 8;
const PADRAO_SELECIONADOS = 5;

/** Valor "redondo" acima do máximo, para a escala do eixo vertical. */
function tetoDaEscala(maximo: number): number {
  if (maximo <= 0) return 1;
  const passo = Math.pow(10, Math.floor(Math.log10(maximo)));
  return Math.ceil(maximo / passo) * passo;
}

/** Divide a série em trechos de anos consecutivos: ano sem dado interrompe a linha em vez de ser ligado ao próximo. */
function trechos(serie: PartyEvolutionSeries["serie"]): PartyEvolutionSeries["serie"][] {
  const resultado: PartyEvolutionSeries["serie"][] = [];
  let atual: PartyEvolutionSeries["serie"] = [];
  for (const ponto of serie) {
    if (atual.length && ponto.ano !== atual[atual.length - 1].ano + 1) {
      resultado.push(atual);
      atual = [];
    }
    atual.push(ponto);
  }
  if (atual.length) resultado.push(atual);
  return resultado;
}

export default function PartyEvolutionChart({ casa }: PartyEvolutionChartProps) {
  const { data, loading, error, retry } = useApi(`party_ippm_evolution_${casa}`, (signal) =>
    getPartyIPPMEvolution({ casa }, signal)
  );
  const [escolha, setEscolha] = useState<string[] | null>(null);

  const partidos = useMemo(() => data?.partidos ?? [], [data]);
  const selecionados = escolha ?? partidos.slice(0, PADRAO_SELECIONADOS).map((p) => p.sigla);
  const visiveis = partidos.filter((p) => selecionados.includes(p.sigla));

  const geometria = useMemo(() => {
    if (!data || data.anos.length === 0) return null;
    const maximo = Math.max(...visiveis.flatMap((p) => p.serie.map((s) => s.ippm)), 0);
    const teto = tetoDaEscala(maximo);
    const [primeiro, ultimo] = [data.anos[0], data.anos[data.anos.length - 1]];
    const larguraUtil = LARGURA - MARGEM.esquerda - MARGEM.direita;
    const alturaUtil = ALTURA - MARGEM.topo - MARGEM.baixo;
    const x = (ano: number) =>
      MARGEM.esquerda + (ultimo === primeiro ? larguraUtil / 2 : ((ano - primeiro) / (ultimo - primeiro)) * larguraUtil);
    const y = (valor: number) => MARGEM.topo + alturaUtil - (valor / teto) * alturaUtil;
    const marcasY = [0, 0.25, 0.5, 0.75, 1].map((f) => f * teto);
    const passoAnos = data.anos.length > 14 ? 3 : data.anos.length > 8 ? 2 : 1;
    const marcasX = data.anos.filter((ano, i) => i % passoAnos === 0 || ano === ultimo);
    return { x, y, marcasY, marcasX };
  }, [data, visiveis]);

  const alternar = (sigla: string) => {
    const atuais = escolha ?? selecionados;
    if (atuais.includes(sigla)) setEscolha(atuais.filter((s) => s !== sigla));
    else if (atuais.length < MAX_SELECIONADOS) setEscolha([...atuais, sigla]);
  };

  if (loading) {
    return (
      <div className="py-16 flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-4 border-violet-500/20 border-t-violet-500 rounded-full animate-spin" />
        <p className="text-sm text-slate-400">Calculando a evolução ano a ano...</p>
      </div>
    );
  }
  if (error) {
    return <ErrorState title="Erro ao carregar a evolução" message={error.message} onRetry={retry} />;
  }
  if (!data || partidos.length === 0 || !geometria) {
    return (
      <EmptyState
        title="Sem histórico para mostrar"
        message="Ainda não há anos com cadeiras registradas para calcular a evolução."
      />
    );
  }

  return (
    <section className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 space-y-4" id="evolution-chart" aria-labelledby="evo-titulo">
      <div className="space-y-1">
        <h3 id="evo-titulo" className="text-base font-bold text-white">
          Como a produtividade mudou ano a ano
        </h3>
        <p className="text-xs text-slate-400">
          Cada linha é um partido: quanto mais alta, mais trabalho legislativo por cadeira naquele ano. Vale de{" "}
          {data.periodo.ano_inicio} a {data.periodo.ano_fim}; antes de 2003 a Câmara não publica o histórico de cadeiras, então
          o índice não pode ser calculado. O filtro de ano não se aplica a esta aba.
        </p>
      </div>

      <div role="group" aria-label="Partidos mostrados no gráfico" className="flex flex-wrap gap-1.5">
        {partidos.map((p) => {
          const ativo = selecionados.includes(p.sigla);
          return (
            <button
              key={p.sigla}
              type="button"
              aria-pressed={ativo}
              onClick={() => alternar(p.sigla)}
              title={p.nome_completo}
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-bold border transition-colors ${
                ativo ? "text-white border-transparent" : "text-slate-400 border-slate-700 hover:text-slate-200"
              }`}
              style={ativo ? { backgroundColor: `${p.cor_hex}55`, borderColor: p.cor_hex } : undefined}
            >
              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: p.cor_hex }} aria-hidden="true" />
              {p.sigla}
            </button>
          );
        })}
      </div>
      <p className="text-[11px] text-slate-500">
        Até {MAX_SELECIONADOS} partidos ao mesmo tempo. Escolhidos: {selecionados.length}.
      </p>

      {visiveis.length === 0 ? (
        <p className="text-xs text-slate-400 py-10 text-center">Escolha ao menos um partido para ver a linha.</p>
      ) : (
        <svg
          viewBox={`0 0 ${LARGURA} ${ALTURA}`}
          className="w-full h-auto"
          role="img"
          aria-label={`Gráfico de linhas do IPPM de ${visiveis.map((p) => p.sigla).join(", ")} entre ${data.periodo.ano_inicio} e ${data.periodo.ano_fim}`}
        >
          {geometria.marcasY.map((valor) => (
            <g key={valor}>
              <line
                x1={MARGEM.esquerda}
                x2={LARGURA - MARGEM.direita}
                y1={geometria.y(valor)}
                y2={geometria.y(valor)}
                stroke="#334155"
                strokeDasharray="3 4"
                strokeWidth={0.7}
              />
              <text x={MARGEM.esquerda - 8} y={geometria.y(valor) + 3} textAnchor="end" fontSize={10} fill="#94a3b8">
                {Number.isInteger(valor) ? valor : valor.toFixed(1)}
              </text>
            </g>
          ))}
          {geometria.marcasX.map((ano) => (
            <text key={ano} x={geometria.x(ano)} y={ALTURA - 14} textAnchor="middle" fontSize={10} fill="#94a3b8">
              {ano}
            </text>
          ))}
          <text x={12} y={ALTURA / 2} fontSize={10} fill="#64748b" transform={`rotate(-90 12 ${ALTURA / 2})`} textAnchor="middle">
            IPPM (pontos por cadeira)
          </text>

          {visiveis.map((p) => (
            <g key={p.sigla}>
              {trechos(p.serie).map((trecho) =>
                trecho.length > 1 ? (
                  <polyline
                    key={`${p.sigla}-${trecho[0].ano}`}
                    points={trecho.map((s) => `${geometria.x(s.ano)},${geometria.y(s.ippm)}`).join(" ")}
                    fill="none"
                    stroke={p.cor_hex}
                    strokeWidth={2}
                    strokeLinejoin="round"
                  />
                ) : null
              )}
              {p.serie.map((s) => (
                <circle key={`${p.sigla}-${s.ano}`} cx={geometria.x(s.ano)} cy={geometria.y(s.ippm)} r={3.5} fill={p.cor_hex} stroke="#0f172a" strokeWidth={1}>
                  <title>
                    {`${p.sigla} em ${s.ano}: IPPM ${s.ippm.toFixed(2).replace(".", ",")} · ${s.projetos_apresentados} projetos, ${s.projetos_aprovados} aprovados · ${s.cadeiras_dia_equivalentes.toFixed(1).replace(".", ",")} cadeiras`}
                  </title>
                </circle>
              ))}
            </g>
          ))}
        </svg>
      )}

      {visiveis.length > 0 && (
        <ul className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
          {visiveis.map((p) => {
            const ultimo = p.serie[p.serie.length - 1];
            return (
              <li key={p.sigla} className="flex items-center gap-2 bg-slate-950/50 border border-slate-800 rounded-lg px-2.5 py-1.5">
                <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: p.cor_hex }} aria-hidden="true" />
                <span className="font-bold text-slate-100">{p.sigla}</span>
                <span className="text-slate-400 ml-auto font-mono">
                  {ultimo.ippm.toFixed(2).replace(".", ",")} <span className="text-slate-500">({ultimo.ano})</span>
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
