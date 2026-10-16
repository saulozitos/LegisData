"""Rotas legislativas: proposições, votações, explorador, ranking de autores, rede de coautoria e calendário.

A regra de negócio vive em `app.services`; aqui ficam só a validação dos parâmetros e a resposta HTTP.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from app.core.database import get_db
from app.models.core import Pessoa
from app.services import autores_ranking_service, calendario_votacoes_service, explorer_service
from app.services import votos_proposicao_service as votos
from app.services.deliberacoes_service import get_deliberacao_detalhe, get_proposicao_deliberacoes
from app.services.legislative_scoring import build_coauthorship_network, get_politician_ialp_metrics
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/propositions", response_model=List[Dict[str, Any]])
def get_propositions_with_voting(
    response: Response,
    limit: int = Query(500, ge=1, le=1000, description="Quantidade máxima de proposições"),
    offset: int = Query(0, ge=0, description="Deslocamento para paginação"),
    db: Session = Depends(get_db),
):
    """
    Retorna a lista de matérias legislativas com placar de votação nominal (Sim, Não, Abstenção),
    autor oficial da matéria e status de aprovação discriminados por Câmara dos Deputados e Senado Federal.
    O total de registros é informado no header X-Total-Count.
    """
    try:
        total, itens = explorer_service.proposicoes_com_votacao(db, limit, offset)
    except SQLAlchemyError as e:
        logger.error("Falha ao consultar proposições no banco: %s", e)
        raise HTTPException(status_code=503, detail="Banco de dados indisponível.")
    if total:
        response.headers["X-Total-Count"] = str(total)
        return itens
    itens = explorer_service.proposicoes_de_arquivos_locais()
    response.headers["X-Total-Count"] = str(len(itens))
    return itens


@router.get("/propositions/{prop_id}/votes")
def get_proposition_nominal_votes(
    prop_id: str,
    house: Optional[str] = None,
    session_id: Optional[str] = None,
    search: Optional[str] = Query(None, max_length=100),
    vote_choice: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Retorna a lista nominal completa dos votos registrados para uma matéria legislativa,
    permitindo filtro por Casa (CAMARA ou SENADO), busca por nome do político e opção de voto (SIM, NAO, ABSTENCAO).
    """
    return votos.votos_da_proposicao(db, prop_id, house, session_id, search, vote_choice)


@router.get("/ranking/authors")
def get_authors_productivity_ranking(
    limit: int = Query(20, ge=1, le=100, description="Quantidade de registros no ranking"),
    partido: Optional[str] = Query(None, max_length=50),
    setor: Optional[str] = Query(None, max_length=100),
    criterio: str = Query(
        "efetividade",
        description="Modo de classificação: 'efetividade' (Score Ponderado), 'lideranca' (Autor Principal), 'coautoria' (Apoio Político) ou 'volume' (Total bruto)",
    ),
    db: Session = Depends(get_db),
):
    """
    Retorna o ranking de produtividade parlamentar. O score é a soma do IALP (metodologia única em param.peso):
    tipo da proposição x papel do autor x andamento da tramitação.
    - Critérios de ordenação: 'efetividade' (Score IALP), 'lideranca' (Autores Principais), 'coautoria' (Apoio Político),
      'volume' (Total Bruto).
    """
    return autores_ranking_service.ranking_autores(db, limit, partido, setor, criterio)


@router.get("/network")
def get_coauthorship_network(
    tipo_proposta: Optional[str] = Query(None, description="Filtro de proposição: 'ALL', 'PEC', 'PL_PLP', 'REQ_INC'"),
    min_weight: int = Query(1, ge=1, le=50, description="Peso mínimo de conexões de coautoria"),
    casa: Optional[str] = Query(None, description="Filtro por Casa: 'CAMARA', 'SENADO', 'ALL'"),
    limit_nodes: int = Query(100, ge=10, le=300, description="Número máximo de nós na rede"),
    db: Session = Depends(get_db),
):
    """
    Retorna o Grafo Não-Direcionado Ponderado de Coautoria:
    - Vértices: Parlamentares com nome, partido, UF, casa, comunidade Louvain e betweenness centrality
    - Arestas: Coautoria legislativa ponderada (peso = número de proposições conjuntas)
    - Algoritmo de Louvain: Detecção de comunidades para mapear bancadas informais
    - Centralidade de Intermediação (Betweenness Centrality): Identificação de pontes de articulação política
    - Filtros dinâmicos: Rede Geral, Rede de PECs, Rede Ordinária (PL/PLP), Rede Burocrática (REQ/INC)
    """
    return build_coauthorship_network(
        db=db,
        tipo_proposta=tipo_proposta,
        min_weight=min_weight,
        casa=casa,
        limit_nodes=limit_nodes,
    )


@router.get("/politicians/{politician_id}/productivity")
def get_politician_productivity(
    politician_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """
    Retorna as métricas consolidadas do Índice de Atividade Legislativa Ponderado (IALP):
    - Score(P) = T * A * S (Tipo * Grau de Autoria * Sucesso Tramitacional)
    - Score de Relevância Consolidado
    - Taxa de Eficácia (% de aprovação como Autor Principal)
    - Índice de Desvio de Foco (Proporção Estrutural vs. Burocrática)
    - Top parceiros de coautoria
    - Proposições detalhadas com detalhamento T, A, S e score
    """
    pessoa = db.query(Pessoa).filter(Pessoa.uid == politician_id).first()
    if not pessoa:
        raise HTTPException(status_code=404, detail="Parlamentar não encontrado.")
    metrics = get_politician_ialp_metrics(politician_id, db)
    return {
        "politician_id": str(politician_id),
        "nome_eleitoral": pessoa.nome_exibicao,
        "foto_url": pessoa.foto_url,
        **metrics,
    }


@router.get("/explorer")
def get_legislative_explorer(
    search: Optional[str] = Query(None, max_length=100),
    setor: Optional[str] = Query(None, max_length=100),
    partido: Optional[str] = Query(None, max_length=50),
    tipo: Optional[str] = None,
    status: Optional[str] = None,
    apenas_votadas: bool = False,
    page: int = Query(1, ge=1, description="Número da página"),
    limit: int = Query(25, ge=1, le=100, description="Quantidade de proposições por página"),
    db: Session = Depends(get_db),
):
    """
    Retorna a lista geral de proposições com filtros, cruzada com Setor/Tema, Autor e Placar Geral (Sim/Não).
    """
    return explorer_service.explorar(db, search, setor, partido, tipo, status, apenas_votadas, page, limit)


@router.get("/propositions/{prop_id}/nominal-votes")
def get_proposition_nominal_votes_split(
    prop_id: str, search: Optional[str] = Query(None, max_length=100), db: Session = Depends(get_db)
):
    """
    Retorna a tabela detalhada de quem votou SIM (A Favor) e quem votou NÃO (Contra),
    com foto, nome, partido e UF de cada parlamentar.
    """
    return votos.votos_nominais_divididos(db, prop_id, search)


@router.get("/calendar")
def get_voting_calendar(
    year: Optional[int] = Query(None, ge=1900, le=2200, description="Ano para filtrar as votações nominais"),
    db: Session = Depends(get_db),
):
    """
    Retorna o Diário do Congresso (Calendário de Votações):
    1. Lista de datas (dias) em que houve registro de sessão de votação no banco.
    2. Estatística global anual: 'Em XXXX, de 365 dias, o Congresso realizou sessões de votação nominal em apenas Y dias'
    3. Detalhes das matérias deliberadas pela Câmara e pelo Senado em cada data, com links oficiais na íntegra.
    Sem o parâmetro `year`, usa o ano mais recente com votações.
    """
    return calendario_votacoes_service.calendario_de_votacoes(db, year)


@router.get("/propositions/{prop_id}/deliberacoes")
@router.get("/proposicoes/{prop_id}/deliberacoes")
def get_proposicao_deliberacoes_endpoint(
    prop_id: str,
    db: Session = Depends(get_db),
):
    """
    Retorna o histórico estruturado de deliberações de uma proposição legislativa (Módulo 3):
    1. DELIBERACAO_COMISSAO: Deliberada em comissões permanentes com ata e parecer do relator.
    2. VOTACAO_SIMBOLICA: Deliberada em plenário por aclamação/acordo de lideranças com orientações partidárias.
    3. VOTACAO_NOMINAL: Deliberada em plenário com painel eletrônico e lista de votos individuais.
    """
    prop = votos.resolver_proposicao(db, prop_id)
    data = get_proposicao_deliberacoes(db, prop.id)
    if not data:
        raise HTTPException(status_code=404, detail="Proposição não encontrada.")
    return data


@router.get("/deliberacoes/{votacao_id}")
def get_deliberacao_detalhe_endpoint(
    votacao_id: str,
    search: Optional[str] = Query(None, max_length=100),
    db: Session = Depends(get_db),
):
    """
    Retorna os detalhes completos de uma deliberação específica:
    - Se tipo_deliberacao = 'NOMINAL', retorna a lista explícita de votos nominais.
    - Se tipo_deliberacao = 'SIMBOLICA', retorna a matriz de orientações partidárias e aviso educativo.
    - Se tipo_deliberacao = 'COMISSAO', retorna comissão, link da ata da reunião e parecer do relator.
    """
    try:
        v_uuid = uuid.UUID(votacao_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="votacao_id inválido.")

    data = get_deliberacao_detalhe(db, v_uuid, search=search)
    if not data:
        raise HTTPException(status_code=404, detail="Deliberação não encontrada.")
    return data
