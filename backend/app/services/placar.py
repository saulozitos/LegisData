"""Placar e sessão principal de uma votação, numa única definição para todas as telas.

Chaves do placar: `sim`, `nao`, `abstencao`, `obstrucao`, `ausente` e `total` (sim + nao + abstencao + obstrucao;
ausentes e Art. 17 não votaram e ficam fora). O resultado oficial publicado pela fonte (`total_*_fonte`) prevalece;
sem ele, vale a contagem dos votos nominais registrados.
"""

from collections import defaultdict
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

from app.models.leg import Votacao, Voto
from sqlalchemy import func
from sqlalchemy.orm import Session

PLACAR_VAZIO: Dict[str, int] = {"sim": 0, "nao": 0, "abstencao": 0, "obstrucao": 0, "ausente": 0, "total": 0}


def placar_de_contagens(contagens: Mapping[str, int]) -> Dict[str, int]:
    """Placar a partir da contagem de votos por opção (`SIM`, `NAO`, `ABSTENCAO`, `OBSTRUCAO`, `AUSENTE`...)."""
    sim, nao = contagens.get("SIM", 0), contagens.get("NAO", 0)
    abst, obs = contagens.get("ABSTENCAO", 0), contagens.get("OBSTRUCAO", 0)
    return {
        "sim": sim,
        "nao": nao,
        "abstencao": abst,
        "obstrucao": obs,
        "ausente": contagens.get("AUSENTE", 0),
        "total": sim + nao + abst + obs,
    }


def placar_da_fonte(votacao: Votacao) -> Optional[Dict[str, int]]:
    """Resultado publicado pela fonte; None quando ela não informou nenhum total."""
    sim, nao = votacao.total_sim_fonte or 0, votacao.total_nao_fonte or 0
    abst, obs = votacao.total_abstencao_fonte or 0, votacao.total_obstrucao_fonte or 0
    if not (sim or nao or abst or obs):
        return None
    return {"sim": sim, "nao": nao, "abstencao": abst, "obstrucao": obs, "ausente": 0, "total": sim + nao + abst + obs}


def placar_da_votacao(votacao: Votacao, contagens: Optional[Mapping[str, int]] = None) -> Dict[str, int]:
    """Placar oficial da votação: totais da fonte e, na falta deles, a contagem dos votos nominais."""
    contado = placar_de_contagens(contagens) if contagens else dict(PLACAR_VAZIO)
    fonte = placar_da_fonte(votacao)
    if fonte is None:
        return contado
    return {**fonte, "ausente": contado["ausente"]}


def contagens_por_votacao(db: Session, *condicoes: Any) -> Dict[int, Dict[str, int]]:
    """Votos por opção de cada votação, numa só consulta (evita N+1)."""
    linhas = (
        db.query(Voto.votacao_id, Voto.opcao_codigo, func.count())
        .join(Votacao, Voto.votacao_id == Votacao.id)
        .filter(*condicoes)
        .group_by(Voto.votacao_id, Voto.opcao_codigo)
        .all()
    )
    agrupado: Dict[int, Dict[str, int]] = defaultdict(dict)
    for votacao_id, opcao, quantidade in linhas:
        agrupado[votacao_id][opcao] = quantidade
    return dict(agrupado)


def placares_das_votacoes(
    votacoes: Iterable[Votacao], contagens: Mapping[int, Mapping[str, int]]
) -> Dict[int, Dict[str, int]]:
    return {v.id: placar_da_votacao(v, contagens.get(v.id)) for v in votacoes}


def sessao_principal(votacoes: Sequence[Votacao], placares: Mapping[int, Mapping[str, int]]) -> Optional[Votacao]:
    """Sessão de maior quórum (desempate: aprovada, depois a mais recente): um destaque com poucos votos não substitui
    a votação de mérito. É a mesma escolha no explorer, na lista de proposições e nos votos nominais."""
    if not votacoes:
        return None
    return max(
        votacoes,
        key=lambda v: (placares.get(v.id, PLACAR_VAZIO).get("total", 0), 1 if v.aprovada else 0, v.data_hora),
    )


def placar_para_tela(placar: Mapping[str, int]) -> Dict[str, int]:
    """Formato das telas de votação: a abstenção já inclui a obstrução (quem participou sem votar sim ou não)."""
    return {
        "SIM": placar["sim"],
        "NAO": placar["nao"],
        "ABSTENCAO": placar["abstencao"] + placar["obstrucao"],
        "TOTAL": placar["total"],
        "OBSTRUCAO": placar["obstrucao"],
        "AUSENTE": placar["ausente"],
    }
