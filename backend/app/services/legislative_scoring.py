"""
Serviço de Pontuação Ponderada da Atividade Legislativa (IALP) e Análise de Redes de Coautoria.

Implementa integralmente a Especificação Técnica de Plataforma Cívica Independente:
1. Mapeamento de Autoria:
   - Autor Principal (Primeiro Signatário): Peso A = 1.0
   - Relator com Parecer Aprovado: Peso A = 0.8
   - Coautor (Demais Signatários): Peso A = 0.2
   - Autor Institucional / Colegiado: Peso A = 0.0 (Isolado de créditos individuais)

2. Matriz de Pesos de Proposição (T):
   - PEC (Emenda Constitucional): 3.0
   - PLP (Lei Complementar): 2.5
   - PL (Lei Ordinária) / MPV (Medida Provisória): 2.0
   - PDL / PR / PRC / PDS (Decretos e Resoluções): 1.0
   - REQ / INC (Requerimentos e Indicações burocráticas): 0.1

3. Multiplicador de Sucesso Tramitacional (S):
   - Protocolado / Em Tramitação: 1.0x
   - Aprovado em Comissão Temática: 1.5x
   - Aprovado em Plenário (Enviado à outra Casa): 2.0x
   - Transformado em Norma Jurídica (Sancionado / Promulgado): 3.0x
   - Arquivado: 0.8x
   - Rejeitado: 0.5x

Fórmula do IALP por proposição:
   Score(P) = T * A * S

Métricas Derivadas:
   - Score de Relevância Consolidado: sum(Score(P))
   - Taxa de Eficácia: (Projetos Avançados ou Sancionados como Autor Principal / Total como Autor Principal) * 100
   - Índice de Desvio de Foco: Comparativo de projetos de alta complexidade (PEC, PLP, PL) vs burocráticos (REQ, INC)

4. Gráfico de Redes (Análise de Coautoria):
   - Grafo Não-Direcionado Ponderado com nós (Parlamentares) e arestas (Coautoria)
   - Detecção de Comunidades via Algoritmo de Louvain (expondo bancadas informais)
   - Centralidade de Intermediação (Betweenness Centrality - pontes de articulação política)
"""

import logging
import uuid
from typing import Any, Dict, Optional, cast

import networkx as nx
from app.models.core import Pessoa
from app.models.enums import StatusTramitacaoEnum, TipoAutoriaEnum, TipoProposicaoEnum
from app.models.leg import Autoria, Proposicao
from app.services.derivados_service import garantir_atualizados
from app.services.ialp_pesos import PesosIALP, carregar_pesos_ialp
from networkx.algorithms.community import louvain_communities
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("legislative_scoring")


# Assinatura coletiva em massa (centenas de signatários) liga todos a todos e esconde as alianças reais: a rede só
# considera proposições com até este número de autores parlamentares.
MAX_AUTORES_POR_PROPOSICAO = 40


def calculate_proposition_score(
    prop_type: str | TipoProposicaoEnum,
    authorship_type: str | TipoAutoriaEnum,
    status: str | StatusTramitacaoEnum,
    pesos: PesosIALP,
    has_approved_session: bool = False,
    is_plenary: bool = False,
) -> float:
    """
    Calcula a pontuação IALP de uma proposição para um parlamentar individual: Score(P) = T * A * S.
    Todos os pesos vêm de `pesos` (param.peso, metodologia IALP); uma votação aprovada eleva a tramitação ao
    patamar de aprovação em plenário ou em comissão quando o status registrado ainda é anterior a ele.
    """
    peso_a = pesos.peso_autoria(authorship_type, prop_type)
    if peso_a <= 0.0:
        return 0.0

    peso_t = pesos.peso_tipo(prop_type)
    status_key = status.value if hasattr(status, "value") else str(status)
    peso_s = pesos.peso_status(status_key)
    if has_approved_session:
        piso = pesos.peso_status("APROVADO_PLENARIO" if is_plenary else "APROVADO_COMISSAO")
        peso_s = max(peso_s, piso)

    return round(peso_t * peso_a * peso_s, 2)


def get_politician_ialp_metrics(politician_id: uuid.UUID, db: Session) -> Dict[str, Any]:
    """
    Calcula o perfil consolidado de produtividade legislativa (IALP) de um parlamentar.
    `politician_id` é o id público (uid) da pessoa. Retorna Score Consolidado, Taxa de Eficácia, Desvio de Foco e
    Proposições Ponderadas; todos os pesos vêm de param.peso.
    """
    pesos = carregar_pesos_ialp(db)
    pessoa_id = db.execute(text("SELECT id FROM core.pessoa WHERE uid = :uid"), {"uid": politician_id}).scalar()
    if pessoa_id is None:
        return get_politician_ialp_metrics_vazio()

    records = (
        db.query(Autoria, Proposicao)
        .join(Proposicao, Autoria.proposicao_id == Proposicao.id)
        .filter(Autoria.pessoa_id == pessoa_id, Autoria.tipo_codigo != "INSTITUCIONAL")
        .all()
    )
    aprovada_em_votacao = {
        r[0]
        for r in db.execute(
            text(
                "SELECT DISTINCT proposicao_id FROM leg.votacao "
                "WHERE aprovada AND tipo_deliberacao IN ('NOMINAL', 'SECRETA') AND proposicao_id = ANY(:ids)"
            ),
            {"ids": [p.id for _, p in records]},
        )
    }

    total_props = len(records)
    score_consolidado = 0.0
    autor_principal_count = 0
    relator_count = 0
    coautor_count = 0

    avancados_autor_principal = 0
    estruturais_count = 0  # PEC, PLP, PL
    burocraticas_count = 0  # REQ, INC

    proposicoes_detalhadas = []

    for pa, prop in records:
        tipo_str = prop.tipo_codigo
        aut_str = pa.tipo_codigo
        status_str = prop.status_codigo

        # Checar se houve votação aprovada
        has_approved_vote = prop.id in aprovada_em_votacao

        score_p = calculate_proposition_score(
            prop_type=tipo_str,
            authorship_type=aut_str,
            status=status_str,
            pesos=pesos,
            has_approved_session=has_approved_vote,
        )
        score_consolidado += score_p

        # Contagem por papel
        if aut_str == "AUTOR_PRINCIPAL":
            autor_principal_count += 1
            if (
                status_str
                in (
                    "APROVADA_E_SANCIONADA",
                    "APROVADA_E_PROMULGADA",
                    "APROVADO_PLENARIO",
                    "APROVADO_COMISSAO",
                )
                or has_approved_vote
            ):
                avancados_autor_principal += 1
        elif aut_str == "RELATOR":
            relator_count += 1
        else:
            coautor_count += 1

        # Classificação Estrutural vs Burocrática (Desvio de Foco)
        if tipo_str in ("PEC", "PLP", "PL", "MPV") or prop.reforma_estrutural:
            estruturais_count += 1
        elif tipo_str in ("REQ", "INC", "RIC", "RCP", "RQC"):
            burocraticas_count += 1

        proposicoes_detalhadas.append(
            {
                "id": str(prop.uid),
                "tipo": tipo_str,
                "numero": prop.numero,
                "ano": prop.ano,
                "ementa": prop.ementa,
                "status": status_str,
                "tipo_autoria": aut_str,
                "peso_tipo": pesos.peso_tipo(tipo_str),
                "peso_autoria": pesos.peso_autoria(aut_str, tipo_str),
                "multiplicador_tramitacao": max(
                    pesos.peso_status(status_str),
                    pesos.peso_status("APROVADO_COMISSAO") if has_approved_vote else 0.0,
                ),
                "score_ialp": score_p,
                "is_reforma_estrutural": prop.reforma_estrutural,
            }
        )

    # Taxa de Eficácia (% de projetos como Autor Principal que avançaram)
    taxa_eficacia = (
        round((avancados_autor_principal / autor_principal_count) * 100, 1) if autor_principal_count > 0 else 0.0
    )

    # Índice de Desvio de Foco
    total_classificadas = estruturais_count + burocraticas_count
    proporcao_estrutural_pct = (
        round((estruturais_count / total_classificadas) * 100, 1)
        if total_classificadas > 0
        else 100.0 if total_props > 0 else 0.0
    )

    # Top coautores do parlamentar
    top_coaut_rows = db.execute(
        text(
            """
            SELECT b.pessoa_id, count(DISTINCT a.proposicao_id) AS projetos_compartilhados
            FROM leg.autoria a
            JOIN leg.autoria b ON b.proposicao_id = a.proposicao_id AND b.pessoa_id <> a.pessoa_id
            WHERE a.pessoa_id = :pid AND b.pessoa_id IS NOT NULL AND b.tipo_codigo <> 'INSTITUCIONAL'
              AND a.tipo_codigo <> 'INSTITUCIONAL'
            GROUP BY b.pessoa_id
            ORDER BY projetos_compartilhados DESC, b.pessoa_id
            LIMIT 10
            """
        ),
        {"pid": pessoa_id},
    ).fetchall()
    top_coautores = []
    if top_coaut_rows:
        pessoas = {p.id: p for p in db.query(Pessoa).filter(Pessoa.id.in_([r[0] for r in top_coaut_rows])).all()}
        for cid, count in top_coaut_rows:
            p = pessoas.get(cid)
            if p:
                top_coautores.append(
                    {
                        "id": str(p.uid),
                        "nome_eleitoral": p.nome_exibicao,
                        "foto_url": p.foto_url,
                        "projetos_compartilhados": int(cast(Any, count)),
                    }
                )

    # Ordenar proposições detalhadas pelo score decrescente
    proposicoes_detalhadas.sort(key=lambda x: (x["score_ialp"], x["ano"]), reverse=True)

    return {
        "score_ialp_total": round(score_consolidado, 2),
        "total_proposicoes": total_props,
        "taxa_eficacia_pct": taxa_eficacia,
        "avancados_autor_principal": avancados_autor_principal,
        "desvio_foco": {
            "estruturais": estruturais_count,
            "burocraticas": burocraticas_count,
            "proporcao_estrutural_pct": proporcao_estrutural_pct,
            "diagnostico": (
                "Foco Estrutural Predominante"
                if proporcao_estrutural_pct >= 70
                else (
                    "Equilíbrio Estrutural / Burocrático"
                    if proporcao_estrutural_pct >= 40
                    else "Predominância de Matérias Burocráticas"
                )
            ),
        },
        "distribuicao_autoria": {
            "autor_principal": autor_principal_count,
            "relator": relator_count,
            "coautor": coautor_count,
        },
        "top_coautores": top_coautores,
        "proposicoes": proposicoes_detalhadas[:50],
    }


def get_politician_ialp_metrics_vazio() -> Dict[str, Any]:
    return {
        "score_ialp_total": 0.0,
        "total_proposicoes": 0,
        "taxa_eficacia_pct": 0.0,
        "avancados_autor_principal": 0,
        "desvio_foco": {
            "estruturais": 0,
            "burocraticas": 0,
            "proporcao_estrutural_pct": 0.0,
            "diagnostico": "Predominância de Matérias Burocráticas",
        },
        "distribuicao_autoria": {"autor_principal": 0, "relator": 0, "coautor": 0},
        "top_coautores": [],
        "proposicoes": [],
    }


def build_coauthorship_network(
    db: Session,
    tipo_proposta: Optional[str] = None,
    min_weight: int = 1,
    casa: Optional[str] = None,
    limit_nodes: int = 100,
    ano_inicio: Optional[int] = None,
    ano_fim: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Constrói o Grafo Não-Direcionado Ponderado de Coautoria:
    - Vértices: Parlamentares (com nome, partido, UF, casa, comunidade Louvain e betweenness)
    - Arestas: Coautoria legislativa ponderada (número de proposições conjuntas)
    - Algoritmo de Louvain: Detecção de bancadas informais / comunidades
    - Betweenness Centrality: Identificação de pontes políticas
    Proposições com mais de MAX_AUTORES_POR_PROPOSICAO autores ficam fora (assinaturas em massa).
    Sem `ano_inicio`/`ano_fim` considera toda a base; o intervalo limita as proposições pelo ano de apresentação.
    """
    clean_tipo = (tipo_proposta or "ALL").upper().strip()
    clean_casa = (casa or "ALL").upper().strip()

    params: Dict[str, Any] = {
        "min_weight": max(1, min_weight),
        "tipo_filter": clean_tipo if clean_tipo in ("PEC", "PL_PLP", "REQ_INC") else None,
        "casa_filter": clean_casa if clean_casa in ("CAMARA", "SENADO") else None,
        "ano_inicio": ano_inicio,
        "ano_fim": ano_fim,
    }

    params["max_autores"] = MAX_AUTORES_POR_PROPOSICAO
    garantir_atualizados(db)  # a rede lê o derivado pré-calculado dos pares de coautoria
    query = text(
        """
        SELECT pessoa_a AS pol_x, pessoa_b AS pol_y, COUNT(*) AS peso
        FROM leg.mv_coautoria_par
        WHERE n_autores <= :max_autores
          AND (CAST(:ano_inicio AS int) IS NULL OR ano >= :ano_inicio)
          AND (CAST(:ano_fim AS int) IS NULL OR ano <= :ano_fim)
          AND (
              CAST(:tipo_filter AS text) IS NULL
              OR (:tipo_filter = 'PEC' AND tipo_codigo = 'PEC')
              OR (:tipo_filter = 'PL_PLP' AND tipo_codigo IN ('PL', 'PLP', 'MPV'))
              OR (:tipo_filter = 'REQ_INC' AND tipo_codigo IN ('REQ', 'INC'))
          )
          AND (
              CAST(:casa_filter AS text) IS NULL
              OR (:casa_filter = 'CAMARA' AND da_camara)
              OR (:casa_filter = 'SENADO' AND do_senado)
          )
        GROUP BY pessoa_a, pessoa_b
        HAVING COUNT(*) >= :min_weight
        ORDER BY peso DESC
        """
    )

    edge_rows = db.execute(query, params).fetchall()

    if not edge_rows:
        return {
            "nodes": [],
            "edges": [],
            "communities": [],
            "stats": {
                "total_nodes": 0,
                "total_edges": 0,
                "total_communities": 0,
                "density": 0.0,
                "tipo_filtro": clean_tipo,
                "top_articulators": [],
            },
        }

    # Monta Grafo NetworkX (nós = id interno da pessoa)
    G = nx.Graph()
    for rx, ry, rw in edge_rows:
        G.add_edge(int(cast(Any, rx)), int(cast(Any, ry)), weight=int(cast(Any, rw)))

    # Limita aos nós de maior grau caso exceda limit_nodes
    if G.number_of_nodes() > limit_nodes:
        degrees = sorted(G.degree(weight="weight"), key=lambda x: x[1], reverse=True)
        top_node_ids = set(n for n, _ in degrees[:limit_nodes])
        G = G.subgraph(top_node_ids).copy()

    # Algoritmo de Louvain para Detecção de Comunidades
    louvain_comm_list = louvain_communities(G, weight="weight", seed=42)
    node_community_map: Dict[int, int] = {}
    for c_idx, comm in enumerate(louvain_comm_list, start=1):
        for nid in comm:
            node_community_map[nid] = c_idx

    # Centralidade de Intermediação (Betweenness Centrality)
    k_samples = min(50, G.number_of_nodes()) if G.number_of_nodes() > 50 else None
    betweenness_map = nx.betweenness_centrality(G, weight="weight", k=k_samples, seed=42)

    # Metadados dos parlamentares da rede: nome, foto, partido vigente (linhagem), UF e casa do mandato mais recente
    meta = {
        r["id"]: r
        for r in db.execute(
            text(
                """
                SELECT pe.id, pe.uid, pe.nome_exibicao, fm.url_origem AS foto, pe.uf_nascimento,
                       coalesce(
                           (SELECT cp.canonico_sigla FROM core.mandato m
                              JOIN core.vw_partido_canonico cp ON cp.id = m.partido_id
                             WHERE m.pessoa_id = pe.id ORDER BY m.inicio DESC LIMIT 1),
                           (SELECT cp.canonico_sigla FROM core.filiacao f
                              JOIN core.vw_partido_canonico cp ON cp.id = f.partido_id
                             WHERE f.pessoa_id = pe.id AND upper_inf(f.periodo) LIMIT 1)) AS partido,
                       mand.uf, mand.cargo
                FROM core.pessoa pe
                LEFT JOIN core.midia fm ON fm.id = pe.foto_midia_id
                LEFT JOIN LATERAL (
                    SELECT coalesce(ci.uf, 'BR') AS uf, c.codigo AS cargo
                    FROM core.mandato m JOIN ref.cargo c ON c.id = m.cargo_id
                    JOIN ref.circunscricao ci ON ci.id = m.circunscricao_id
                    WHERE m.pessoa_id = pe.id AND m.condicao <> 'NOMEADO' ORDER BY m.inicio DESC LIMIT 1
                ) mand ON true
                WHERE pe.id = ANY(:ids)
                """
            ),
            {"ids": list(G.nodes())},
        ).mappings()
    }

    # Monta lista de Nós formatados
    nodes_payload = []
    community_party_counts: Dict[int, Dict[str, int]] = {}

    for nid in G.nodes():
        info = meta.get(nid)
        name = info["nome_exibicao"] if info else "Parlamentar"
        photo = info["foto"] if info else None
        uf = (info["uf"] or info["uf_nascimento"] or "DF") if info else "DF"
        house = "SENADO" if info and info["cargo"] == "SENADOR" else "CAMARA"
        party_sigla = (info["partido"] if info else None) or "S/P"

        comm_id = node_community_map.get(nid, 1)
        community_party_counts.setdefault(comm_id, {}).setdefault(party_sigla, 0)
        community_party_counts[comm_id][party_sigla] += 1

        bw_score = round(float(betweenness_map.get(nid, 0.0)), 4)
        degree_val = int(G.degree[nid])

        nodes_payload.append(
            {
                "id": str(info["uid"]) if info else str(nid),
                "name": name,
                "party": party_sigla,
                "uf": uf,
                "house": house,
                "photo_url": photo,
                "community": comm_id,
                "betweenness_centrality": bw_score,
                "degree": degree_val,
            }
        )

    # Ordenar nós pela centralidade de intermediação
    nodes_payload.sort(key=lambda x: (x["betweenness_centrality"], x["degree"]), reverse=True)

    # Monta lista de Arestas formatadas
    uid_by_id = {nid: (str(meta[nid]["uid"]) if nid in meta else str(nid)) for nid in G.nodes()}
    edges_payload = []
    for u, v, data in G.edges(data=True):
        edges_payload.append(
            {
                "source": uid_by_id[u],
                "target": uid_by_id[v],
                "weight": int(data.get("weight", 1)),
            }
        )

    # Metadados das Comunidades Detectadas (Bancadas Informais)
    communities_payload = []
    comm_colors = ["#22d3ee", "#a855f7", "#34d399", "#f59e0b", "#ec4899", "#6366f1", "#14b8a6"]
    for c_idx in sorted(community_party_counts.keys()):
        party_counts = community_party_counts[c_idx]
        sorted_parties = sorted(party_counts.items(), key=lambda x: x[1], reverse=True)
        top_parties_str = ", ".join(f"{p} ({c})" for p, c in sorted_parties[:3])
        total_in_comm = sum(party_counts.values())
        communities_payload.append(
            {
                "community_id": c_idx,
                "total_parlamentares": total_in_comm,
                "partidos_predominantes": top_parties_str,
                "color": comm_colors[(c_idx - 1) % len(comm_colors)],
                "label": f"Bancada Informal {c_idx} ({sorted_parties[0][0] if sorted_parties else 'Mista'})",
            }
        )

    density = round(float(nx.density(G)), 4)

    return {
        "nodes": nodes_payload,
        "edges": edges_payload,
        "communities": communities_payload,
        "stats": {
            "total_nodes": G.number_of_nodes(),
            "total_edges": G.number_of_edges(),
            "total_communities": len(louvain_comm_list),
            "density": density,
            "tipo_filtro": clean_tipo,
            "top_articulators": [n["name"] for n in nodes_payload[:5]],
        },
    }
