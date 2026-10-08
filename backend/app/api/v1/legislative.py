import math
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, String, cast, desc, or_, case

from app.core.database import get_db
from app.models import (
    Proposition, VotingSession, ParliamentaryVote,
    VotoOpcaoEnum, CasaLegislativaEnum, Politician, PoliticalParty, Mandate, PartyAffiliation,
    StatusTramitacaoEnum, TipoProposicaoEnum
)
from app.core.config import PROCESSED_DATA_DIR

router = APIRouter()
DATA_DIR = PROCESSED_DATA_DIR


def _build_house_placar(db: Session, sessions: List[VotingSession]) -> tuple:
    if not sessions:
        return {"SIM": 0, "NAO": 0, "ABSTENCAO": 0, "TOTAL": 0}, None, []

    # Ordenar priorizando sessões aprovadas ou com maior número de votos
    ordered_sessions = sorted(sessions, key=lambda s: (1 if s.is_approved else 0, s.session_datetime), reverse=True)
    all_sessions_details = []
    best_placar = {"SIM": 0, "NAO": 0, "ABSTENCAO": 0, "TOTAL": 0}
    best_session = None

    for idx, s in enumerate(ordered_sessions):
        votos = db.query(
            ParliamentaryVote.vote_choice,
            func.count(ParliamentaryVote.id)
        ).filter_by(voting_session_id=s.id).group_by(ParliamentaryVote.vote_choice).all()

        sim_count = sum(c for v, c in votos if v == VotoOpcaoEnum.SIM)
        nao_count = sum(c for v, c in votos if v == VotoOpcaoEnum.NAO)
        abst_count = sum(c for v, c in votos if v == VotoOpcaoEnum.ABSTENCAO)
        total_votos = sum(c for _, c in votos)

        sess_info = {
            "sessao_id": str(s.id),
            "external_id": s.external_id,
            "data_hora": s.session_datetime.isoformat(),
            "titulo": s.agenda_title,
            "descricao": s.detailed_description or s.agenda_title,
            "aprovada": s.is_approved,
            "placar": {
                "SIM": sim_count,
                "NAO": nao_count,
                "ABSTENCAO": abst_count,
                "TOTAL": total_votos
            }
        }
        all_sessions_details.append(sess_info)

        if idx == 0 or (best_placar["TOTAL"] == 0 and total_votos > 0):
            best_placar = sess_info["placar"]
            best_session = {
                "sessao_id": str(s.id),
                "data_hora": s.session_datetime.isoformat(),
                "titulo": s.agenda_title,
                "descricao": s.detailed_description or s.agenda_title,
                "aprovada": s.is_approved
            }

    return best_placar, best_session, all_sessions_details


@router.get("/propositions", response_model=List[Dict[str, Any]])
def get_propositions_with_voting(db: Session = Depends(get_db)):
    """
    Retorna a lista de matérias legislativas com placar de votação nominal (Sim, Não, Abstenção),
    autor oficial da matéria e status de aprovação discriminados por Câmara dos Deputados e Senado Federal.
    """
    try:
        props = db.query(Proposition).order_by(Proposition.presentation_date.desc()).all()
        if props:
            result = []
            for p in props:
                sessoes = db.query(VotingSession).filter_by(proposition_id=p.id).all()
                sessoes_camara = [s for s in sessoes if s.legislative_house == CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS]
                sessoes_senado = [s for s in sessoes if s.legislative_house == CasaLegislativaEnum.SENADO_FEDERAL]

                placar_camara, sessao_camara, lista_camara = _build_house_placar(db, sessoes_camara)
                placar_senado, sessao_senado, lista_senado = _build_house_placar(db, sessoes_senado)

                # Placar consolidado padrão (prioriza a casa onde houve votação com quórum)
                if placar_camara["TOTAL"] > 0:
                    default_placar = placar_camara
                    default_sessao = sessao_camara
                elif placar_senado["TOTAL"] > 0:
                    default_placar = placar_senado
                    default_sessao = sessao_senado
                else:
                    default_placar = {"SIM": 0, "NAO": 0, "ABSTENCAO": 0, "TOTAL": 0}
                    default_sessao = None

                author_display = p.author_name or ("Poder Executivo" if p.is_executive_initiative else "Comissão / Parlamentares")

                result.append({
                    "id": str(p.id),
                    "camara_id": p.external_camara_id,
                    "tipo": p.proposition_type.value,
                    "numero": p.number,
                    "ano": p.year,
                    "titulo": p.title,
                    "ementa": p.summary,
                    "autor_nome": author_display,
                    "area_tematica": p.thematic_area,
                    "data_apresentacao": p.presentation_date.isoformat(),
                    "status": p.status.value,
                    "is_reforma_estrutural": p.is_structural_reform,
                    "iniciativa_executivo": p.is_executive_initiative,
                    "placar": default_placar,
                    "sessao": default_sessao,
                    "placar_camara": placar_camara,
                    "sessao_camara": sessao_camara,
                    "sessoes_camara_lista": lista_camara,
                    "placar_senado": placar_senado,
                    "sessao_senado": sessao_senado,
                    "sessoes_senado_lista": lista_senado,
                    "url_oficial": p.official_url or (
                        f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={p.external_camara_id}"
                        if p.external_camara_id else
                        f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{p.external_senado_id}"
                        if p.external_senado_id else None
                    )
                })
            return result
    except Exception as e:
        pass

    # Fallback local
    prop_file = DATA_DIR / "proposicoes_2023.json"
    sess_file = DATA_DIR / "sessoes_votacao_2023.json"
    votos_file = DATA_DIR / "votos_nominais_2023.json"

    if not prop_file.exists():
        return []

    with open(prop_file, "r", encoding="utf-8") as f:
        proposicoes = json.load(f)

    sessoes_dict = {}
    if sess_file.exists():
        with open(sess_file, "r", encoding="utf-8") as f:
            for s in json.load(f):
                sessoes_dict[s["proposicao_camara_id"]] = s

    votos_contagem = {}
    if votos_file.exists():
        with open(votos_file, "r", encoding="utf-8") as f:
            for v in json.load(f):
                pid = v["proposicao_camara_id"]
                if pid not in votos_contagem:
                    votos_contagem[pid] = {"SIM": 0, "NAO": 0, "ABSTENCAO": 0, "TOTAL": 0}
                opcao = v.get("voto", "OUTROS")
                if opcao in votos_contagem[pid]:
                    votos_contagem[pid][opcao] += 1
                votos_contagem[pid]["TOTAL"] += 1

    result = []
    for p in proposicoes:
        cid = p["camara_id"]
        result.append({
            "id": str(cid),
            "camara_id": cid,
            "tipo": p["tipo"],
            "numero": p["numero"],
            "ano": p["ano"],
            "titulo": p["titulo"],
            "ementa": p["ementa"],
            "autor_nome": p.get("autor_nome", "Poder Executivo" if p.get("iniciativa_executivo") else "Parlamentar"),
            "area_tematica": p.get("area_tematica", "Geral"),
            "data_apresentacao": p.get("data_apresentacao", "2023-01-01"),
            "status": "EM_TRAMITACAO",
            "is_reforma_estrutural": p.get("is_reforma_estrutural", False),
            "iniciativa_executivo": p.get("iniciativa_executivo", False),
            "placar": votos_contagem.get(cid, {"SIM": 0, "NAO": 0, "ABSTENCAO": 0, "TOTAL": 0}),
            "sessao": sessoes_dict.get(cid)
        })

    return result


@router.get("/propositions/{prop_id}/votes")
def get_proposition_nominal_votes(
    prop_id: str,
    house: Optional[str] = None,
    session_id: Optional[str] = None,
    search: Optional[str] = None,
    vote_choice: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Retorna a lista nominal completa dos votos registrados para uma matéria legislativa,
    permitindo filtro por Casa (CAMARA ou SENADO), busca por nome do político e opção de voto (SIM, NAO, ABSTENCAO).
    """
    # 1. Localizar proposição
    prop = None
    try:
        import uuid
        prop_uuid = uuid.UUID(prop_id)
        prop = db.query(Proposition).filter_by(id=prop_uuid).first()
    except (ValueError, AttributeError):
        pass

    if not prop and prop_id.isdigit():
        num_val = int(prop_id)
        prop = db.query(Proposition).filter(
            (Proposition.number == num_val) | (Proposition.external_camara_id == num_val)
        ).first()

    if not prop:
        # Tentar buscar pelo primeiro ID que contenha o termo
        prop = db.query(Proposition).filter(cast(Proposition.id, String).ilike(f"%{prop_id}%")).first()

    if not prop:
        return {"proposicao": None, "total": 0, "votos": []}

    # 2. Filtrar sessões de votação
    sessions_query = db.query(VotingSession).filter_by(proposition_id=prop.id)
    if house:
        h_enum = CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS if "CAMARA" in house.upper() else CasaLegislativaEnum.SENADO_FEDERAL
        sessions_query = sessions_query.filter_by(legislative_house=h_enum)

    all_house_sessions = sessions_query.all()
    if not all_house_sessions:
        return {
            "proposicao": {
                "id": str(prop.id),
                "titulo": prop.title,
                "numero": prop.number,
                "ano": prop.year,
                "autor_nome": prop.author_name or "Poder Executivo",
            },
            "sessoes_disponiveis": [],
            "sessao_ativa": None,
            "total": 0,
            "votos": []
        }

    sessoes_disponiveis = [
        {
            "id": str(s.id),
            "titulo": s.agenda_title,
            "data_hora": s.session_datetime.isoformat(),
            "casa": s.legislative_house.value,
            "aprovada": s.is_approved
        }
        for s in all_house_sessions
    ]

    selected_session = None
    if session_id:
        try:
            import uuid
            sess_uuid = uuid.UUID(session_id)
            selected_session = next((s for s in all_house_sessions if s.id == sess_uuid), None)
        except Exception:
            pass

    if not selected_session:
        # Priorizar a sessão com maior quantidade de votos ou aprovada
        selected_session = max(
            all_house_sessions,
            key=lambda s: db.query(ParliamentaryVote).filter_by(voting_session_id=s.id).count()
        )

    session_ids = [selected_session.id]

    # 3. Consultar votos nominais
    votes_query = (
        db.query(
            ParliamentaryVote,
            Politician,
            PoliticalParty,
            VotingSession
        )
        .join(Politician, ParliamentaryVote.politician_id == Politician.id)
        .outerjoin(PoliticalParty, ParliamentaryVote.party_id == PoliticalParty.id)
        .join(VotingSession, ParliamentaryVote.voting_session_id == VotingSession.id)
        .filter(ParliamentaryVote.voting_session_id.in_(session_ids))
    )

    if vote_choice:
        try:
            v_enum = VotoOpcaoEnum[vote_choice.upper()]
            votes_query = votes_query.filter(ParliamentaryVote.vote_choice == v_enum)
        except KeyError:
            pass

    if search:
        s_term = f"%{search}%"
        votes_query = votes_query.filter(
            (Politician.electoral_name.ilike(s_term)) |
            (PoliticalParty.acronym.ilike(s_term))
        )

    # Ordenar por nome eleitoral
    raw_results = votes_query.order_by(Politician.electoral_name.asc()).limit(600).all()

    # Mapear estados dos mandatos para obter a UF
    politician_ids = [p.id for _, p, _, _ in raw_results]
    mandates = db.query(Mandate.politician_id, Mandate.jurisdiction_state, Mandate.office).filter(
        Mandate.politician_id.in_(politician_ids)
    ).all()
    uf_map = {m.politician_id: (m.jurisdiction_state, m.office.value) for m in mandates}

    items = []
    for vote, pol, party, sess in raw_results:
        mand_info = uf_map.get(pol.id, ("DF", "DEPUTADO_FEDERAL"))
        items.append({
            "voto_id": str(vote.id),
            "politico_id": str(pol.id),
            "nome_eleitoral": pol.electoral_name,
            "nome_civil": pol.civil_name,
            "partido_sigla": party.acronym if party else "S.PART.",
            "uf": mand_info[0],
            "cargo": mand_info[1],
            "foto_url": pol.photo_url,
            "decisao": vote.vote_choice.value,
            "sessao_id": str(sess.id),
            "sessao_titulo": sess.agenda_title,
            "casa_legislativa": sess.legislative_house.value,
            "data_sessao": sess.session_datetime.isoformat()
        })

    return {
        "proposicao": {
            "id": str(prop.id),
            "titulo": prop.title,
            "numero": prop.number,
            "ano": prop.year,
            "autor_nome": prop.author_name or "Poder Executivo",
            "area_tematica": prop.thematic_area,
        },
        "sessao_ativa": {
            "id": str(selected_session.id),
            "titulo": selected_session.agenda_title,
            "descricao": selected_session.detailed_description or selected_session.agenda_title,
            "data_hora": selected_session.session_datetime.isoformat(),
            "casa": selected_session.legislative_house.value,
            "aprovada": selected_session.is_approved
        } if selected_session else None,
        "sessoes_disponiveis": sessoes_disponiveis,
        "total": len(items),
        "votos": items
    }


@router.get("/ranking/authors")
def get_authors_productivity_ranking(
    limit: int = 20,
    partido: Optional[str] = None,
    setor: Optional[str] = None,
    criterio: str = Query("efetividade", description="Modo de classificação: 'efetividade' (Score IPLE) ou 'volume' (Total bruto de proposições)"),
    db: Session = Depends(get_db)
):
    """
    Retorna o ranking de produtividade parlamentar com dupla metodologia:
    - Efetividade (Score IPLE): Pondera leis aprovadas (+15 pts), reformas estruturantes/PECs (+4 pts) e volume moderado,
      coibindo o 'spam legislativo' de matérias cosméticas ou sem tramitação.
    - Volume: Ordenação puramente quantitativa por total de proposições protocoladas.
    Permite filtrar por partido, setor/tema e critério de ordenação.
    """
    query = (
        db.query(
            Proposition.author_politician_id,
            func.count(Proposition.id).label("total_props"),
            func.sum(case((Proposition.status.in_([StatusTramitacaoEnum.APROVADA_E_SANCIONADA, StatusTramitacaoEnum.APROVADA_E_PROMULGADA]), 1), else_=0)).label("aprovadas"),
            func.sum(case((Proposition.is_structural_reform.is_(True), 1), (Proposition.proposition_type.in_([TipoProposicaoEnum.PEC, TipoProposicaoEnum.PLP]), 1), else_=0)).label("estruturantes")
        )
        .filter(Proposition.author_politician_id.isnot(None))
    )

    if setor and setor.lower() not in ("todos", "todas", "all"):
        clean_setor = setor.strip()
        termo_principal = clean_setor.split("&")[0].split("/")[0].strip()
        query = query.filter(
            or_(
                Proposition.thematic_area.ilike(f"%{clean_setor}%"),
                Proposition.thematic_area.ilike(f"%{termo_principal}%")
            )
        )

    if partido and partido.lower() not in ("todos", "todas", "all"):
        clean_partido = partido.strip().upper()
        matching_party_ids = [
            p.id for p in db.query(PoliticalParty.id).filter(
                or_(
                    func.upper(PoliticalParty.acronym) == clean_partido,
                    PoliticalParty.acronym.ilike(f"%{clean_partido}%"),
                    PoliticalParty.full_name.ilike(f"%{clean_partido}%")
                )
            ).all()
        ]
        if matching_party_ids:
            pols_mandate = db.query(Mandate.politician_id).filter(Mandate.party_id.in_(matching_party_ids))
            pols_aff = db.query(PartyAffiliation.politician_id).filter(PartyAffiliation.party_id.in_(matching_party_ids))
            query = query.filter(
                or_(
                    Proposition.author_politician_id.in_(pols_mandate),
                    Proposition.author_politician_id.in_(pols_aff)
                )
            )
        else:
            query = query.filter(Proposition.author_politician_id == uuid.uuid4())

    all_authors = query.group_by(Proposition.author_politician_id).all()

    if not all_authors:
        return []

    # Calcular Score IPLE para cada parlamentar
    scored_authors = []
    for aid, total, apr, est in all_authors:
        total_val = int(total or 0)
        apr_val = int(apr or 0)
        est_val = int(est or 0)
        # Fórmula IPLE: Leis aprovadas (15 pts) + Matérias estruturantes (4 pts) + Volume com teto de 50 (0.6 pt)
        score = min(100.0, round((apr_val * 15.0) + (est_val * 4.0) + (min(total_val, 50) * 0.6), 1))

        if apr_val >= 2:
            diag = "Alta Eficácia Legislativa"
        elif apr_val >= 1:
            diag = "Média Eficácia"
        elif total_val >= 30 and apr_val == 0:
            diag = "Volume Alto sem Leis Aprovadas"
        else:
            diag = "Em Tramitação"

        scored_authors.append({
            "author_id": aid,
            "total_props": total_val,
            "aprovadas": apr_val,
            "estruturantes": est_val,
            "score": score,
            "diagnostico": diag
        })

    # Ordenação por critério
    if criterio and criterio.lower() == "volume":
        scored_authors.sort(key=lambda x: (x["total_props"], x["score"]), reverse=True)
    else:
        # Default: Efetividade (Score IPLE)
        scored_authors.sort(key=lambda x: (x["score"], x["aprovadas"], x["estruturantes"], x["total_props"]), reverse=True)

    author_counts = scored_authors[:limit]
    politician_ids = [a["author_id"] for a in author_counts]
    politicians = {p.id: p for p in db.query(Politician).filter(Politician.id.in_(politician_ids)).all()}

    # Buscar mandatos e partidos
    mandates = db.query(Mandate).filter(Mandate.politician_id.in_(politician_ids)).all()
    mandate_map = {}
    for m in mandates:
        if m.politician_id not in mandate_map or (m.start_date and mandate_map[m.politician_id].start_date and m.start_date > mandate_map[m.politician_id].start_date):
            mandate_map[m.politician_id] = m

    # Buscar filiações atuais como fallback
    current_affs = db.query(PartyAffiliation).filter(PartyAffiliation.politician_id.in_(politician_ids), PartyAffiliation.is_current.is_(True)).all()
    aff_map = {aff.politician_id: aff for aff in current_affs}

    party_ids = list(set([m.party_id for m in mandate_map.values() if m.party_id] + [a.party_id for a in aff_map.values() if a.party_id]))
    parties = {p.id: p for p in db.query(PoliticalParty).filter(PoliticalParty.id.in_(party_ids)).all()}

    # Setores por parlamentar
    sector_rows = (
        db.query(
            Proposition.author_politician_id,
            Proposition.thematic_area,
            func.count(Proposition.id).label("total_setor")
        )
        .filter(Proposition.author_politician_id.in_(politician_ids))
        .group_by(Proposition.author_politician_id, Proposition.thematic_area)
        .order_by(Proposition.author_politician_id, desc("total_setor"))
        .all()
    )

    sectors_by_author = {}
    for aid, st, cnt in sector_rows:
        if aid not in sectors_by_author:
            sectors_by_author[aid] = []
        sectors_by_author[aid].append((st or "Geral", cnt))

    ranking = []
    for idx, item in enumerate(author_counts, start=1):
        pol_id = item["author_id"]
        pol = politicians.get(pol_id)
        if not pol:
            continue

        mand = mandate_map.get(pol_id)
        aff = aff_map.get(pol_id)
        party = parties.get(mand.party_id) if (mand and mand.party_id) else (parties.get(aff.party_id) if aff else None)
        uf = mand.jurisdiction_state if mand else (pol.birthplace_state or "DF")
        cargo = mand.office.value if mand else "DEPUTADO_FEDERAL"
        partido_sigla = party.acronym if party else "S.PART."
        espectro = party.political_spectrum.value if (party and party.political_spectrum) else "CENTRO"

        author_sectors = sectors_by_author.get(pol_id, [])
        principal_setor = author_sectors[0][0] if author_sectors else "Economia & Finanças"
        total_principal = author_sectors[0][1] if author_sectors else item["total_props"]

        distribuicao = [
            {
                "setor": st,
                "total": cnt,
                "percentual": round((cnt / item["total_props"]) * 100, 1) if item["total_props"] > 0 else 0
            }
            for st, cnt in author_sectors
        ]

        ranking.append({
            "posicao": idx,
            "politico_id": str(pol.id),
            "nome_eleitoral": pol.electoral_name,
            "nome_civil": pol.civil_name,
            "partido_sigla": partido_sigla,
            "espectro_politico": espectro,
            "uf": uf,
            "cargo": cargo,
            "foto_url": pol.photo_url,
            "total_proposicoes": item["total_props"],
            "proposicoes_aprovadas": item["aprovadas"],
            "proposicoes_estruturantes": item["estruturantes"],
            "score_produtividade": item["score"],
            "classificacao_efetividade": item["diagnostico"],
            "principal_setor": principal_setor,
            "total_principal_setor": total_principal,
            "distribuicao_setores": distribuicao
        })

    return ranking


@router.get("/explorer")
def get_legislative_explorer(
    search: Optional[str] = None,
    setor: Optional[str] = None,
    tipo: Optional[str] = None,
    status: Optional[str] = None,
    apenas_votadas: bool = False,
    page: int = 1,
    limit: int = 25,
    db: Session = Depends(get_db)
):
    """
    Retorna a lista geral de proposições com filtros, cruzada com Setor/Tema, Autor e Placar Geral (Sim/Não).
    """
    query = db.query(Proposition)

    if search:
        s_term = f"%{search}%"
        query = query.filter(
            or_(
                Proposition.title.ilike(s_term),
                Proposition.summary.ilike(s_term),
                Proposition.author_name.ilike(s_term),
                Proposition.thematic_area.ilike(s_term)
            )
        )

    if setor and setor.lower() not in ("todos", "todas", "all"):
        query = query.filter(Proposition.thematic_area.ilike(f"%{setor}%"))

    if tipo and tipo.lower() not in ("todos", "todas", "all"):
        try:
            from app.models.legislative import TipoProposicaoEnum
            t_enum = TipoProposicaoEnum[tipo.upper()]
            query = query.filter(Proposition.proposition_type == t_enum)
        except (KeyError, ValueError):
            pass

    if status and status.lower() not in ("todos", "todas", "all"):
        try:
            from app.models.legislative import StatusTramitacaoEnum
            st_enum = StatusTramitacaoEnum[status.upper()]
            query = query.filter(Proposition.status == st_enum)
        except (KeyError, ValueError):
            pass

    if apenas_votadas:
        query = query.join(VotingSession, Proposition.id == VotingSession.proposition_id)

    total_items = query.distinct().count()

    todos_setores = [
        row[0] for row in db.query(Proposition.thematic_area)
        .filter(Proposition.thematic_area.isnot(None))
        .distinct()
        .order_by(Proposition.thematic_area.asc())
        .all()
    ]

    offset = max(0, (page - 1) * limit)
    proposicoes = (
        query.order_by(Proposition.presentation_date.desc(), Proposition.number.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    author_ids = [p.author_politician_id for p in proposicoes if p.author_politician_id]
    politicians = {p.id: p for p in db.query(Politician).filter(Politician.id.in_(author_ids)).all()}
    mandates = db.query(Mandate).filter(Mandate.politician_id.in_(author_ids)).all()
    mandate_map = {m.politician_id: m for m in mandates}
    party_ids = [m.party_id for m in mandates if m.party_id]
    parties = {p.id: p for p in db.query(PoliticalParty).filter(PoliticalParty.id.in_(party_ids)).all()}

    items = []
    for p in proposicoes:
        sessoes = db.query(VotingSession).filter_by(proposition_id=p.id).all()
        placar, sessao, _ = _build_house_placar(db, sessoes)
        tem_votacao = placar["TOTAL"] > 0

        autor_pol = politicians.get(p.author_politician_id) if p.author_politician_id else None
        autor_mand = mandate_map.get(p.author_politician_id) if p.author_politician_id else None
        autor_party = parties.get(autor_mand.party_id) if (autor_mand and autor_mand.party_id) else None

        partido_sigla = autor_party.acronym if autor_party else ("GOV" if p.is_executive_initiative else "S.PART.")
        uf = autor_mand.jurisdiction_state if autor_mand else "DF"
        foto = autor_pol.photo_url if autor_pol else None
        autor_display = p.author_name or (autor_pol.electoral_name if autor_pol else ("Poder Executivo" if p.is_executive_initiative else "Parlamentar"))

        resultado_str = "EM_TRAMITACAO"
        if sessao:
            resultado_str = "APROVADA" if sessao.get("aprovada") else "REJEITADA"
        elif p.status.value in ("APROVADA_E_SANCIONADA", "APROVADA_E_PROMULGADA"):
            resultado_str = "APROVADA"

        items.append({
            "id": str(p.id),
            "camara_id": p.external_camara_id,
            "tipo": p.proposition_type.value,
            "numero": p.number,
            "ano": p.year,
            "titulo": p.title,
            "ementa": p.summary,
            "setor": p.thematic_area or "Administração & Cidadania",
            "eixo_impacto": p.impact_axis or "Geral",
            "autor_nome": autor_display,
            "autor_politico_id": str(p.author_politician_id) if p.author_politician_id else None,
            "autor_partido": partido_sigla,
            "autor_uf": uf,
            "autor_foto": foto,
            "status": p.status.value,
            "data_apresentacao": p.presentation_date.isoformat(),
            "is_reforma_estrutural": p.is_structural_reform,
            "iniciativa_executivo": p.is_executive_initiative,
            "url_oficial": p.official_url or (
                f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={p.external_camara_id}"
                if p.external_camara_id else
                f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{p.external_senado_id}"
                if p.external_senado_id else None
            ),
            "tem_votacao": tem_votacao,
            "sessao_id": sessao["sessao_id"] if sessao else None,
            "placar": {
                "sim": placar["SIM"],
                "nao": placar["NAO"],
                "abstencao": placar["ABSTENCAO"],
                "total": placar["TOTAL"],
                "resultado": resultado_str
            }
        })

    return {
        "total": total_items,
        "page": page,
        "limit": limit,
        "total_pages": math.ceil(total_items / limit) if total_items > 0 else 1,
        "setores_disponiveis": todos_setores,
        "items": items
    }


@router.get("/propositions/{prop_id}/nominal-votes")
def get_proposition_nominal_votes_split(
    prop_id: str,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Retorna a tabela detalhada de quem votou SIM (A Favor) e quem votou NÃO (Contra),
    com foto, nome, partido e UF de cada parlamentar.
    """
    # 1. Localizar Proposição
    prop = None
    try:
        import uuid
        prop_uuid = uuid.UUID(prop_id)
        prop = db.query(Proposition).filter_by(id=prop_uuid).first()
    except (ValueError, AttributeError):
        pass

    if not prop and prop_id.isdigit():
        num_val = int(prop_id)
        prop = db.query(Proposition).filter(
            (Proposition.number == num_val) | (Proposition.external_camara_id == num_val)
        ).first()

    if not prop:
        prop = db.query(Proposition).filter(cast(Proposition.id, String).ilike(f"%{prop_id}%")).first()

    if not prop:
        return {
            "proposicao": None,
            "sessao": None,
            "placar": {"sim": 0, "nao": 0, "abstencao": 0, "obstrucao": 0, "total": 0},
            "votos_sim": [],
            "votos_nao": [],
            "votos_abstencao": [],
            "votos_obstrucao": []
        }

    # 2. Localizar Sessões de Votação
    sessions = db.query(VotingSession).filter_by(proposition_id=prop.id).all()
    if not sessions:
        return {
            "proposicao": {
                "id": str(prop.id),
                "titulo": prop.title,
                "numero": prop.number,
                "ano": prop.year,
                "ementa": prop.summary,
                "setor": prop.thematic_area,
                "autor_nome": prop.author_name or "Poder Executivo",
                "status": prop.status.value,
                "data_apresentacao": prop.presentation_date.isoformat()
            },
            "sessao": None,
            "placar": {"sim": 0, "nao": 0, "abstencao": 0, "obstrucao": 0, "total": 0},
            "votos_sim": [],
            "votos_nao": [],
            "votos_abstencao": [],
            "votos_obstrucao": []
        }

    # Selecionar sessão prioritária (com maior quórum)
    selected_session = max(
        sessions,
        key=lambda s: db.query(ParliamentaryVote).filter_by(voting_session_id=s.id).count()
    )

    # 3. Consultar Votos Nominais da Sessão
    votes_query = (
        db.query(
            ParliamentaryVote,
            Politician,
            PoliticalParty
        )
        .join(Politician, ParliamentaryVote.politician_id == Politician.id)
        .outerjoin(PoliticalParty, ParliamentaryVote.party_id == PoliticalParty.id)
        .filter(ParliamentaryVote.voting_session_id == selected_session.id)
    )

    if search:
        s_term = f"%{search}%"
        votes_query = votes_query.filter(
            or_(
                Politician.electoral_name.ilike(s_term),
                Politician.civil_name.ilike(s_term),
                PoliticalParty.acronym.ilike(s_term)
            )
        )

    all_votes = votes_query.order_by(Politician.electoral_name.asc()).all()

    # Mapear estados e cargos dos parlamentares
    pol_ids = [p.id for _, p, _ in all_votes]
    mandates = db.query(Mandate.politician_id, Mandate.jurisdiction_state, Mandate.office).filter(
        Mandate.politician_id.in_(pol_ids)
    ).all()
    mandate_info = {m.politician_id: (m.jurisdiction_state, m.office.value) for m in mandates}

    votos_sim = []
    votos_nao = []
    votos_abstencao = []
    votos_obstrucao = []

    for vote, pol, party in all_votes:
        uf, cargo = mandate_info.get(pol.id, ("DF", "DEPUTADO_FEDERAL"))
        espectro = party.political_spectrum.value if (party and party.political_spectrum) else "CENTRO"

        item = {
            "politico_id": str(pol.id),
            "nome_eleitoral": pol.electoral_name,
            "nome_civil": pol.civil_name,
            "partido_sigla": party.acronym if party else "S.PART.",
            "espectro_politico": espectro,
            "uf": uf,
            "cargo": cargo,
            "foto_url": pol.photo_url,
            "decisao": vote.vote_choice.value
        }

        if vote.vote_choice == VotoOpcaoEnum.SIM:
            votos_sim.append(item)
        elif vote.vote_choice == VotoOpcaoEnum.NAO:
            votos_nao.append(item)
        elif vote.vote_choice == VotoOpcaoEnum.ABSTENCAO:
            votos_abstencao.append(item)
        elif vote.vote_choice == VotoOpcaoEnum.OBSTRUCAO:
            votos_obstrucao.append(item)

    return {
        "proposicao": {
            "id": str(prop.id),
            "titulo": prop.title,
            "numero": prop.number,
            "ano": prop.year,
            "ementa": prop.summary,
            "setor": prop.thematic_area,
            "autor_nome": prop.author_name or "Poder Executivo",
            "status": prop.status.value,
            "data_apresentacao": prop.presentation_date.isoformat(),
            "url_oficial": prop.official_url or (
                f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={prop.external_camara_id}"
                if prop.external_camara_id else
                f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{prop.external_senado_id}"
                if prop.external_senado_id else None
            )
        },
        "sessao": {
            "id": str(selected_session.id),
            "titulo": selected_session.agenda_title,
            "descricao": selected_session.detailed_description or selected_session.agenda_title,
            "data_hora": selected_session.session_datetime.isoformat(),
            "casa_legislativa": selected_session.legislative_house.value,
            "aprovada": selected_session.is_approved,
            "total_votos": len(all_votes)
        },
        "placar": {
            "sim": len(votos_sim),
            "nao": len(votos_nao),
            "abstencao": len(votos_abstencao),
            "obstrucao": len(votos_obstrucao),
            "total": len(all_votes)
        },
        "votos_sim": votos_sim,
        "votos_nao": votos_nao,
        "votos_abstencao": votos_abstencao,
        "votos_obstrucao": votos_obstrucao
    }


@router.get("/calendar")
def get_voting_calendar(
    year: Optional[int] = Query(None, description="Ano para filtrar as votações nominais"),
    db: Session = Depends(get_db)
):
    """
    Retorna o Diário do Congresso (Calendário de Votações):
    1. Lista de datas (dias) em que houve registro de sessão de votação no banco.
    2. Estatística global anual: 'Em XXXX, de 365 dias, o Congresso realizou sessões de votação nominal em apenas Y dias'
    3. Detalhes das matérias deliberadas pela Câmara e pelo Senado em cada data, com links oficiais na íntegra.
    """
    all_sessions = (
        db.query(VotingSession, Proposition)
        .join(Proposition, VotingSession.proposition_id == Proposition.id)
        .order_by(desc(VotingSession.session_datetime))
        .all()
    )

    if not all_sessions:
        return {
            "ano_selecionado": year or 2023,
            "anos_disponiveis": [2023],
            "estatisticas_anuais": {
                "ano": year or 2023,
                "total_dias_ano": 365,
                "dias_com_votacao": 0,
                "percentual_dias_ativos": 0.0,
                "total_sessoes_ano": 0,
                "texto_estatistica": f"Em {year or 2023}, de 365 dias, o Congresso realizou sessões de votação nominal em 0 dias."
            },
            "dias": []
        }

    anos_disponiveis = sorted(list(set(s.session_datetime.year for s, _ in all_sessions)), reverse=True)
    selected_year = year if (year and year in anos_disponiveis) else (2023 if 2023 in anos_disponiveis else anos_disponiveis[0])

    sessoes_ano = [(s, p) for s, p in all_sessions if s.session_datetime.year == selected_year]

    meses_pt = {
        1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
        5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
        9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
    }
    dias_semana_pt = {
        0: "Segunda-feira", 1: "Terça-feira", 2: "Quarta-feira",
        3: "Quinta-feira", 4: "Sexta-feira", 5: "Sábado", 6: "Domingo"
    }

    dias_dict: Dict[str, Dict[str, Any]] = {}
    for sess, prop in sessoes_ano:
        dt_str = sess.session_datetime.strftime("%Y-%m-%d")
        if dt_str not in dias_dict:
            d_obj = sess.session_datetime.date()
            dias_dict[dt_str] = {
                "data": dt_str,
                "dia": d_obj.day,
                "mes": d_obj.month,
                "ano": d_obj.year,
                "dia_semana": dias_semana_pt.get(d_obj.weekday(), ""),
                "data_formatada": f"{d_obj.day:02d} de {meses_pt.get(d_obj.month, '')} de {d_obj.year}",
                "total_votacoes": 0,
                "camara_count": 0,
                "senado_count": 0,
                "sessoes": []
            }

        votos = (
            db.query(ParliamentaryVote.vote_choice, func.count(ParliamentaryVote.id))
            .filter_by(voting_session_id=sess.id)
            .group_by(ParliamentaryVote.vote_choice)
            .all()
        )
        sim_count = sum(c for v, c in votos if v == VotoOpcaoEnum.SIM)
        nao_count = sum(c for v, c in votos if v == VotoOpcaoEnum.NAO)
        abst_count = sum(c for v, c in votos if v in (VotoOpcaoEnum.ABSTENCAO, VotoOpcaoEnum.OBSTRUCAO, VotoOpcaoEnum.AUSENTE))
        total_v = sum(c for _, c in votos)

        casa_str = sess.legislative_house.value
        if casa_str == "CAMARA_DOS_DEPUTADOS":
            dias_dict[dt_str]["camara_count"] += 1
        else:
            dias_dict[dt_str]["senado_count"] += 1

        dias_dict[dt_str]["total_votacoes"] += 1

        url_oficial = prop.official_url or (
            f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={prop.external_camara_id}"
            if prop.external_camara_id else
            f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{prop.external_senado_id}"
            if prop.external_senado_id else None
        )

        dias_dict[dt_str]["sessoes"].append({
            "sessao_id": str(sess.id),
            "casa": casa_str,
            "casa_nome": "Câmara dos Deputados" if casa_str == "CAMARA_DOS_DEPUTADOS" else "Senado Federal",
            "hora": sess.session_datetime.strftime("%H:%M"),
            "titulo": sess.agenda_title,
            "descricao": sess.detailed_description or sess.agenda_title,
            "aprovada": sess.is_approved,
            "placar": {
                "sim": sim_count,
                "nao": nao_count,
                "abstencao": abst_count,
                "total": total_v
            },
            "proposicao": {
                "id": str(prop.id),
                "titulo": prop.title,
                "tipo": prop.proposition_type.value,
                "numero": prop.number,
                "ano": prop.year,
                "ementa": prop.summary,
                "setor": prop.thematic_area or "Economia & Finanças",
                "autor_nome": prop.author_name or "Poder Executivo",
                "status": prop.status.value,
                "url_oficial": url_oficial
            }
        })

    lista_dias = sorted(list(dias_dict.values()), key=lambda d: d["data"], reverse=True)

    is_bissexto = (selected_year % 4 == 0 and (selected_year % 100 != 0 or selected_year % 400 == 0))
    total_dias_ano = 366 if is_bissexto else 365
    dias_com_votacao = len(lista_dias)
    percentual_ativo = round((dias_com_votacao / total_dias_ano) * 100, 1)

    texto_estatistica = (
        f"Em {selected_year}, de {total_dias_ano} dias, o Congresso realizou "
        f"sessões de votação nominal em apenas {dias_com_votacao} dias ({percentual_ativo}% do ano)."
    )

    return {
        "ano_selecionado": selected_year,
        "anos_disponiveis": anos_disponiveis,
        "estatisticas_anuais": {
            "ano": selected_year,
            "total_dias_ano": total_dias_ano,
            "dias_com_votacao": dias_com_votacao,
            "percentual_dias_ativos": percentual_ativo,
            "total_sessoes_ano": len(sessoes_ano),
            "texto_estatistica": texto_estatistica
        },
        "dias": lista_dias
    }
