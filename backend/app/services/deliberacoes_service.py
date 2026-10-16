import uuid
from typing import Any, Dict, List, Optional, cast

from app.core.links import url_oficial_proposicao
from app.models.core import Partido, Pessoa, PessoaNome
from app.models.leg import Proposicao, Votacao, Voto
from app.services.placar import contagens_por_votacao, placar_da_votacao
from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

AVISO_SIMBOLICA = (
    "Votação Simbólica: Deliberada no plenário por acordo visual e aclamação entre as bancadas partidárias, "
    "sem abertura de painel eletrônico nominal nem registro individual de voto de cada parlamentar. "
    "A apuração democrática é aferida pelas orientações oficiais das bancadas partidárias registradas em ata."
)


def _orientacoes(v: Votacao) -> List[Dict[str, str]]:
    return [
        {"partido_bancada": o.bancada, "orientacao": o.orientacao}
        for o in sorted(v.orientacoes, key=lambda o: o.bancada)
    ]


def _placar_nominal(db: Session, v: Votacao) -> Dict[str, int]:
    """Placar oficial da votação (totais da fonte ou contagem dos votos nominais), no formato das deliberações."""
    placar = placar_da_votacao(v, contagens_por_votacao(db, Votacao.id == v.id).get(v.id))
    return {k: placar[k] for k in ("sim", "nao", "abstencao", "obstrucao", "total")}


def _campos_comissao(v: Votacao) -> Dict[str, Any]:
    return {
        "nome_comissao": v.nome_comissao or v.local_deliberacao,
        "link_ata_reuniao": v.link_ata,
        "relator_nome": v.relator_nome,
        "parecer_relator_numero": v.parecer_numero,
        "parecer_relator_texto": v.parecer_texto,
        "link_parecer_relator": v.link_parecer,
    }


def get_proposicao_deliberacoes(db: Session, prop_id: int) -> Optional[Dict[str, Any]]:
    """Deliberações (comissão, simbólica e nominal) de uma proposição. `prop_id` é o id interno de leg.proposicao."""
    prop = db.query(Proposicao).filter(Proposicao.id == prop_id).first()
    if not prop:
        return None

    prop_dict = {
        "id": str(prop.uid),
        "titulo": prop.titulo,
        "numero": prop.numero,
        "ano": prop.ano,
        "tipo": prop.tipo_codigo,
        "ementa": prop.ementa,
        "setor": prop.area_tematica or "Geral",
        "autor_nome": prop.autor_nome or ("Poder Executivo" if prop.iniciativa_executivo else "Congresso Nacional"),
        "status": prop.status_codigo,
        "data_apresentacao": prop.data_apresentacao.isoformat() if prop.data_apresentacao else None,
        "url_oficial": url_oficial_proposicao(prop),
    }

    votacoes = db.query(Votacao).filter(Votacao.proposicao_id == prop.id).order_by(Votacao.data_hora.desc()).all()
    deliberacoes_out: List[Dict[str, Any]] = []
    for v in votacoes:
        # votação secreta aparece como nominal: o placar vem do total apurado
        tipo = "NOMINAL" if v.tipo_deliberacao == "SECRETA" else v.tipo_deliberacao
        item: Dict[str, Any] = {
            "id": str(v.uid),
            "tipo_deliberacao": tipo,
            "data_hora": v.data_hora.isoformat(),
            "local_deliberacao": v.local_deliberacao or (v.casa.nome if v.casa else None),
            "resumo_decisao": v.resumo_decisao or v.titulo_pauta,
            "aprovada": v.aprovada,
            "orientacoes_partidarias": _orientacoes(v),
        }
        if tipo == "COMISSAO":
            item.update(_campos_comissao(v))
        elif tipo == "SIMBOLICA":
            item["aviso_educativo"] = AVISO_SIMBOLICA
        elif tipo == "NOMINAL":
            placar = _placar_nominal(db, v)
            item["placar"] = placar
            item["total_votos_nominais"] = placar["total"]
        deliberacoes_out.append(item)

    return {
        "proposicao": prop_dict,
        "total_deliberacoes": len(deliberacoes_out),
        "deliberacoes": deliberacoes_out,
    }


def get_deliberacao_detalhe(
    db: Session, votacao_uid: uuid.UUID, search: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    votacao = db.query(Votacao).filter(Votacao.uid == votacao_uid).first()
    if not votacao:
        return None

    prop = votacao.proposicao
    prop_dict = None
    if prop:
        prop_dict = {
            "id": str(prop.uid),
            "titulo": prop.titulo,
            "numero": prop.numero,
            "ano": prop.ano,
            "tipo": prop.tipo_codigo,
            "ementa": prop.ementa,
            "setor": prop.area_tematica or "Geral",
            "autor_nome": prop.autor_nome or ("Poder Executivo" if prop.iniciativa_executivo else "Congresso"),
            "url_oficial": url_oficial_proposicao(prop),
        }

    tipo = "NOMINAL" if votacao.tipo_deliberacao == "SECRETA" else votacao.tipo_deliberacao
    res: Dict[str, Any] = {
        "id": str(votacao.uid),
        "proposicao_id": str(prop.uid) if prop else None,
        "proposicao": prop_dict,
        "tipo_deliberacao": tipo,
        "data_hora": votacao.data_hora.isoformat(),
        "local_deliberacao": votacao.local_deliberacao or (votacao.casa.nome if votacao.casa else None),
        "resumo_decisao": votacao.resumo_decisao or votacao.titulo_pauta,
        "aprovada": votacao.aprovada,
        "orientacoes_partidarias": _orientacoes(votacao),
    }

    if tipo == "COMISSAO":
        res.update(_campos_comissao(votacao))
    elif tipo == "SIMBOLICA":
        res["aviso_educativo"] = AVISO_SIMBOLICA
    elif tipo == "NOMINAL":
        res["placar"] = _placar_nominal(db, votacao)

        nome_civil = (
            select(PessoaNome.nome)
            .where(PessoaNome.pessoa_id == Pessoa.id, PessoaNome.tipo == "CIVIL")
            .limit(1)
            .scalar_subquery()
        )
        votes_query = (
            db.query(Voto, Pessoa, Partido, nome_civil)
            .join(Pessoa, Voto.pessoa_id == Pessoa.id)
            .outerjoin(Partido, Voto.partido_id == Partido.id)
            .filter(Voto.votacao_id == votacao.id)
        )
        if search and search.strip():
            st = f"%{search.strip()}%"
            votes_query = votes_query.filter(or_(Pessoa.nome_exibicao.ilike(st), nome_civil.ilike(st)))
        all_votos = votes_query.order_by(Pessoa.nome_exibicao.asc()).all()

        ufs = _ufs(db, [pessoa.id for _, pessoa, _, _ in all_votos])
        votos_sim: List[Dict[str, Any]] = []
        votos_nao: List[Dict[str, Any]] = []
        votos_abstencao: List[Dict[str, Any]] = []
        votos_obstrucao: List[Dict[str, Any]] = []
        for vn, pessoa, partido, civil in all_votos:
            v_item = {
                "politico_id": str(pessoa.uid),
                "nome_eleitoral": pessoa.nome_exibicao,
                "nome_civil": civil or pessoa.nome_exibicao,
                "partido_sigla": partido.sigla if partido else "S.PART.",
                "uf": ufs.get(pessoa.id, "BR"),
                "foto_url": pessoa.foto_url,
                "voto": vn.opcao_codigo,
            }
            if vn.opcao_codigo == "SIM":
                votos_sim.append(v_item)
            elif vn.opcao_codigo == "NAO":
                votos_nao.append(v_item)
            elif vn.opcao_codigo in ("ABSTENCAO", "AUSENTE", "ARTIGO_17"):
                votos_abstencao.append(v_item)
            elif vn.opcao_codigo == "OBSTRUCAO":
                votos_obstrucao.append(v_item)

        res["votos_sim"] = votos_sim
        res["votos_nao"] = votos_nao
        res["votos_abstencao"] = votos_abstencao
        res["votos_obstrucao"] = votos_obstrucao
        res["total_votos_filtrados"] = len(all_votos)

    return res


def _ufs(db: Session, pessoa_ids: List[int]) -> Dict[int, str]:
    """UF de cada pessoa a partir do mandato mais recente (BR quando o mandato é nacional)."""
    if not pessoa_ids:
        return {}
    rows = db.execute(
        text(
            """
            SELECT DISTINCT ON (m.pessoa_id) m.pessoa_id, coalesce(ci.uf, 'BR')
            FROM core.mandato m JOIN ref.circunscricao ci ON ci.id = m.circunscricao_id
            WHERE m.pessoa_id = ANY(:ids) AND m.condicao <> 'NOMEADO'
            ORDER BY m.pessoa_id, m.inicio DESC
            """
        ),
        {"ids": pessoa_ids},
    )
    return {int(cast(Any, pid)): str(uf) for pid, uf in rows}
