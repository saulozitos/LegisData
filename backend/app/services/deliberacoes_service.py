from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.legislative import (
    Proposition,
    VotacaoProposicao,
    VotoNominal,
)
from app.models.politician import Politician, PoliticalParty, Mandate


def _official_url(prop: Proposition) -> Optional[str]:
    if prop.official_url:
        return prop.official_url
    if prop.full_text_url:
        return prop.full_text_url
    if prop.external_camara_id:
        return f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={prop.external_camara_id}"
    if prop.external_senado_id:
        return f"https://legis.senado.leg.br/materia/detalhe/{prop.external_senado_id}"
    return None


def get_proposicao_deliberacoes(db: Session, prop_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    prop = db.query(Proposition).filter(Proposition.id == prop_id).first()
    if not prop:
        return None

    prop_dict = {
        "id": str(prop.id),
        "titulo": prop.title,
        "numero": prop.number,
        "ano": prop.year,
        "tipo": prop.proposition_type.value,
        "ementa": prop.summary,
        "setor": prop.thematic_area or "Geral",
        "autor_nome": prop.author_name or ("Poder Executivo" if prop.is_executive_initiative else "Congresso Nacional"),
        "status": prop.status.value,
        "data_apresentacao": prop.presentation_date.isoformat() if prop.presentation_date else None,
        "url_oficial": _official_url(prop),
    }

    votacoes = (
        db.query(VotacaoProposicao)
        .filter(VotacaoProposicao.proposicao_id == prop.id)
        .order_by(VotacaoProposicao.data_hora.desc())
        .all()
    )

    deliberacoes_out: List[Dict[str, Any]] = []

    for v in votacoes:
        orientacoes = [
            {"partido_bancada": op.partido_bancada, "orientacao": op.orientacao}
            for op in v.orientacoes_partidarias
        ]

        item: Dict[str, Any] = {
            "id": str(v.id),
            "tipo_deliberacao": v.tipo_deliberacao,
            "data_hora": v.data_hora.isoformat(),
            "local_deliberacao": v.local_deliberacao,
            "resumo_decisao": v.resumo_decisao,
            "aprovada": v.aprovada,
            "orientacoes_partidarias": orientacoes,
        }

        if v.tipo_deliberacao == "COMISSAO":
            item["nome_comissao"] = v.nome_comissao or v.local_deliberacao
            item["link_ata_reuniao"] = v.link_ata_reuniao
            item["relator_nome"] = v.relator_nome
            item["parecer_relator_numero"] = v.parecer_relator_numero
            item["parecer_relator_texto"] = v.parecer_relator_texto
            item["link_parecer_relator"] = v.link_parecer_relator
        elif v.tipo_deliberacao == "SIMBOLICA":
            item["aviso_educativo"] = (
                "Votação Simbólica: Deliberada no plenário por acordo visual e aclamação entre as bancadas partidárias, "
                "sem abertura de painel eletrônico nominal nem registro individual de voto de cada parlamentar. "
                "A apuração democrática é aferida pelas orientações oficiais das bancadas partidárias registradas em ata."
            )
        elif v.tipo_deliberacao == "NOMINAL":
            total = (v.total_sim or 0) + (v.total_nao or 0) + (v.total_abstencao or 0) + (v.total_obstrucao or 0)
            item["placar"] = {
                "sim": v.total_sim or 0,
                "nao": v.total_nao or 0,
                "abstencao": v.total_abstencao or 0,
                "obstrucao": v.total_obstrucao or 0,
                "total": total,
            }
            item["total_votos_nominais"] = total

        deliberacoes_out.append(item)

    return {
        "proposicao": prop_dict,
        "total_deliberacoes": len(deliberacoes_out),
        "deliberacoes": deliberacoes_out,
    }


def get_deliberacao_detalhe(
    db: Session, votacao_id: uuid.UUID, search: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    votacao = db.query(VotacaoProposicao).filter(VotacaoProposicao.id == votacao_id).first()
    if not votacao:
        return None

    prop = db.query(Proposition).filter(Proposition.id == votacao.proposicao_id).first()
    prop_dict = None
    if prop:
        prop_dict = {
            "id": str(prop.id),
            "titulo": prop.title,
            "numero": prop.number,
            "ano": prop.year,
            "tipo": prop.proposition_type.value,
            "ementa": prop.summary,
            "setor": prop.thematic_area or "Geral",
            "autor_nome": prop.author_name or ("Poder Executivo" if prop.is_executive_initiative else "Congresso"),
            "url_oficial": _official_url(prop),
        }

    orientacoes = [
        {"partido_bancada": op.partido_bancada, "orientacao": op.orientacao}
        for op in votacao.orientacoes_partidarias
    ]

    res: Dict[str, Any] = {
        "id": str(votacao.id),
        "proposicao_id": str(votacao.proposicao_id),
        "proposicao": prop_dict,
        "tipo_deliberacao": votacao.tipo_deliberacao,
        "data_hora": votacao.data_hora.isoformat(),
        "local_deliberacao": votacao.local_deliberacao,
        "resumo_decisao": votacao.resumo_decisao,
        "aprovada": votacao.aprovada,
        "orientacoes_partidarias": orientacoes,
    }

    if votacao.tipo_deliberacao == "COMISSAO":
        res["nome_comissao"] = votacao.nome_comissao or votacao.local_deliberacao
        res["link_ata_reuniao"] = votacao.link_ata_reuniao
        res["relator_nome"] = votacao.relator_nome
        res["parecer_relator_numero"] = votacao.parecer_relator_numero
        res["parecer_relator_texto"] = votacao.parecer_relator_texto
        res["link_parecer_relator"] = votacao.link_parecer_relator
    elif votacao.tipo_deliberacao == "SIMBOLICA":
        res["aviso_educativo"] = (
            "Votação Simbólica: Deliberada no plenário por acordo visual e aclamação entre as bancadas partidárias, "
            "sem abertura de painel eletrônico nominal nem registro individual de voto de cada parlamentar. "
            "A apuração democrática é aferida pelas orientações oficiais das bancadas partidárias registradas em ata."
        )
    elif votacao.tipo_deliberacao == "NOMINAL":
        total = (votacao.total_sim or 0) + (votacao.total_nao or 0) + (votacao.total_abstencao or 0) + (votacao.total_obstrucao or 0)
        res["placar"] = {
            "sim": votacao.total_sim or 0,
            "nao": votacao.total_nao or 0,
            "abstencao": votacao.total_abstencao or 0,
            "obstrucao": votacao.total_obstrucao or 0,
            "total": total,
        }

        # Query nominal votes
        votes_query = (
            db.query(VotoNominal, Politician)
            .join(Politician, VotoNominal.parlamentar_id == Politician.id)
            .filter(VotoNominal.votacao_id == votacao.id)
        )

        if search and search.strip():
            st = f"%{search.strip()}%"
            votes_query = votes_query.filter(
                or_(
                    Politician.electoral_name.ilike(st),
                    Politician.civil_name.ilike(st),
                )
            )

        all_votos = votes_query.order_by(Politician.electoral_name.asc()).all()

        # Context mandates for party & UF
        pol_ids = [p.id for _, p in all_votos]
        mandates = (
            db.query(Mandate, PoliticalParty)
            .outerjoin(PoliticalParty, Mandate.party_id == PoliticalParty.id)
            .filter(Mandate.politician_id.in_(pol_ids))
            .all()
        )
        party_by_pol = {}
        for m, party in mandates:
            sigla = party.acronym if party else "S.PART."
            uf = m.jurisdiction_state or "BR"
            party_by_pol[m.politician_id] = (sigla, uf)

        votos_sim = []
        votos_nao = []
        votos_abstencao = []
        votos_obstrucao = []

        for vn, pol in all_votos:
            party_sigla, uf = party_by_pol.get(pol.id, ("S.PART.", "BR"))
            v_item = {
                "politico_id": str(pol.id),
                "nome_eleitoral": pol.electoral_name,
                "nome_civil": pol.civil_name,
                "partido_sigla": party_sigla,
                "uf": uf,
                "foto_url": pol.photo_url,
                "voto": vn.voto,
            }
            if vn.voto == "SIM":
                votos_sim.append(v_item)
            elif vn.voto == "NAO":
                votos_nao.append(v_item)
            elif vn.voto in ("ABSTENCAO", "AUSENTE", "ARTIGO_17"):
                votos_abstencao.append(v_item)
            elif vn.voto == "OBSTRUCAO":
                votos_obstrucao.append(v_item)

        res["votos_sim"] = votos_sim
        res["votos_nao"] = votos_nao
        res["votos_abstencao"] = votos_abstencao
        res["votos_obstrucao"] = votos_obstrucao
        res["total_votos_filtrados"] = len(all_votos)

    return res
