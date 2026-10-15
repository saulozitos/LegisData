import json
import logging
import math
import re
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import PROCESSED_DATA_DIR
from app.core.database import get_db
from app.models import (
    Casa,
    CasaLegislativaEnum,
    Mandate,
    VotoOpcaoEnum,
)
from app.models.core import Mandato, Partido, Pessoa, PessoaNome
from app.models.leg import Autoria, Proposicao, Votacao, Voto
from app.services.ialp_pesos import carregar_pesos_ialp
from app.services.legislative_scoring import (
    build_coauthorship_network,
    get_politician_ialp_metrics,
)
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import and_, bindparam, desc, exists, extract, func, or_, select, text
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


def _official_url(prop: Proposicao) -> Optional[str]:
    if prop.url_oficial:
        return prop.url_oficial
    if prop.id_camara:
        return f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={prop.id_camara}"
    if prop.id_senado:
        return f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{prop.id_senado}"
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


# Votações que a API trata como "sessões": votação nominal (ou secreta, só com totais) em plenário.
# Deliberações simbólicas e de comissão têm endpoints próprios (/deliberacoes).
TIPOS_SESSAO = ("NOMINAL", "SECRETA")


def _titulo_votacao(v: Votacao) -> str:
    return v.titulo_pauta or v.resumo_decisao or v.local_deliberacao or "Votação"


def _casa_codigo(v: Votacao) -> Optional[str]:
    return v.casa.codigo if v.casa else None


def _totais_fonte(v: Votacao) -> Tuple[int, int, int, int]:
    return (
        v.total_sim_fonte or 0,
        v.total_nao_fonte or 0,
        v.total_abstencao_fonte or 0,
        v.total_obstrucao_fonte or 0,
    )


def _placar_da_fonte(v: Votacao) -> Dict[str, int]:
    sim, nao, abst, obs = _totais_fonte(v)
    return {
        "SIM": sim,
        "NAO": nao,
        "ABSTENCAO": abst + obs,
        "TOTAL": sim + nao + abst + obs,
        "OBSTRUCAO": obs,
        "AUSENTE": 0,
    }


def _session_tallies(db: Session, *conditions) -> Dict[int, Dict[str, int]]:
    """Contagem de votos por votação em UMA consulta (evita N+1)."""
    rows = (
        db.query(Voto.votacao_id, Voto.opcao_codigo, func.count())
        .join(Votacao, Voto.votacao_id == Votacao.id)
        .filter(*conditions)
        .group_by(Voto.votacao_id, Voto.opcao_codigo)
        .all()
    )
    grouped: Dict[int, Dict[VotoOpcaoEnum, int]] = defaultdict(dict)
    for votacao_id, opcao, qty in rows:
        grouped[votacao_id][VotoOpcaoEnum(opcao)] = qty
    return {vid: _placar_from_counts(c) for vid, c in grouped.items()}


def _build_house_placar(sessions: List[Votacao], tallies: Dict[int, Dict[str, int]]) -> tuple:
    """
    Devolve (placar_principal, sessao_principal, detalhes_de_todas_as_sessoes).
    A sessão principal é a de maior quórum nominal (desempate: aprovada, depois a mais recente), e não
    simplesmente a mais recente: uma votação de destaque com poucos votos não deve substituir a de mérito.
    """
    if not sessions:
        return dict(EMPTY_PLACAR), None, []

    def total_of(s: Votacao) -> int:
        t = tallies.get(s.id)
        if t and t.get("TOTAL", 0) > 0:
            return t["TOTAL"]
        return sum(_totais_fonte(s))

    ordered = sorted(sessions, key=lambda s: (total_of(s), 1 if s.aprovada else 0, s.data_hora), reverse=True)
    details = []
    for s in ordered:
        placar = tallies.get(s.id)
        sim, nao, _, _ = _totais_fonte(s)
        if (not placar or placar.get("TOTAL", 0) == 0) and (sim or nao or s.secreta):
            placar = _placar_da_fonte(s)
        details.append(
            {
                "sessao_id": str(s.uid),
                "external_id": s.id_externo,
                "data_hora": s.data_hora.isoformat(),
                "titulo": _titulo_votacao(s),
                "descricao": s.descricao or _titulo_votacao(s),
                "aprovada": s.aprovada,
                "is_votacao_secreta": s.secreta,
                "placar": placar or dict(EMPTY_PLACAR),
            }
        )

    best = ordered[0]
    best_session = {
        "sessao_id": str(best.uid),
        "data_hora": best.data_hora.isoformat(),
        "titulo": _titulo_votacao(best),
        "descricao": best.descricao or _titulo_votacao(best),
        "aprovada": best.aprovada,
        "is_votacao_secreta": best.secreta,
    }
    return details[0]["placar"], best_session, details


_MANDATO_CONTEXTO_SQL = text(
    """
    SELECT m.pessoa_id, coalesce(ci.uf, 'BR') AS uf, c.codigo AS cargo, m.inicio, m.fim
    FROM core.mandato m
    JOIN ref.cargo c ON c.id = m.cargo_id
    JOIN ref.circunscricao ci ON ci.id = m.circunscricao_id
    WHERE m.pessoa_id = ANY(:ids) AND m.condicao <> 'NOMEADO'
    ORDER BY m.inicio DESC
    """
)


def _mandate_context(db: Session, pessoa_ids: List[int], ref_date: Optional[date] = None) -> Dict[int, Tuple[str, str]]:
    """
    (UF, cargo) por pessoa. Escolhe o mandato vigente na data de referência; sem ele, o mais recente.
    Não existe valor padrão inventado: pessoa sem mandato simplesmente não aparece no mapa.
    """
    if not pessoa_ids:
        return {}
    result: Dict[int, Tuple[str, str]] = {}
    covering: set = set()
    for pid, uf, cargo, start, end in db.execute(_MANDATO_CONTEXTO_SQL, {"ids": list(pessoa_ids)}):
        is_covering = bool(ref_date and start and start <= ref_date and (end is None or end >= ref_date))
        if pid not in result or (is_covering and pid not in covering):
            result[pid] = (uf, cargo)
        if is_covering:
            covering.add(pid)
    return result


def _resolve_proposition(db: Session, prop_id: str) -> Proposicao:
    """Resolve por UUID público ou por ID externo (Câmara/Senado). Número de matéria NÃO identifica: não é único."""
    try:
        prop = db.query(Proposicao).filter(Proposicao.uid == uuid.UUID(prop_id)).first()
        if prop:
            return prop
    except ValueError:
        pass

    if prop_id.isdigit():
        num_val = int(prop_id)
        prop = (
            db.query(Proposicao)
            .filter(or_(Proposicao.id_camara == num_val, Proposicao.id_senado == num_val))
            .order_by(Proposicao.id_camara.is_(None), Proposicao.data_apresentacao.desc())
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


def _sessoes_da_casa(query, casa: Optional[CasaLegislativaEnum]):
    query = query.filter(Votacao.tipo_deliberacao.in_(TIPOS_SESSAO))
    if casa:
        query = query.join(Casa, Casa.id == Votacao.casa_id).filter(Casa.codigo == casa.value)
    return query


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
    sessions_by_prop: Dict[int, List[Votacao]] = defaultdict(list)
    tallies: Dict[int, Dict[str, int]] = {}
    try:
        total = db.query(func.count(Proposicao.id)).scalar() or 0
        has_session = exists().where(Votacao.proposicao_id == Proposicao.id, Votacao.tipo_deliberacao.in_(TIPOS_SESSAO))
        props = (
            db.query(Proposicao)
            .order_by(has_session.desc(), Proposicao.data_apresentacao.desc(), Proposicao.id)
            .offset(offset)
            .limit(limit)
            .all()
            if total
            else []
        )
        if props:
            prop_ids = [p.id for p in props]
            for s in _sessoes_da_casa(db.query(Votacao), None).filter(Votacao.proposicao_id.in_(prop_ids)).all():
                sessions_by_prop[s.proposicao_id].append(s)
            tallies = _session_tallies(
                db, Votacao.proposicao_id.in_(prop_ids), Votacao.tipo_deliberacao.in_(TIPOS_SESSAO)
            )
    except SQLAlchemyError as e:
        logger.error("Falha ao consultar proposições no banco: %s", e)
        raise HTTPException(status_code=503, detail="Banco de dados indisponível.")

    if props:
        response.headers["X-Total-Count"] = str(total)
        result = []
        for p in props:
            sessoes = sessions_by_prop.get(p.id, [])
            sessoes_camara = [s for s in sessoes if _casa_codigo(s) == CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS.value]
            sessoes_senado = [s for s in sessoes if _casa_codigo(s) == CasaLegislativaEnum.SENADO_FEDERAL.value]

            placar_camara, sessao_camara, lista_camara = _build_house_placar(sessoes_camara, tallies)
            placar_senado, sessao_senado, lista_senado = _build_house_placar(sessoes_senado, tallies)

            # Placar consolidado padrão (prioriza a casa onde houve votação com quórum)
            if placar_camara["TOTAL"] > 0:
                default_placar, default_sessao = placar_camara, sessao_camara
            elif placar_senado["TOTAL"] > 0:
                default_placar, default_sessao = placar_senado, sessao_senado
            else:
                default_placar, default_sessao = dict(EMPTY_PLACAR), None

            author_display = p.autor_nome or (
                "Poder Executivo" if p.iniciativa_executivo else "Comissão / Parlamentares"
            )

            result.append(
                {
                    "id": str(p.uid),
                    "camara_id": p.id_camara,
                    "tipo": p.tipo_codigo,
                    "numero": p.numero,
                    "ano": p.ano,
                    "titulo": p.titulo,
                    "ementa": p.ementa,
                    "autor_nome": author_display,
                    "area_tematica": p.area_tematica,
                    "data_apresentacao": p.data_apresentacao.isoformat(),
                    "status": p.status_codigo,
                    "is_reforma_estrutural": p.reforma_estrutural,
                    "iniciativa_executivo": p.iniciativa_executivo,
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

    sessions_query = _sessoes_da_casa(db.query(Votacao), house_enum).filter(Votacao.proposicao_id == prop.id)
    all_house_sessions = sessions_query.order_by(Votacao.data_hora.desc()).all()
    proposicao_resumo = {
        "id": str(prop.uid),
        "titulo": prop.titulo,
        "numero": prop.numero,
        "ano": prop.ano,
        "autor_nome": prop.autor_nome or ("Poder Executivo" if prop.iniciativa_executivo else None),
    }
    if not all_house_sessions:
        return {
            "proposicao": proposicao_resumo,
            "sessoes_disponiveis": [],
            "sessao_ativa": None,
            "total": 0,
            "votos": [],
        }

    sessoes_disponiveis = [
        {
            "id": str(s.uid),
            "titulo": _titulo_votacao(s),
            "data_hora": s.data_hora.isoformat(),
            "casa": _casa_codigo(s),
            "aprovada": s.aprovada,
            "is_votacao_secreta": s.secreta,
        }
        for s in all_house_sessions
    ]

    selected_session = None
    if session_id:
        try:
            sess_uuid = uuid.UUID(session_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail="session_id inválido.")
        selected_session = next((s for s in all_house_sessions if s.uid == sess_uuid), None)
        if not selected_session:
            raise HTTPException(status_code=404, detail="Sessão não pertence a esta proposição/casa.")

    if not selected_session:
        # Sessão de maior quórum, calculada em uma única consulta agregada
        tallies = _session_tallies(db, Votacao.id.in_([s.id for s in all_house_sessions]))
        selected_session = max(
            all_house_sessions,
            key=lambda s: (
                tallies.get(s.id, EMPTY_PLACAR)["TOTAL"] or (_totais_fonte(s)[0] + _totais_fonte(s)[1]),
                s.data_hora,
            ),
        )

    proposicao_com_area = {**proposicao_resumo, "area_tematica": prop.area_tematica}
    if selected_session.secreta:
        placar_secreto = _placar_da_fonte(selected_session)
        return {
            "proposicao": proposicao_com_area,
            "sessao_ativa": {
                "id": str(selected_session.uid),
                "titulo": _titulo_votacao(selected_session),
                "descricao": selected_session.descricao or _titulo_votacao(selected_session),
                "data_hora": selected_session.data_hora.isoformat(),
                "casa": _casa_codigo(selected_session),
                "aprovada": selected_session.aprovada,
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
        .filter(Voto.votacao_id == selected_session.id)
    )

    if choice_enum:
        votes_query = votes_query.filter(Voto.opcao_codigo == choice_enum.value)

    if search and search.strip():
        votes_query = votes_query.filter(or_(_contains(Pessoa.nome_exibicao, search), _contains(Partido.sigla, search)))

    total_matching = votes_query.count()
    raw_results = votes_query.order_by(Pessoa.nome_exibicao.asc(), Pessoa.id).limit(MAX_NOMINAL_VOTES).all()

    session_date = _to_brt(selected_session.data_hora).date()
    context = _mandate_context(db, [pessoa.id for _, pessoa, _, _ in raw_results], session_date)
    casa_sessao = _casa_codigo(selected_session)
    fallback_cargo = "DEPUTADO_FEDERAL" if casa_sessao == CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS.value else "SENADOR"

    items = []
    for vote, pessoa, partido, civil in raw_results:
        uf, cargo = context.get(pessoa.id, (None, fallback_cargo))
        items.append(
            {
                "voto_id": f"{selected_session.uid}:{pessoa.uid}",
                "politico_id": str(pessoa.uid),
                "nome_eleitoral": pessoa.nome_exibicao,
                "nome_civil": civil or pessoa.nome_exibicao,
                "partido_sigla": partido.sigla if partido else "S.PART.",
                "uf": uf,
                "cargo": cargo,
                "foto_url": pessoa.foto_url,
                "decisao": vote.opcao_codigo,
                "sessao_id": str(selected_session.uid),
                "sessao_titulo": _titulo_votacao(selected_session),
                "casa_legislativa": casa_sessao,
                "data_sessao": selected_session.data_hora.isoformat(),
            }
        )

    return {
        "proposicao": proposicao_com_area,
        "sessao_ativa": {
            "id": str(selected_session.uid),
            "titulo": _titulo_votacao(selected_session),
            "descricao": selected_session.descricao or _titulo_votacao(selected_session),
            "data_hora": selected_session.data_hora.isoformat(),
            "casa": casa_sessao,
            "aprovada": selected_session.aprovada,
        },
        "sessoes_disponiveis": sessoes_disponiveis,
        "total": len(items),
        "total_correspondente": total_matching,
        "truncado": total_matching > len(items),
        "votos": items,
    }


_STATUS_LEI = ("APROVADA_E_SANCIONADA", "APROVADA_E_PROMULGADA")

_PARTIDO_ATUAL_SQL = """
    AND (
        EXISTS (SELECT 1 FROM core.mandato m JOIN core.vw_partido_canonico c ON c.id = m.partido_id
                 WHERE m.pessoa_id = v.pessoa_id AND (m.fim IS NULL OR m.fim >= current_date)
                   AND c.canonico_sigla_normalizada = ref.normalizar_texto(:partido))
        OR EXISTS (SELECT 1 FROM core.filiacao f JOIN core.vw_partido_canonico c ON c.id = f.partido_id
                    WHERE f.pessoa_id = v.pessoa_id AND upper_inf(f.periodo)
                      AND c.canonico_sigla_normalizada = ref.normalizar_texto(:partido))
        OR EXISTS (SELECT 1 FROM core.mandato m2 JOIN core.mandato_partido mp ON mp.mandato_id = m2.id
                    JOIN core.vw_partido_canonico c ON c.id = mp.partido_id
                    WHERE m2.pessoa_id = v.pessoa_id AND mp.periodo @> current_date
                      AND c.canonico_sigla_normalizada = ref.normalizar_texto(:partido))
    )
"""

_AUTORES_DETALHE_SQL = text(
    """
    SELECT pe.id, pe.uid, pe.nome_exibicao,
           (SELECT n.nome FROM core.pessoa_nome n WHERE n.pessoa_id = pe.id AND n.tipo = 'CIVIL' LIMIT 1) AS nome_civil,
           fm.url_origem AS foto,
           coalesce(
               (SELECT cp.canonico_id FROM core.mandato m JOIN core.vw_partido_canonico cp ON cp.id = m.partido_id
                 WHERE m.pessoa_id = pe.id ORDER BY m.inicio DESC LIMIT 1),
               (SELECT cp.canonico_id FROM core.filiacao f JOIN core.vw_partido_canonico cp ON cp.id = f.partido_id
                 WHERE f.pessoa_id = pe.id AND upper_inf(f.periodo) LIMIT 1)) AS partido_id,
           mand.uf, mand.cargo
    FROM core.pessoa pe
    LEFT JOIN core.midia fm ON fm.id = pe.foto_midia_id
    LEFT JOIN LATERAL (
        SELECT coalesce(ci.uf, 'BR') AS uf, c.codigo AS cargo
        FROM core.mandato m JOIN ref.cargo c ON c.id = m.cargo_id JOIN ref.circunscricao ci ON ci.id = m.circunscricao_id
        WHERE m.pessoa_id = pe.id AND m.condicao <> 'NOMEADO' ORDER BY m.inicio DESC LIMIT 1
    ) mand ON true
    WHERE pe.id = ANY(:ids)
    """
)


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
    crit_clean = criterio.lower().strip()
    valid_criterios = ("efetividade", "volume", "lideranca", "coautoria")
    if crit_clean not in valid_criterios:
        raise HTTPException(status_code=422, detail=f"Critério inválido. Use um de: {', '.join(valid_criterios)}.")

    params: Dict[str, Any] = {"leis": list(_STATUS_LEI)}
    filtros = ""
    if not _is_filter_all(setor):
        clean_setor = setor.strip()
        termo_principal = clean_setor.split("&")[0].split("/")[0].strip()
        termos = [clean_setor] + ([termo_principal] if termo_principal and termo_principal != clean_setor else [])
        condicoes = []
        for i, termo in enumerate(termos):
            params[f"setor{i}"] = f"%{_escape_like(termo)}%"
            condicoes.append(f"p.area_tematica ILIKE :setor{i} ESCAPE '\\'")
        filtros += " AND (" + " OR ".join(condicoes) + ")"
    if not _is_filter_all(partido):
        params["partido"] = partido.strip()
        filtros += _PARTIDO_ATUAL_SQL

    agregado = text(
        f"""
        SELECT v.pessoa_id AS author_id,
               count(*) AS total_props,
               count(*) FILTER (WHERE v.tipo_autoria = 'AUTOR_PRINCIPAL') AS lideranca,
               count(*) FILTER (WHERE v.tipo_autoria = 'COAUTOR') AS coautoria,
               count(*) FILTER (WHERE v.status_codigo IN :leis) AS aprovadas,
               count(*) FILTER (WHERE p.reforma_estrutural OR v.tipo_proposicao IN ('PEC', 'PLP')) AS estruturantes,
               round(sum(v.pontos_ialp)::numeric, 1) AS score
        FROM leg.vw_autoria_pontuada v
        JOIN leg.proposicao p ON p.id = v.proposicao_id
        WHERE v.pessoa_id IS NOT NULL {filtros}
        GROUP BY v.pessoa_id
        """
    ).bindparams(bindparam("leis", expanding=True))
    all_authors = db.execute(agregado, params).mappings().all()
    if not all_authors:
        return []

    scored_authors = []
    for row in all_authors:
        total_val = int(row["total_props"] or 0)
        lider_val = int(row["lideranca"] or 0)
        coaut_val = int(row["coautoria"] or 0)
        apr_val = int(row["aprovadas"] or 0)
        est_val = int(row["estruturantes"] or 0)
        score = float(row["score"] or 0)
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
                "author_id": row["author_id"],
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
        scored_authors.sort(key=lambda x: (x["total_props"], x["score"], x["author_id"]), reverse=True)
    elif crit_clean == "lideranca":
        scored_authors.sort(
            key=lambda x: (x["autoria_principal_count"], x["score"], x["total_props"], x["author_id"]), reverse=True
        )
    elif crit_clean == "coautoria":
        scored_authors.sort(
            key=lambda x: (x["coautoria_count"], x["score"], x["total_props"], x["author_id"]), reverse=True
        )
    else:
        scored_authors.sort(
            key=lambda x: (
                x["score"],
                x["aprovadas"],
                x["autoria_principal_count"],
                x["estruturantes"],
                x["total_props"],
                x["author_id"],
            ),
            reverse=True,
        )

    author_counts = scored_authors[:limit]
    pessoa_ids = [a["author_id"] for a in author_counts]
    detalhes = {r["id"]: r for r in db.execute(_AUTORES_DETALHE_SQL, {"ids": pessoa_ids}).mappings()}
    partidos = {
        r["id"]: r
        for r in db.execute(
            text("SELECT id, sigla, espectro_politico FROM core.vw_partido WHERE id = ANY(:ids)"),
            {"ids": [d["partido_id"] for d in detalhes.values() if d["partido_id"]]},
        ).mappings()
    }

    sector_rows = db.execute(
        text(
            """
            SELECT a.pessoa_id, p.area_tematica, count(*) AS total_setor
            FROM leg.autoria a JOIN leg.proposicao p ON p.id = a.proposicao_id
            WHERE a.pessoa_id = ANY(:ids) AND a.tipo_codigo <> 'INSTITUCIONAL'
            GROUP BY a.pessoa_id, p.area_tematica
            ORDER BY a.pessoa_id, total_setor DESC
            """
        ),
        {"ids": pessoa_ids},
    ).all()
    sectors_by_author: Dict[int, List[Tuple[str, int]]] = {}
    for aid, st, cnt in sector_rows:
        sectors_by_author.setdefault(aid, []).append((st or "Geral", cnt))

    ranking = []
    for idx, item in enumerate(author_counts, start=1):
        pessoa_id = item["author_id"]
        pol = detalhes.get(pessoa_id)
        if not pol:
            continue
        party = partidos.get(pol["partido_id"]) if pol["partido_id"] else None

        author_sectors = sectors_by_author.get(pessoa_id, [])
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
                "politico_id": str(pol["uid"]),
                "nome_eleitoral": pol["nome_exibicao"],
                "nome_civil": pol["nome_civil"] or pol["nome_exibicao"],
                "partido_sigla": party["sigla"] if party else "S.PART.",
                "espectro_politico": party["espectro_politico"] if party else None,
                "uf": pol["uf"],
                "cargo": pol["cargo"],
                "foto_url": pol["foto"],
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
                    "proporcao_estrutural_pct": (
                        round((item["estruturantes"] / item["total_props"]) * 100, 1)
                        if item["total_props"] > 0
                        else 0.0
                    ),
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


def _parse_codigo(db: Session, tabela: str, value: Optional[str], label: str) -> Optional[str]:
    """Valida um código de referência (tipo de proposição ou status) contra a tabela, sem lista fixa no código."""
    if _is_filter_all(value):
        return None
    codigo = value.strip().upper()
    validos = [r[0] for r in db.execute(text(f"SELECT codigo FROM {tabela} ORDER BY codigo"))]
    if codigo not in validos:
        raise HTTPException(
            status_code=422, detail=f"{label} inválido '{value}'. Valores aceitos: {', '.join(validos)}."
        )
    return codigo


_AUTOR_PRINCIPAL_SQL = text(
    """
    SELECT p.id AS proposicao_id, pe.uid AS pessoa_uid, pe.nome_exibicao, fm.url_origem AS foto,
           coalesce(pc.canonico_sigla,
                    (SELECT cp.canonico_sigla FROM core.mandato m JOIN core.vw_partido_canonico cp ON cp.id = m.partido_id
                      WHERE m.pessoa_id = pe.id ORDER BY m.inicio DESC LIMIT 1)) AS partido,
           coalesce(a.uf,
                    (SELECT ci.uf FROM core.mandato m JOIN ref.circunscricao ci ON ci.id = m.circunscricao_id
                      WHERE m.pessoa_id = pe.id AND m.condicao <> 'NOMEADO' ORDER BY m.inicio DESC LIMIT 1)) AS uf
    FROM leg.proposicao p
    LEFT JOIN LATERAL (
        SELECT x.pessoa_id, x.partido_id, x.uf FROM leg.autoria x
        WHERE x.proposicao_id = p.id AND x.tipo_codigo = 'AUTOR_PRINCIPAL' ORDER BY x.ordem LIMIT 1
    ) a ON true
    LEFT JOIN core.pessoa pe ON pe.id = coalesce(a.pessoa_id, p.autor_pessoa_id)
    LEFT JOIN core.midia fm ON fm.id = pe.foto_midia_id
    LEFT JOIN core.vw_partido_canonico pc ON pc.id = a.partido_id
    WHERE p.id = ANY(:ids)
    """
)


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
    tipo_codigo = _parse_codigo(db, "ref.tipo_proposicao", tipo, "Tipo")
    status_codigo = _parse_codigo(db, "ref.status_tramitacao", status, "Status")

    query = db.query(Proposicao)

    if search and search.strip():
        query = query.filter(
            or_(
                _contains(Proposicao.titulo, search),
                _contains(Proposicao.ementa, search),
                _contains(Proposicao.autor_nome, search),
                _contains(Proposicao.area_tematica, search),
            )
        )

    if not _is_filter_all(setor):
        query = query.filter(_contains(Proposicao.area_tematica, setor))

    if not _is_filter_all(partido):
        clean_partido = partido.strip().upper()
        if clean_partido in {"GOV", "GOVERNO", "PODER EXECUTIVO"}:
            query = query.filter(Proposicao.iniciativa_executivo.is_(True))
        elif clean_partido in {"S.PART.", "SEM PARTIDO"}:
            query = query.filter(
                and_(
                    Proposicao.autor_pessoa_id.is_(None),
                    Proposicao.iniciativa_executivo.is_(False),
                    ~exists().where(and_(Autoria.proposicao_id == Proposicao.id, Autoria.partido_id.isnot(None))),
                )
            )
        else:
            # partido vigente da linhagem: PMDB e MDB, por exemplo, respondem ao mesmo filtro
            lineage_ids = (
                select(text("c.id"))
                .select_from(text("core.vw_partido_canonico c"))
                .where(
                    text("c.canonico_sigla_normalizada = ref.normalizar_texto(:sigla)").bindparams(sigla=clean_partido)
                )
            )
            query = query.filter(
                or_(
                    exists().where(
                        and_(
                            Autoria.proposicao_id == Proposicao.id,
                            Autoria.tipo_codigo == "AUTOR_PRINCIPAL",
                            Autoria.partido_id.in_(lineage_ids),
                        )
                    ),
                    Proposicao.autor_pessoa_id.in_(
                        select(Mandato.pessoa_id).where(Mandato.partido_id.in_(lineage_ids))
                    ),
                    Proposicao.autor_nome.ilike(f"%({clean_partido}/%"),
                    Proposicao.autor_nome.ilike(f"%/{clean_partido})%"),
                )
            )

    if tipo_codigo:
        query = query.filter(Proposicao.tipo_codigo == tipo_codigo)

    if status_codigo:
        query = query.filter(Proposicao.status_codigo == status_codigo)

    if apenas_votadas:
        # EXISTS evita a duplicação de linhas de um JOIN com várias votações por proposição
        query = query.filter(
            exists().where(Votacao.proposicao_id == Proposicao.id, Votacao.tipo_deliberacao.in_(TIPOS_SESSAO))
        )

    total_items = query.count()

    todos_setores = [
        row[0]
        for row in db.query(Proposicao.area_tematica)
        .filter(Proposicao.area_tematica.isnot(None))
        .distinct()
        .order_by(Proposicao.area_tematica.asc())
        .all()
    ]

    offset = (page - 1) * limit
    proposicoes = (
        query.order_by(Proposicao.data_apresentacao.desc(), Proposicao.numero.desc(), Proposicao.id)
        .offset(offset)
        .limit(limit)
        .all()
    )

    pesos = carregar_pesos_ialp(db)
    prop_ids = [p.id for p in proposicoes]
    sessions_by_prop: Dict[int, List[Votacao]] = defaultdict(list)
    tallies: Dict[int, Dict[str, int]] = {}
    delibs_by_prop: Dict[int, List[Votacao]] = defaultdict(list)
    autores: Dict[int, Any] = {}
    if prop_ids:
        for v in db.query(Votacao).filter(Votacao.proposicao_id.in_(prop_ids)).order_by(Votacao.data_hora.desc()).all():
            delibs_by_prop[v.proposicao_id].append(v)
            if v.tipo_deliberacao in TIPOS_SESSAO:
                sessions_by_prop[v.proposicao_id].append(v)
        tallies = _session_tallies(db, Votacao.proposicao_id.in_(prop_ids), Votacao.tipo_deliberacao.in_(TIPOS_SESSAO))
        autores = {r.proposicao_id: r for r in db.execute(_AUTOR_PRINCIPAL_SQL, {"ids": prop_ids})}

    items = []
    for p in proposicoes:
        placar, sessao, _ = _build_house_placar(sessions_by_prop.get(p.id, []), tallies)
        tem_votacao = placar["TOTAL"] > 0

        autor = autores.get(p.id)
        if autor is not None and autor.partido:
            partido_sigla = autor.partido
        elif p.iniciativa_executivo:
            partido_sigla = "GOV"
        elif p.autor_nome:
            m = _PARTY_SIGLA_RE.search(p.autor_nome)
            partido_sigla = m.group(1).strip() if m else "S.PART."
        else:
            partido_sigla = "S.PART."
        autor_display = p.autor_nome or (
            autor.nome_exibicao
            if autor is not None and autor.nome_exibicao
            else ("Poder Executivo" if p.iniciativa_executivo else "Parlamentar")
        )

        peso_comp = pesos.peso_tipo(p.tipo_codigo)
        mult_tram = pesos.peso_status(p.status_codigo)

        resultado_str = "EM_TRAMITACAO"
        if sessao:
            resultado_str = "APROVADA" if sessao.get("aprovada") else "REJEITADA"
        elif p.status_codigo in ("APROVADA_E_SANCIONADA", "APROVADA_E_PROMULGADA"):
            resultado_str = "APROVADA"

        prop_delibs = delibs_by_prop.get(p.id, [])
        tipo_delib = (
            ("NOMINAL" if prop_delibs[0].tipo_deliberacao == "SECRETA" else prop_delibs[0].tipo_deliberacao)
            if prop_delibs
            else ("NOMINAL" if tem_votacao else None)
        )
        total_delib = len(prop_delibs) or (1 if tem_votacao else 0)

        items.append(
            {
                "id": str(p.uid),
                "tipo_deliberacao": tipo_delib,
                "total_deliberacoes": total_delib,
                "camara_id": p.id_camara,
                "tipo": p.tipo_codigo,
                "numero": p.numero,
                "ano": p.ano,
                "titulo": p.titulo,
                "ementa": p.ementa,
                "setor": p.area_tematica or "Não classificado",
                "eixo_impacto": p.eixo_impacto or "Geral",
                "autor_nome": autor_display,
                "autor_politico_id": str(autor.pessoa_uid) if autor is not None and autor.pessoa_uid else None,
                "autor_partido": partido_sigla,
                "autor_uf": autor.uf if autor is not None else None,
                "autor_foto": autor.foto if autor is not None else None,
                "status": p.status_codigo,
                "data_apresentacao": p.data_apresentacao.isoformat(),
                "is_reforma_estrutural": p.reforma_estrutural,
                "iniciativa_executivo": p.iniciativa_executivo,
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
        "id": str(prop.uid),
        "titulo": prop.titulo,
        "numero": prop.numero,
        "ano": prop.ano,
        "ementa": prop.ementa,
        "setor": prop.area_tematica,
        "autor_nome": prop.autor_nome or ("Poder Executivo" if prop.iniciativa_executivo else None),
        "status": prop.status_codigo,
        "data_apresentacao": prop.data_apresentacao.isoformat(),
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

    sessions = _sessoes_da_casa(db.query(Votacao), None).filter(Votacao.proposicao_id == prop.id).all()
    if not sessions:
        return empty

    # Sessão prioritária: maior quórum nominal (uma consulta agregada, sem N+1)
    tallies = _session_tallies(db, Votacao.id.in_([s.id for s in sessions]))
    selected_session = max(sessions, key=lambda s: (tallies.get(s.id, EMPTY_PLACAR)["TOTAL"], s.data_hora))

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
        .filter(Voto.votacao_id == selected_session.id)
    )

    if search and search.strip():
        votes_query = votes_query.filter(
            or_(
                _contains(Pessoa.nome_exibicao, search),
                _contains(nome_civil, search),
                _contains(Partido.sigla, search),
            )
        )

    all_votes = votes_query.order_by(Pessoa.nome_exibicao.asc(), Pessoa.id).all()

    session_date = _to_brt(selected_session.data_hora).date()
    context = _mandate_context(db, [pessoa.id for _, pessoa, _, _ in all_votes], session_date)
    casa_sessao = _casa_codigo(selected_session)
    fallback_cargo = "DEPUTADO_FEDERAL" if casa_sessao == CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS.value else "SENADOR"
    espectros = dict(
        db.execute(
            text(
                "SELECT DISTINCT ON (partido_id) partido_id, espectro FROM core.partido_posicao_ideologica "
                "WHERE escala = 'ESPECTRO_5' ORDER BY partido_id, ano_referencia DESC NULLS LAST, id DESC"
            )
        ).all()
    )

    votos_sim: List[Dict[str, Any]] = []
    votos_nao: List[Dict[str, Any]] = []
    votos_abstencao: List[Dict[str, Any]] = []
    votos_obstrucao: List[Dict[str, Any]] = []
    buckets = {
        VotoOpcaoEnum.SIM.value: votos_sim,
        VotoOpcaoEnum.NAO.value: votos_nao,
        VotoOpcaoEnum.ABSTENCAO.value: votos_abstencao,
        VotoOpcaoEnum.OBSTRUCAO.value: votos_obstrucao,
    }

    for vote, pessoa, partido, civil in all_votes:
        bucket = buckets.get(vote.opcao_codigo)
        if bucket is None:  # AUSENTE / Art. 17 não votaram
            continue
        uf, cargo = context.get(pessoa.id, (None, fallback_cargo))
        bucket.append(
            {
                "politico_id": str(pessoa.uid),
                "nome_eleitoral": pessoa.nome_exibicao,
                "nome_civil": civil or pessoa.nome_exibicao,
                "partido_sigla": partido.sigla if partido else "S.PART.",
                "espectro_politico": espectros.get(partido.id) if partido else None,
                "uf": uf,
                "cargo": cargo,
                "foto_url": pessoa.foto_url,
                "decisao": vote.opcao_codigo,
            }
        )

    total_votantes = len(votos_sim) + len(votos_nao) + len(votos_abstencao) + len(votos_obstrucao)
    return {
        "proposicao": prop_info,
        "sessao": {
            "id": str(selected_session.uid),
            "titulo": _titulo_votacao(selected_session),
            "descricao": selected_session.descricao or _titulo_votacao(selected_session),
            "data_hora": selected_session.data_hora.isoformat(),
            "casa_legislativa": casa_sessao,
            "aprovada": selected_session.aprovada,
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
    year_col = extract("year", Votacao.data_hora)
    anos_disponiveis = sorted(
        (int(r[0]) for r in db.query(year_col).filter(Votacao.tipo_deliberacao.in_(TIPOS_SESSAO)).distinct().all()),
        reverse=True,
    )

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
    year_filter = (
        Votacao.data_hora >= year_start,
        Votacao.data_hora < year_end,
        Votacao.tipo_deliberacao.in_(TIPOS_SESSAO),
    )

    sessoes_ano = (
        db.query(Votacao, Proposicao)
        .join(Proposicao, Votacao.proposicao_id == Proposicao.id)
        .filter(*year_filter)
        .order_by(desc(Votacao.data_hora), Votacao.id)
        .all()
    )
    tallies = _session_tallies(db, *year_filter)

    dias_dict: Dict[str, Dict[str, Any]] = {}
    for sess, prop in sessoes_ano:
        local_dt = _to_brt(sess.data_hora)
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
        casa_str = _casa_codigo(sess)
        if casa_str == "CAMARA_DOS_DEPUTADOS":
            dias_dict[dt_str]["camara_count"] += 1
        else:
            dias_dict[dt_str]["senado_count"] += 1
        dias_dict[dt_str]["total_votacoes"] += 1

        dias_dict[dt_str]["sessoes"].append(
            {
                "sessao_id": str(sess.uid),
                "casa": casa_str,
                "casa_nome": ("Câmara dos Deputados" if casa_str == "CAMARA_DOS_DEPUTADOS" else "Senado Federal"),
                "hora": local_dt.strftime("%H:%M"),
                "titulo": _titulo_votacao(sess),
                "descricao": sess.descricao or _titulo_votacao(sess),
                "aprovada": sess.aprovada,
                "is_votacao_secreta": bool(sess.secreta),
                "placar": {
                    "sim": placar["SIM"],
                    "nao": placar["NAO"],
                    "abstencao": placar["ABSTENCAO"],
                    "total": placar["TOTAL"],
                },
                "proposicao": {
                    "id": str(prop.uid),
                    "titulo": prop.titulo,
                    "tipo": prop.tipo_codigo,
                    "numero": prop.numero,
                    "ano": prop.ano,
                    "ementa": prop.ementa,
                    "setor": prop.area_tematica,
                    "autor_nome": prop.autor_nome or ("Poder Executivo" if prop.iniciativa_executivo else None),
                    "status": prop.status_codigo,
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
