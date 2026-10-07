import json
import uuid
import unicodedata
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc, cast, String, or_

from app.core.database import get_db
from app.models import (
    Politician, Mandate, PartyAffiliation, PoliticalParty,
    PoliticianRemuneration, AttendanceRecord, Proposition,
    ParliamentaryVote, VotingSession, TipoPresencaEnum,
    CargoPoliticoEnum, CasaLegislativaEnum, PoliticianAssetDeclaration,
    DespesaCota, EmendaParlamentar, CertidaoJudicial, DoacaoCampanha
)
from app.core.config import PROCESSED_DATA_DIR

router = APIRouter()
DATA_DIR = PROCESSED_DATA_DIR

_ceap_cache: Optional[Dict[str, Any]] = None
_emendas_cache: Optional[List[Dict[str, Any]]] = None


def _normalize_name(text: Optional[str]) -> str:
    if not text:
        return ""
    return "".join(c for c in unicodedata.normalize("NFD", text.upper()) if unicodedata.category(c) != "Mn").strip()


def _get_processed_ceap(electoral_name: str, civil_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    global _ceap_cache
    if _ceap_cache is None:
        file_path = DATA_DIR / "despesas_ceap_2019_2026.json"
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    _ceap_cache = {_normalize_name(k): v for k, v in raw.items()}
            except Exception:
                _ceap_cache = {}
        else:
            _ceap_cache = {}

    norm_elec = _normalize_name(electoral_name)
    norm_civ = _normalize_name(civil_name) if civil_name else ""

    if norm_elec in _ceap_cache:
        return _ceap_cache[norm_elec]
    if norm_civ and norm_civ in _ceap_cache:
        return _ceap_cache[norm_civ]

    for k, v in _ceap_cache.items():
        if (norm_elec and (norm_elec in k or k in norm_elec)) or (norm_civ and (norm_civ in k or k in norm_civ)):
            return v
    return None


def _get_processed_emendas(electoral_name: str, civil_name: Optional[str] = None) -> List[Dict[str, Any]]:
    global _emendas_cache
    if _emendas_cache is None:
        file_path = DATA_DIR / "emendas_parlamentares_2019_2026.json"
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    _emendas_cache = json.load(f)
            except Exception:
                _emendas_cache = []
        else:
            _emendas_cache = []

    norm_elec = _normalize_name(electoral_name)
    norm_civ = _normalize_name(civil_name) if civil_name else ""

    res = []
    for item in _emendas_cache:
        item_norm = _normalize_name(item.get("politician_name", ""))
        if (norm_elec and (norm_elec == item_norm or norm_elec in item_norm or item_norm in norm_elec)) or \
           (norm_civ and (norm_civ == item_norm or norm_civ in item_norm or item_norm in norm_civ)):
            res.append(item)
    return res


SIMBOLICO_KEYWORDS = [
    "homenagem", "dia nacional", "dia municipal", "dia estadual", "semana nacional",
    "denomina", "título", "titulo", "cidadão honorário", "cidadao honorario",
    "patrono", "patrona", "comemora", "comemoração", "comemoracao", "monumento",
    "nomeia", "inscreve no livro dos heróis", "livro dos herois", "capital nacional do",
    "institui o dia", "institui a semana"
]

PARTY_GOV_BASELINE = {
    "PT": 98.5, "PCdoB": 96.0, "PV": 94.5, "REDE": 92.0, "PSOL": 86.5,
    "PSB": 84.0, "PDT": 79.0, "MDB": 74.0, "PSD": 72.5, "SOLIDARIEDADE": 68.0,
    "AVANTE": 66.0, "CIDADANIA": 60.0, "UNIÃO": 58.0, "PP": 54.5,
    "REPUBLICANOS": 51.0, "PODEMOS": 46.0, "PODE": 46.0, "PSDB": 42.0,
    "PRD": 38.0, "NOVO": 18.0, "PL": 14.5
}


def _format_photo_url(politician: Politician) -> Optional[str]:
    """Retorna URL confiável da foto ou fallback local para presidentes."""
    if politician.photo_url:
        return politician.photo_url

    name_lower = politician.electoral_name.lower()
    if "itamar" in name_lower:
        return "/presidents/itamar-franco.jpg"
    if "cardoso" in name_lower or "fhc" in name_lower:
        return "/presidents/fhc.jpg"
    if "lula" in name_lower and "fonte" not in name_lower:
        return "/presidents/lula.jpg"
    if "dilma" in name_lower:
        return "/presidents/dilma.jpg"
    if "temer" in name_lower:
        return "/presidents/temer.jpg"
    if "bolsonaro" in name_lower:
        return "/presidents/bolsonaro.jpg"

    if politician.camara_id:
        return f"https://www.camara.leg.br/internet/deputado/bandep/{politician.camara_id}.jpg"

    return None


@router.get("/presidents", response_model=List[Dict[str, Any]])
def get_historical_presidents():
    """
    Retorna o catálogo histórico completo dos Presidentes do Brasil (Itamar Franco -> Presente),
    incluindo ministros da fazenda, vices, partidos e marcos econômicos.
    """
    file_path = DATA_DIR / "presidentes_historico.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Dados de presidentes ainda não processados.")
    
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/presidents/{mandate_id}")
def get_president_by_mandate(mandate_id: str):
    """Retorna detalhes específicos de um mandato presidencial."""
    file_path = DATA_DIR / "presidentes_historico.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Dados não encontrados.")
        
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        for pres in data:
            if pres["id_referencia"] == mandate_id:
                return pres
                
    raise HTTPException(status_code=404, detail=f"Mandato '{mandate_id}' não encontrado.")


@router.get("", response_model=Dict[str, Any])
@router.get("/", response_model=Dict[str, Any])
def search_politicians(
    search: Optional[str] = Query(None, description="Busca por nome eleitoral ou civil"),
    office: Optional[str] = Query(None, description="Filtro por cargo (DEPUTADO_FEDERAL, SENADOR, PRESIDENTE)"),
    party: Optional[str] = Query(None, description="Filtro por sigla do partido"),
    partido: Optional[str] = Query(None, description="Alias para party"),
    uf: Optional[str] = Query(None, description="Filtro por UF de jurisdição"),
    limit: int = Query(50, ge=1, le=800, description="Quantidade máxima de registros"),
    offset: int = Query(0, ge=0, description="Deslocamento para paginação"),
    db: Session = Depends(get_db)
):
    """
    Endpoint para busca e seleção de políticos para alimentar Autocomplete, Combobox e Bancadas.
    Retorna lista consolidada com nome, partido atual, cargo, UF e foto.
    """
    query = db.query(Politician)

    if search:
        search_pattern = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Politician.electoral_name.ilike(search_pattern),
                Politician.civil_name.ilike(search_pattern)
            )
        )

    target_party = (party or partido).strip() if (party or partido) else None
    if target_party and target_party.lower() in ("todos", "todas", "all"):
        target_party = None

    # Filtrar por partido, cargo ou UF com alta precisão
    if target_party or office or uf:
        if target_party:
            clean_party = target_party.strip().upper()
            party_ids_subq = db.query(PoliticalParty.id).filter(
                or_(
                    func.upper(PoliticalParty.acronym) == clean_party,
                    PoliticalParty.acronym.ilike(f"%{clean_party}%"),
                    PoliticalParty.full_name.ilike(f"%{clean_party}%")
                )
            ).subquery()

            party_mandate_subq = db.query(Mandate.politician_id).filter(Mandate.party_id.in_(party_ids_subq))
            party_aff_subq = db.query(PartyAffiliation.politician_id).filter(PartyAffiliation.party_id.in_(party_ids_subq))

            query = query.filter(
                or_(
                    Politician.id.in_(party_mandate_subq),
                    Politician.id.in_(party_aff_subq)
                )
            )

        if office and office.lower() not in ("todos", "todas", "all"):
            try:
                c_enum = CargoPoliticoEnum[office.upper()]
                mandate_office_subq = db.query(Mandate.politician_id).filter(Mandate.office == c_enum)
                query = query.filter(Politician.id.in_(mandate_office_subq))
            except KeyError:
                pass

        if uf and uf.lower() not in ("todos", "todas", "all"):
            mandate_uf_subq = db.query(Mandate.politician_id).filter(Mandate.jurisdiction_state == uf.upper())
            query = query.filter(
                or_(
                    Politician.id.in_(mandate_uf_subq),
                    Politician.birthplace_state == uf.upper()
                )
            )

    total_count = query.count()
    politicians = query.order_by(Politician.electoral_name.asc()).offset(offset).limit(limit).all()

    results = []
    for pol in politicians:
        # Obter mandato filtrado ou mais recente
        latest_mandate_q = (
            db.query(Mandate, PoliticalParty)
            .outerjoin(PoliticalParty, Mandate.party_id == PoliticalParty.id)
            .filter(Mandate.politician_id == pol.id)
        )
        if office:
            try:
                c_enum = CargoPoliticoEnum[office.upper()]
                latest_mandate_q = latest_mandate_q.filter(Mandate.office == c_enum)
            except KeyError:
                pass
        if target_party:
            latest_mandate_q = latest_mandate_q.filter(PoliticalParty.acronym.ilike(target_party))

        latest_mandate = latest_mandate_q.order_by(desc(Mandate.start_date)).first()
        if not latest_mandate:
            latest_mandate = (
                db.query(Mandate, PoliticalParty)
                .outerjoin(PoliticalParty, Mandate.party_id == PoliticalParty.id)
                .filter(Mandate.politician_id == pol.id)
                .order_by(desc(Mandate.start_date))
                .first()
            )

        mandate_obj = latest_mandate[0] if latest_mandate else None
        party_obj = latest_mandate[1] if latest_mandate else None

        # Obter partido da filiação atual caso não tenha no mandato
        if not party_obj:
            current_aff = (
                db.query(PartyAffiliation, PoliticalParty)
                .join(PoliticalParty, PartyAffiliation.party_id == PoliticalParty.id)
                .filter(PartyAffiliation.politician_id == pol.id, PartyAffiliation.is_current.is_(True))
                .first()
            )
            if current_aff:
                party_obj = current_aff[1]

        results.append({
            "id": str(pol.id),
            "nome_eleitoral": pol.electoral_name,
            "nome_civil": pol.civil_name,
            "cargo": mandate_obj.office.value if mandate_obj else "PARLAMENTAR",
            "partido_sigla": party_obj.acronym if party_obj else "S.PART.",
            "partido_nome": party_obj.full_name if party_obj else "Sem Partido",
            "uf": mandate_obj.jurisdiction_state if mandate_obj else (pol.birthplace_state or "BR"),
            "foto_url": _format_photo_url(pol),
            "camara_id": pol.camara_id,
            "senado_id": pol.senado_id
        })

    return {
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "politicos": results
    }


@router.get("/{politician_id}", response_model=Dict[str, Any])
def get_politician_dossier(
    politician_id: str,
    db: Session = Depends(get_db)
):
    """
    Retorna o dossiê individual 360º completo de um político:
    - Trajetória de cargos ocupados
    - Histórico completo de partidos aos quais pertenceu
    - Remunerações detalhadas e médias
    - Matérias de autoria própria
    - Histórico de votações nominais nas grandes leis
    - Contabilização de presenças e faltas com taxa de assiduidade
    """
    pol = None

    # 1. Tentar busca por UUID
    try:
        pol_uuid = uuid.UUID(politician_id)
        pol = db.query(Politician).filter_by(id=pol_uuid).first()
    except (ValueError, AttributeError):
        pass

    # 2. Tentar busca por ID externo da Câmara ou Senado
    if not pol and politician_id.isdigit():
        num_id = int(politician_id)
        pol = db.query(Politician).filter(
            or_(Politician.camara_id == num_id, Politician.senado_id == num_id)
        ).first()

    # 3. Tentar busca aproximada por nome ou identificador slug
    if not pol:
        clean_slug = politician_id.replace("-", " ")
        pol = db.query(Politician).filter(
            or_(
                Politician.electoral_name.ilike(f"%{clean_slug}%"),
                Politician.civil_name.ilike(f"%{clean_slug}%")
            )
        ).first()

    if not pol:
        raise HTTPException(status_code=404, detail=f"Político '{politician_id}' não encontrado.")

    # A. Trajetória de Mandatos
    mandates_db = (
        db.query(Mandate, PoliticalParty)
        .outerjoin(PoliticalParty, Mandate.party_id == PoliticalParty.id)
        .filter(Mandate.politician_id == pol.id)
        .order_by(desc(Mandate.start_date))
        .all()
    )

    mandatos_list = []
    latest_mandate_id = None
    cargo_atual = "PARLAMENTAR"
    uf_atual = pol.birthplace_state or "BR"
    partido_atual_sigla = "S.PART."

    for idx, (m, party) in enumerate(mandates_db):
        if idx == 0:
            latest_mandate_id = m.id
            cargo_atual = m.office.value
            uf_atual = m.jurisdiction_state
            if party:
                partido_atual_sigla = party.acronym

        mandatos_list.append({
            "id": str(m.id),
            "cargo": m.office.value,
            "esfera": m.sphere.value,
            "ano_eleicao": m.election_year,
            "numero_mandato": m.term_number,
            "data_inicio": m.start_date.isoformat() if m.start_date else None,
            "data_fim": m.end_date.isoformat() if m.end_date else None,
            "status": m.status.value,
            "partido_sigla": party.acronym if party else "S.PART.",
            "uf": m.jurisdiction_state,
            "total_votos": m.total_votes,
            "percentual_votos": float(m.vote_percentage) if m.vote_percentage else None,
            "coligacao": m.coalition_name
        })

    # B. Histórico Completo de Partidos (Filiações TSE)
    affiliations_db = (
        db.query(PartyAffiliation, PoliticalParty)
        .join(PoliticalParty, PartyAffiliation.party_id == PoliticalParty.id)
        .filter(PartyAffiliation.politician_id == pol.id)
        .order_by(desc(PartyAffiliation.start_date))
        .all()
    )

    filiacoes_list = []
    for aff, party in affiliations_db:
        if aff.is_current and party:
            partido_atual_sigla = party.acronym

        filiacoes_list.append({
            "id": str(aff.id),
            "partido_sigla": party.acronym,
            "partido_nome": party.full_name,
            "data_filiacao": aff.start_date.isoformat() if aff.start_date else None,
            "data_desfiliacao": aff.end_date.isoformat() if aff.end_date else None,
            "is_atual": aff.is_current,
            "motivo_desfiliacao": aff.disaffiliation_reason.value if aff.disaffiliation_reason else None,
            "uf": aff.state
        })

    # C. Remunerações (Salário, CEAP, Benefícios)
    remuns_db = (
        db.query(PoliticianRemuneration)
        .filter(PoliticianRemuneration.politician_id == pol.id)
        .order_by(desc(PoliticianRemuneration.reference_year), desc(PoliticianRemuneration.reference_month))
        .all()
    )

    remuneracao_historico = []
    total_bruto_ano = Decimal("0.00")
    total_liquido_ano = Decimal("0.00")
    total_ceap_ano = Decimal("0.00")
    total_beneficios_ano = Decimal("0.00")

    for r in remuns_db:
        if r.reference_year == 2023:
            total_bruto_ano += r.gross_salary
            total_liquido_ano += r.net_salary
            total_ceap_ano += r.parliamentary_quota_ceap
            total_beneficios_ano += (r.housing_allowance + r.other_benefits)

        remuneracao_historico.append({
            "ano": r.reference_year,
            "mes": r.reference_month,
            "salario_bruto": float(r.gross_salary),
            "salario_liquido": float(r.net_salary),
            "cota_ceap": float(r.parliamentary_quota_ceap),
            "auxilio_moradia": float(r.housing_allowance),
            "outros_beneficios": float(r.other_benefits),
            "fonte": r.data_source
        })

    qtd_meses = len([r for r in remuns_db if r.reference_year == 2023]) or 1
    media_ceap = (total_ceap_ano / Decimal(str(qtd_meses))).quantize(Decimal("0.01"))
    sal_bruto_atual = float(remuns_db[0].gross_salary) if remuns_db else 41650.92
    sal_liquido_atual = float(remuns_db[0].net_salary) if remuns_db else 31238.19

    # D. Matérias de Autoria Própria
    is_pres_exec = "lula" in pol.electoral_name.lower() or "bolsonaro" in pol.electoral_name.lower()
    prop_conditions = [Proposition.author_politician_id == pol.id]
    if is_pres_exec:
        prop_conditions.append(Proposition.is_executive_initiative.is_(True))

    proposicoes_db = (
        db.query(Proposition)
        .filter(or_(*prop_conditions))
        .order_by(desc(Proposition.presentation_date))
        .all()
    )

    materias_propostas = []
    for p in proposicoes_db:
        url_oficial = p.official_url or (
            f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={p.external_camara_id}"
            if p.external_camara_id else
            f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{p.external_senado_id}"
            if p.external_senado_id else None
        )
        txt_full = f"{p.title} {p.summary or ''} {p.thematic_area or ''}".lower()
        is_simb = any(k in txt_full for k in SIMBOLICO_KEYWORDS)
        classif = "SIMBOLICO" if is_simb else "IMPACTO"
        justif = "Matéria de cunho honorífico/simbólico" if is_simb else "Matéria com impacto estrutural e substantivo"

        materias_propostas.append({
            "id": str(p.id),
            "tipo": p.proposition_type.value,
            "numero": p.number,
            "ano": p.year,
            "titulo": p.title,
            "ementa": p.summary,
            "status": p.status.value,
            "area_tematica": p.thematic_area,
            "data_apresentacao": p.presentation_date.isoformat() if p.presentation_date else None,
            "is_reforma_estrutural": p.is_structural_reform,
            "url_oficial": url_oficial,
            "classificacao_relevancia": classif,
            "justificativa_relevancia": justif
        })

    total_props = len(materias_propostas)
    props_simb = sum(1 for p in materias_propostas if p.get("classificacao_relevancia") == "SIMBOLICO")
    props_imp = total_props - props_simb
    pct_imp = round((props_imp / total_props) * 100, 1) if total_props > 0 else 100.0
    pct_simb = round((props_simb / total_props) * 100, 1) if total_props > 0 else 0.0

    relevancia_legislativa = {
        "total_proposicoes": total_props,
        "projetos_impacto": props_imp,
        "projetos_simbolicos": props_simb,
        "percentual_impacto": pct_imp,
        "percentual_simbolico": pct_simb,
        "diagnostico": "Alta Relevância Estrutural" if pct_imp >= 75 else ("Equilíbrio Legislativo" if pct_imp >= 50 else "Foco em Pautas Simbólicas")
    }

    # E. Como Votou nas Principais Leis
    votos_db = (
        db.query(ParliamentaryVote, VotingSession, Proposition)
        .join(VotingSession, ParliamentaryVote.voting_session_id == VotingSession.id)
        .join(Proposition, VotingSession.proposition_id == Proposition.id)
        .filter(ParliamentaryVote.politician_id == pol.id)
        .order_by(desc(VotingSession.session_datetime))
        .all()
    )

    votos_nominais = []
    historico_votos = []
    alinhamento_tematico_map = {}
    votos_analisados_gov = 0
    votos_alinhados_gov = 0
    votos_divergentes_gov = 0

    for vote, sess, prop in votos_db:
        eixo = prop.impact_axis or "Geral"
        if eixo not in alinhamento_tematico_map:
            alinhamento_tematico_map[eixo] = {
                "eixo": eixo,
                "total_votacoes": 0,
                "votos_sim": 0,
                "votos_nao": 0,
                "votos_abstencao": 0,
                "percentual_favoravel": 0.0
            }

        alinhamento_tematico_map[eixo]["total_votacoes"] += 1
        v_opt = vote.vote_choice.value if hasattr(vote.vote_choice, "value") else str(vote.vote_choice)
        if v_opt == "SIM":
            alinhamento_tematico_map[eixo]["votos_sim"] += 1
            voto_label = "Sim"
            votos_analisados_gov += 1
            votos_alinhados_gov += 1
        elif v_opt == "NAO":
            alinhamento_tematico_map[eixo]["votos_nao"] += 1
            voto_label = "Não"
            votos_analisados_gov += 1
            votos_divergentes_gov += 1
        elif "ABST" in v_opt:
            alinhamento_tematico_map[eixo]["votos_abstencao"] += 1
            voto_label = "Abstenção"
        elif "OBST" in v_opt:
            alinhamento_tematico_map[eixo]["votos_abstencao"] += 1
            voto_label = "Obstrução"
        else:
            alinhamento_tematico_map[eixo]["votos_abstencao"] += 1
            voto_label = "Ausente"

        dt_formatada = sess.session_datetime.strftime("%d/%m/%Y") if sess.session_datetime else ""
        tema_display = prop.thematic_area or prop.impact_axis or "Geral"
        numero_display = f"{prop.proposition_type.value} {prop.number}/{prop.year}" if prop.number else prop.title
        url_oficial_prop = prop.official_url or (
            f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={prop.external_camara_id}"
            if prop.external_camara_id else
            f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{prop.external_senado_id}"
            if prop.external_senado_id else None
        )

        voto_dict = {
            "proposicao_id": str(prop.id),
            "proposicao_titulo": prop.title,
            "proposicao_numero": numero_display,
            "proposicao_tipo": prop.proposition_type.value,
            "tema": tema_display,
            "setor": prop.thematic_area or "Geral",
            "eixo_impacto": prop.impact_axis or "Geral",
            "data": dt_formatada,
            "data_iso": sess.session_datetime.isoformat() if sess.session_datetime else None,
            "voto": voto_label,
            "decisao": v_opt,
            "sessao_titulo": sess.agenda_title,
            "sessao_aprovada": sess.is_approved,
            "casa_legislativa": sess.legislative_house.value,
            "url_oficial": url_oficial_prop
        }

        historico_votos.append(voto_dict)

        votos_nominais.append({
            "proposicao_id": str(prop.id),
            "proposicao_titulo": prop.title,
            "proposicao_tipo": prop.proposition_type.value,
            "proposicao_numero": prop.number,
            "proposicao_ano": prop.year,
            "eixo_impacto": prop.impact_axis or "Geral",
            "eixos_tags": prop.impact_tags or "",
            "decisao": v_opt,
            "sessao_titulo": sess.agenda_title,
            "sessao_data": sess.session_datetime.isoformat(),
            "sessao_aprovada": sess.is_approved,
            "casa_legislativa": sess.legislative_house.value
        })

    alinhamento_tematico_list = []
    for eixo, dados in alinhamento_tematico_map.items():
        total_decididos = dados["votos_sim"] + dados["votos_nao"]
        if total_decididos > 0:
            dados["percentual_favoravel"] = round((dados["votos_sim"] / total_decididos) * 100, 1)
        else:
            dados["percentual_favoravel"] = 0.0
        alinhamento_tematico_list.append(dados)

    alinhamento_tematico_list.sort(key=lambda x: x["total_votacoes"], reverse=True)

    # Basômetro - Taxa de Governismo
    if votos_analisados_gov >= 2:
        taxa_governismo_pct = round((votos_alinhados_gov / votos_analisados_gov) * 100, 1)
    else:
        taxa_governismo_pct = PARTY_GOV_BASELINE.get(partido_atual_sigla, 50.0)

    if taxa_governismo_pct >= 80.0:
        classif_gov = "Governista Fiel"
    elif taxa_governismo_pct >= 60.0:
        classif_gov = "Base Aliada Moderada"
    elif taxa_governismo_pct >= 40.0:
        classif_gov = "Independente / Centro"
    elif taxa_governismo_pct >= 20.0:
        classif_gov = "Oposição Moderada"
    else:
        classif_gov = "Oposição Firme"

    basometro = {
        "taxa_governismo_pct": taxa_governismo_pct,
        "total_votacoes_analisadas": votos_analisados_gov,
        "votos_alinhados": votos_alinhados_gov,
        "votos_divergentes": votos_divergentes_gov,
        "classificacao": classif_gov,
        "partido_sigla": partido_atual_sigla
    }

    # F. Contabilização de Presenças e Faltas (Assiduidade)
    attendances_query = db.query(AttendanceRecord).filter(AttendanceRecord.politician_id == pol.id)
    total_sessoes = attendances_query.count()

    presencas_count = attendances_query.filter(AttendanceRecord.attendance_status == TipoPresencaEnum.PRESENTE).count()
    faltas_justif_count = attendances_query.filter(
        AttendanceRecord.attendance_status.in_([
            TipoPresencaEnum.AUSENCIA_JUSTIFICADA,
            TipoPresencaEnum.LICENCA_MEDICA,
            TipoPresencaEnum.MISSAO_OFICIAL
        ])
    ).count()
    faltas_injustif_count = attendances_query.filter(
        AttendanceRecord.attendance_status == TipoPresencaEnum.AUSENCIA_NAO_JUSTIFICADA
    ).count()

    taxa_presenca = round((presencas_count / total_sessoes * 100), 1) if total_sessoes > 0 else 100.0

    amostra_faltas = (
        attendances_query
        .filter(AttendanceRecord.attendance_status != TipoPresencaEnum.PRESENTE)
        .order_by(desc(AttendanceRecord.session_date))
        .limit(10)
        .all()
    )

    faltas_registros = [
        {
            "data": a.session_date.isoformat(),
            "tipo": a.attendance_status.value,
            "justificativa": a.justification,
            "casa": a.legislative_house.value
        }
        for a in amostra_faltas
    ]

    # G. Evolução Patrimonial (TSE DivulgaCand)
    assets_db = (
        db.query(PoliticianAssetDeclaration)
        .filter(PoliticianAssetDeclaration.politician_id == pol.id)
        .order_by(asc(PoliticianAssetDeclaration.election_year))
        .all()
    )

    patrimonio_historico = []
    for a in assets_db:
        val_float = float(a.declared_value_brl)
        val_formatado = f"R$ {val_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        patrimonio_historico.append({
            "ano": a.election_year,
            "valor": val_float,
            "valor_formatado": val_formatado,
            "detalhes": a.asset_details or "Declaração de bens regular registrada no TSE"
        })

    crescimento_pct = 0.0
    crescimento_absoluto = 0.0
    if len(patrimonio_historico) >= 2:
        val_inicial = patrimonio_historico[0]["valor"]
        val_final = patrimonio_historico[-1]["valor"]
        crescimento_absoluto = round(val_final - val_inicial, 2)
        if val_inicial > 0:
            crescimento_pct = round(((val_final - val_inicial) / val_inicial) * 100, 1)

    patrimonio_resumo = {
        "possui_dados": len(patrimonio_historico) > 0,
        "total_declaracoes": len(patrimonio_historico),
        "primeiro_ano": patrimonio_historico[0]["ano"] if patrimonio_historico else None,
        "primeiro_valor": patrimonio_historico[0]["valor"] if patrimonio_historico else 0.0,
        "primeiro_valor_formatado": patrimonio_historico[0]["valor_formatado"] if patrimonio_historico else "R$ 0,00",
        "ultimo_ano": patrimonio_historico[-1]["ano"] if patrimonio_historico else None,
        "ultimo_valor": patrimonio_historico[-1]["valor"] if patrimonio_historico else 0.0,
        "ultimo_valor_formatado": patrimonio_historico[-1]["valor_formatado"] if patrimonio_historico else "R$ 0,00",
        "crescimento_pct": crescimento_pct,
        "crescimento_absoluto": crescimento_absoluto,
    }

    # H. Custo do Mandato (CEAP)
    ceap_db = (
        db.query(DespesaCota)
        .filter(DespesaCota.politician_id == pol.id)
        .order_by(desc(DespesaCota.year), desc(DespesaCota.month))
        .all()
    )
    if ceap_db:
        total_ceap_geral = float(sum([d.net_value for d in ceap_db]))
        gastos_por_tipo_map = {}
        for d in ceap_db:
            t = d.expense_type
            gastos_por_tipo_map[t] = gastos_por_tipo_map.get(t, 0.0) + float(d.net_value)

        gastos_por_tipo = [
            {
                "tipo_despesa": t,
                "total_gasto": round(v, 2),
                "percentual": round((v / total_ceap_geral * 100), 1) if total_ceap_geral > 0 else 0.0
            }
            for t, v in gastos_por_tipo_map.items()
        ]
        gastos_por_tipo.sort(key=lambda x: x["total_gasto"], reverse=True)

        fornecedores_map = {}
        for d in ceap_db:
            f_key = d.supplier_name
            if f_key not in fornecedores_map:
                fornecedores_map[f_key] = {
                    "nome_fornecedor": d.supplier_name,
                    "cnpj_cpf": d.supplier_cnpj_cpf,
                    "total_recebido": 0.0,
                    "num_notas": 0
                }
            fornecedores_map[f_key]["total_recebido"] += float(d.net_value)
            fornecedores_map[f_key]["num_notas"] += 1

        maiores_fornecedores = list(fornecedores_map.values())
        maiores_fornecedores.sort(key=lambda x: x["total_recebido"], reverse=True)
        maiores_fornecedores = maiores_fornecedores[:10]
        for mf in maiores_fornecedores:
            mf["total_recebido"] = round(mf["total_recebido"], 2)

        despesas_recentes = [
            {
                "ano": d.year,
                "mes": d.month,
                "tipo_despesa": d.expense_type,
                "valor_liquido": float(d.net_value),
                "nome_fornecedor": d.supplier_name,
                "cnpj_cpf": d.supplier_cnpj_cpf,
                "data_emissao": d.issue_date.isoformat() if d.issue_date else None,
                "documento_url": d.document_url
            }
            for d in ceap_db[:15]
        ]

        custos_ceap = {
            "possui_dados": True,
            "gasto_total_recente": round(total_ceap_geral, 2),
            "total_notas": len(ceap_db),
            "gastos_por_tipo": gastos_por_tipo,
            "maiores_fornecedores": maiores_fornecedores,
            "despesas_recentes": despesas_recentes
        }
    else:
        proc_ceap = _get_processed_ceap(pol.electoral_name, pol.civil_name)
        if proc_ceap:
            total_ceap_geral = float(proc_ceap.get("total_gasto", 0.0))
            gastos_por_tipo = [
                {
                    "tipo_despesa": t,
                    "total_gasto": round(float(v), 2),
                    "percentual": round((float(v) / total_ceap_geral * 100), 1) if total_ceap_geral > 0 else 0.0
                }
                for t, v in proc_ceap.get("por_tipo", {}).items()
            ]
            gastos_por_tipo.sort(key=lambda x: x["total_gasto"], reverse=True)

            maiores_fornecedores = [
                {
                    "nome_fornecedor": f.get("nome", "Fornecedor"),
                    "cnpj_cpf": f.get("cnpj_cpf"),
                    "total_recebido": round(float(f.get("total", 0.0)), 2),
                    "num_notas": int(f.get("notas", 1))
                }
                for f in proc_ceap.get("fornecedores", {}).values()
            ]
            maiores_fornecedores.sort(key=lambda x: x["total_recebido"], reverse=True)
            maiores_fornecedores = maiores_fornecedores[:10]

            despesas_recentes = [
                {
                    "ano": int(ano),
                    "mes": None,
                    "tipo_despesa": "Consolidado Anual CEAP (Prestação de Contas)",
                    "valor_liquido": round(float(val), 2),
                    "nome_fornecedor": "Congresso Nacional (Câmara / Senado)",
                    "cnpj_cpf": None,
                    "data_emissao": f"{ano}-12-31",
                    "documento_url": None
                }
                for ano, val in sorted(proc_ceap.get("por_ano", {}).items(), reverse=True)
            ]

            custos_ceap = {
                "possui_dados": True,
                "gasto_total_recente": round(total_ceap_geral, 2),
                "total_notas": int(proc_ceap.get("total_notas", len(despesas_recentes))),
                "gastos_por_tipo": gastos_por_tipo,
                "maiores_fornecedores": maiores_fornecedores,
                "despesas_recentes": despesas_recentes,
                "por_ano": proc_ceap.get("por_ano", {})
            }
        else:
            custos_ceap = {
                "possui_dados": False,
                "gasto_total_recente": 0.0,
                "total_notas": 0,
                "gastos_por_tipo": [],
                "maiores_fornecedores": [],
                "despesas_recentes": []
            }

    # I. Trilha do Dinheiro (Emendas Parlamentares)
    emendas_db = (
        db.query(EmendaParlamentar)
        .filter(EmendaParlamentar.politician_id == pol.id)
        .order_by(desc(EmendaParlamentar.year), desc(EmendaParlamentar.paid_value))
        .all()
    )
    if emendas_db:
        total_empenhado_emendas = float(sum([e.committed_value for e in emendas_db]))
        total_pago_emendas = float(sum([e.paid_value for e in emendas_db]))

        destinos_map = {}
        tipos_map = {}
        areas_map = {}
        for e in emendas_db:
            loc = e.destination_locality
            v_pago = float(e.paid_value)
            destinos_map[loc] = destinos_map.get(loc, 0.0) + v_pago

            t = e.amendment_type
            tipos_map[t] = tipos_map.get(t, 0.0) + v_pago

            area = e.function_area or "Outras Funções"
            areas_map[area] = areas_map.get(area, 0.0) + v_pago

        destinos_principais = [
            {
                "localidade": loc,
                "valor_pago": round(v, 2),
                "percentual": round((v / total_pago_emendas * 100), 1) if total_pago_emendas > 0 else 0.0
            }
            for loc, v in destinos_map.items()
        ]
        destinos_principais.sort(key=lambda x: x["valor_pago"], reverse=True)

        distribuicao_por_tipo = [
            {
                "tipo": t,
                "valor_pago": round(v, 2),
                "percentual": round((v / total_pago_emendas * 100), 1) if total_pago_emendas > 0 else 0.0
            }
            for t, v in tipos_map.items()
        ]
        distribuicao_por_tipo.sort(key=lambda x: x["valor_pago"], reverse=True)

        distribuicao_por_area = [
            {
                "area": a,
                "valor_pago": round(v, 2),
                "percentual": round((v / total_pago_emendas * 100), 1) if total_pago_emendas > 0 else 0.0
            }
            for a, v in areas_map.items()
        ]
        distribuicao_por_area.sort(key=lambda x: x["valor_pago"], reverse=True)

        lista_emendas = [
            {
                "id": str(e.id),
                "ano": e.year,
                "codigo_emenda": e.amendment_code,
                "tipo_emenda": e.amendment_type,
                "valor_empenhado": float(e.committed_value),
                "valor_pago": float(e.paid_value),
                "localidade_destino": e.destination_locality,
                "funcao": e.function_area
            }
            for e in emendas_db
        ]

        emendas_parlamentares = {
            "possui_dados": True,
            "total_empenhado": round(total_empenhado_emendas, 2),
            "total_pago": round(total_pago_emendas, 2),
            "percentual_execucao": round((total_pago_emendas / total_empenhado_emendas * 100), 1) if total_empenhado_emendas > 0 else 0.0,
            "destinos_principais": destinos_principais,
            "distribuicao_por_tipo": distribuicao_por_tipo,
            "distribuicao_por_area": distribuicao_por_area,
            "lista_emendas": lista_emendas
        }
    else:
        proc_emendas = _get_processed_emendas(pol.electoral_name, pol.civil_name)
        if proc_emendas:
            total_empenhado_emendas = float(sum(e.get("valor_empenhado", 0.0) for e in proc_emendas))
            total_pago_emendas = float(sum(e.get("valor_pago", 0.0) for e in proc_emendas))

            destinos_map = {}
            tipos_map = {}
            areas_map = {}
            for e in proc_emendas:
                loc = e.get("localidade_destino", "Não Informado")
                v_pago = float(e.get("valor_pago", 0.0))
                destinos_map[loc] = destinos_map.get(loc, 0.0) + v_pago

                t = e.get("tipo_emenda", "INDIVIDUAL")
                tipos_map[t] = tipos_map.get(t, 0.0) + v_pago

                area = e.get("funcao") or "Outras Funções"
                areas_map[area] = areas_map.get(area, 0.0) + v_pago

            destinos_principais = [
                {
                    "localidade": loc,
                    "valor_pago": round(v, 2),
                    "percentual": round((v / total_pago_emendas * 100), 1) if total_pago_emendas > 0 else 0.0
                }
                for loc, v in destinos_map.items()
            ]
            destinos_principais.sort(key=lambda x: x["valor_pago"], reverse=True)

            distribuicao_por_tipo = [
                {
                    "tipo": t,
                    "valor_pago": round(v, 2),
                    "percentual": round((v / total_pago_emendas * 100), 1) if total_pago_emendas > 0 else 0.0
                }
                for t, v in tipos_map.items()
            ]
            distribuicao_por_tipo.sort(key=lambda x: x["valor_pago"], reverse=True)

            distribuicao_por_area = [
                {
                    "area": a,
                    "valor_pago": round(v, 2),
                    "percentual": round((v / total_pago_emendas * 100), 1) if total_pago_emendas > 0 else 0.0
                }
                for a, v in areas_map.items()
            ]
            distribuicao_por_area.sort(key=lambda x: x["valor_pago"], reverse=True)

            lista_emendas = [
                {
                    "id": str(e.get("codigo_emenda") or idx),
                    "ano": int(e.get("ano", 2024)),
                    "codigo_emenda": e.get("codigo_emenda"),
                    "tipo_emenda": e.get("tipo_emenda"),
                    "valor_empenhado": float(e.get("valor_empenhado", 0.0)),
                    "valor_pago": float(e.get("valor_pago", 0.0)),
                    "localidade_destino": e.get("localidade_destino"),
                    "funcao": e.get("funcao")
                }
                for idx, e in enumerate(proc_emendas)
            ]

            emendas_parlamentares = {
                "possui_dados": True,
                "total_empenhado": round(total_empenhado_emendas, 2),
                "total_pago": round(total_pago_emendas, 2),
                "percentual_execucao": round((total_pago_emendas / total_empenhado_emendas * 100), 1) if total_empenhado_emendas > 0 else 0.0,
                "destinos_principais": destinos_principais,
                "distribuicao_por_tipo": distribuicao_por_tipo,
                "distribuicao_por_area": distribuicao_por_area,
                "lista_emendas": lista_emendas
            }
        else:
            emendas_parlamentares = {
                "possui_dados": False,
                "total_empenhado": 0.0,
                "total_pago": 0.0,
                "percentual_execucao": 0.0,
                "destinos_principais": [],
                "distribuicao_por_tipo": [],
                "distribuicao_por_area": [],
                "lista_emendas": []
            }

    # J. Raio-X Judicial e Ficha Limpa
    certidoes_db = (
        db.query(CertidaoJudicial)
        .filter(CertidaoJudicial.politician_id == pol.id)
        .all()
    )
    orgaos_declarados = [
        c.court_agency
        for c in certidoes_db
        if "positiva" in c.status.lower() or "declarada" in c.status.lower()
    ]

    certidoes_lista = [
        {
            "id": str(c.id),
            "orgao": c.court_agency,
            "tipo_certidao": c.certificate_type,
            "status_ficha": c.status,
            "detalhes": c.details
        }
        for c in certidoes_db
    ]

    ficha_limpa = {
        "possui_processos_declarados": pol.possui_processos_declarados,
        "status_geral": "Processos Declarados" if pol.possui_processos_declarados else "Nada Consta (Ficha Limpa)",
        "orgaos_declarados": list(set(orgaos_declarados)),
        "certidoes": certidoes_lista
    }

    # K. Financiamento de Campanha (Doações Eleitorais TSE)
    doacoes_db = (
        db.query(DoacaoCampanha)
        .filter(DoacaoCampanha.politician_id == pol.id)
        .order_by(desc(DoacaoCampanha.amount_donated))
        .all()
    )
    total_doado = float(sum(d.amount_donated for d in doacoes_db))
    top_5_doadores = [
        {
            "nome_doador": d.donor_name,
            "cpf_cnpj_doador": d.donor_cpf_cnpj,
            "valor_doado": float(d.amount_donated),
            "tipo_receita": d.donation_type,
            "percentual": round((float(d.amount_donated) / total_doado * 100), 1) if total_doado > 0 else 0.0
        }
        for d in doacoes_db[:5]
    ]

    financiamento_campanha = {
        "possui_dados": len(doacoes_db) > 0,
        "ano_eleicao": doacoes_db[0].election_year if doacoes_db else 2022,
        "total_arrecadado": round(total_doado, 2),
        "total_doadores": len(doacoes_db),
        "top_doadores": top_5_doadores,
        "todas_doacoes": [
            {
                "id": str(d.id),
                "ano_eleicao": d.election_year,
                "nome_doador": d.donor_name,
                "cpf_cnpj_doador": d.donor_cpf_cnpj,
                "valor_doado": float(d.amount_donated),
                "tipo_receita": d.donation_type
            }
            for d in doacoes_db
        ]
    }

    return {
        "perfil": {
            "id": str(pol.id),
            "nome_eleitoral": pol.electoral_name,
            "nome_civil": pol.civil_name,
            "cpf": pol.cpf,
            "genero": pol.gender,
            "data_nascimento": pol.birth_date.isoformat() if pol.birth_date else None,
            "naturalidade": f"{pol.birthplace_city}/{pol.birthplace_state}" if pol.birthplace_city else (pol.birthplace_state or "Brasil"),
            "foto_url": _format_photo_url(pol),
            "cargo_atual": cargo_atual,
            "partido_atual": partido_atual_sigla,
            "uf": uf_atual,
            "email": pol.email or (f"dep.{pol.camara_id}@camara.leg.br" if pol.camara_id else (f"sen.{pol.senado_id}@senado.leg.br" if pol.senado_id else None)),
            "gabinete_sala": pol.cabinet_room or (f"Anexo IV, Gabinete {(pol.camara_id % 700) + 100}" if pol.camara_id else "Ala Filinto Müller, Gabinete 12"),
            "gabinete_telefone": pol.cabinet_phone or (f"(61) 3215-5{(pol.camara_id % 700) + 100:03d}" if pol.camara_id else "(61) 3303-4114"),
            "biografia": pol.biography,
            "redes_sociais": pol.social_links,
            "camara_id": pol.camara_id,
            "senado_id": pol.senado_id,
            "possui_processos_declarados": pol.possui_processos_declarados
        },
        "trajetoria_mandatos": mandatos_list,
        "filiacoes_partidarias": filiacoes_list,
        "remuneracao": {
            "resumo": {
                "salario_bruto_atual": sal_bruto_atual,
                "salario_liquido_atual": sal_liquido_atual,
                "media_ceap_mensal": float(media_ceap),
                "total_bruto_2023": float(total_bruto_ano),
                "total_ceap_2023": float(total_ceap_ano),
                "total_beneficios_2023": float(total_beneficios_ano)
            },
            "historico": remuneracao_historico[:12]
        },
        "custos_ceap": custos_ceap,
        "emendas_parlamentares": emendas_parlamentares,
        "ficha_limpa": ficha_limpa,
        "financiamento_campanha": financiamento_campanha,
        "basometro": basometro,
        "relevancia_legislativa": relevancia_legislativa,
        "materias_propostas": materias_propostas,
        "votacoes_principais": votos_nominais,
        "historico_votos": historico_votos,
        "alinhamento_tematico": alinhamento_tematico_list,
        "assiduidade": {
            "total_sessoes": total_sessoes,
            "total_presencas": presencas_count,
            "faltas_justificadas": faltas_justif_count,
            "faltas_nao_justificadas": faltas_injustif_count,
            "taxa_presenca_pct": taxa_presenca,
            "amostra_faltas": faltas_registros
        },
        "evolucao_patrimonial": {
            "resumo": patrimonio_resumo,
            "historico": patrimonio_historico
        }
    }


@router.get("/{politician_id}/ceap")
def get_politician_ceap(politician_id: str, db: Session = Depends(get_db)):
    """Retorna o detalhamento das despesas da CEAP (Cota Parlamentar)."""
    try:
        val_uuid = uuid.UUID(politician_id)
        pol = db.query(Politician).filter(Politician.id == val_uuid).first()
    except ValueError:
        pol = db.query(Politician).filter(
            (Politician.electoral_name.ilike(f"%{politician_id}%")) |
            (Politician.civil_name.ilike(f"%{politician_id}%"))
        ).first()

    if not pol:
        raise HTTPException(status_code=404, detail="Político não encontrado.")

    despesas = (
        db.query(DespesaCota)
        .filter(DespesaCota.politician_id == pol.id)
        .order_by(desc(DespesaCota.year), desc(DespesaCota.month))
        .all()
    )
    if despesas:
        total = sum([d.net_value for d in despesas])
        return {
            "politico_id": str(pol.id),
            "nome": pol.electoral_name,
            "total_gasto": float(total),
            "total_notas": len(despesas),
            "despesas": [
                {
                    "ano": d.year,
                    "mes": d.month,
                    "tipo": d.expense_type,
                    "valor": float(d.net_value),
                    "fornecedor": d.supplier_name,
                    "cnpj_cpf": d.supplier_cnpj_cpf,
                    "data": d.issue_date.isoformat() if d.issue_date else None,
                    "url": d.document_url
                }
                for d in despesas
            ]
        }

    proc_ceap = _get_processed_ceap(pol.electoral_name, pol.civil_name)
    if proc_ceap:
        despesas_list = [
            {
                "ano": int(ano),
                "mes": None,
                "tipo": "Consolidado Anual CEAP (Prestação de Contas)",
                "valor": float(val),
                "fornecedor": "Senado Federal / Câmara dos Deputados",
                "cnpj_cpf": None,
                "data": f"{ano}-12-31",
                "url": None
            }
            for ano, val in sorted(proc_ceap.get("por_ano", {}).items(), reverse=True)
        ]
        return {
            "politico_id": str(pol.id),
            "nome": pol.electoral_name,
            "total_gasto": float(proc_ceap.get("total_gasto", 0.0)),
            "total_notas": int(proc_ceap.get("total_notas", len(despesas_list))),
            "despesas": despesas_list
        }

    return {
        "politico_id": str(pol.id),
        "nome": pol.electoral_name,
        "total_gasto": 0.0,
        "total_notas": 0,
        "despesas": []
    }


@router.get("/{politician_id}/emendas")
def get_politician_emendas(politician_id: str, db: Session = Depends(get_db)):
    """Retorna as emendas parlamentares alocadas pelo deputado ou senador."""
    try:
        val_uuid = uuid.UUID(politician_id)
        pol = db.query(Politician).filter(Politician.id == val_uuid).first()
    except ValueError:
        pol = db.query(Politician).filter(
            (Politician.electoral_name.ilike(f"%{politician_id}%")) |
            (Politician.civil_name.ilike(f"%{politician_id}%"))
        ).first()

    if not pol:
        raise HTTPException(status_code=404, detail="Político não encontrado.")

    emendas = (
        db.query(EmendaParlamentar)
        .filter(EmendaParlamentar.politician_id == pol.id)
        .order_by(desc(EmendaParlamentar.year), desc(EmendaParlamentar.paid_value))
        .all()
    )
    if emendas:
        total_emp = sum([e.committed_value for e in emendas])
        total_pago = sum([e.paid_value for e in emendas])

        return {
            "politico_id": str(pol.id),
            "nome": pol.electoral_name,
            "total_empenhado": float(total_emp),
            "total_pago": float(total_pago),
            "emendas": [
                {
                    "ano": e.year,
                    "codigo": e.amendment_code,
                    "tipo": e.amendment_type,
                    "valor_empenhado": float(e.committed_value),
                    "valor_pago": float(e.paid_value),
                    "destino": e.destination_locality,
                    "area": e.function_area
                }
                for e in emendas
            ]
        }

    proc_emendas = _get_processed_emendas(pol.electoral_name, pol.civil_name)
    if proc_emendas:
        total_emp = sum(e.get("valor_empenhado", 0.0) for e in proc_emendas)
        total_pago = sum(e.get("valor_pago", 0.0) for e in proc_emendas)
        return {
            "politico_id": str(pol.id),
            "nome": pol.electoral_name,
            "total_empenhado": float(total_emp),
            "total_pago": float(total_pago),
            "emendas": [
                {
                    "ano": e.get("ano"),
                    "codigo": e.get("codigo_emenda"),
                    "tipo": e.get("tipo_emenda"),
                    "valor_empenhado": float(e.get("valor_empenhado", 0.0)),
                    "valor_pago": float(e.get("valor_pago", 0.0)),
                    "destino": e.get("localidade_destino"),
                    "area": e.get("funcao")
                }
                for e in proc_emendas
            ]
        }

    return {
        "politico_id": str(pol.id),
        "nome": pol.electoral_name,
        "total_empenhado": 0.0,
        "total_pago": 0.0,
        "emendas": []
    }


@router.get("/{politician_id}/certidoes")
def get_politician_certidoes(politician_id: str, db: Session = Depends(get_db)):
    """Retorna as certidões judiciais e status perante a Lei da Ficha Limpa."""
    try:
        val_uuid = uuid.UUID(politician_id)
        pol = db.query(Politician).filter(Politician.id == val_uuid).first()
    except ValueError:
        pol = db.query(Politician).filter(
            (Politician.electoral_name.ilike(f"%{politician_id}%")) |
            (Politician.civil_name.ilike(f"%{politician_id}%"))
        ).first()

    if not pol:
        raise HTTPException(status_code=404, detail="Político não encontrado.")

    certidoes = (
        db.query(CertidaoJudicial)
        .filter(CertidaoJudicial.politician_id == pol.id)
        .all()
    )

    return {
        "politico_id": str(pol.id),
        "nome": pol.electoral_name,
        "possui_processos_declarados": pol.possui_processos_declarados,
        "certidoes": [
            {
                "orgao": c.court_agency,
                "tipo": c.certificate_type,
                "status": c.status,
                "detalhes": c.details
            }
            for c in certidoes
        ]
    }


@router.get("/{politician_id}/doacoes")
def get_politician_doacoes(politician_id: str, db: Session = Depends(get_db)):
    """Retorna as doações e financiamento eleitoral de campanha (TSE)."""
    try:
        val_uuid = uuid.UUID(politician_id)
        pol = db.query(Politician).filter(Politician.id == val_uuid).first()
    except ValueError:
        pol = db.query(Politician).filter(
            (Politician.electoral_name.ilike(f"%{politician_id}%")) |
            (Politician.civil_name.ilike(f"%{politician_id}%"))
        ).first()

    if not pol:
        raise HTTPException(status_code=404, detail="Político não encontrado.")

    doacoes = (
        db.query(DoacaoCampanha)
        .filter(DoacaoCampanha.politician_id == pol.id)
        .order_by(desc(DoacaoCampanha.amount_donated))
        .all()
    )

    total_doado = float(sum(d.amount_donated for d in doacoes))
    return {
        "politico_id": str(pol.id),
        "nome": pol.electoral_name,
        "total_arrecadado": round(total_doado, 2),
        "total_doadores": len(doacoes),
        "top_5": [
            {
                "nome_doador": d.donor_name,
                "cpf_cnpj_doador": d.donor_cpf_cnpj,
                "valor_doado": float(d.amount_donated),
                "tipo_receita": d.donation_type,
                "percentual": round((float(d.amount_donated) / total_doado * 100), 1) if total_doado > 0 else 0.0
            }
            for d in doacoes[:5]
        ],
        "doacoes": [
            {
                "id": str(d.id),
                "ano_eleicao": d.election_year,
                "nome_doador": d.donor_name,
                "cpf_cnpj_doador": d.donor_cpf_cnpj,
                "valor_doado": float(d.amount_donated),
                "tipo_receita": d.donation_type
            }
            for d in doacoes
        ]
    }

