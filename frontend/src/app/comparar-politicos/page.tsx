"use client";

import React, { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Header from "@/components/Header";
import Compartilhar from "@/components/Compartilhar";
import { atualizarUrl, montarLink } from "@/lib/compartilhar";
import { useApi } from "@/hooks/useApi";
import { getPoliticianDossier, searchPoliticians, type PoliticoBuscaItem, type PoliticoDossier } from "@/services/api";
import { ErrorState, LoadingState } from "@/components/StateViews";
import { fmtBRL, fmtNum, isNum } from "@/lib/format";
import { X } from "lucide-react";

const MAXIMO = 5;

function idsDaUrl(valor: string | null): string[] {
  return (valor ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, MAXIMO);
}

/** Valor ausente nunca vira zero: mostra "indisponível". */
function ou(valor: string | number | null | undefined, formatar: (v: number) => string = fmtNum): string {
  if (valor === null || valor === undefined) return "indisponível";
  return typeof valor === "number" ? (isNum(valor) ? formatar(valor) : "indisponível") : valor;
}

export function linhasDaComparacao(d: PoliticoDossier): Array<[string, string]> {
  const baso = d.basometro;
  const resumo = d.resumo_votos;
  return [
    ["Cargo", ou(d.perfil.cargo_atual)],
    ["Partido atual", ou(d.perfil.partido_atual)],
    ["UF", ou(d.perfil.uf)],
    [
      "Presença nas sessões",
      d.assiduidade && d.assiduidade.total_sessoes > 0 ? `${ou(d.assiduidade.taxa_presenca_pct)}%` : "indisponível",
    ],
    ["Sessões registradas", ou(d.assiduidade?.total_sessoes)],
    ["Votos registrados", ou(baso?.votos_registrados)],
    ["Votou SIM", ou(resumo?.sim.total)],
    ["Votou NÃO", ou(resumo?.nao.total)],
    [
      "Alinhamento ao Governo",
      isNum(baso?.taxa_governismo_pct) ? `${baso?.taxa_governismo_pct}%` : "sem índice (amostra insuficiente)",
    ],
    ["Projetos de sua autoria", String(d.materias_propostas.length)],
    ["Trocas de partido", ou(d.indices_inteligencia?.estabilidade_partidaria?.total_trocas)],
    ["Média mensal da cota (CEAP)", ou(d.remuneracao?.resumo?.media_ceap_mensal, fmtBRL)],
  ];
}

function Coluna({ id, onRemover }: { id: string; onRemover: (id: string) => void }) {
  const q = useApi(`comparar-politico:${id}`, (signal) => getPoliticianDossier(id, signal));
  if (q.loading) return <LoadingState label="Carregando..." />;
  if (q.error || !q.data) return <ErrorState message="Não foi possível carregar este político." onRetry={q.retry} />;
  const d = q.data;
  return (
    <section aria-label={`Dados de ${d.perfil.nome_eleitoral}`} className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
      <div className="flex items-start justify-between gap-2">
        <h2 className="text-sm font-bold text-white">{d.perfil.nome_eleitoral}</h2>
        <button
          type="button"
          onClick={() => onRemover(id)}
          aria-label={`Remover ${d.perfil.nome_eleitoral} da comparação`}
          className="text-slate-400 hover:text-rose-300"
        >
          <X className="w-4 h-4" aria-hidden="true" />
        </button>
      </div>
      <dl className="mt-3 space-y-2 text-xs">
        {linhasDaComparacao(d).map(([rotulo, valor]) => (
          <div key={rotulo} className="flex justify-between gap-3 border-b border-slate-800/70 pb-1.5">
            <dt className="text-slate-400">{rotulo}</dt>
            <dd className={`font-mono font-semibold text-right ${valor.startsWith("indispon") || valor.startsWith("sem índice") ? "text-slate-500" : "text-slate-100"}`}>
              {valor}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function Seletor({ escolhidos, onAdicionar }: { escolhidos: string[]; onAdicionar: (id: string) => void }) {
  const [texto, setTexto] = useState("");
  const [termo, setTermo] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setTermo(texto.trim()), 300);
    return () => clearTimeout(t);
  }, [texto]);
  const busca = useApi(
    `comparar-busca:${termo}`,
    (signal) => searchPoliticians(termo, undefined, undefined, undefined, 8, signal),
    termo.length >= 2
  );
  const itens: PoliticoBuscaItem[] = termo.length >= 2 ? (busca.data?.politicos ?? []) : [];
  return (
    <div className="space-y-2">
      <label htmlFor="busca-comparar" className="text-xs font-semibold text-slate-300">
        Adicionar parlamentar ({escolhidos.length}/{MAXIMO})
      </label>
      <input
        id="busca-comparar"
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
        disabled={escolhidos.length >= MAXIMO}
        placeholder={escolhidos.length >= MAXIMO ? "Limite de 5 atingido" : "Digite o nome..."}
        className="w-full rounded-xl bg-slate-950 border border-slate-700 px-3 py-2 text-sm text-white"
      />
      {itens.length > 0 && (
        <ul className="rounded-xl border border-slate-800 bg-slate-950 divide-y divide-slate-800">
          {itens
            .filter((p) => !escolhidos.includes(p.id))
            .map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  onClick={() => {
                    onAdicionar(p.id);
                    setTexto("");
                  }}
                  className="w-full text-left px-3 py-2 text-sm text-slate-200 hover:bg-slate-800"
                >
                  {p.nome_eleitoral} <span className="text-slate-400">({p.partido_sigla}/{p.uf})</span>
                </button>
              </li>
            ))}
        </ul>
      )}
    </div>
  );
}

function CompararPoliticos() {
  const parametros = useSearchParams();
  const [ids, setIds] = useState<string[]>(() => idsDaUrl(parametros?.get("ids") ?? null));

  function mudar(proximos: string[]) {
    setIds(proximos);
    atualizarUrl({ ids: proximos.join(",") || null });
  }

  const link = montarLink({ ids: ids.join(",") }, "/comparar-politicos");

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <Header />
      <main className="max-w-7xl mx-auto px-4 py-6 space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold text-white">Comparar parlamentares</h1>
            <p className="text-xs text-slate-400">
              Até {MAXIMO} lado a lado, com os mesmos números do perfil de cada um. Sem nota e sem ranking: valor sem dado
              aparece como indisponível.
            </p>
          </div>
          {ids.length > 0 && (
            <Compartilhar
              link={link}
              nomeDoArquivo="comparacao-parlamentares"
              cartao={{
                titulo: "Comparação de parlamentares",
                linhas: [["Parlamentares comparados", String(ids.length)]],
                fonte: "LegisData, com dados abertos da Câmara e do Senado",
                data: new Date().toLocaleDateString("pt-BR"),
                periodo: "Mandatos registrados na base",
                etapa: "Perfil de cada parlamentar",
                link,
              }}
            />
          )}
        </div>
        <Seletor escolhidos={ids} onAdicionar={(id) => mudar([...ids, id].slice(0, MAXIMO))} />
        {ids.length === 0 ? (
          <p className="text-sm text-slate-400">Escolha ao menos dois parlamentares para comparar.</p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {ids.map((id) => (
              <Coluna key={id} id={id} onRemover={(r) => mudar(ids.filter((x) => x !== r))} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense fallback={null}>
      <CompararPoliticos />
    </Suspense>
  );
}
