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
from typing import Any, Dict, List, Optional, Set, Tuple, cast

import networkx as nx
from app.models.legislative import (
    Proposition,
    PropositionAuthor,
    StatusTramitacaoEnum,
    TipoAutoriaEnum,
    TipoProposicaoEnum,
)
from app.models.politician import Mandate, PartyAffiliation, PoliticalParty, Politician
from networkx.algorithms.community import louvain_communities
from sqlalchemy import func, text
from sqlalchemy.orm import Session

logger = logging.getLogger("legislative_scoring")

# ─── MATRIZ DE PESOS CIENTÍFICA (ESPECIFICAÇÃO TÉCNICA) ──────────────────────

PESO_AUTORIA: Dict[str, float] = {
    "AUTOR_PRINCIPAL": 1.0,
    "RELATOR": 0.8,
    "COAUTOR": 0.2,
    "INSTITUCIONAL": 0.0,
}

PESO_COMPLEXIDADE = PESO_TIPO = {
    "PEC": 3.0,
    "PLP": 2.5,
    "PL": 2.0,
    "MPV": 2.0,
    "PDL": 1.0,
    "PR": 1.0,
    "PRC": 1.0,
    "PDS": 1.0,
    "DECRETO_PRES": 1.0,
    "LEI_DELEGADA": 1.0,
    "REQ": 0.1,
    "INC": 0.1,
    "REQUERIMENTO": 0.1,
    "INDICACAO": 0.1,
}

MULTIPLICADOR_TRAMITACAO: Dict[str, float] = {
    "APROVADA_E_SANCIONADA": 3.0,
    "APROVADA_E_PROMULGADA": 3.0,
    "SANCIONADO": 3.0,
    "APROVADO_PLENARIO": 2.0,
    "APROVADO_COMISSAO": 1.5,
    "EM_TRAMITACAO": 1.0,
    "VETADA_PARCIAL": 1.5,
    "VETADA_TOTAL": 1.0,
    "ARQUIVADA": 0.8,
    "REJEITADA": 0.5,
}

INSTITUTIONAL_KEYWORDS = frozenset(
    [
        "comissao",
        "camara dos deputados",
        "senado federal",
        "mesa diretora",
        "poder executivo",
        "tribunal",
        "conselho",
        "bancada",
        "procuradoria",
        "defensoria",
    ]
)


def calculate_proposition_score(
    prop_type: str | TipoProposicaoEnum,
    authorship_type: str | TipoAutoriaEnum,
    status: str | StatusTramitacaoEnum,
    has_approved_session: bool = False,
    is_plenary: bool = False,
) -> float:
    """
    Calcula a pontuação IALP de uma proposição para um parlamentar individual.
    Score(P) = T * A * S
    """
    aut_key = authorship_type.value if hasattr(authorship_type, "value") else str(authorship_type)
    peso_a = PESO_AUTORIA.get(aut_key, 0.2)
    if peso_a <= 0.0:
        return 0.0

    tipo_key = prop_type.value if hasattr(prop_type, "value") else str(prop_type)
    peso_t = PESO_TIPO.get(tipo_key, 1.0)

    status_key = status.value if hasattr(status, "value") else str(status)

    if status_key in (
        "APROVADA_E_SANCIONADA",
        "APROVADA_E_PROMULGADA",
        "SANCIONADO",
    ):
        peso_s = 3.0
    elif status_key == "APROVADO_PLENARIO" or (has_approved_session and is_plenary):
        peso_s = 2.0
    elif status_key == "APROVADO_COMISSAO" or has_approved_session:
        peso_s = 1.5
    else:
        peso_s = MULTIPLICADOR_TRAMITACAO.get(status_key, 1.0)

    return round(peso_t * peso_a * peso_s, 2)


def get_politician_ialp_metrics(politician_id: uuid.UUID, db: Session) -> Dict[str, Any]:
    """
    Calcula o perfil consolidado de produtividade legislativa (IALP) de um parlamentar.
    Retorna Score Consolidado, Taxa de Eficácia, Desvio de Foco e Proposições Ponderadas.
    """
    records = (
        db.query(PropositionAuthor, Proposition)
        .join(Proposition, PropositionAuthor.proposition_id == Proposition.id)
        .filter(
            PropositionAuthor.politician_id == politician_id,
            PropositionAuthor.authorship_type != TipoAutoriaEnum.INSTITUCIONAL,
        )
        .all()
    )

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
        tipo_str = (
            prop.proposition_type.value if hasattr(prop.proposition_type, "value") else str(prop.proposition_type)
        )
        aut_str = pa.authorship_type.value if hasattr(pa.authorship_type, "value") else str(pa.authorship_type)
        status_str = prop.status.value if hasattr(prop.status, "value") else str(prop.status)

        # Checar se houve votação aprovada
        has_approved_vote = any(v.is_approved for v in (prop.voting_sessions or []))

        score_p = calculate_proposition_score(
            prop_type=tipo_str,
            authorship_type=aut_str,
            status=status_str,
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
                    "SANCIONADO",
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
        if tipo_str in ("PEC", "PLP", "PL", "MPV") or prop.is_structural_reform:
            estruturais_count += 1
        elif tipo_str in ("REQ", "INC", "REQUERIMENTO", "INDICACAO"):
            burocraticas_count += 1

        proposicoes_detalhadas.append(
            {
                "id": str(prop.id),
                "tipo": tipo_str,
                "numero": prop.number,
                "ano": prop.year,
                "ementa": prop.summary,
                "status": status_str,
                "tipo_autoria": aut_str,
                "peso_tipo": PESO_TIPO.get(tipo_str, 1.0),
                "peso_autoria": PESO_AUTORIA.get(aut_str, 0.2),
                "multiplicador_tramitacao": (
                    3.0
                    if status_str in ("APROVADA_E_SANCIONADA", "APROVADA_E_PROMULGADA")
                    else (1.5 if has_approved_vote else 1.0)
                ),
                "score_ialp": score_p,
                "is_reforma_estrutural": prop.is_structural_reform,
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
    coautores_query = text(
        """
        SELECT
            b."politicoId" AS coautor_id,
            COUNT(DISTINCT a."proposicaoId") AS projetos_compartilhados
        FROM proposicoes_autores a
        JOIN proposicoes_autores b ON a."proposicaoId" = b."proposicaoId"
        WHERE a."politicoId" = :pid
          AND b."politicoId" != :pid
          AND b."politicoId" IS NOT NULL
          AND b."tipoAutoria" != 'INSTITUCIONAL'
        GROUP BY b."politicoId"
        ORDER BY projetos_compartilhados DESC
        LIMIT 10;
    """
    )
    pid_param = str(politician_id)
    top_coaut_rows = db.execute(coautores_query, {"pid": pid_param}).fetchall()
    top_coautores = []
    if top_coaut_rows:
        coaut_ids = [uuid.UUID(str(r[0])) if isinstance(r[0], str) else r[0] for r in top_coaut_rows if r[0]]
        pols_map = {p.id: p for p in db.query(Politician).filter(Politician.id.in_(coaut_ids)).all()}
        for cid, count in top_coaut_rows:
            p = pols_map.get(cid)
            if p:
                top_coautores.append(
                    {
                        "id": str(p.id),
                        "nome_eleitoral": p.electoral_name,
                        "foto_url": p.photo_url,
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


def build_coauthorship_network(
    db: Session,
    tipo_proposta: Optional[str] = None,
    min_weight: int = 1,
    casa: Optional[str] = None,
    limit_nodes: int = 100,
) -> Dict[str, Any]:
    """
    Constrói o Grafo Não-Direcionado Ponderado de Coautoria:
    - Vértices: Parlamentares (com nome, partido, UF, casa, comunidade Louvain e betweenness)
    - Arestas: Coautoria legislativa ponderada (número de proposições conjuntas)
    - Algoritmo de Louvain: Detecção de bancadas informais / comunidades
    - Betweenness Centrality: Identificação de pontes políticas
    """
    clean_tipo = (tipo_proposta or "ALL").upper().strip()
    clean_casa = (casa or "ALL").upper().strip()

    params: Dict[str, Any] = {
        "min_weight": max(1, min_weight),
        "tipo_filter": clean_tipo if clean_tipo in ("PEC", "PL_PLP", "REQ_INC") else None,
        "casa_filter": clean_casa if clean_casa in ("CAMARA", "SENADO") else None,
    }

    query = text(
        """
        SELECT
            a."politicoId" AS pol_x,
            b."politicoId" AS pol_y,
            COUNT(DISTINCT a."proposicaoId") AS peso
        FROM proposicoes_autores a
        JOIN proposicoes_autores b ON a."proposicaoId" = b."proposicaoId"
        JOIN proposicoes p ON a."proposicaoId" = p.id
        WHERE a."politicoId" IS NOT NULL
          AND b."politicoId" IS NOT NULL
          AND a."politicoId" < b."politicoId"
          AND a."tipoAutoria" != 'INSTITUCIONAL'
          AND b."tipoAutoria" != 'INSTITUCIONAL'
          AND (
              :tipo_filter IS NULL
              OR (:tipo_filter = 'PEC' AND p.tipo = 'PEC')
              OR (:tipo_filter = 'PL_PLP' AND p.tipo IN ('PL', 'PLP', 'MPV'))
              OR (:tipo_filter = 'REQ_INC' AND p.tipo IN ('REQ', 'INC'))
          )
          AND (
              :casa_filter IS NULL
              OR (:casa_filter = 'CAMARA' AND p."idExternoCamara" IS NOT NULL)
              OR (:casa_filter = 'SENADO' AND p."idExternoSenado" IS NOT NULL)
          )
        GROUP BY a."politicoId", b."politicoId"
        HAVING COUNT(DISTINCT a."proposicaoId") >= :min_weight
        ORDER BY peso DESC;
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

    # Monta Grafo NetworkX
    G = nx.Graph()
    for rx, ry, rw in edge_rows:
        G.add_edge(str(rx), str(ry), weight=int(cast(Any, rw)))

    # Limita aos nós de maior grau caso exceda limit_nodes
    if G.number_of_nodes() > limit_nodes:
        degrees = sorted(G.degree(weight="weight"), key=lambda x: x[1], reverse=True)
        top_node_ids = set(n for n, _ in degrees[:limit_nodes])
        G = G.subgraph(top_node_ids).copy()

    # Algoritmo de Louvain para Detecção de Comunidades
    louvain_comm_list = louvain_communities(G, weight="weight", seed=42)
    node_community_map: Dict[str, int] = {}
    for c_idx, comm in enumerate(louvain_comm_list, start=1):
        for nid in comm:
            node_community_map[nid] = c_idx

    # Centralidade de Intermediação (Betweenness Centrality)
    k_samples = min(50, G.number_of_nodes()) if G.number_of_nodes() > 50 else None
    betweenness_map = nx.betweenness_centrality(G, weight="weight", k=k_samples, seed=42)

    # Obter metadados dos parlamentares da rede
    pol_uuids = [uuid.UUID(nid) for nid in G.nodes()]
    politicians = db.query(Politician).filter(Politician.id.in_(pol_uuids)).all()
    pol_obj_map = {str(p.id): p for p in politicians}

    # Buscar filiação partidária e mandato atual dos nós
    mandates = (
        db.query(Mandate, PoliticalParty)
        .outerjoin(PoliticalParty, Mandate.party_id == PoliticalParty.id)
        .filter(Mandate.politician_id.in_(pol_uuids))
        .all()
    )
    mandate_map: Dict[str, Tuple[Mandate, Optional[PoliticalParty]]] = {}
    for m, party in mandates:
        mandate_map[str(m.politician_id)] = (m, party)

    affiliations = (
        db.query(PartyAffiliation, PoliticalParty)
        .join(PoliticalParty, PartyAffiliation.party_id == PoliticalParty.id)
        .filter(PartyAffiliation.politician_id.in_(pol_uuids), PartyAffiliation.is_current.is_(True))
        .all()
    )
    party_aff_map: Dict[str, str] = {str(aff.politician_id): p.acronym for aff, p in affiliations}

    # Monta lista de Nós formatados
    nodes_payload = []
    community_party_counts: Dict[int, Dict[str, int]] = {}

    for nid in G.nodes():
        pol = pol_obj_map.get(nid)
        name = pol.electoral_name if pol else "Parlamentar"
        photo = pol.photo_url if pol else None

        mandate_info = mandate_map.get(nid)
        uf = mandate_info[0].jurisdiction_state if mandate_info else (pol.birthplace_state if pol else "DF")
        house = "SENADO" if mandate_info and "SENADOR" in str(mandate_info[0].office) else "CAMARA"
        party_sigla = (
            (mandate_info[1].acronym if mandate_info and mandate_info[1] else None) or party_aff_map.get(nid) or "S/P"
        )

        comm_id = node_community_map.get(nid, 1)
        community_party_counts.setdefault(comm_id, {}).setdefault(party_sigla, 0)
        community_party_counts[comm_id][party_sigla] += 1

        bw_score = round(float(betweenness_map.get(nid, 0.0)), 4)
        degree_val = int(G.degree[nid])

        nodes_payload.append(
            {
                "id": nid,
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
    edges_payload = []
    for u, v, data in G.edges(data=True):
        edges_payload.append(
            {
                "source": u,
                "target": v,
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


def sync_proposition_authors(db: Session, force: bool = False) -> int:
    """
    Sincroniza a tabela relacional proposicoes_autores a partir dos campos autorNome
    e autorPoliticoId das proposições. Executado idempotentemente.
    """
    from etl.utils.names import NON_PERSON_AUTHORS, normalize_name_tokens

    existing_count = db.query(func.count(PropositionAuthor.id)).scalar() or 0
    if existing_count > 0 and not force:
        return int(existing_count)

    politicos = db.query(Politician).all()
    pol_name_map: Dict[str, Set[uuid.UUID]] = {}
    for p in politicos:
        for name in (p.electoral_name, p.civil_name):
            norm = normalize_name_tokens(name)
            if norm:
                pol_name_map.setdefault(norm, set()).add(p.id)

    unique_pols: Dict[str, uuid.UUID] = {
        name: next(iter(pids)) for name, pids in pol_name_map.items() if len(pids) == 1
    }

    props = db.query(Proposition).all()
    records_to_insert: List[PropositionAuthor] = []

    for prop in props:
        autor_raw = (prop.author_name or "").strip()
        if not autor_raw:
            if prop.author_politician_id:
                records_to_insert.append(
                    PropositionAuthor(
                        proposition_id=prop.id,
                        politician_id=prop.author_politician_id,
                        author_name=prop.author_name or "Autor Desconhecido",
                        authorship_type=TipoAutoriaEnum.AUTOR_PRINCIPAL,
                        order=1,
                    )
                )
            continue

        parts = [p.strip() for p in autor_raw.split(",") if p.strip()]
        if not parts:
            continue

        first = parts[0]
        first_norm = normalize_name_tokens(first)
        is_inst = (
            first_norm in NON_PERSON_AUTHORS
            or any(kw in first_norm for kw in INSTITUTIONAL_KEYWORDS)
            or prop.is_executive_initiative
        )

        if is_inst:
            records_to_insert.append(
                PropositionAuthor(
                    proposition_id=prop.id,
                    politician_id=None,
                    author_name=first,
                    authorship_type=TipoAutoriaEnum.INSTITUCIONAL,
                    order=1,
                )
            )
        else:
            pid = prop.author_politician_id or unique_pols.get(first_norm)
            records_to_insert.append(
                PropositionAuthor(
                    proposition_id=prop.id,
                    politician_id=pid,
                    author_name=first,
                    authorship_type=TipoAutoriaEnum.AUTOR_PRINCIPAL,
                    order=1,
                )
            )

        # Coautores (do 2º signatário em diante)
        for idx, co in enumerate(parts[1:], start=2):
            co_norm = normalize_name_tokens(co)
            co_pid = unique_pols.get(co_norm)
            records_to_insert.append(
                PropositionAuthor(
                    proposition_id=prop.id,
                    politician_id=co_pid,
                    author_name=co,
                    authorship_type=TipoAutoriaEnum.COAUTOR,
                    order=idx,
                )
            )

    if records_to_insert:
        db.bulk_save_objects(records_to_insert)
        db.commit()

    return len(records_to_insert)
