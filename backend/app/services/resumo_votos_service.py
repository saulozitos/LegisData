"""Como um parlamentar votou nas votações nominais: Sim, Não e ausente, com a lista completa de cada grupo."""

from typing import Any, Dict, List

from app.core.links import url_oficial_proposicao
from app.core.query_utils import to_brt
from app.models.leg import Proposicao, Votacao, Voto
from sqlalchemy import desc
from sqlalchemy.orm import Session

GRUPOS = {"SIM": "sim", "NAO": "nao", "AUSENTE": "ausente"}


def resumo_votos(db: Session, pessoa_id: int) -> Dict[str, Any]:
    """
    Total e lista completa (da mais recente à mais antiga) das votações em que a pessoa votou Sim, Não ou esteve
    ausente. A lista não tem limite por decisão de produto: o bloco do Raio-X rola dentro de uma altura fixa.
    """
    linhas = (
        db.query(Voto.opcao_codigo, Votacao, Proposicao)
        .join(Votacao, Voto.votacao_id == Votacao.id)
        .join(Proposicao, Votacao.proposicao_id == Proposicao.id)
        .filter(Voto.pessoa_id == pessoa_id, Voto.opcao_codigo.in_(list(GRUPOS)))
        .order_by(desc(Votacao.data_hora), Votacao.id)
        .all()
    )
    itens: Dict[str, List[Dict[str, Any]]] = {chave: [] for chave in GRUPOS.values()}
    for opcao, sess, prop in linhas:
        quando = to_brt(sess.data_hora)
        itens[GRUPOS[opcao]].append(
            {
                "proposicao_id": str(prop.uid),
                "proposicao_titulo": prop.titulo,
                "proposicao_numero": f"{prop.tipo_codigo} {prop.numero}/{prop.ano}" if prop.numero else prop.titulo,
                "data": quando.strftime("%d/%m/%Y") if quando else "",
                "casa_legislativa": sess.casa.codigo if sess.casa else "CAMARA_DOS_DEPUTADOS",
                "url_oficial": url_oficial_proposicao(prop),
            }
        )
    return {chave: {"total": len(lista), "itens": lista} for chave, lista in itens.items()}
