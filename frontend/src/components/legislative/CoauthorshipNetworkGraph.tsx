"use client";

import React, { useState, useEffect, useMemo, useRef, useCallback } from "react";
import {
  getCoauthorshipNetwork,
  CoauthorshipNetworkResponse,
  CoauthorshipNetworkNode,
} from "@/services/api";
import {
  Share2,
  Sparkles,
  Zap,
  Info,
  ZoomIn,
  ZoomOut,
  Maximize2,
  RefreshCw,
  Search,
  ExternalLink,
  Layers,
  Award,
  AlertCircle,
  X,
} from "lucide-react";
import Image from "next/image";

interface CoauthorshipNetworkGraphProps {
  onSelectPolitician?: (id: string) => void;
}

interface SimNode extends CoauthorshipNetworkNode {
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
}

const COMMUNITY_PALETTE = [
  "#22d3ee", // cyan
  "#a855f7", // purple
  "#34d399", // emerald
  "#f59e0b", // amber
  "#ec4899", // pink
  "#6366f1", // indigo
  "#14b8a6", // teal
  "#f43f5e", // rose
  "#8b5cf6", // violet
  "#10b981", // green
];

function computeSimNodes(networkData: CoauthorshipNetworkResponse | null): SimNode[] {
  if (!networkData || networkData.nodes.length === 0) {
    return [];
  }

  const width = 900;
  const height = 650;
  const centerX = width / 2;
  const centerY = height / 2;

  // Calcular centros de comunidades para agrupamento visual Louvain
  const commIds = Array.from(new Set(networkData.nodes.map((n) => n.community))).sort((a, b) => a - b);
  const commCenters: Record<number, { x: number; y: number }> = {};
  const angleStep = (2 * Math.PI) / Math.max(commIds.length, 1);
  const commRadius = Math.min(width, height) * 0.32;

  commIds.forEach((cid, idx) => {
    const angle = idx * angleStep;
    commCenters[cid] = {
      x: centerX + Math.cos(angle) * commRadius,
      y: centerY + Math.sin(angle) * commRadius,
    };
  });

  // Inicializa posições dos nós próximas ao centro da sua comunidade Louvain
  const maxBw = Math.max(...networkData.nodes.map((n) => n.betweenness_centrality), 0.001);
  const nodes: SimNode[] = networkData.nodes.map((n, i) => {
    const cCenter = commCenters[n.community] || { x: centerX, y: centerY };
    const jitterAngle = (i * 137.5 * Math.PI) / 180;
    const jitterDist = 40 + (i % 5) * 18;
    // Tamanho proporcional à Centralidade de Intermediação (Betweenness)
    const bwRatio = n.betweenness_centrality / maxBw;
    const radius = 10 + Math.round(bwRatio * 18);

    return {
      ...n,
      x: cCenter.x + Math.cos(jitterAngle) * jitterDist,
      y: cCenter.y + Math.sin(jitterAngle) * jitterDist,
      vx: 0,
      vy: 0,
      radius,
    };
  });

  const nodeMap = new Map<string, SimNode>();
  nodes.forEach((n) => nodeMap.set(n.id, n));

  // Iterações de layout de forças (Coulomb + Hooke + Cluster)
  const iterations = 80;
  for (let iter = 0; iter < iterations; iter++) {
    const alpha = 1 - iter / iterations;

    // 1. Repulsão entre todos os pares de nós
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const n1 = nodes[i];
        const n2 = nodes[j];
        const dx = n2.x - n1.x;
        const dy = n2.y - n1.y;
        const distSq = dx * dx + dy * dy || 1;
        const dist = Math.sqrt(distSq);
        const minDist = n1.radius + n2.radius + 15;

        if (dist < 260) {
          const force = ((minDist * minDist) / (distSq * 1.2)) * alpha * 0.8;
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          n1.vx -= fx;
          n1.vy -= fy;
          n2.vx += fx;
          n2.vy += fy;
        }
      }
    }

    // 2. Atração por arestas de coautoria
    for (const edge of networkData.edges) {
      const source = nodeMap.get(edge.source);
      const target = nodeMap.get(edge.target);
      if (!source || !target) continue;

      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const targetDist = Math.max(50, 160 - Math.min(edge.weight * 6, 90));
      const force = ((dist - targetDist) / targetDist) * 0.12 * alpha;

      const fx = (dx / dist) * force * 15;
      const fy = (dy / dist) * force * 15;
      source.vx += fx;
      source.vy += fy;
      target.vx -= fx;
      target.vy -= fy;
    }

    // 3. Atração em direção ao centro da sua comunidade Louvain
    for (const node of nodes) {
      const cCenter = commCenters[node.community] || { x: centerX, y: centerY };
      const cDx = cCenter.x - node.x;
      const cDy = cCenter.y - node.y;
      node.vx += cDx * 0.02 * alpha;
      node.vy += cDy * 0.02 * alpha;

      // Gravidade suave em direção ao centro geral
      node.vx += (centerX - node.x) * 0.005 * alpha;
      node.vy += (centerY - node.y) * 0.005 * alpha;

      // Atualizar posições amortecidas
      node.x += node.vx * 0.45;
      node.y += node.vy * 0.45;
      node.vx *= 0.7;
      node.vy *= 0.7;

      // Manter dentro dos limites da tela
      node.x = Math.max(node.radius + 20, Math.min(width - node.radius - 20, node.x));
      node.y = Math.max(node.radius + 20, Math.min(height - node.radius - 20, node.y));
    }
  }

  return nodes;
}

export default function CoauthorshipNetworkGraph({
  onSelectPolitician,
}: CoauthorshipNetworkGraphProps) {
  // Filtros dinâmicos da especificação
  const [tipoProposta, setTipoProposta] = useState<string>("ALL");
  const [minWeight, setMinWeight] = useState<number>(1);
  const [casa, setCasa] = useState<string>("ALL");
  const [limitNodes, setLimitNodes] = useState<number>(60);
  const [searchTerm, setSearchTerm] = useState<string>("");

  // Estado dos dados da API
  const [networkData, setNetworkData] = useState<CoauthorshipNetworkResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadTrigger, setReloadTrigger] = useState<number>(0);

  // Estados de visualização e interatividade
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [selectedCommunityId, setSelectedCommunityId] = useState<number | null>(null);
  const [showMetodologia, setShowMetodologia] = useState<boolean>(false);

  // Zoom e Pan
  const [zoom, setZoom] = useState<number>(1);
  const [pan, setPan] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState<boolean>(false);
  const [panStart, setPanStart] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  // Posições arrastadas pelo usuário
  const [draggedOffsets, setDraggedOffsets] = useState<Record<string, { x: number; y: number }>>({});
  const svgRef = useRef<SVGSVGElement | null>(null);
  const draggingNodeRef = useRef<{ id: string; startX: number; startY: number } | null>(null);

  // Fetch de dados da rede da API real
  useEffect(() => {
    let isMounted = true;
    getCoauthorshipNetwork(tipoProposta, minWeight, casa, limitNodes)
      .then((data) => {
        if (isMounted) {
          setNetworkData(data);
          setError(null);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError("Não foi possível carregar o grafo de coautoria do Congresso.");
          setLoading(false);
          console.error(err);
        }
      });
    return () => {
      isMounted = false;
    };
  }, [tipoProposta, minWeight, casa, limitNodes, reloadTrigger]);

  const handleReload = useCallback(() => {
    setLoading(true);
    setReloadTrigger((prev) => prev + 1);
  }, []);

  // Simulação de nós derivada via useMemo
  const baseSimNodes = useMemo(() => computeSimNodes(networkData), [networkData]);

  const simNodes = useMemo(() => {
    if (Object.keys(draggedOffsets).length === 0) return baseSimNodes;
    return baseSimNodes.map((n) => {
      const offset = draggedOffsets[n.id];
      return offset ? { ...n, x: offset.x, y: offset.y } : n;
    });
  }, [baseSimNodes, draggedOffsets]);

  // Mapa de arestas conectadas para destaque instantâneo
  const connectedNodeIds = useMemo(() => {
    const targetId = hoveredNodeId || selectedNodeId;
    if (!targetId || !networkData) return null;

    const set = new Set<string>();
    set.add(targetId);
    networkData.edges.forEach((e) => {
      if (e.source === targetId) set.add(e.target);
      if (e.target === targetId) set.add(e.source);
    });
    return set;
  }, [hoveredNodeId, selectedNodeId, networkData]);

  // Nó atualmente selecionado
  const selectedNode = useMemo(() => {
    if (!selectedNodeId || !networkData) return null;
    return networkData.nodes.find((n) => n.id === selectedNodeId) || null;
  }, [selectedNodeId, networkData]);

  // Coautores diretos do nó selecionado
  const selectedNodeCoauthors = useMemo(() => {
    if (!selectedNodeId || !networkData) return [];
    const directEdges = networkData.edges.filter(
      (e) => e.source === selectedNodeId || e.target === selectedNodeId
    );
    const map = new Map<string, number>();
    directEdges.forEach((e) => {
      const otherId = e.source === selectedNodeId ? e.target : e.source;
      map.set(otherId, (map.get(otherId) || 0) + e.weight);
    });

    const result = Array.from(map.entries())
      .map(([id, weight]) => {
        const node = networkData.nodes.find((n) => n.id === id);
        return {
          id,
          name: node?.name || "Parlamentar",
          party: node?.party || "S/P",
          uf: node?.uf || "BR",
          weight,
          community: node?.community ?? 1,
        };
      })
      .sort((a, b) => b.weight - a.weight);

    return result;
  }, [selectedNodeId, networkData]);

  // Tratamento de Pan e Drag
  const handleMouseDown = (e: React.MouseEvent<SVGSVGElement>) => {
    if ((e.target as HTMLElement).tagName === "svg") {
      setIsPanning(true);
      setPanStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
    }
  };

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (isPanning) {
      setPan({ x: e.clientX - panStart.x, y: e.clientY - panStart.y });
    } else if (draggingNodeRef.current) {
      const drag = draggingNodeRef.current;
      const svg = svgRef.current;
      if (!svg) return;
      const rect = svg.getBoundingClientRect();
      const mouseX = (e.clientX - rect.left - pan.x) / zoom;
      const mouseY = (e.clientY - rect.top - pan.y) / zoom;

      setDraggedOffsets((prev) => ({
        ...prev,
        [drag.id]: { x: mouseX, y: mouseY },
      }));
    }
  };

  const handleMouseUp = () => {
    setIsPanning(false);
    draggingNodeRef.current = null;
  };

  const startDragNode = (nodeId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    draggingNodeRef.current = { id: nodeId, startX: e.clientX, startY: e.clientY };
  };

  // Cores por comunidade
  const getCommunityColor = (cid: number) => {
    return COMMUNITY_PALETTE[(cid - 1) % COMMUNITY_PALETTE.length] || "#22d3ee";
  };

  // Nós filtrados por busca
  const matchesSearch = (n: CoauthorshipNetworkNode) => {
    if (!searchTerm.trim()) return true;
    const term = searchTerm.toLowerCase();
    return (
      n.name.toLowerCase().includes(term) ||
      n.party.toLowerCase().includes(term) ||
      n.uf.toLowerCase().includes(term)
    );
  };

  return (
    <div className="space-y-4">
      {/* ========================================================================= */}
      {/* 1. CABEÇALHO DO MÓDULO DE REDES & BARRA DE METODOLOGIA                     */}
      {/* ========================================================================= */}
      <div className="bg-gradient-to-r from-slate-900/90 via-slate-950 to-indigo-950/40 border border-indigo-500/30 rounded-2xl p-4 sm:p-5 shadow-xl backdrop-blur-md">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-2xl bg-indigo-500/10 border border-indigo-500/30 text-indigo-400 shadow-inner">
              <Share2 className="w-6 h-6 animate-pulse" aria-hidden="true" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base sm:text-lg font-black text-white flex items-center gap-2">
                  Grafo de Redes & Análise de Coautoria
                </h2>
                <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                  Módulo Científico 2
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Mapeamento das bancadas informais (Algoritmo de Louvain) e pontes de articulação política (Betweenness Centrality).
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setShowMetodologia(!showMetodologia)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-900/90 border border-slate-800 text-xs font-semibold text-indigo-300 hover:text-indigo-200 hover:border-indigo-500/40 transition-colors"
              aria-expanded={showMetodologia}
            >
              <Info className="w-3.5 h-3.5" aria-hidden="true" />
              <span>{showMetodologia ? "Ocultar Metodologia" : "Entenda os Algoritmos"}</span>
            </button>
            <button
              type="button"
              onClick={handleReload}
              disabled={loading}
              className="p-1.5 rounded-xl bg-slate-900 border border-slate-800 text-slate-400 hover:text-white transition-colors"
              title="Recarregar grafo de coautoria"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin text-cyan-400" : ""}`} />
            </button>
          </div>
        </div>

        {/* Modal / Card Retrátil de Metodologia */}
        {showMetodologia && (
          <div className="bg-slate-950/90 border border-indigo-500/30 rounded-2xl p-4 sm:p-5 text-xs text-slate-300 space-y-3 mt-3 animate-in fade-in duration-300 shadow-xl">
            <h3 className="font-bold text-white text-sm flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-indigo-400" aria-hidden="true" />
              Metodologia de Modelagem de Redes Políticas
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-[11px] leading-relaxed">
              <div className="bg-slate-900/70 p-3 rounded-xl border border-slate-800 space-y-1">
                <span className="font-bold text-cyan-300 block flex items-center gap-1.5">
                  <Layers className="w-3.5 h-3.5" />
                  1. Grafo Não-Direcionado Ponderado
                </span>
                <p className="text-slate-400">
                  Os nós representam parlamentares reais. As arestas conectam parlamentares que assinaram proposições conjuntamente.
                  O peso <em>W</em> corresponde ao total de projetos em parceria.
                </p>
              </div>
              <div className="bg-slate-900/70 p-3 rounded-xl border border-slate-800 space-y-1">
                <span className="font-bold text-purple-300 block flex items-center gap-1.5">
                  <Zap className="w-3.5 h-3.5" />
                  2. Comunidades de Louvain
                </span>
                <p className="text-slate-400">
                  Agrupa nós pela densidade de coautoria, expondo <strong>bancadas informais</strong> e frentes transpartidárias que votam e constroem textos juntas, independente do partido oficial.
                </p>
              </div>
              <div className="bg-slate-900/70 p-3 rounded-xl border border-slate-800 space-y-1">
                <span className="font-bold text-amber-300 block flex items-center gap-1.5">
                  <Award className="w-3.5 h-3.5" />
                  3. Betweenness Centrality
                </span>
                <p className="text-slate-400">
                  Mensura parlamentares que funcionam como <strong>pontes estratégicas</strong> entre grupos políticos opostos. Nós maiores representam maior capacidade de articulação e trânsito político.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* 2. BARRA DE CONTROLE E FILTROS DINÂMICOS                                  */}
        {/* ========================================================================= */}
        <div className="mt-3 flex flex-wrap items-center gap-2.5">
          {/* Filtro Dinâmico por Tipo de Proposta */}
          <div className="inline-flex p-1 bg-slate-900 border border-slate-800 rounded-xl text-xs font-semibold flex-wrap gap-1">
            <button
              type="button"
              onClick={() => {
                setLoading(true);
                setTipoProposta("ALL");
              }}
              className={`px-3 py-1 rounded-lg transition-all ${
                tipoProposta === "ALL"
                  ? "bg-indigo-500/25 text-indigo-300 border border-indigo-500/40 shadow-sm"
                  : "text-slate-300 hover:text-white"
              }`}
            >
              Rede Geral
            </button>
            <button
              type="button"
              onClick={() => {
                setLoading(true);
                setTipoProposta("PEC");
              }}
              className={`px-3 py-1 rounded-lg transition-all ${
                tipoProposta === "PEC"
                  ? "bg-amber-500/25 text-amber-300 border border-amber-500/40 shadow-sm"
                  : "text-slate-300 hover:text-white"
              }`}
              title="Rede Ideológica de Propostas de Emenda Constitucional"
            >
              PECs (Ideológica)
            </button>
            <button
              type="button"
              onClick={() => {
                setLoading(true);
                setTipoProposta("PL_PLP");
              }}
              className={`px-3 py-1 rounded-lg transition-all ${
                tipoProposta === "PL_PLP"
                  ? "bg-cyan-500/25 text-cyan-300 border border-cyan-500/40 shadow-sm"
                  : "text-slate-300 hover:text-white"
              }`}
              title="Rede Ordinária de Leis Ordinárias e Complementares"
            >
              PL & PLP (Ordinária)
            </button>
            <button
              type="button"
              onClick={() => {
                setLoading(true);
                setTipoProposta("REQ_INC");
              }}
              className={`px-3 py-1 rounded-lg transition-all ${
                tipoProposta === "REQ_INC"
                  ? "bg-rose-500/25 text-rose-300 border border-rose-500/40 shadow-sm"
                  : "text-slate-300 hover:text-white"
              }`}
              title="Rede Operacional / Burocrática de Requerimentos e Indicações"
            >
              REQ & INC (Operacional)
            </button>
          </div>

          {/* Filtro por Casa Legislativa */}
          <div className="flex items-center gap-1.5 bg-slate-900 border border-slate-800 rounded-xl px-2.5 py-1.5">
            <label htmlFor="network-casa-select" className="text-[11px] font-semibold text-slate-400">
              Casa:
            </label>
            <select
              id="network-casa-select"
              value={casa}
              onChange={(e) => {
                setLoading(true);
                setCasa(e.target.value);
              }}
              className="bg-transparent text-xs font-bold text-slate-200 focus:outline-none cursor-pointer pr-1"
            >
              <option value="ALL" className="bg-slate-900">Congresso (Todas)</option>
              <option value="CAMARA" className="bg-slate-900">Câmara dos Deputados</option>
              <option value="SENADO" className="bg-slate-900">Senado Federal</option>
            </select>
          </div>

          {/* Slider de Peso Mínimo de Coautoria */}
          <div className="flex items-center gap-2 bg-slate-900 border border-slate-800 rounded-xl px-3 py-1.5 text-xs">
            <span className="text-[11px] text-slate-400 font-semibold whitespace-nowrap">
              Força Mínima (W ≥ {minWeight}):
            </span>
            <input
              type="range"
              min="1"
              max="15"
              value={minWeight}
              onChange={(e) => {
                setLoading(true);
                setMinWeight(Number(e.target.value));
              }}
              className="w-20 accent-indigo-400 cursor-pointer"
            />
          </div>

          {/* Limite de Nós */}
          <div className="flex items-center gap-1.5 bg-slate-900 border border-slate-800 rounded-xl px-2.5 py-1.5">
            <label htmlFor="network-limit-select" className="text-[11px] font-semibold text-slate-400">
              Amostra:
            </label>
            <select
              id="network-limit-select"
              value={limitNodes}
              onChange={(e) => {
                setLoading(true);
                setLimitNodes(Number(e.target.value));
              }}
              className="bg-transparent text-xs font-bold text-slate-200 focus:outline-none cursor-pointer pr-1"
            >
              <option value={30} className="bg-slate-900">30 Nós</option>
              <option value={60} className="bg-slate-900">60 Nós</option>
              <option value={100} className="bg-slate-900">100 Nós</option>
              <option value={150} className="bg-slate-900">150 Nós</option>
            </select>
          </div>

          {/* Busca por Parlamentar no Grafo */}
          <div className="flex items-center gap-1.5 bg-slate-900 border border-slate-800 rounded-xl px-2.5 py-1.5 ml-auto">
            <Search className="w-3.5 h-3.5 text-slate-400" />
            <input
              type="text"
              placeholder="Buscar no grafo..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="bg-transparent text-xs text-white placeholder-slate-500 focus:outline-none w-28 sm:w-36"
            />
            {searchTerm && (
              <button
                type="button"
                onClick={() => setSearchTerm("")}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-3 h-3" />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 3. ESTATÍSTICAS DA REDE & LEGENDA DE BANCADAS INFORMAIS (LOUVAIN)           */}
      {/* ========================================================================= */}
      {networkData && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3">
            <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider block">
              Parlamentares Conectados
            </span>
            <span className="text-xl font-black text-white font-mono mt-1 block">
              {networkData.stats.total_nodes}
            </span>
            <span className="text-[10px] text-slate-400">
              Vértices ativos no recorte
            </span>
          </div>

          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3">
            <span className="text-[10px] text-indigo-400 font-bold uppercase tracking-wider block">
              Conexões de Coautoria
            </span>
            <span className="text-xl font-black text-indigo-300 font-mono mt-1 block">
              {networkData.stats.total_edges}
            </span>
            <span className="text-[10px] text-slate-400">
              Arestas com peso ≥ {minWeight}
            </span>
          </div>

          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3">
            <span className="text-[10px] text-purple-400 font-bold uppercase tracking-wider block">
              Bancadas Informais
            </span>
            <span className="text-xl font-black text-purple-300 font-mono mt-1 block">
              {networkData.stats.total_communities}
            </span>
            <span className="text-[10px] text-slate-400">
              Clusters de Louvain detectados
            </span>
          </div>

          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3">
            <span className="text-[10px] text-cyan-400 font-bold uppercase tracking-wider block">
              Densidade da Rede
            </span>
            <span className="text-xl font-black text-cyan-300 font-mono mt-1 block">
              {(networkData.stats.density * 100).toFixed(1)}%
            </span>
            <span className="text-[10px] text-slate-400">
              Nível de conectividade política
            </span>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 4. VISUALIZADOR PRINCIPAL DO GRAFO EM SVG                                  */}
      {/* ========================================================================= */}
      <div className="relative bg-slate-950 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl h-[560px] sm:h-[620px] select-none">
        {/* Controles Flutuantes de Zoom / Pan */}
        <div className="absolute top-3 right-3 z-20 flex flex-col gap-1.5 bg-slate-900/90 border border-slate-800 p-1.5 rounded-xl shadow-lg backdrop-blur-md">
          <button
            type="button"
            onClick={() => setZoom((z) => Math.min(z + 0.2, 2.5))}
            className="p-1.5 text-slate-300 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
            title="Aproximar"
          >
            <ZoomIn className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={() => setZoom((z) => Math.max(z - 0.2, 0.4))}
            className="p-1.5 text-slate-300 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
            title="Afastar"
          >
            <ZoomOut className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={() => {
              setZoom(1);
              setPan({ x: 0, y: 0 });
            }}
            className="p-1.5 text-slate-300 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
            title="Resetar Câmera"
          >
            <Maximize2 className="w-4 h-4" />
          </button>
        </div>

        {/* Legenda de Bancadas Informais Detectadas (Louvain) */}
        {networkData && networkData.communities.length > 0 && (
          <div className="absolute top-3 left-3 z-20 max-w-[280px] bg-slate-900/90 border border-slate-800/90 p-2.5 rounded-xl shadow-lg backdrop-blur-md space-y-1.5 max-h-48 overflow-y-auto">
            <span className="text-[10px] font-bold text-slate-300 uppercase tracking-wider block flex items-center gap-1.5">
              <Zap className="w-3 h-3 text-purple-400" />
              Bancadas Informais (Louvain)
            </span>
            <div className="space-y-1">
              {networkData.communities.map((comm) => {
                const isSelected = selectedCommunityId === comm.community_id;
                return (
                  <button
                    key={comm.community_id}
                    type="button"
                    onClick={() =>
                      setSelectedCommunityId(isSelected ? null : comm.community_id)
                    }
                    className={`w-full flex items-center justify-between text-left px-2 py-1 rounded-lg text-[11px] transition-colors border ${
                      isSelected
                        ? "bg-slate-800 border-slate-600 text-white shadow-sm"
                        : "border-transparent hover:bg-slate-800/60 text-slate-300"
                    }`}
                  >
                    <div className="flex items-center gap-2 truncate">
                      <span
                        className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                        style={{ backgroundColor: comm.color }}
                      />
                      <span className="truncate">{comm.label}</span>
                    </div>
                    <span className="font-mono text-[10px] text-slate-400 ml-1.5 flex-shrink-0">
                      {comm.total_parlamentares}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Estado de Carregamento */}
        {loading && (
          <div className="absolute inset-0 z-30 bg-slate-950/80 flex flex-col items-center justify-center gap-3 backdrop-blur-sm">
            <RefreshCw className="w-8 h-8 text-indigo-400 animate-spin" />
            <span className="text-xs font-bold text-slate-300 font-mono">
              Processando Algoritmo de Louvain & Centralidades...
            </span>
          </div>
        )}

        {/* Estado de Erro */}
        {error && (
          <div className="absolute inset-0 z-30 bg-slate-950/90 flex flex-col items-center justify-center gap-3 p-6 text-center">
            <AlertCircle className="w-8 h-8 text-rose-400" />
            <span className="text-sm font-bold text-slate-200">{error}</span>
            <button
              type="button"
              onClick={handleReload}
              className="px-4 py-1.5 rounded-xl bg-indigo-600 text-white text-xs font-bold hover:bg-indigo-500 transition-colors"
            >
              Tentar Novamente
            </button>
          </div>
        )}

        {/* Grafo SVG Interativo */}
        <svg
          ref={svgRef}
          className="w-full h-full cursor-grab active:cursor-grabbing"
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          role="img"
          aria-label="Grafo interativo de coautoria política"
        >
          <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
            {/* 1. Camada de Arestas (Conexões de Coautoria Ponderadas) */}
            {networkData &&
              networkData.edges.map((edge) => {
                const source = simNodes.find((n) => n.id === edge.source);
                const target = simNodes.find((n) => n.id === edge.target);
                if (!source || !target) return null;

                const isConnected =
                  connectedNodeIds &&
                  (connectedNodeIds.has(edge.source) && connectedNodeIds.has(edge.target));
                const isDimmed =
                  connectedNodeIds && !isConnected;

                const strokeWidth = Math.min(1 + edge.weight * 0.4, 6);
                const strokeOpacity = isConnected ? 0.85 : isDimmed ? 0.08 : 0.25;
                const strokeColor = isConnected ? "#818cf8" : "#475569";

                return (
                  <line
                    key={`${edge.source}-${edge.target}`}
                    x1={source.x}
                    y1={source.y}
                    x2={target.x}
                    y2={target.y}
                    stroke={strokeColor}
                    strokeWidth={strokeWidth}
                    strokeOpacity={strokeOpacity}
                    strokeLinecap="round"
                  />
                );
              })}

            {/* 2. Camada de Nós (Parlamentares) */}
            {simNodes.map((node) => {
              const commColor = getCommunityColor(node.community);
              const isSelected = selectedNodeId === node.id;
              const isHovered = hoveredNodeId === node.id;
              const isConnected = connectedNodeIds ? connectedNodeIds.has(node.id) : true;
              const isCommunityFiltered =
                selectedCommunityId !== null && node.community !== selectedCommunityId;
              const isSearchMatch = matchesSearch(node);

              const opacity = isCommunityFiltered || !isSearchMatch
                ? 0.15
                : !isConnected
                ? 0.25
                : 1;

              return (
                <g
                  key={node.id}
                  transform={`translate(${node.x}, ${node.y})`}
                  className="cursor-pointer transition-transform duration-75"
                  onMouseEnter={() => setHoveredNodeId(node.id)}
                  onMouseLeave={() => setHoveredNodeId(null)}
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedNodeId(isSelected ? null : node.id);
                  }}
                  onMouseDown={(e) => startDragNode(node.id, e)}
                  opacity={opacity}
                >
                  {/* Halo de Destaque / Seleção */}
                  {(isSelected || isHovered) && (
                    <circle
                      r={node.radius + 7}
                      fill="none"
                      stroke={commColor}
                      strokeWidth={3}
                      strokeDasharray="4 2"
                      className="animate-spin"
                      style={{ transformOrigin: "0 0" }}
                    />
                  )}

                  {/* Círculo Principal com Cor de Bancada Informal (Louvain) */}
                  <circle
                    r={node.radius}
                    fill="#0f172a"
                    stroke={commColor}
                    strokeWidth={isSelected || isHovered ? 3.5 : 2}
                    className="transition-all hover:scale-110"
                  />

                  {/* Sigla do Partido no Centro */}
                  <text
                    textAnchor="middle"
                    dy=".35em"
                    fontSize={Math.max(8, node.radius * 0.65)}
                    fontWeight="bold"
                    fill={commColor}
                    className="pointer-events-none select-none font-mono"
                  >
                    {node.party}
                  </text>

                  {/* Nome do Parlamentar (em nós de alta centralidade ou no hover/seleção) */}
                  {(node.betweenness_centrality > 0.05 || isHovered || isSelected || node.degree >= 10) && (
                    <text
                      y={node.radius + 12}
                      textAnchor="middle"
                      fontSize={10}
                      fontWeight="600"
                      fill="#f1f5f9"
                      className="pointer-events-none select-none drop-shadow-md"
                    >
                      {node.name.split(" ").slice(0, 2).join(" ")} ({node.uf})
                    </text>
                  )}
                </g>
              );
            })}
          </g>
        </svg>

        {/* Card Lateral Flutuante com Detalhes do Parlamentar Selecionado */}
        {selectedNode && (
          <div className="absolute bottom-3 right-3 z-30 w-80 bg-slate-900/95 border border-indigo-500/40 rounded-2xl p-4 shadow-2xl backdrop-blur-md animate-in slide-in-from-bottom-3 duration-200">
            <div className="flex items-start justify-between gap-2 pb-2.5 border-b border-slate-800">
              <div className="flex items-center gap-3">
                <div className="relative w-12 h-12 rounded-full overflow-hidden bg-slate-800 border-2 border-indigo-500/50 flex-shrink-0">
                  {selectedNode.photo_url ? (
                    <Image
                      src={selectedNode.photo_url}
                      alt={selectedNode.name}
                      fill
                      className="object-cover"
                      unoptimized
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-xs font-bold text-slate-400">
                      {selectedNode.name.slice(0, 2)}
                    </div>
                  )}
                </div>
                <div>
                  <h3 className="font-bold text-white text-sm leading-tight">
                    {selectedNode.name}
                  </h3>
                  <div className="flex items-center gap-1.5 mt-1">
                    <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-slate-800 text-slate-200">
                      {selectedNode.party} • {selectedNode.uf}
                    </span>
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300">
                      {selectedNode.house === "SENADO" ? "Senado" : "Câmara"}
                    </span>
                  </div>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setSelectedNodeId(null)}
                className="text-slate-400 hover:text-white p-1"
                aria-label="Fechar detalhes"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="py-2.5 space-y-2 text-xs border-b border-slate-800">
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Bancada Informal (Louvain):</span>
                <span
                  className="font-bold px-2 py-0.5 rounded text-[11px]"
                  style={{
                    backgroundColor: `${getCommunityColor(selectedNode.community)}20`,
                    color: getCommunityColor(selectedNode.community),
                  }}
                >
                  Cluster #{selectedNode.community}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Ponte Articuladora (Betweenness):</span>
                <span className="font-mono font-bold text-amber-300">
                  {(selectedNode.betweenness_centrality * 100).toFixed(2)}%
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Grau de Coautoria (Conexões):</span>
                <span className="font-mono font-bold text-white">
                  {selectedNode.degree} parlamentares
                </span>
              </div>
            </div>

            {/* Top Coautores Imediatos */}
            <div className="pt-2.5 space-y-1.5">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                Principais Parceiros de Assinatura:
              </span>
              <div className="space-y-1 max-h-28 overflow-y-auto pr-1">
                {selectedNodeCoauthors.slice(0, 4).map((coa) => (
                  <div
                    key={coa.id}
                    className="flex items-center justify-between text-[11px] bg-slate-950/60 px-2 py-1 rounded-lg border border-slate-800/80"
                  >
                    <span className="truncate text-slate-200">
                      {coa.name} <span className="text-slate-500 font-mono">({coa.party})</span>
                    </span>
                    <span className="font-mono font-bold text-indigo-400 ml-1.5 flex-shrink-0">
                      {coa.weight} {coa.weight === 1 ? "proj" : "projs"}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {onSelectPolitician && (
              <button
                type="button"
                onClick={() => onSelectPolitician(selectedNode.id)}
                className="w-full mt-3 py-1.5 px-3 rounded-xl bg-gradient-to-r from-indigo-600 to-cyan-600 hover:from-indigo-500 hover:to-cyan-500 text-white font-bold text-xs flex items-center justify-center gap-1.5 transition-all shadow-md"
              >
                <span>Ver Dossiê Completo</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        )}
      </div>

      {/* ========================================================================= */}
      {/* 5. TOP ARTICULADORES (BETWEENNESS CENTRALITY - PONTES POLÍTICAS)            */}
      {/* ========================================================================= */}
      {networkData && (
        <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Award className="w-4 h-4 text-amber-400" />
              <h3 className="text-xs sm:text-sm font-bold text-white uppercase tracking-wider">
                Maiores Pontes de Articulação (Centralidade de Intermediação)
              </h3>
            </div>
            <span className="text-[10px] text-slate-400 font-mono">
              Betweenness Centrality
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-2.5">
            {networkData.nodes.slice(0, 5).map((pol, idx) => {
              const isSelected = selectedNodeId === pol.id;
              return (
                <button
                  key={pol.id}
                  type="button"
                  onClick={() => setSelectedNodeId(isSelected ? null : pol.id)}
                  className={`flex flex-col justify-between p-2.5 rounded-xl border text-left transition-all ${
                    isSelected
                      ? "bg-indigo-500/20 border-indigo-500/60 shadow-md ring-1 ring-indigo-500"
                      : "bg-slate-950/80 border-slate-800 hover:border-slate-700"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-mono font-bold text-amber-400">
                      #{idx + 1} Ponte
                    </span>
                    <span className="text-[10px] font-mono font-bold px-1.5 py-0.2 rounded bg-slate-800 text-slate-300">
                      {pol.party}-{pol.uf}
                    </span>
                  </div>
                  <div className="my-1.5">
                    <span className="font-bold text-white text-xs block truncate">
                      {pol.name}
                    </span>
                    <span className="text-[10px] text-slate-400">
                      {pol.degree} conexões ativas
                    </span>
                  </div>
                  <div className="text-[10px] font-mono font-bold text-indigo-300 pt-1 border-t border-slate-800/80">
                    Articulação: {(pol.betweenness_centrality * 100).toFixed(2)}%
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
