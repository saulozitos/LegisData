"""
Classificação das mudanças de legenda na trajetória de um político.

Passar de PMDB para MDB não é trocar de partido: é o mesmo partido com outro nome e sigla (renomeação registrada no TSE).
Fusões e incorporações também não são escolha do parlamentar. Só a mudança para um partido sem relação com o anterior
conta como troca. A relação vem do banco: a linhagem (`core.partido.linhagem_id`, usada por `core.vw_partido_canonico`)
cobre as renomeações e `core.partido_sucessao` cobre fusões e incorporações.
"""

from typing import Any, Dict, List, Sequence, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

INICIAL = "INICIAL"
TROCA = "TROCA"
RENOMEACAO = "RENOMEACAO"
FUSAO = "FUSAO"
INCORPORACAO = "INCORPORACAO"
SUCESSAO = "SUCESSAO"

ROTULOS = {
    INICIAL: "Filiação inicial",
    TROCA: "Troca de partido",
    RENOMEACAO: "Mudança de nome e sigla do mesmo partido",
    FUSAO: "Fusão de partidos",
    INCORPORACAO: "Incorporação de partido",
    SUCESSAO: "Sucessão partidária",
}


def sucessoes(db: Session) -> Dict[Tuple[int, int], str]:
    """(partido de origem, partido de destino) -> tipo, para fusões, incorporações e sucessões."""
    linhas: List[Any] = db.execute(
        text(
            "SELECT partido_origem_id, partido_destino_id, tipo FROM core.partido_sucessao "
            "WHERE tipo IN ('FUSAO', 'INCORPORACAO', 'SUCESSAO')"
        )
    ).all()
    return {(int(o), int(d)): str(tipo) for o, d, tipo in linhas}


def classificar(canonicos_em_ordem: Sequence[int], relacoes: Dict[Tuple[int, int], str]) -> List[str]:
    """
    Tipo de cada filiação em relação à anterior, na ordem cronológica recebida. `canonicos_em_ordem` traz o partido
    vigente da linhagem de cada filiação (renomeações já resolvidas); a primeira é sempre INICIAL.
    """
    tipos: List[str] = []
    for i, atual in enumerate(canonicos_em_ordem):
        if i == 0:
            tipos.append(INICIAL)
            continue
        anterior = canonicos_em_ordem[i - 1]
        if anterior == atual:
            tipos.append(RENOMEACAO)
        else:
            tipos.append(relacoes.get((anterior, atual), TROCA))
    return tipos


def contar_trocas(tipos: Sequence[str]) -> int:
    """Só a troca de verdade conta: renomeação, fusão e incorporação não."""
    return sum(1 for t in tipos if t == TROCA)
