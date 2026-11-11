"""
O que cada votação decidiu: texto principal, urgência, destaque, emenda, parecer, requerimento.

A fonte só traz o texto da deliberação; as regras que o classificam são linhas de `ref.objeto_votacao_regra`. Votação sem
regra que case fica sem objeto (`None`): a tela diz que a fonte não informa, e nada é suposto.
"""

from typing import Any, Dict, Iterable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


def objetos_das_votacoes(db: Session, ids: Iterable[int]) -> Dict[int, Optional[Dict[str, Any]]]:
    """id da votação -> {codigo, rotulo, explicacao, decide_merito}, ou None quando nenhuma regra casa."""
    lista = sorted(set(ids))
    resultado: Dict[int, Optional[Dict[str, Any]]] = {i: None for i in lista}
    if not lista:
        return resultado
    linhas = db.execute(
        text(
            """
            SELECT v.id, o.codigo, o.rotulo, o.explicacao, o.decide_merito
            FROM leg.votacao v
            JOIN LATERAL (
                SELECT r.codigo FROM ref.objeto_votacao_regra r
                WHERE lower(coalesce(v.descricao, '') || ' ' || coalesce(v.titulo_pauta, '')) ~ r.padrao
                ORDER BY r.ordem LIMIT 1
            ) m ON true
            JOIN ref.objeto_votacao o ON o.codigo = m.codigo
            WHERE v.id = ANY(:ids)
            """
        ),
        {"ids": lista},
    ).all()
    for vid, codigo, rotulo, explicacao, decide_merito in linhas:
        resultado[vid] = {
            "codigo": codigo,
            "rotulo": rotulo,
            "explicacao": explicacao,
            "decide_merito": decide_merito,
        }
    return resultado
