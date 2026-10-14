import re
import json
import logging
import math
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import PROCESSED_DATA_DIR
from app.core.database import get_db
from app.models import (
    CasaLegislativaEnum,
    Mandate,
    ParliamentaryVote,
    PartyAffiliation,
    PoliticalParty,
    Politician,
    Proposition,
    PropositionAuthor,
    StatusTramitacaoEnum,
    TipoAutoriaEnum,
    TipoProposicaoEnum,
    VotingSession,
    VotoOpcaoEnum,
)
from app.services.legislative_scoring import (
    MULTIPLICADOR_TRAMITACAO,
    PESO_COMPLEXIDADE,
    build_coauthorship_network,
    get_politician_ialp_metrics,
)
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import and_, case, desc, exists, extract, func, literal, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
router = APIRouter()
DATA_DIR = PROCESSED_DATA_DIR

# Fuso fixo do Brasil (sem horário de verão desde 2019) para exibir datas/horas de sessões
BRT = timezone(timedelta(hours=-3))
ALL_KEYWORDS = ("todos", "todas", "all")
MAX_NOMINAL_VOTES = 600
EMPTY_PLACAR = {"SIM": 0, "NAO": 0, "ABSTENCAO": 0, "TOTAL": 0}
_PARTY_SIGLA_RE = re.compile(r"\(([A-ZÀ-Ú0-9_ -]+)(?:/[A-Z]{2})?\)")


def _escape_like(value: str) -> str:
    """Escapa curingas do LIKE para que '%' e '_' digitados pelo usuário sejam literais."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _contains(column, value: str):
    return column.ilike(f"%{_escape_like(value.strip())}%", escape="\\")


def _to_brt(dt: datetime) -> datetime:
    return dt.astimezone(BRT) if dt.tzinfo else dt


def _official_url(prop: Proposition) -> Optional[str]:
    if prop.official_url:
        return prop.official_url
    if prop.external_camara_id:
        return f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={prop.external_camara_id}"
    if prop.external_senado_id:
        return f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{prop.external_senado_id}"
    return None


def _current_mandate_clause():
    today = date.today()
    return or_(Mandate.end_date.is_(None), Mandate.end_date >= today)


def _is_filter_all(value: Optional[str]) -> bool:
    return not value or value.strip().lower() in ALL_KEYWORDS


# ---------------------------------------------------------------------------
# Placar (uma única definição para todas as telas)
#   SIM, NAO      -> votos nominais
#   ABSTENCAO     -> abstenção + obstrução (participaram sem votar SIM/NAO)
#   TOTAL         -> SIM + NAO + ABSTENCAO  (AUSENTE e Art. 17 não entram: não votaram)
# ---------------------------------------------------------------------------
def _placar_from_counts(counts: Dict[VotoOpcaoEnum, int]) -> Dict[str, int]:
    sim = counts.get(VotoOpcaoEnum.SIM, 0)
    nao = counts.get(VotoOpcaoEnum.NAO, 0)
    obstrucao = counts.get(VotoOpcaoEnum.OBSTRUCAO, 0)
    abst = counts.get(VotoOpcaoEnum.ABSTENCAO, 0) + obstrucao
    return {
        "SIM": sim,
        "NAO": nao,
        "ABSTENCAO": abst,
        "TOTAL": sim + nao + abst,
        "OBSTRUCAO": obstrucao,
        "AUSENTE": counts.get(VotoOpcaoEnum.AUSENTE, 0),
    }


def _session_tallies(db: Session, *conditions) -> Dict[uuid.UUID, Dict[str, int]]:
    """Contagem de votos por sessão em UMA consulta (evita N+1)."""
    rows = (
        db.query(ParliamentaryVote.voting_session_id, ParliamentaryVote.vote_choice, func.count(ParliamentaryVote.id))
        .join(VotingSession, ParliamentaryVote.voting_session_id == VotingSession.id)
        .filter(*conditions)
        .group_by(ParliamentaryVote.voting_session_id, ParliamentaryVote.vote_choice)
        .all()
    )
    grouped: Dict[uuid.UUID, Dict[VotoOpcaoEnum, int]] = defaultdict(dict)
    for sid, choice, qty in rows:
        grouped[sid][choice] = qty
    return {sid: _placar_from_counts(c) for sid, c in grouped.items()}


def _build_house_placar(sessions: List[VotingSession], tallies: Dict[uuid.UUID, Dict[str, int]]) -> tuple:
    """
    Devolve (placar_principal, sessao_principal, detalhes_de_todas_as_sessoes).
    A sessão principal é a de maior quórum nominal (desempate: aprovada, depois a mais recente), e não
    simplesmente a mais recente: uma votação de destaque com poucos votos não deve substituir a de mérito.
    """
    if not sessions:
        return dict(EMPTY_PLACAR), None, []

    def total_of(s: VotingSession) -> int:
        t = tallies.get(s.id)
        if t and t.get("TOTAL", 0) > 0:
            return t["TOTAL"]
        return (
            (s.votes_yes_count or 0)
            + (s.votes_no_count or 0)
            + (s.votes_abstain_count or 0)
            + (s.votes_obstruction_count or 0)
        )

    ordered = sorted(sessions, key=lambda s: (total_of(s), 1 if s.is_approved else 0, s.session_datetime), reverse=True)
    details = []
    for s in ordered:
        placar = tallies.get(s.id)
        if (not placar or placar.get("TOTAL", 0) == 0) and (s.votes_yes_count or s.votes_no_count or s.is_secret_vote):
            abst = (s.votes_abstain_count or 0) + (s.votes_obstruction_count or 0)
            placar = {
                "SIM": s.votes_yes_count or 0,
                "NAO": s.votes_no_count or 0,
                "ABSTENCAO": abst,
                "TOTAL": (s.votes_yes_count or 0) + (s.votes_no_count or 0) + abst,
                "OBSTRUCAO": s.votes_obstruction_count or 0,
                "AUSENTE": 0,
            }
        details.append(
            {
                "sessao_id": str(s.id),
                "external_id": s.external_id,
                "data_hora": s.session_datetime.isoformat(),
                "titulo": s.agenda_title,
                "descricao": s.detailed_description or s.agenda_title,
                "aprovada": s.is_approved,
                "is_votacao_secreta": s.is_secret_vote,
                "placar": placar or dict(EMPTY_PLACAR),
            }
        )

    best = ordered[0]
    best_session = {
        "sessao_id": str(best.id),
        "data_hora": best.session_datetime.isoformat(),
        "titulo": best.agenda_title,
        "descricao": best.detailed_description or best.agenda_title,
        "aprovada": best.is_approved,
        "is_votacao_secreta": best.is_secret_vote,
    }
    return details[0]["placar"], best_session, details


def _mandate_context(
    db: Session, politician_ids: List[uuid.UUID], ref_date: Optional[date] = None
) -> Dict[uuid.UUID, Tuple[str, str]]:
    """
    (UF, cargo) por político. Escolhe o mandato vigente na data de referência; sem ele, o mais recente.
    Não existe valor padrão inventado: político sem mandato simplesmente não aparece no mapa.
    """
    if not politician_ids:
        return {}
    rows = (
        db.query(
            Mandate.politician_id, Mandate.jurisdiction_state, Mandate.office, Mandate.start_date, Mandate.end_date
        )
        .filter(Mandate.politician_id.in_(politician_ids))
        .order_by(Mandate.start_date.desc())
        .all()
    )
    result: Dict[uuid.UUID, Tuple[str, str]] = {}
    covering: set = set()
    for pid, uf, office, start, end in rows:
        is_covering = bool(
            ref_date and start and start <= ref_date and (end is None or end >= ref_date)  # mandato na data
        )
        if pid not in result or (is_covering and pid not in covering):
            result[pid] = (uf, office.value)
        if is_covering:
            covering.add(pid)
    return result


def _resolve_proposition(db: Session, prop_id: str) -> Proposition:
    """Resolve por UUID ou por ID externo (Câmara/Senado). Número de matéria NÃO identifica: não é único."""
    try:
        prop = db.query(Proposition).filter(Proposition.id == uuid.UUID(prop_id)).first()
        if prop:
            return prop
    except ValueError:
        pass

    if prop_id.isdigit():
        num_val = int(prop_id)
        prop = (
            db.query(Proposition)
            .filter(or_(Proposition.external_camara_id == num_val, Proposition.external_senado_id == num_val))
            .order_by(Proposition.external_camara_id.is_(None), Proposition.presentation_date.desc())
            .first()
        )
        if prop:
            return prop

    raise HTTPException(status_code=404, detail=f"Proposição '{prop_id}' não encontrada.")


def _parse_house(house: Optional[str]) -> Optional[CasaLegislativaEnum]:
    if _is_filter_all(house):
        return None
    key = house.strip().upper()
    if key.startswith("CAMARA"):
        return CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS
    if key.startswith("SENADO"):
        return CasaLegislativaEnum.SENADO_FEDERAL
    raise HTTPException(status_code=422, detail="Casa inválida. Use CAMARA ou SENADO.")


def _parse_enum(enum_cls, value: Optional[str], label: str):
    if _is_filter_all(value):
        return None
    try:
        return enum_cls[value.strip().upper()]
    except KeyError:
        valid = ", ".join(e.name for e in enum_cls)
        raise HTTPException(status_code=422, detail=f"{label} inválido '{value}'. Valores aceitos: {valid}.")


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
    sessions_by_prop: Dict[uuid.UUID, List[VotingSession]] = defaultdict(list)
    tallies: Dict[uuid.UUID, Dict[str, int]] = {}
    try:
        total = db.query(func.count(Proposition.id)).scalar() or 0
        has_session = exists().where(VotingSession.proposition_id == Proposition.id)
        props = (
            db.query(Proposition)
            .order_by(has_session.desc(), Proposition.presentation_date.desc(), Proposition.id)
            .offset(offset)
            .limit(limit)
            .all()
            if total
            else []
        )
        if props:
            prop_ids = [p.id for p in props]
            for s in db.query(VotingSession).filter(VotingSession.proposition_id.in_(prop_ids)).all():
                sessions_by_prop[s.proposition_id].append(s)
            tallies = _session_tallies(db, VotingSession.proposition_id.in_(prop_ids))
    except SQLAlchemyError as e:
        logger.error("Falha ao consultar proposições no banco: %s", e)
        raise HTTPException(status_code=503, detail="Banco de dados indisponível.")

    if props:
        response.headers["X-Total-Count"] = str(total)
        result = []
        for p in props:
            sessoes = sessions_by_prop.get(p.id, [])
            sessoes_camara = [s for s in sessoes if s.legislative_house == CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS]
            sessoes_senado = [s for s in sessoes if s.legislative_house == CasaLegislativaEnum.SENADO_FEDERAL]

            placar_camara, sessao_camara, lista_camara = _build_house_placar(sessoes_camara, tallies)
            placar_senado, sessao_senado, lista_senado = _build_house_placar(sessoes_senado, tallies)

            # Placar consolidado padrão (prioriza a casa onde houve votação com quórum)
            if placar_camara["TOTAL"] > 0:
                default_placar, default_sessao = placar_camara, sessao_camara
            elif placar_senado["TOTAL"] > 0:
                default_placar, default_sessao = placar_senado, sessao_senado
            else:
                default_placar, default_sessao = dict(EMPTY_PLACAR), None

            author_display = p.author_name or (
                "Poder Executivo" if p.is_executive_initiative else "Comissão / Parlamentares"
            )

            result.append(
                {
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
                    "url_oficial": _official_url(p),
                }
            )
        return result

    if total:
        # Há dados no banco, mas a página pedida está além do fim
        response.headers["X-Total-Count"] = str(total)
        return []

    return _propositions_from_local_files(response)


def _propositions_from_local_files(response: Response) -> List[Dict[str, Any]]:
    """Fallback de desenvolvimento: banco vazio (ainda não carregado). Dados do arquivo do ETL, sem datas inventadas."""
    prop_file = DATA_DIR / "proposicoes_2023.json"
    sess_file = DATA_DIR / "sessoes_votacao_2023.json"
    votos_file = DATA_DIR / "votos_nominais_2023.json"

    if not prop_file.exists():
        response.headers["X-Total-Count"] = "0"
        return []

    with open(prop_file, "r", encoding="utf-8") as f:
        proposicoes = json.load(f)

    sessoes_dict = {}
    if sess_file.exists():
        with open(sess_file, "r", encoding="utf-8") as f:
            for s in json.load(f):
                if s.get("proposicao_camara_id") is not None:
                    sessoes_dict[s["proposicao_camara_id"]] = s

    votos_contagem: Dict[Any, Dict[str, int]] = {}
    if votos_file.exists():
        with open(votos_file, "r", encoding="utf-8") as f:
            for v in json.load(f):
                pid = v.get("proposicao_camara_id")
                if pid is None:
                    continue
                counts = votos_contagem.setdefault(pid, {"SIM": 0, "NAO": 0, "ABSTENCAO": 0, "TOTAL": 0})
                opcao = v.get("voto", "OUTROS")
                if opcao in ("SIM", "NAO", "ABSTENCAO", "OBSTRUCAO"):
                    counts["ABSTENCAO" if opcao == "OBSTRUCAO" else opcao] += 1
                    counts["TOTAL"] += 1

    result = []
    for p in proposicoes:
        cid = p.get("camara_id")
        if cid is None:
            continue
        result.append(
            {
                "id": str(cid),
                "camara_id": cid,
                "tipo": p.get("tipo"),
                "numero": p.get("numero"),
                "ano": p.get("ano"),
                "titulo": p.get("titulo"),
                "ementa": p.get("ementa"),
                "autor_nome": p.get("autor_nome") or ("Poder Executivo" if p.get("iniciativa_executivo") else None),
                "area_tematica": p.get("area_tematica"),
                "data_apresentacao": p.get("data_apresentacao"),
                "status": p.get("status"),
                "is_reforma_estrutural": p.get("is_reforma_estrutural", False),
                "iniciativa_executivo": p.get("iniciativa_executivo", False),
                "placar": votos_contagem.get(cid, dict(EMPTY_PLACAR)),
                "sessao": sessoes_dict.get(cid),
            }
        )
    response.headers["X-Total-Count"] = str(len(result))
    return result


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
    prop = _resolve_proposition(db, prop_id)
    house_enum = _parse_house(house)
    choice_enum = _parse_enum(VotoOpcaoEnum, vote_choice, "Voto")

    sessions_query = db.query(VotingSession).filter(VotingSession.proposition_id == prop.id)
    if house_enum:
        sessions_query = sessions_query.filter(VotingSession.legislative_house == house_enum)

    all_house_sessions = sessions_query.order_by(VotingSession.session_datetime.desc()).all()
    if not all_house_sessions:
        return {
            "proposicao": {
                "id": str(prop.id),
                "titulo": prop.title,
                "numero": prop.number,
                "ano": prop.year,
                "autor_nome": prop.author_name or ("Poder Executivo" if prop.is_executive_initiative else None),
            },
            "sessoes_disponiveis": [],
            "sessao_ativa": None,
            "total": 0,
            "votos": [],
        }

    sessoes_disponiveis = [
        {
            "id": str(s.id),
            "titulo": s.agenda_title,
            "data_hora": s.session_datetime.isoformat(),
            "casa": s.legislative_house.value,
            "aprovada": s.is_approved,
            "is_votacao_secreta": s.is_secret_vote,
        }
        for s in all_house_sessions
    ]

    selected_session = None
    if session_id:
        try:
            sess_uuid = uuid.UUID(session_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail="session_id inválido.")
        selected_session = next((s for s in all_house_sessions if s.id == sess_uuid), None)
        if not selected_session:
            raise HTTPException(status_code=404, detail="Sessão não pertence a esta proposição/casa.")

    if not selected_session:
        # Sessão de maior quórum, calculada em uma única consulta agregada
        tallies = _session_tallies(db, VotingSession.id.in_([s.id for s in all_house_sessions]))
        selected_session = max(
            all_house_sessions,
            key=lambda s: (
                tallies.get(s.id, EMPTY_PLACAR)["TOTAL"] or ((s.votes_yes_count or 0) + (s.votes_no_count or 0)),
                s.session_datetime,
            ),
        )

    if selected_session.is_secret_vote:
        abst = (selected_session.votes_abstain_count or 0) + (selected_session.votes_obstruction_count or 0)
        placar_secreto = {
            "SIM": selected_session.votes_yes_count or 0,
            "NAO": selected_session.votes_no_count or 0,
            "ABSTENCAO": abst,
            "TOTAL": (selected_session.votes_yes_count or 0) + (selected_session.votes_no_count or 0) + abst,
            "OBSTRUCAO": selected_session.votes_obstruction_count or 0,
            "AUSENTE": 0,
        }
        return {
            "proposicao": {
                "id": str(prop.id),
                "titulo": prop.title,
                "numero": prop.number,
                "ano": prop.year,
                "autor_nome": prop.author_name or ("Poder Executivo" if prop.is_executive_initiative else None),
                "area_tematica": prop.thematic_area,
            },
            "sessao_ativa": {
                "id": str(selected_session.id),
                "titulo": selected_session.agenda_title,
                "descricao": selected_session.detailed_description or selected_session.agenda_title,
                "data_hora": selected_session.session_datetime.isoformat(),
                "casa": selected_session.legislative_house.value,
                "aprovada": selected_session.is_approved,
                "is_votacao_secreta": True,
                "placar": placar_secreto,
            },
            "sessoes_disponiveis": sessoes_disponiveis,
            "is_votacao_secreta": True,
            "aviso": "Votação secreta: conforme o Regimento Interno do Senado Federal, os votos individuais não são divulgados nominalmente. O resultado oficial acima reflete a apuração agregada da urna.",
            "placar": placar_secreto,
            "total": placar_secreto["TOTAL"],
            "total_correspondente": placar_secreto["TOTAL"],
            "truncado": False,
            "votos": [],
        }

    votes_query = (
        db.query(ParliamentaryVote, Politician, PoliticalParty, VotingSession)
        .join(Politician, ParliamentaryVote.politician_id == Politician.id)
        .outerjoin(PoliticalParty, ParliamentaryVote.party_id == PoliticalParty.id)
        .join(VotingSession, ParliamentaryVote.voting_session_id == VotingSession.id)
        .filter(ParliamentaryVote.voting_session_id == selected_session.id)
    )

    if choice_enum:
        votes_query = votes_query.filter(ParliamentaryVote.vote_choice == choice_enum)

    if search and search.strip():
        votes_query = votes_query.filter(
            or_(_contains(Politician.electoral_name, search), _contains(PoliticalParty.acronym, search))
        )

    total_matching = votes_query.count()
    raw_results = votes_query.order_by(Politician.electoral_name.asc(), Politician.id).limit(MAX_NOMINAL_VOTES).all()

    session_date = _to_brt(selected_session.session_datetime).date()
    context = _mandate_context(db, [p.id for _, p, _, _ in raw_results], session_date)
    fallback_cargo = (
        "DEPUTADO_FEDERAL"
        if selected_session.legislative_house == CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS
        else "SENADOR"
    )

    items = []
    for vote, pol, party, sess in raw_results:
        uf, cargo = context.get(pol.id, (None, fallback_cargo))
        items.append(
            {
                "voto_id": str(vote.id),
                "politico_id": str(pol.id),
                "nome_eleitoral": pol.electoral_name,
                "nome_civil": pol.civil_name,
                "partido_sigla": party.acronym if party else "S.PART.",
                "uf": uf,
                "cargo": cargo,
                "foto_url": pol.photo_url,
                "decisao": vote.vote_choice.value,
                "sessao_id": str(sess.id),
                "sessao_titulo": sess.agenda_title,
                "casa_legislativa": sess.legislative_house.value,
                "data_sessao": sess.session_datetime.isoformat(),
            }
        )

    return {
        "proposicao": {
            "id": str(prop.id),
            "titulo": prop.title,
            "numero": prop.number,
            "ano": prop.year,
            "autor_nome": prop.author_name or ("Poder Executivo" if prop.is_executive_initiative else None),
            "area_tematica": prop.thematic_area,
        },
        "sessao_ativa": {
            "id": str(selected_session.id),
            "titulo": selected_session.agenda_title,
            "descricao": selected_session.detailed_description or selected_session.agenda_title,
            "data_hora": selected_session.session_datetime.isoformat(),
            "casa": selected_session.legislative_house.value,
            "aprovada": selected_session.is_approved,
        },
        "sessoes_disponiveis": sessoes_disponiveis,
        "total": len(items),
        "total_correspondente": total_matching,
        "truncado": total_matching > len(items),
        "votos": items,
    }


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
    Retorna o ranking de produtividade parlamentar com metodologia ponderada de 4 pilares:
    - Ponderação por Papel: Autor Principal (1.0x) vs Coautor (0.2x) vs Produção Institucional (isolada).
    - Complexidade: Alta (PEC, peso 3.0), Média (PL/PLP/MPV, peso 2.0), Baixa (PDL/Resoluções, peso 1.0).
    - Tramitação: Sucesso legislativo (leis aprovadas/promulgadas +6 pts, avanço em votação 1.5x).
    - Critérios de ordenação: 'efetividade' (Score Ponderado), 'lideranca' (Autores Principais), 'coautoria' (Apoio Político), 'volume' (Total Bruto).
    """
    crit_clean = criterio.lower().strip()
    valid_criterios = ("efetividade", "volume", "lideranca", "coautoria")
    if crit_clean not in valid_criterios:
        raise HTTPException(status_code=422, detail=f"Critério inválido. Use um de: {', '.join(valid_criterios)}.")

    has_authors_detail = (db.query(func.count(PropositionAuthor.id)).scalar() or 0) > 0

    if has_authors_detail:
        query = db.query(
            PropositionAuthor.politician_id.label("author_id"),
            func.count(Proposition.id).label("total_props"),
            func.sum(case((PropositionAuthor.authorship_type == TipoAutoriaEnum.AUTOR_PRINCIPAL, 1), else_=0)).label(
                "lideranca"
            ),
            func.sum(case((PropositionAuthor.authorship_type == TipoAutoriaEnum.COAUTOR, 1), else_=0)).label(
                "coautoria"
            ),
            func.sum(
                case(
                    (
                        Proposition.status.in_(
                            [
                                StatusTramitacaoEnum.APROVADA_E_SANCIONADA,
                                StatusTramitacaoEnum.APROVADA_E_PROMULGADA,
                            ]
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("aprovadas"),
            func.sum(
                case(
                    (Proposition.is_structural_reform.is_(True), 1),
                    (
                        Proposition.proposition_type.in_([TipoProposicaoEnum.PEC, TipoProposicaoEnum.PLP]),
                        1,
                    ),
                    else_=0,
                )
            ).label("estruturantes"),
            func.sum(
                case(
                    (
                        and_(
                            PropositionAuthor.authorship_type == TipoAutoriaEnum.AUTOR_PRINCIPAL,
                            Proposition.proposition_type == TipoProposicaoEnum.PEC,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("pec_lider"),
            func.sum(
                case(
                    (
                        and_(
                            PropositionAuthor.authorship_type == TipoAutoriaEnum.COAUTOR,
                            Proposition.proposition_type == TipoProposicaoEnum.PEC,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("pec_coautor"),
            func.sum(
                case(
                    (
                        and_(
                            PropositionAuthor.authorship_type == TipoAutoriaEnum.AUTOR_PRINCIPAL,
                            Proposition.proposition_type.in_(
                                [TipoProposicaoEnum.PL, TipoProposicaoEnum.PLP, TipoProposicaoEnum.MPV]
                            ),
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("pl_lider"),
            func.sum(
                case(
                    (
                        and_(
                            PropositionAuthor.authorship_type == TipoAutoriaEnum.COAUTOR,
                            Proposition.proposition_type.in_(
                                [TipoProposicaoEnum.PL, TipoProposicaoEnum.PLP, TipoProposicaoEnum.MPV]
                            ),
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("pl_coautor"),
        ).join(Proposition, PropositionAuthor.proposition_id == Proposition.id)
        query = query.filter(
            PropositionAuthor.politician_id.isnot(None),
            PropositionAuthor.authorship_type != TipoAutoriaEnum.INSTITUCIONAL,
        )
        filter_author_col = PropositionAuthor.politician_id
    else:
        query = db.query(
            Proposition.author_politician_id.label("author_id"),
            func.count(Proposition.id).label("total_props"),
            func.count(Proposition.id).label("lideranca"),
            literal(0).label("coautoria"),
            func.sum(
                case(
                    (
                        Proposition.status.in_(
                            [
                                StatusTramitacaoEnum.APROVADA_E_SANCIONADA,
                                StatusTramitacaoEnum.APROVADA_E_PROMULGADA,
                            ]
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("aprovadas"),
            func.sum(
                case(
                    (Proposition.is_structural_reform.is_(True), 1),
                    (
                        Proposition.proposition_type.in_([TipoProposicaoEnum.PEC, TipoProposicaoEnum.PLP]),
                        1,
                    ),
                    else_=0,
                )
            ).label("estruturantes"),
            func.sum(case((Proposition.proposition_type == TipoProposicaoEnum.PEC, 1), else_=0)).label("pec_lider"),
            literal(0).label("pec_coautor"),
            func.sum(
                case(
                    (
                        Proposition.proposition_type.in_(
                            [TipoProposicaoEnum.PL, TipoProposicaoEnum.PLP, TipoProposicaoEnum.MPV]
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("pl_lider"),
            literal(0).label("pl_coautor"),
        ).filter(Proposition.author_politician_id.isnot(None))
        filter_author_col = Proposition.author_politician_id

    if not _is_filter_all(setor):
        clean_setor = setor.strip()
        termo_principal = clean_setor.split("&")[0].split("/")[0].strip()
        conditions = [_contains(Proposition.thematic_area, clean_setor)]
        if termo_principal and termo_principal != clean_setor:
            conditions.append(_contains(Proposition.thematic_area, termo_principal))
        query = query.filter(or_(*conditions))

    if not _is_filter_all(partido):
        clean_partido = partido.strip().upper()
        matching_party_ids = db.query(PoliticalParty.id).filter(func.upper(PoliticalParty.acronym) == clean_partido)
        pols_mandate = db.query(Mandate.politician_id).filter(
            Mandate.party_id.in_(matching_party_ids), _current_mandate_clause()
        )
        pols_aff = db.query(PartyAffiliation.politician_id).filter(
            PartyAffiliation.party_id.in_(matching_party_ids), PartyAffiliation.is_current.is_(True)
        )
        query = query.filter(
            or_(
                filter_author_col.in_(pols_mandate),
                filter_author_col.in_(pols_aff),
            )
        )

    all_authors = query.group_by(filter_author_col).all()

    if not all_authors:
        return []

    # Calcular Score Ponderado para cada parlamentar
    scored_authors = []
    for row in all_authors:
        aid = row.author_id
        total_val = int(row.total_props or 0)
        lider_val = int(row.lideranca or 0)
        coaut_val = int(row.coautoria or 0)
        apr_val = int(row.aprovadas or 0)
        est_val = int(row.estruturantes or 0)
        pec_lid = int(row.pec_lider or 0)
        pec_coa = int(row.pec_coautor or 0)
        pl_lid = int(row.pl_lider or 0)
        pl_coa = int(row.pl_coautor or 0)

        outros_lid = max(0, lider_val - pec_lid - pl_lid)
        outros_coa = max(0, coaut_val - pec_coa - pl_coa)

        if has_authors_detail:
            # Fórmula de Atividade Ponderada:
            # Liderança (Autor Principal): PEC (+3.0 pts), PL/PLP (+2.0 pts), Outros (+1.0 pt), Leis Aprovadas (+6.0 pts)
            # Apoio Político (Coautor): PEC (+0.6 pt), PL/PLP (+0.4 pt), Outros (+0.2 pt)
            pts_lider = (pec_lid * 3.0) + (pl_lid * 2.0) + (outros_lid * 1.0) + (apr_val * 6.0)
            pts_coaut = (pec_coa * 0.6) + (pl_coa * 0.4) + (outros_coa * 0.2)
            score = round(pts_lider + pts_coaut, 1)
        else:
            # Compatibilidade com fórmula IPLE padrão caso a tabela detalhada esteja ausente
            score = min(
                100.0,
                round((apr_val * 15.0) + (est_val * 4.0) + (min(total_val, 50) * 0.6), 1),
            )

        taxa_eficiencia = round((apr_val / max(lider_val, 1)) * 100, 1) if lider_val > 0 else 0.0

        if apr_val >= 2:
            diag = "Alta Eficácia Legislativa"
        elif apr_val >= 1:
            diag = "Média Eficácia"
        elif lider_val >= 20 and apr_val == 0:
            diag = "Volume Alto sem Leis Aprovadas"
        elif coaut_val > lider_val * 2:
            diag = "Articulação & Apoio Político"
        elif lider_val >= 10:
            diag = "Liderança Propositiva"
        else:
            diag = "Em Tramitação"

        scored_authors.append(
            {
                "author_id": aid,
                "total_props": total_val,
                "autoria_principal_count": lider_val,
                "coautoria_count": coaut_val,
                "aprovadas": apr_val,
                "estruturantes": est_val,
                "taxa_eficiencia_pct": taxa_eficiencia,
                "score": score,
                "diagnostico": diag,
            }
        )

    # Ordenação por critério (desempate determinístico pelo ID do autor)
    if crit_clean == "volume":
        scored_authors.sort(key=lambda x: (x["total_props"], x["score"], str(x["author_id"])), reverse=True)
    elif crit_clean == "lideranca":
        scored_authors.sort(
            key=lambda x: (x["autoria_principal_count"], x["score"], x["total_props"], str(x["author_id"])),
            reverse=True,
        )
    elif crit_clean == "coautoria":
        scored_authors.sort(
            key=lambda x: (x["coautoria_count"], x["score"], x["total_props"], str(x["author_id"])), reverse=True
        )
    else:
        scored_authors.sort(
            key=lambda x: (
                x["score"],
                x["aprovadas"],
                x["autoria_principal_count"],
                x["estruturantes"],
                x["total_props"],
                str(x["author_id"]),
            ),
            reverse=True,
        )

    author_counts = scored_authors[:limit]
    politician_ids = [a["author_id"] for a in author_counts]
    politicians = {p.id: p for p in db.query(Politician).filter(Politician.id.in_(politician_ids)).all()}

    # Mandato mais recente de cada autor
    mandates = (
        db.query(Mandate).filter(Mandate.politician_id.in_(politician_ids)).order_by(Mandate.start_date.asc()).all()
    )
    mandate_map: Dict[uuid.UUID, Mandate] = {}
    for m in mandates:  # ordem crescente: o último sobrescreve e fica com o mais recente
        mandate_map[m.politician_id] = m

    current_affs = (
        db.query(PartyAffiliation)
        .filter(
            PartyAffiliation.politician_id.in_(politician_ids),
            PartyAffiliation.is_current.is_(True),
        )
        .all()
    )
    aff_map = {aff.politician_id: aff for aff in current_affs}

    party_ids = list(
        set(
            [m.party_id for m in mandate_map.values() if m.party_id]
            + [a.party_id for a in aff_map.values() if a.party_id]
        )
    )
    parties = {p.id: p for p in db.query(PoliticalParty).filter(PoliticalParty.id.in_(party_ids)).all()}

    if has_authors_detail:
        sector_rows = (
            db.query(
                PropositionAuthor.politician_id,
                Proposition.thematic_area,
                func.count(Proposition.id).label("total_setor"),
            )
            .join(Proposition, PropositionAuthor.proposition_id == Proposition.id)
            .filter(PropositionAuthor.politician_id.in_(politician_ids))
            .group_by(PropositionAuthor.politician_id, Proposition.thematic_area)
            .order_by(PropositionAuthor.politician_id, desc("total_setor"))
            .all()
        )
    else:
        sector_rows = (
            db.query(
                Proposition.author_politician_id,
                Proposition.thematic_area,
                func.count(Proposition.id).label("total_setor"),
            )
            .filter(Proposition.author_politician_id.in_(politician_ids))
            .group_by(Proposition.author_politician_id, Proposition.thematic_area)
            .order_by(Proposition.author_politician_id, desc("total_setor"))
            .all()
        )

    sectors_by_author: Dict[uuid.UUID, List[Tuple[str, int]]] = {}
    for aid, st, cnt in sector_rows:
        sectors_by_author.setdefault(aid, []).append((st or "Geral", cnt))

    ranking = []
    for idx, item in enumerate(author_counts, start=1):
        pol_id = item["author_id"]
        pol = politicians.get(pol_id)
        if not pol:
            continue

        mand = mandate_map.get(pol_id)
        aff = aff_map.get(pol_id)
        party = parties.get(mand.party_id) if (mand and mand.party_id) else (parties.get(aff.party_id) if aff else None)
        partido_sigla = party.acronym if party else "S.PART."
        espectro = party.political_spectrum.value if (party and party.political_spectrum) else None

        author_sectors = sectors_by_author.get(pol_id, [])
        principal_setor = author_sectors[0][0] if author_sectors else "Geral"
        total_principal = author_sectors[0][1] if author_sectors else item["total_props"]

        distribuicao = [
            {
                "setor": st,
                "total": cnt,
                "percentual": (round((cnt / item["total_props"]) * 100, 1) if item["total_props"] > 0 else 0),
            }
            for st, cnt in author_sectors
        ]

        ranking.append(
            {
                "posicao": idx,
                "politico_id": str(pol.id),
                "nome_eleitoral": pol.electoral_name,
                "nome_civil": pol.civil_name,
                "partido_sigla": partido_sigla,
                "espectro_politico": espectro,
                "uf": mand.jurisdiction_state if mand else None,
                "cargo": mand.office.value if mand else None,
                "foto_url": pol.photo_url,
                "total_proposicoes": item["total_props"],
                "autoria_principal_count": item["autoria_principal_count"],
                "coautoria_count": item["coautoria_count"],
                "proposicoes_aprovadas": item["aprovadas"],
                "proposicoes_estruturantes": item["estruturantes"],
                "taxa_eficiencia_pct": item["taxa_eficiencia_pct"],
                "score_produtividade": item["score"],
                "score_ponderado": item["score"],
                "score_ialp": item["score"],
                "desvio_foco": {
                    "estruturais": item["estruturantes"],
                    "burocraticas": max(0, item["total_props"] - item["estruturantes"]),
                    "proporcao_estrutural_pct": round((item["estruturantes"] / item["total_props"]) * 100, 1) if item["total_props"] > 0 else 0.0,
                },
                "classificacao_efetividade": item["diagnostico"],
                "principal_setor": principal_setor,
                "total_principal_setor": total_principal,
                "distribuicao_setores": distribuicao,
            }
        )

    return ranking


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
    pol = db.query(Politician).filter(Politician.id == politician_id).first()
    if not pol:
        raise HTTPException(status_code=404, detail="Parlamentar não encontrado.")
    metrics = get_politician_ialp_metrics(politician_id, db)
    return {
        "politician_id": str(politician_id),
        "nome_eleitoral": pol.electoral_name,
        "foto_url": pol.photo_url,
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
    tipo_enum = _parse_enum(TipoProposicaoEnum, tipo, "Tipo")
    status_enum = _parse_enum(StatusTramitacaoEnum, status, "Status")

    query = db.query(Proposition)

    if search and search.strip():
        query = query.filter(
            or_(
                _contains(Proposition.title, search),
                _contains(Proposition.summary, search),
                _contains(Proposition.author_name, search),
                _contains(Proposition.thematic_area, search),
            )
        )

    if not _is_filter_all(setor):
        query = query.filter(_contains(Proposition.thematic_area, setor))

    if not _is_filter_all(partido):
        clean_partido = partido.strip().upper()
        if clean_partido in {"GOV", "GOVERNO", "PODER EXECUTIVO"}:
            query = query.filter(Proposition.is_executive_initiative.is_(True))
        elif clean_partido in {"S.PART.", "SEM PARTIDO"}:
            query = query.filter(
                and_(
                    Proposition.author_politician_id.is_(None),
                    Proposition.is_executive_initiative.is_(False),
                )
            )
        else:
            party_ids = db.query(PoliticalParty.id).filter(func.upper(PoliticalParty.acronym) == clean_partido)
            pols = db.query(Mandate.politician_id).filter(Mandate.party_id.in_(party_ids))
            query = query.filter(
                or_(
                    Proposition.author_politician_id.in_(pols),
                    exists().where(
                        and_(
                            PropositionAuthor.proposition_id == Proposition.id,
                            PropositionAuthor.politician_id.in_(pols),
                            PropositionAuthor.authorship_type == TipoAutoriaEnum.AUTOR_PRINCIPAL,
                        )
                    ),
                    Proposition.author_name.ilike(f"%({clean_partido}/%"),
                    Proposition.author_name.ilike(f"%/{clean_partido})%"),
                )
            )

    if tipo_enum:
        query = query.filter(Proposition.proposition_type == tipo_enum)

    if status_enum:
        query = query.filter(Proposition.status == status_enum)

    if apenas_votadas:
        # EXISTS evita a duplicação de linhas de um JOIN com várias sessões por proposição
        query = query.filter(exists().where(VotingSession.proposition_id == Proposition.id))

    total_items = query.count()

    todos_setores = [
        row[0]
        for row in db.query(Proposition.thematic_area)
        .filter(Proposition.thematic_area.isnot(None))
        .distinct()
        .order_by(Proposition.thematic_area.asc())
        .all()
    ]

    offset = (page - 1) * limit
    proposicoes = (
        query.order_by(Proposition.presentation_date.desc(), Proposition.number.desc(), Proposition.id)
        .offset(offset)
        .limit(limit)
        .all()
    )

    prop_ids = [p.id for p in proposicoes]
    author_ids = [p.author_politician_id for p in proposicoes if p.author_politician_id]
    politicians = {p.id: p for p in db.query(Politician).filter(Politician.id.in_(author_ids)).all()}
    mandates = db.query(Mandate).filter(Mandate.politician_id.in_(author_ids)).order_by(Mandate.start_date.asc()).all()
    mandate_map: Dict[uuid.UUID, Mandate] = {}
    for m in mandates:
        mandate_map[m.politician_id] = m
    party_ids = [m.party_id for m in mandate_map.values() if m.party_id]
    parties = {p.id: p for p in db.query(PoliticalParty).filter(PoliticalParty.id.in_(party_ids)).all()}

    sessions_by_prop: Dict[uuid.UUID, List[VotingSession]] = defaultdict(list)
    tallies: Dict[uuid.UUID, Dict[str, int]] = {}
    delibs_by_prop: Dict[uuid.UUID, List[Any]] = defaultdict(list)
    if prop_ids:
        for s in db.query(VotingSession).filter(VotingSession.proposition_id.in_(prop_ids)).all():
            sessions_by_prop[s.proposition_id].append(s)
        tallies = _session_tallies(db, VotingSession.proposition_id.in_(prop_ids))

        from app.models.legislative import VotacaoProposicao
        for vp in (
            db.query(VotacaoProposicao)
            .filter(VotacaoProposicao.proposicao_id.in_(prop_ids))
            .order_by(VotacaoProposicao.data_hora.desc())
            .all()
        ):
            delibs_by_prop[vp.proposicao_id].append(vp)

    items = []
    for p in proposicoes:
        placar, sessao, _ = _build_house_placar(sessions_by_prop.get(p.id, []), tallies)
        tem_votacao = placar["TOTAL"] > 0

        autor_pol = politicians.get(p.author_politician_id) if p.author_politician_id else None
        autor_mand = mandate_map.get(p.author_politician_id) if p.author_politician_id else None
        autor_party = parties.get(autor_mand.party_id) if (autor_mand and autor_mand.party_id) else None

        if autor_party:
            partido_sigla = autor_party.acronym
        elif p.is_executive_initiative:
            partido_sigla = "GOV"
        elif p.author_name:
            m = _PARTY_SIGLA_RE.search(p.author_name)
            partido_sigla = m.group(1).strip() if m else "S.PART."
        else:
            partido_sigla = "S.PART."
        autor_display = p.author_name or (
            autor_pol.electoral_name
            if autor_pol
            else ("Poder Executivo" if p.is_executive_initiative else "Parlamentar")
        )

        peso_comp = PESO_COMPLEXIDADE.get(p.proposition_type, 1.0)
        mult_tram = MULTIPLICADOR_TRAMITACAO.get(p.status, 1.0)

        resultado_str = "EM_TRAMITACAO"
        if sessao:
            resultado_str = "APROVADA" if sessao.get("aprovada") else "REJEITADA"
        elif p.status.value in ("APROVADA_E_SANCIONADA", "APROVADA_E_PROMULGADA"):
            resultado_str = "APROVADA"

        prop_delibs = delibs_by_prop.get(p.id, [])
        tipo_delib = prop_delibs[0].tipo_deliberacao if prop_delibs else ("NOMINAL" if tem_votacao else None)
        total_delib = len(prop_delibs) or (1 if tem_votacao else 0)

        items.append(
            {
                "id": str(p.id),
                "tipo_deliberacao": tipo_delib,
                "total_deliberacoes": total_delib,
                "camara_id": p.external_camara_id,
                "tipo": p.proposition_type.value,
                "numero": p.number,
                "ano": p.year,
                "titulo": p.title,
                "ementa": p.summary,
                "setor": p.thematic_area or "Não classificado",
                "eixo_impacto": p.impact_axis or "Geral",
                "autor_nome": autor_display,
                "autor_politico_id": (str(p.author_politician_id) if p.author_politician_id else None),
                "autor_partido": partido_sigla,
                "autor_uf": autor_mand.jurisdiction_state if autor_mand else None,
                "autor_foto": autor_pol.photo_url if autor_pol else None,
                "status": p.status.value,
                "data_apresentacao": p.presentation_date.isoformat(),
                "is_reforma_estrutural": p.is_structural_reform,
                "iniciativa_executivo": p.is_executive_initiative,
                "peso_complexidade": peso_comp,
                "multiplicador_tramitacao": mult_tram,
                "score_base": round(peso_comp * mult_tram, 2),
                "url_oficial": _official_url(p),
                "tem_votacao": tem_votacao,
                "sessao_id": sessao["sessao_id"] if sessao else None,
                "placar": {
                    "sim": placar["SIM"],
                    "nao": placar["NAO"],
                    "abstencao": placar["ABSTENCAO"],
                    "total": placar["TOTAL"],
                    "resultado": resultado_str,
                },
            }
        )

    return {
        "total": total_items,
        "page": page,
        "limit": limit,
        "total_pages": math.ceil(total_items / limit) if total_items > 0 else 1,
        "setores_disponiveis": todos_setores,
        "items": items,
    }


@router.get("/propositions/{prop_id}/nominal-votes")
def get_proposition_nominal_votes_split(
    prop_id: str, search: Optional[str] = Query(None, max_length=100), db: Session = Depends(get_db)
):
    """
    Retorna a tabela detalhada de quem votou SIM (A Favor) e quem votou NÃO (Contra),
    com foto, nome, partido e UF de cada parlamentar.
    """
    prop = _resolve_proposition(db, prop_id)

    prop_info = {
        "id": str(prop.id),
        "titulo": prop.title,
        "numero": prop.number,
        "ano": prop.year,
        "ementa": prop.summary,
        "setor": prop.thematic_area,
        "autor_nome": prop.author_name or ("Poder Executivo" if prop.is_executive_initiative else None),
        "status": prop.status.value,
        "data_apresentacao": prop.presentation_date.isoformat(),
        "url_oficial": _official_url(prop),
    }
    from app.services.deliberacoes_service import get_proposicao_deliberacoes
    delib_data = get_proposicao_deliberacoes(db, prop.id)
    deliberacoes_list = delib_data.get("deliberacoes", []) if delib_data else []

    empty = {
        "proposicao": prop_info,
        "sessao": None,
        "placar": {"sim": 0, "nao": 0, "abstencao": 0, "obstrucao": 0, "total": 0},
        "votos_sim": [],
        "votos_nao": [],
        "votos_abstencao": [],
        "votos_obstrucao": [],
        "deliberacoes": deliberacoes_list,
    }

    sessions = db.query(VotingSession).filter(VotingSession.proposition_id == prop.id).all()
    if not sessions:
        return empty

    # Sessão prioritária: maior quórum nominal (uma consulta agregada, sem N+1)
    tallies = _session_tallies(db, VotingSession.id.in_([s.id for s in sessions]))
    selected_session = max(sessions, key=lambda s: (tallies.get(s.id, EMPTY_PLACAR)["TOTAL"], s.session_datetime))

    votes_query = (
        db.query(ParliamentaryVote, Politician, PoliticalParty)
        .join(Politician, ParliamentaryVote.politician_id == Politician.id)
        .outerjoin(PoliticalParty, ParliamentaryVote.party_id == PoliticalParty.id)
        .filter(ParliamentaryVote.voting_session_id == selected_session.id)
    )

    if search and search.strip():
        votes_query = votes_query.filter(
            or_(
                _contains(Politician.electoral_name, search),
                _contains(Politician.civil_name, search),
                _contains(PoliticalParty.acronym, search),
            )
        )

    all_votes = votes_query.order_by(Politician.electoral_name.asc(), Politician.id).all()

    session_date = _to_brt(selected_session.session_datetime).date()
    context = _mandate_context(db, [p.id for _, p, _ in all_votes], session_date)
    fallback_cargo = (
        "DEPUTADO_FEDERAL"
        if selected_session.legislative_house == CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS
        else "SENADOR"
    )

    votos_sim: List[Dict[str, Any]] = []
    votos_nao: List[Dict[str, Any]] = []
    votos_abstencao: List[Dict[str, Any]] = []
    votos_obstrucao: List[Dict[str, Any]] = []
    buckets = {
        VotoOpcaoEnum.SIM: votos_sim,
        VotoOpcaoEnum.NAO: votos_nao,
        VotoOpcaoEnum.ABSTENCAO: votos_abstencao,
        VotoOpcaoEnum.OBSTRUCAO: votos_obstrucao,
    }

    for vote, pol, party in all_votes:
        bucket = buckets.get(vote.vote_choice)
        if bucket is None:  # AUSENTE / Art. 17 não votaram
            continue
        uf, cargo = context.get(pol.id, (None, fallback_cargo))
        bucket.append(
            {
                "politico_id": str(pol.id),
                "nome_eleitoral": pol.electoral_name,
                "nome_civil": pol.civil_name,
                "partido_sigla": party.acronym if party else "S.PART.",
                "espectro_politico": party.political_spectrum.value if (party and party.political_spectrum) else None,
                "uf": uf,
                "cargo": cargo,
                "foto_url": pol.photo_url,
                "decisao": vote.vote_choice.value,
            }
        )

    total_votantes = len(votos_sim) + len(votos_nao) + len(votos_abstencao) + len(votos_obstrucao)
    return {
        "proposicao": prop_info,
        "sessao": {
            "id": str(selected_session.id),
            "titulo": selected_session.agenda_title,
            "descricao": selected_session.detailed_description or selected_session.agenda_title,
            "data_hora": selected_session.session_datetime.isoformat(),
            "casa_legislativa": selected_session.legislative_house.value,
            "aprovada": selected_session.is_approved,
            "total_votos": total_votantes,
        },
        "placar": {
            "sim": len(votos_sim),
            "nao": len(votos_nao),
            "abstencao": len(votos_abstencao),
            "obstrucao": len(votos_obstrucao),
            "total": total_votantes,
        },
        "votos_sim": votos_sim,
        "votos_nao": votos_nao,
        "votos_abstencao": votos_abstencao,
        "votos_obstrucao": votos_obstrucao,
    }


MESES_PT = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}
DIAS_SEMANA_PT = {
    0: "Segunda-feira",
    1: "Terça-feira",
    2: "Quarta-feira",
    3: "Quinta-feira",
    4: "Sexta-feira",
    5: "Sábado",
    6: "Domingo",
}


def _days_in_year(year: int) -> int:
    return 366 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 365


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
    year_col = extract("year", VotingSession.session_datetime)
    anos_disponiveis = sorted((int(r[0]) for r in db.query(year_col).distinct().all()), reverse=True)

    if not anos_disponiveis:
        ano = year or date.today().year
        total_dias = _days_in_year(ano)
        return {
            "ano_selecionado": ano,
            "anos_disponiveis": [],
            "estatisticas_anuais": {
                "ano": ano,
                "total_dias_ano": total_dias,
                "dias_com_votacao": 0,
                "percentual_dias_ativos": 0.0,
                "total_sessoes_ano": 0,
                "texto_estatistica": f"Em {ano}, de {total_dias} dias, o Congresso realizou sessões de votação nominal em 0 dias.",
            },
            "dias": [],
        }

    if year is not None and year not in anos_disponiveis:
        raise HTTPException(status_code=404, detail=f"Sem votações registradas em {year}.")
    selected_year = year if year is not None else anos_disponiveis[0]

    # Filtro de ano feito no banco (não carrega todas as sessões de todos os anos)
    year_start = datetime(selected_year, 1, 1, tzinfo=BRT)
    year_end = datetime(selected_year + 1, 1, 1, tzinfo=BRT)
    year_filter = (VotingSession.session_datetime >= year_start, VotingSession.session_datetime < year_end)

    sessoes_ano = (
        db.query(VotingSession, Proposition)
        .join(Proposition, VotingSession.proposition_id == Proposition.id)
        .filter(*year_filter)
        .order_by(desc(VotingSession.session_datetime), VotingSession.id)
        .all()
    )
    tallies = _session_tallies(db, *year_filter)

    dias_dict: Dict[str, Dict[str, Any]] = {}
    for sess, prop in sessoes_ano:
        local_dt = _to_brt(sess.session_datetime)
        dt_str = local_dt.strftime("%Y-%m-%d")
        if dt_str not in dias_dict:
            d_obj = local_dt.date()
            dias_dict[dt_str] = {
                "data": dt_str,
                "dia": d_obj.day,
                "mes": d_obj.month,
                "ano": d_obj.year,
                "dia_semana": DIAS_SEMANA_PT.get(d_obj.weekday(), ""),
                "data_formatada": f"{d_obj.day:02d} de {MESES_PT.get(d_obj.month, '')} de {d_obj.year}",
                "total_votacoes": 0,
                "camara_count": 0,
                "senado_count": 0,
                "sessoes": [],
            }

        placar = tallies.get(sess.id, EMPTY_PLACAR)
        casa_str = sess.legislative_house.value
        if casa_str == "CAMARA_DOS_DEPUTADOS":
            dias_dict[dt_str]["camara_count"] += 1
        else:
            dias_dict[dt_str]["senado_count"] += 1
        dias_dict[dt_str]["total_votacoes"] += 1

        dias_dict[dt_str]["sessoes"].append(
            {
                "sessao_id": str(sess.id),
                "casa": casa_str,
                "casa_nome": ("Câmara dos Deputados" if casa_str == "CAMARA_DOS_DEPUTADOS" else "Senado Federal"),
                "hora": local_dt.strftime("%H:%M"),
                "titulo": sess.agenda_title,
                "descricao": sess.detailed_description or sess.agenda_title,
                "aprovada": sess.is_approved,
                "is_votacao_secreta": bool(sess.is_secret_vote),
                "placar": {
                    "sim": placar["SIM"],
                    "nao": placar["NAO"],
                    "abstencao": placar["ABSTENCAO"],
                    "total": placar["TOTAL"],
                },
                "proposicao": {
                    "id": str(prop.id),
                    "titulo": prop.title,
                    "tipo": prop.proposition_type.value,
                    "numero": prop.number,
                    "ano": prop.year,
                    "ementa": prop.summary,
                    "setor": prop.thematic_area,
                    "autor_nome": prop.author_name or ("Poder Executivo" if prop.is_executive_initiative else None),
                    "status": prop.status.value,
                    "url_oficial": _official_url(prop),
                },
            }
        )

    lista_dias = sorted(dias_dict.values(), key=lambda d: d["data"], reverse=True)

    total_dias_ano = _days_in_year(selected_year)
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
            "texto_estatistica": texto_estatistica,
        },
        "dias": lista_dias,
    }


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
    prop = _resolve_proposition(db, prop_id)
    from app.services.deliberacoes_service import get_proposicao_deliberacoes
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

    from app.services.deliberacoes_service import get_deliberacao_detalhe
    data = get_deliberacao_detalhe(db, v_uuid, search=search)
    if not data:
        raise HTTPException(status_code=404, detail="Deliberação não encontrada.")
    return data
