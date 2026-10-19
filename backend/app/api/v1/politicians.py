import re
import unicodedata
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from app.core.database import get_db
from app.core.links import url_oficial_proposicao
from app.core.numeros import brl
from app.core.numeros import pct as _pct
from app.core.query_utils import ALL_KEYWORDS, BRT, contains
from app.models import (
    CargoPoliticoEnum,
    CasaLegislativaEnum,
    Mandate,
    PartyAffiliation,
    PoliticalParty,
    Politician,
    ProcessoJudicial,
)
from app.models.leg import Autoria, Proposicao, Votacao, Voto
from app.services import financas_service
from app.services.basometro import calcular_basometro
from app.services.financas_service import Certidao
from app.services.ialp_pesos import carregar_pesos_ialp
from app.services.ialp_pontos import pontos_ialp_pessoa
from app.services.presidencia_service import listar_presidentes, periodo_do_mandato, presidente_por_referencia
from app.services.resumo_votos_service import resumo_votos as resumo_votos_do_parlamentar
from app.services.roi_cidadao import METODOLOGIA as ROI_METODOLOGIA
from app.services.roi_cidadao import PISO_DE_PONTOS, calcular_roi
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, desc, func
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import or_, text
from sqlalchemy.orm import Session

router = APIRouter()

# Limites de listas devolvidas no dossiê (os agregados são calculados sobre todos os registros; a exceção é o resumo de
# doações, que agrupa doadores em Python sobre as doações lidas do banco)
MAX_VOTES_LISTED = 300
MAX_PROPOSITIONS_LISTED = 500
# Quando a fonte repete o parlamentar na mesma proposição, vale o papel de maior peso: autor principal, relator, coautor
_PRIORIDADE_PAPEL: Dict[str, int] = {"AUTOR_PRINCIPAL": 0, "RELATOR": 1, "COAUTOR": 2}


def _normalize_name(text: Optional[str]) -> str:
    if not text:
        return ""
    return "".join(c for c in unicodedata.normalize("NFD", text.upper()) if unicodedata.category(c) != "Mn").strip()


SIMBOLICO_KEYWORDS = [
    "homenagem",
    "dia nacional",
    "dia municipal",
    "dia estadual",
    "semana nacional",
    "denomina",
    "título",
    "titulo",
    "cidadão honorário",
    "cidadao honorario",
    "patrono",
    "patrona",
    "comemora",
    "comemoração",
    "comemoracao",
    "monumento",
    "nomeia",
    "inscreve no livro dos heróis",
    "livro dos herois",
    "capital nacional do",
    "institui o dia",
    "institui a semana",
]

# Fotos locais dos presidentes, aplicadas SOMENTE a quem possui mandato de PRESIDENTE (nunca por substring de nome)
PRESIDENT_PHOTOS = {
    "ITAMAR FRANCO": "/presidents/itamar-franco.jpg",
    "FERNANDO HENRIQUE CARDOSO": "/presidents/fhc.jpg",
    "LUIZ INACIO LULA DA SILVA": "/presidents/lula.jpg",
    "LULA": "/presidents/lula.jpg",
    "DILMA ROUSSEFF": "/presidents/dilma.jpg",
    "MICHEL TEMER": "/presidents/temer.jpg",
    "JAIR BOLSONARO": "/presidents/bolsonaro.jpg",
    "JAIR MESSIAS BOLSONARO": "/presidents/bolsonaro.jpg",
}

VOTE_LABELS = {
    "SIM": "Sim",
    "NAO": "Não",
    "ABSTENCAO": "Abstenção",
    "OBSTRUCAO": "Obstrução",
    "AUSENTE": "Ausente",
    "ARTIGO_17": "Art. 17",
}


def _pessoas_financas(db: Session, pol: Politician) -> List[int]:
    """Cadastros de `core.pessoa` do parlamentar, onde ficam as finanças (ver `financas_service`)."""
    return financas_service.pessoas_do_parlamentar(db, pol.id, pol.camara_id, pol.senado_id)


_UNIDADE_ASSIDUIDADE = {
    CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS.value: "dia com sessão deliberativa",
    CasaLegislativaEnum.SENADO_FEDERAL.value: "dia com votação nominal em plenário",
}
_FONTE_ASSIDUIDADE = {
    CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS.value: "Câmara dos Deputados — Presença em Plenário (Ato da Mesa nº 191/2017)",
    CasaLegislativaEnum.SENADO_FEDERAL.value: "Senado Federal — votações nominais de plenário (presença derivada do voto)",
}


def _unidade_assiduidade(casas: Any) -> Optional[str]:
    return " / ".join(_UNIDADE_ASSIDUIDADE[c] for c in sorted(casas) if c in _UNIDADE_ASSIDUIDADE) or None


def _fonte_assiduidade(casas: Any) -> Optional[str]:
    return " | ".join(_FONTE_ASSIDUIDADE[c] for c in sorted(casas) if c in _FONTE_ASSIDUIDADE) or None


def _format_photo_url(politician: Politician, is_president: bool = False) -> Optional[str]:
    """Retorna URL confiável da foto ou fallback local para presidentes (identificados por mandato)."""
    if is_president:
        for candidate in (_normalize_name(politician.electoral_name), _normalize_name(politician.civil_name)):
            if candidate in PRESIDENT_PHOTOS:
                return PRESIDENT_PHOTOS[candidate]

    if politician.senado_id:
        return f"https://legis.senado.leg.br/senadores/fotos-oficiais/{politician.senado_id}"

    if politician.camara_id:
        return f"https://www.camara.leg.br/internet/deputado/bandep/{politician.camara_id}.jpg"

    if politician.photo_url:
        url = politician.photo_url.strip()
        if "senado.leg.br" in url and politician.senado_id:
            return f"https://legis.senado.leg.br/senadores/fotos-oficiais/{politician.senado_id}"
        if url.startswith("http://"):
            return "https://" + url[7:]
        return url

    return None


def _to_brt(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(BRT)


@router.get("/presidents", response_model=List[Dict[str, Any]])
def get_historical_presidents(db: Session = Depends(get_db)):
    """
    Retorna a lista canônica unificada de presidentes históricos desde 1995, com fotos oficiais,
    partidos, períodos de mandato, vices e ministros da Fazenda/Economia.
    """
    presidents = listar_presidentes(db)
    if not presidents:
        raise HTTPException(status_code=404, detail="Dados de presidentes ainda não processados.")
    return presidents


@router.get("/presidents/{mandate_id}")
def get_president_by_mandate(mandate_id: str, db: Session = Depends(get_db)):
    """Retorna detalhes específicos de um mandato presidencial unificado."""
    pres = presidente_por_referencia(db, mandate_id)
    if not pres:
        raise HTTPException(status_code=404, detail=f"Mandato '{mandate_id}' não encontrado.")
    return pres


def _parse_office(office: Optional[str]) -> Optional[CargoPoliticoEnum]:
    if not office or office.lower() in ALL_KEYWORDS:
        return None
    try:
        return CargoPoliticoEnum[office.strip().upper()]
    except KeyError:
        valid = ", ".join(c.name for c in CargoPoliticoEnum)
        raise HTTPException(status_code=422, detail=f"Cargo inválido '{office}'. Valores aceitos: {valid}.")


def _parse_uf(uf: Optional[str]) -> Optional[str]:
    if not uf or uf.lower() in ALL_KEYWORDS:
        return None
    clean = uf.strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", clean):
        raise HTTPException(status_code=422, detail=f"UF inválida '{uf}'. Use a sigla de 2 letras.")
    return clean


PARTY_SIGLA_ALIASES: Dict[str, str] = {
    "PODEMOS": "PODE",
    "PC DO B": "PCDOB",
    "PC_DO_B": "PCDOB",
    "PRB": "REPUBLICANOS",
    "PRB/REP": "REPUBLICANOS",
    "SD": "SOLIDARIEDADE",
    "PATRI": "PATRIOTA",
}


def _is_current_mandate_clause():
    today = date.today()
    return or_(Mandate.end_date.is_(None), Mandate.end_date >= today)


@router.get("", response_model=Dict[str, Any])
@router.get("/", response_model=Dict[str, Any])
def search_politicians(
    search: Optional[str] = Query(None, max_length=100, description="Busca por nome eleitoral ou civil"),
    office: Optional[str] = Query(None, description="Filtro por cargo (DEPUTADO_FEDERAL, SENADOR, PRESIDENTE)"),
    party: Optional[str] = Query(None, max_length=50, description="Filtro por sigla do partido (match exato)"),
    partido: Optional[str] = Query(None, max_length=50, description="Alias para party"),
    uf: Optional[str] = Query(None, description="Filtro por UF de jurisdição do mandato"),
    mandate_id: Optional[str] = Query(
        None, description="Filtro por mandato presidencial (ex: lula-2023, bolsonaro-2019)"
    ),
    limit: int = Query(50, ge=1, le=800, description="Quantidade máxima de registros"),
    offset: int = Query(0, ge=0, description="Deslocamento para paginação"),
    db: Session = Depends(get_db),
):
    """
    Endpoint para busca e seleção de políticos para alimentar Autocomplete, Combobox e Bancadas.
    Retorna lista consolidada com nome, partido atual, cargo, UF e foto.
    """
    query = db.query(Politician)

    if search and search.strip():
        query = query.filter(
            or_(
                contains(Politician.electoral_name, search),
                contains(Politician.civil_name, search),
            )
        )

    raw_party = (party or partido or "").strip()
    target_party = None if not raw_party or raw_party.lower() in ALL_KEYWORDS else raw_party.upper()
    office_enum = _parse_office(office)
    clean_uf = _parse_uf(uf)

    if target_party:
        # Match de sigla com suporte a aliases conhecidos (ex.: Podemos -> PODE, PC do B -> PCdoB)
        norm_sigla = PARTY_SIGLA_ALIASES.get(target_party, target_party)
        party_ids = db.query(PoliticalParty.id).filter(
            or_(
                func.upper(PoliticalParty.acronym) == target_party,
                func.upper(PoliticalParty.acronym) == norm_sigla,
            )
        )
        if mandate_id and mandate_id.strip():
            date_range = periodo_do_mandato(db, mandate_id.strip())
            if date_range:
                m_start, m_end = date_range
                mandate_clause = and_(
                    Mandate.start_date <= m_end,
                    or_(Mandate.end_date.is_(None), Mandate.end_date >= m_start),
                )
                aff_clause = and_(
                    PartyAffiliation.start_date <= m_end,
                    or_(PartyAffiliation.end_date.is_(None), PartyAffiliation.end_date >= m_start),
                )
            else:
                mandate_clause = _is_current_mandate_clause()
                aff_clause = PartyAffiliation.is_current.is_(True)
        else:
            mandate_clause = _is_current_mandate_clause()
            aff_clause = PartyAffiliation.is_current.is_(True)

        party_mandate_subq = db.query(Mandate.politician_id).filter(Mandate.party_id.in_(party_ids), mandate_clause)
        party_aff_subq = db.query(PartyAffiliation.politician_id).filter(
            PartyAffiliation.party_id.in_(party_ids), aff_clause
        )
        query = query.filter(or_(Politician.id.in_(party_mandate_subq), Politician.id.in_(party_aff_subq)))

    if office_enum:
        query = query.filter(Politician.id.in_(db.query(Mandate.politician_id).filter(Mandate.office == office_enum)))

    if clean_uf:
        query = query.filter(
            Politician.id.in_(db.query(Mandate.politician_id).filter(Mandate.jurisdiction_state == clean_uf))
        )

    if mandate_id and mandate_id.strip():
        date_range = periodo_do_mandato(db, mandate_id.strip())
        if date_range:
            m_start, m_end = date_range
            mandate_active_subq = db.query(Mandate.politician_id).filter(
                Mandate.start_date <= m_end,
                or_(Mandate.end_date.is_(None), Mandate.end_date >= m_start),
            )
            if office_enum:
                mandate_active_subq = mandate_active_subq.filter(Mandate.office == office_enum)
            query = query.filter(Politician.id.in_(mandate_active_subq))

    total_count = query.count()
    politicians = query.order_by(Politician.electoral_name.asc(), Politician.id.asc()).offset(offset).limit(limit).all()

    # Busca em lote (sem N+1): todos os mandatos e filiações atuais dos políticos da página
    pol_ids = [p.id for p in politicians]
    mandates_by_pol: Dict[uuid.UUID, List[Any]] = {}
    current_party_by_pol: Dict[uuid.UUID, PoliticalParty] = {}
    if pol_ids:
        mandate_rows = (
            db.query(Mandate, PoliticalParty)
            .outerjoin(PoliticalParty, Mandate.party_id == PoliticalParty.id)
            .filter(Mandate.politician_id.in_(pol_ids))
            .order_by(desc(Mandate.start_date))
            .all()
        )
        for m, p in mandate_rows:
            mandates_by_pol.setdefault(m.politician_id, []).append((m, p))

        aff_rows = (
            db.query(PartyAffiliation, PoliticalParty)
            .join(PoliticalParty, PartyAffiliation.party_id == PoliticalParty.id)
            .filter(PartyAffiliation.politician_id.in_(pol_ids), PartyAffiliation.is_current.is_(True))
            .all()
        )
        for aff, p in aff_rows:
            current_party_by_pol.setdefault(aff.politician_id, p)

    results = []
    for pol in politicians:
        candidates = mandates_by_pol.get(pol.id, [])
        preferred = [
            c
            for c in candidates
            if (not office_enum or c[0].office == office_enum)
            and (not target_party or (c[1] and c[1].acronym.upper() == target_party))
        ]
        chosen = (preferred or candidates or [None])[0]
        mandate_obj = chosen[0] if chosen else None
        party_obj = chosen[1] if chosen else None
        if not party_obj:
            party_obj = current_party_by_pol.get(pol.id)

        is_president = any(c[0].office == CargoPoliticoEnum.PRESIDENTE for c in candidates)
        results.append(
            {
                "id": str(pol.id),
                "nome_eleitoral": pol.electoral_name,
                "nome_civil": pol.civil_name,
                "cargo": mandate_obj.office.value if mandate_obj else "PARLAMENTAR",
                "partido_sigla": party_obj.acronym if party_obj else "S.PART.",
                "partido_nome": party_obj.full_name if party_obj else "Sem Partido",
                "uf": (mandate_obj.jurisdiction_state if mandate_obj else (pol.birthplace_state or "BR")),
                "foto_url": _format_photo_url(pol, is_president),
                "camara_id": pol.camara_id,
                "senado_id": pol.senado_id,
            }
        )

    return {
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "politicos": results,
    }


def _politico_do_core(db: Session, uid: uuid.UUID) -> Optional[Politician]:
    """
    Parlamentar que existe só no schema novo (ex.: ex-parlamentares carregados pelo histórico e pela presença).
    Devolve um Politician transitório, nunca persistido, para que as seções ainda legadas do dossiê respondam vazias
    e as seções já migradas (proposições, votos, presença) usem o `core`/`leg` pelo mesmo uid.
    """
    linha = (
        db.execute(
            text(
                """
                SELECT pe.nome_exibicao, pe.uf_nascimento, pe.data_nascimento, fm.url_origem AS foto,
                       (SELECT valor::int FROM core.pessoa_identificador WHERE pessoa_id = pe.id AND tipo = 'CAMARA_ID'
                         LIMIT 1) AS camara_id,
                       (SELECT valor::int FROM core.pessoa_identificador WHERE pessoa_id = pe.id AND tipo = 'SENADO_ID'
                         LIMIT 1) AS senado_id,
                       (SELECT n.nome FROM core.pessoa_nome n WHERE n.pessoa_id = pe.id AND n.tipo = 'CIVIL'
                         LIMIT 1) AS nome_civil
                FROM core.pessoa pe LEFT JOIN core.midia fm ON fm.id = pe.foto_midia_id WHERE pe.uid = :uid
                """
            ),
            {"uid": uid},
        )
        .mappings()
        .first()
    )
    if not linha:
        return None
    return Politician(
        id=uid,
        civil_name=linha["nome_civil"] or linha["nome_exibicao"],
        electoral_name=linha["nome_exibicao"],
        camara_id=linha["camara_id"],
        senado_id=linha["senado_id"],
        birth_date=linha["data_nascimento"],
        birthplace_state=linha["uf_nascimento"],
        photo_url=linha["foto"],
        possui_processos_declarados=False,
    )


def _trajetoria_core(db: Session, uid: uuid.UUID) -> Dict[str, Any]:
    """Mandatos e filiações de `core` para parlamentar sem registro legado (mesmo formato do dossiê)."""
    mandatos = (
        db.execute(
            text(
                """
                SELECT m.uid, c.codigo AS cargo, c.esfera, e.ano AS ano_eleicao, m.numero_mandato, m.inicio, m.fim,
                       m.votos, m.percentual_votos, m.coligacao, coalesce(ci.uf, 'BR') AS uf,
                       (SELECT cp.canonico_sigla FROM core.vw_partido_canonico cp
                         WHERE cp.id = coalesce((SELECT mp.partido_id FROM core.mandato_partido mp
                                                  WHERE mp.mandato_id = m.id ORDER BY lower(mp.periodo) DESC LIMIT 1),
                                                m.partido_id)) AS partido
                FROM core.mandato m
                JOIN core.pessoa pe ON pe.id = m.pessoa_id
                JOIN ref.cargo c ON c.id = m.cargo_id
                JOIN ref.circunscricao ci ON ci.id = m.circunscricao_id
                LEFT JOIN core.eleicao e ON e.id = m.eleicao_id
                WHERE pe.uid = :uid AND m.condicao <> 'NOMEADO'
                ORDER BY m.inicio DESC
                """
            ),
            {"uid": uid},
        )
        .mappings()
        .all()
    )
    filiacoes = (
        db.execute(
            text(
                """
                SELECT f.id, cp.canonico_sigla AS sigla, p.nome, lower(f.periodo) AS inicio,
                       CASE WHEN upper_inf(f.periodo) THEN NULL ELSE upper(f.periodo) END AS fim,
                       upper_inf(f.periodo) AS atual, f.uf
                FROM core.filiacao f
                JOIN core.pessoa pe ON pe.id = f.pessoa_id
                JOIN core.partido p ON p.id = f.partido_id
                JOIN core.vw_partido_canonico cp ON cp.id = f.partido_id
                WHERE pe.uid = :uid ORDER BY lower(f.periodo) DESC
                """
            ),
            {"uid": uid},
        )
        .mappings()
        .all()
    )
    hoje = date.today()
    return {
        "mandatos": [
            {
                "id": str(m["uid"]),
                "cargo": m["cargo"],
                "esfera": m["esfera"],
                "ano_eleicao": m["ano_eleicao"],
                "numero_mandato": m["numero_mandato"],
                "data_inicio": m["inicio"].isoformat(),
                "data_fim": m["fim"].isoformat() if m["fim"] else None,
                "status": "EM_EXERCICIO" if (m["fim"] is None or m["fim"] >= hoje) else "ENCERRADO",
                "partido_sigla": m["partido"] or "S.PART.",
                "uf": m["uf"],
                "total_votos": m["votos"],
                "percentual_votos": float(m["percentual_votos"]) if m["percentual_votos"] is not None else None,
                "coligacao": m["coligacao"],
            }
            for m in mandatos
        ],
        "filiacoes": [
            {
                "id": str(f["id"]),
                "partido_sigla": f["sigla"],
                "partido_nome": f["nome"],
                "data_filiacao": f["inicio"].isoformat() if f["inicio"] else None,
                "data_desfiliacao": f["fim"].isoformat() if f["fim"] else None,
                "is_atual": f["atual"],
                "motivo_desfiliacao": None,
                "uf": f["uf"],
            }
            for f in filiacoes
        ],
    }


def _resolve_politician(db: Session, politician_id: str) -> Politician:
    """
    Resolve o político por UUID, ID da Câmara/Senado ou nome exato (slug). Nunca por substring:
    se o nome for ambíguo devolve 409 em vez de escolher um registro arbitrário.
    """
    try:
        uid = uuid.UUID(politician_id)
        pol = db.query(Politician).filter(Politician.id == uid).first()
        if pol:
            return pol
        pol = _politico_do_core(db, uid)
        if pol:
            return pol
    except ValueError:
        pass

    if politician_id.isdigit():
        num_id = int(politician_id)
        pol = (
            db.query(Politician)
            .filter(or_(Politician.camara_id == num_id, Politician.senado_id == num_id))
            .order_by(Politician.camara_id.is_(None), Politician.electoral_name)
            .first()
        )
        if pol:
            return pol

    slug = politician_id.replace("-", " ").strip().lower()
    if slug:
        matches = (
            db.query(Politician)
            .filter(or_(func.lower(Politician.electoral_name) == slug, func.lower(Politician.civil_name) == slug))
            .order_by(Politician.electoral_name, Politician.id)
            .limit(2)
            .all()
        )
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise HTTPException(status_code=409, detail=f"Identificador '{politician_id}' é ambíguo; use o ID.")

    raise HTTPException(status_code=404, detail=f"Político '{politician_id}' não encontrado.")


def _enrich_judicial_records(pol: Politician, certidoes_db: List[Certidao], db: Session) -> Dict[str, Any]:
    """
    Consolida dados judiciais a partir de `processos_judiciais` e `certidoes_judiciais`.
    Campos ausentes são devolvidos como None: nenhum número de processo, data ou código é inventado.
    """
    processos_db = (
        db.query(ProcessoJudicial)
        .filter(ProcessoJudicial.politician_id == pol.id)
        .order_by(desc(ProcessoJudicial.process_date))
        .all()
    )
    processos_detalhados: List[Dict[str, Any]] = [
        {
            "numero_processo": p.process_number,
            "tribunal": p.court_agency,
            "data_processo": p.process_date,
            "classe_assunto": p.case_class,
            "descricao": p.description,
            "situacao_juridica": p.legal_status,
            "link_comprovacao": p.proof_url,
            "status_resumo": p.status_summary,
        }
        for p in processos_db
    ]

    def _is_positive(cert: Certidao) -> bool:
        status_clean = (cert.status or "").lower()
        return "positiva" in status_clean or "declarada" in status_clean

    # Certidão positiva/declarada registrada também significa que há processos, mesmo que o sinalizador esteja desligado
    possui_processos = (
        len(processos_detalhados) > 0
        or bool(pol.possui_processos_declarados)
        or any(_is_positive(c) for c in certidoes_db)
    )

    # Sinalizado como positivo mas sem detalhamento individual: usa apenas o que a certidão realmente registra
    if possui_processos and not processos_detalhados:
        for c in certidoes_db:
            status_clean = (c.status or "").lower()
            if "positiva" in status_clean or "declarada" in status_clean:
                processos_detalhados.append(
                    {
                        "numero_processo": c.process_number,
                        "tribunal": c.court_agency,
                        "data_processo": c.issue_date,
                        "classe_assunto": c.certificate_type,
                        "descricao": c.details,
                        "situacao_juridica": None,
                        "link_comprovacao": c.proof_url,
                        "status_resumo": "Declarado no TSE",
                    }
                )

    certidoes_lista = []
    orgaos_declarados = []
    for c in certidoes_db:
        status_c = c.status or ""
        is_pos = "positiva" in status_c.lower() or "declarada" in status_c.lower()
        if is_pos:
            orgaos_declarados.append(c.court_agency)

        certidoes_lista.append(
            {
                "id": str(c.id),
                "orgao": c.court_agency,
                "tipo_certidao": c.certificate_type,
                "tipo": c.certificate_type,
                "status_ficha": status_c,
                "status": status_c,
                "detalhes": c.details,
                "numero_processo": c.process_number,
                "data_emissao": c.issue_date,
                "link_comprovacao": c.proof_url,
                "codigo_autenticidade": c.auth_code,
            }
        )

    return {
        "possui_processos_declarados": possui_processos,
        # "Nada Consta" só é afirmado quando há certidão registrada; sem nenhum dado o status é null (desconhecido)
        "status_geral": (
            "Processos Declarados" if possui_processos else ("Nada Consta (Ficha Limpa)" if certidoes_lista else None)
        ),
        "dados_certidoes_disponiveis": len(certidoes_lista) > 0 or len(processos_detalhados) > 0,
        "orgaos_declarados": sorted(set(orgaos_declarados)),
        # Portal público de consulta (não aponta para um candidato específico)
        "link_tse_divulgacand": "https://divulgacandcontas.tse.jus.br/divulga/#/",
        "processos_detalhados": processos_detalhados,
        "certidoes": certidoes_lista,
    }


@router.get("/{politician_id}", response_model=Dict[str, Any])
def get_politician_dossier(politician_id: str, db: Session = Depends(get_db)):
    """
    Retorna o dossiê individual 360º completo de um político:
    - Trajetória de cargos ocupados
    - Histórico completo de partidos aos quais pertenceu
    - Remunerações detalhadas e médias
    - Matérias de autoria própria
    - Histórico de votações nominais nas grandes leis
    - Contabilização de presenças e faltas com taxa de assiduidade

    Dados ausentes são devolvidos como null (ou "possui_dados": false); nada é inferido ou fabricado.
    """
    pol = _resolve_politician(db, politician_id)
    pessoas = _pessoas_financas(db, pol)

    # A. Trajetória de Mandatos
    mandates_db = (
        db.query(Mandate, PoliticalParty)
        .outerjoin(PoliticalParty, Mandate.party_id == PoliticalParty.id)
        .filter(Mandate.politician_id == pol.id)
        .order_by(desc(Mandate.start_date))
        .all()
    )

    mandatos_list = []
    cargo_atual = "PARLAMENTAR"
    uf_atual = pol.birthplace_state or "BR"
    partido_atual_sigla = "S.PART."
    presidential_periods = []

    for idx, (m, party) in enumerate(mandates_db):
        if idx == 0:
            cargo_atual = m.office.value
            uf_atual = m.jurisdiction_state
            if party:
                partido_atual_sigla = party.acronym
        if m.office == CargoPoliticoEnum.PRESIDENTE:
            presidential_periods.append((m.start_date, m.end_date))

        mandatos_list.append(
            {
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
                "percentual_votos": (float(m.vote_percentage) if m.vote_percentage is not None else None),
                "coligacao": m.coalition_name,
            }
        )

    sem_registro_legado = sa_inspect(pol).transient
    if sem_registro_legado:
        trajetoria = _trajetoria_core(db, pol.id)
        mandatos_list = trajetoria["mandatos"]
        if mandatos_list:
            cargo_atual = mandatos_list[0]["cargo"]
            uf_atual = mandatos_list[0]["uf"]
            partido_atual_sigla = mandatos_list[0]["partido_sigla"]
        presidential_periods = [
            (date.fromisoformat(m["data_inicio"]), date.fromisoformat(m["data_fim"]) if m["data_fim"] else None)
            for m in mandatos_list
            if m["cargo"] == "PRESIDENTE"
        ]

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

        filiacoes_list.append(
            {
                "id": str(aff.id),
                "partido_sigla": party.acronym,
                "partido_nome": party.full_name,
                "data_filiacao": aff.start_date.isoformat() if aff.start_date else None,
                "data_desfiliacao": aff.end_date.isoformat() if aff.end_date else None,
                "is_atual": aff.is_current,
                "motivo_desfiliacao": (aff.disaffiliation_reason.value if aff.disaffiliation_reason else None),
                "uf": aff.state,
            }
        )
    if sem_registro_legado:
        filiacoes_list = trajetoria["filiacoes"]
        atual = next((f for f in filiacoes_list if f["is_atual"]), None)
        if atual:
            partido_atual_sigla = atual["partido_sigla"]

    # C. Remunerações (Salário, CEAP, Benefícios) — totais calculados no banco para o ano mais recente com dados
    remun = financas_service.remuneracao(db, pessoas)
    remuneracao_historico = remun["historico"]
    ano_remuneracao = remun["ano"]
    total_bruto_ano = remun["total_bruto_ano"]
    total_ceap_ano = remun["total_ceap_ano"]
    total_beneficios_ano = remun["total_beneficios_ano"]
    media_ceap = remun["media_ceap"]
    sal_bruto_atual = remun["bruto_atual"]
    sal_liquido_atual = remun["liquido_atual"]
    # Subsídio bruto registrado no período coberto pela fonte: o líquido só é coletado para o mês mais recente.
    salario_acumulado_registrado = remun["acumulado"]

    # D. Matérias de Autoria Própria e Atividade Legislativa (schema leg; iniciativas do Executivo só para quem
    # exerceu mandato de PRESIDENTE, restritas ao período do mandato)
    pessoa_id = db.execute(text("SELECT id FROM core.pessoa WHERE uid = :uid"), {"uid": pol.id}).scalar()
    materias_propostas = []
    pecs_count = 0
    pls_count = 0
    outros_count = 0
    total_score_ponderado = 0.0
    props_aprovadas = 0
    pesos = carregar_pesos_ialp(db)

    author_filter = [Autoria.pessoa_id == pessoa_id, Autoria.tipo_codigo != "INSTITUCIONAL"]
    # a fonte às vezes repete o mesmo parlamentar como autor principal e coautor da mesma proposição:
    # conta-se uma vez por proposição, prevalecendo o papel de autor principal
    principais_sq = (
        db.query(Autoria.proposicao_id).filter(*author_filter, Autoria.tipo_codigo == "AUTOR_PRINCIPAL").subquery()
    )
    author_records_count = (
        db.query(func.count(func.distinct(Autoria.proposicao_id))).filter(*author_filter).scalar() or 0
        if pessoa_id is not None
        else 0
    )

    def _classificar(p: Proposicao) -> Dict[str, str]:
        txt_full = f"{p.titulo} {p.ementa or ''} {p.area_tematica or ''}".lower()
        is_simb = any(k in txt_full for k in SIMBOLICO_KEYWORDS)
        return {
            "classificacao_relevancia": "SIMBOLICO" if is_simb else "IMPACTO",
            "justificativa_relevancia": (
                "Matéria de cunho honorífico/simbólico" if is_simb else "Matéria com impacto estrutural e substantivo"
            ),
        }

    def _item(p: Proposicao, papel: str) -> Dict[str, Any]:
        nonlocal total_score_ponderado, props_aprovadas, pecs_count, pls_count, outros_count
        peso_part = pesos.peso_autoria(papel, p.tipo_codigo)
        peso_comp = pesos.peso_tipo(p.tipo_codigo)
        if p.status_codigo in ("APROVADA_E_SANCIONADA", "APROVADA_E_PROMULGADA"):
            props_aprovadas += 1
        bonus_tram = pesos.peso_status(p.status_codigo)
        prop_score = round(peso_part * peso_comp * bonus_tram, 2)
        total_score_ponderado += prop_score
        if p.tipo_codigo == "PEC":
            pecs_count += 1
        elif p.tipo_codigo in ("PL", "PLP", "MPV"):
            pls_count += 1
        else:
            outros_count += 1
        return {
            "id": str(p.uid),
            "tipo": p.tipo_codigo,
            "numero": p.numero,
            "ano": p.ano,
            "titulo": p.titulo,
            "ementa": p.ementa,
            "status": p.status_codigo,
            "area_tematica": p.area_tematica,
            "data_apresentacao": (p.data_apresentacao.isoformat() if p.data_apresentacao else None),
            "is_reforma_estrutural": p.reforma_estrutural,
            "url_oficial": url_oficial_proposicao(p),
            "papel_autoria": papel,
            "peso_participacao": peso_part,
            "peso_complexidade": peso_comp,
            "bonus_tramitacao": bonus_tram,
            "score_calculado": prop_score,
            **_classificar(p),
        }

    if author_records_count > 0:
        lideranca_count = db.query(func.count(func.distinct(principais_sq.c.proposicao_id))).scalar() or 0
        coautoria_count = int(author_records_count) - int(lideranca_count)
        total_props_db = author_records_count

        author_items = (
            db.query(Autoria, Proposicao)
            .join(Proposicao, Autoria.proposicao_id == Proposicao.id)
            .filter(*author_filter)
            .order_by(desc(Proposicao.data_apresentacao), Autoria.ordem.asc(), Proposicao.id)
            .limit(MAX_PROPOSITIONS_LISTED)
            .all()
        )
        papeis: Dict[int, str] = {}
        for pa, p in author_items:
            papel_da_linha = str(pa.tipo_codigo)
            papel_anterior = papeis.get(p.id)
            if papel_anterior is None or _PRIORIDADE_PAPEL.get(papel_da_linha, 9) < _PRIORIDADE_PAPEL.get(
                papel_anterior, 9
            ):
                papeis[p.id] = papel_da_linha
        vistos: set = set()
        for pa, p in author_items:
            if p.id in vistos:
                continue
            vistos.add(p.id)
            materias_propostas.append(_item(p, papeis[p.id]))
    else:
        prop_conditions = [Proposicao.autor_pessoa_id == pessoa_id] if pessoa_id is not None else []
        for p_start, p_end in presidential_periods:
            exec_clause = and_(Proposicao.iniciativa_executivo.is_(True), Proposicao.data_apresentacao >= p_start)
            if p_end:
                exec_clause = and_(exec_clause, Proposicao.data_apresentacao <= p_end)
            prop_conditions.append(exec_clause)
        if prop_conditions:
            props_filter = or_(*prop_conditions)
            total_props_db = db.query(func.count(Proposicao.id)).filter(props_filter).scalar() or 0
            proposicoes_db = (
                db.query(Proposicao)
                .filter(props_filter)
                .order_by(desc(Proposicao.data_apresentacao), Proposicao.id)
                .limit(MAX_PROPOSITIONS_LISTED)
                .all()
            )
        else:
            total_props_db, proposicoes_db = 0, []
        lideranca_count = total_props_db
        coautoria_count = 0
        for p in proposicoes_db:
            materias_propostas.append(_item(p, "AUTOR_PRINCIPAL"))

    total_props = len(materias_propostas)
    props_simb = sum(1 for p in materias_propostas if p.get("classificacao_relevancia") == "SIMBOLICO")
    props_imp = total_props - props_simb
    pct_imp = _pct(props_imp, total_props) if total_props > 0 else None
    pct_simb = _pct(props_simb, total_props) if total_props > 0 else None

    if pct_imp is None:
        diagnostico_legislativo = None
    elif pct_imp >= 75:
        diagnostico_legislativo = "Alta Relevância Estrutural"
    elif pct_imp >= 50:
        diagnostico_legislativo = "Equilíbrio Legislativo"
    else:
        diagnostico_legislativo = "Foco em Pautas Simbólicas"

    taxa_eficiencia = round((props_aprovadas / max(lideranca_count, 1)) * 100, 1) if lideranca_count > 0 else 0.0

    relevancia_legislativa = {
        "total_proposicoes": total_props,
        "total_proposicoes_registradas": int(total_props_db),
        "amostra_limitada": int(total_props_db) > total_props,
        "lideranca_legislativa_count": int(lideranca_count),
        "apoio_politico_count": int(coautoria_count),
        "taxa_eficiencia_pct": taxa_eficiencia,
        "score_atividade_ponderada": round(total_score_ponderado, 1),
        "score_ialp": round(total_score_ponderado, 1),
        "desvio_foco": {
            "estruturais": pecs_count + pls_count,
            "burocraticas": outros_count,
            "proporcao_estrutural_pct": round(((pecs_count + pls_count) / max(total_props, 1)) * 100, 1),
            "diagnostico": (
                "Foco Estrutural Predominante"
                if (pecs_count + pls_count) >= outros_count
                else "Foco Burocrático / Operacional"
            ),
        },
        "distribuicao_complexidade": {
            "alta": pecs_count,
            "media": pls_count,
            "baixa": outros_count,
        },
        "projetos_impacto": props_imp,
        "projetos_simbolicos": props_simb,
        "percentual_impacto": pct_imp,
        "percentual_simbolico": pct_simb,
        "diagnostico": diagnostico_legislativo,
    }

    # E. Como Votou nas Principais Leis — agregados no banco; apenas os votos mais recentes são listados
    axis_col = func.coalesce(Proposicao.eixo_impacto, "Geral")
    pessoa_param = pessoa_id if pessoa_id is not None else -1
    axis_rows = (
        db.query(axis_col, Voto.opcao_codigo, func.count())
        .join(Votacao, Voto.votacao_id == Votacao.id)
        .join(Proposicao, Votacao.proposicao_id == Proposicao.id)
        .filter(Voto.pessoa_id == pessoa_param)
        .group_by(axis_col, Voto.opcao_codigo)
        .all()
    )
    alinhamento_tematico_map: Dict[str, Dict[str, Any]] = {}
    votos_sim_total = votos_nao_total = 0
    for eixo, choice_val, qty in axis_rows:
        entry = alinhamento_tematico_map.setdefault(
            eixo,
            {
                "eixo": eixo,
                "total_votacoes": 0,
                "votos_sim": 0,
                "votos_nao": 0,
                "votos_abstencao": 0,
                "votos_outros": 0,
                "percentual_favoravel": 0.0,
            },
        )
        entry["total_votacoes"] += qty
        if choice_val == "SIM":
            entry["votos_sim"] += qty
            votos_sim_total += qty
        elif choice_val == "NAO":
            entry["votos_nao"] += qty
            votos_nao_total += qty
        elif choice_val in ("ABSTENCAO", "OBSTRUCAO"):
            entry["votos_abstencao"] += qty
        else:
            entry["votos_outros"] += qty

    alinhamento_tematico_list = []
    for dados in alinhamento_tematico_map.values():
        dados["percentual_favoravel"] = _pct(dados["votos_sim"], dados["votos_sim"] + dados["votos_nao"])
        alinhamento_tematico_list.append(dados)
    alinhamento_tematico_list.sort(key=lambda x: x["total_votacoes"], reverse=True)

    votos_db = (
        db.query(Voto, Votacao, Proposicao)
        .join(Votacao, Voto.votacao_id == Votacao.id)
        .join(Proposicao, Votacao.proposicao_id == Proposicao.id)
        .filter(Voto.pessoa_id == pessoa_param)
        .order_by(desc(Votacao.data_hora), Voto.votacao_id)
        .limit(MAX_VOTES_LISTED)
        .all()
    )

    votos_nominais = []
    historico_votos = []
    for vote, sess, prop in votos_db:
        v_opt = vote.opcao_codigo
        voto_label = VOTE_LABELS.get(v_opt, v_opt)
        sess_dt = _to_brt(sess.data_hora)
        numero_display = f"{prop.tipo_codigo} {prop.numero}/{prop.ano}" if prop.numero else prop.titulo
        casa_codigo = sess.casa.codigo if sess.casa else "CAMARA_DOS_DEPUTADOS"
        titulo_sessao = sess.titulo_pauta or sess.resumo_decisao

        historico_votos.append(
            {
                "proposicao_id": str(prop.uid),
                "proposicao_titulo": prop.titulo,
                "proposicao_numero": numero_display,
                "proposicao_tipo": prop.tipo_codigo,
                "tema": prop.area_tematica or prop.eixo_impacto or "Geral",
                "setor": prop.area_tematica or "Geral",
                "eixo_impacto": prop.eixo_impacto or "Geral",
                "data": sess_dt.strftime("%d/%m/%Y") if sess_dt else "",
                "data_iso": sess_dt.isoformat() if sess_dt else None,
                "voto": voto_label,
                "decisao": v_opt,
                "sessao_titulo": titulo_sessao,
                "sessao_aprovada": sess.aprovada,
                "casa_legislativa": casa_codigo,
                "url_oficial": url_oficial_proposicao(prop),
            }
        )

        votos_nominais.append(
            {
                "proposicao_id": str(prop.uid),
                "proposicao_titulo": prop.titulo,
                "proposicao_tipo": prop.tipo_codigo,
                "proposicao_numero": prop.numero,
                "proposicao_ano": prop.ano,
                "eixo_impacto": prop.eixo_impacto or "Geral",
                "eixos_tags": prop.eixos_impacto or "",
                "decisao": v_opt,
                "sessao_titulo": titulo_sessao,
                "sessao_data": sess_dt.isoformat() if sess_dt else None,
                "sessao_aprovada": sess.aprovada,
                "casa_legislativa": casa_codigo,
            }
        )

    resumo_votos = resumo_votos_do_parlamentar(db, pessoa_param)

    # Basômetro: alinhamento à orientação do governo em cada votação nominal (sem baseline inventado).
    basometro = calcular_basometro(db, pessoa_id, partido_atual_sigla, votos_sim_total, votos_nao_total)

    # F. Contabilização de Presenças e Faltas (Assiduidade) a partir de leg.vw_presenca_conhecida. Na Câmara, antes de
    # ref.cobertura_presenca.falta_desde só há presença (nenhuma falta é publicada nem inferida): esses dias ficam fora
    # da taxa para não inflá-la, e entram apenas na contagem de presenças sem falta registrada.
    att_row = (
        db.execute(
            text(
                """
                SELECT count(*) AS total,
                       count(*) FILTER (WHERE presente) AS presencas,
                       count(*) FILTER (WHERE justificada) AS justificadas,
                       count(*) FILTER (WHERE tipo_codigo = 'AUSENCIA_NAO_JUSTIFICADA') AS nao_justificadas,
                       count(*) FILTER (WHERE tipo_codigo = 'AUSENCIA_INFERIDA') AS inferidas,
                       count(*) FILTER (WHERE com_justificativa) AS dias_com_justificativa,
                       count(*) FILTER (WHERE na_inferencia) AS dias_na_inferencia,
                       string_agg(DISTINCT casa, ',') AS casas, min(data_sessao) AS inicio, max(data_sessao) AS fim
                FROM leg.vw_presenca_conhecida WHERE pessoa_id = :pid
                """
            ),
            {"pid": pessoa_param},
        )
        .mappings()
        .one()
    )
    presencas_sem_falta = (
        db.execute(
            text("SELECT count(*) FROM leg.presenca WHERE pessoa_id = :pid"),
            {"pid": pessoa_param},
        ).scalar()
        or 0
    ) - att_row["total"]
    att_casas = set((att_row["casas"] or "").split(",")) - {""}
    att_inicio, att_fim = att_row["inicio"], att_row["fim"]
    total_sessoes = att_row["total"]
    presencas_count = att_row["presencas"]
    total_faltas = total_sessoes - presencas_count
    # categoria que o período não permite saber vem como None, nunca como zero
    informa_justificativa = att_row["dias_com_justificativa"] > 0
    faltas_justif_count: Optional[int] = att_row["justificadas"] if informa_justificativa else None
    faltas_injustif_count: Optional[int] = att_row["nao_justificadas"] if informa_justificativa else None
    faltas_inferidas_count: Optional[int] = att_row["inferidas"] if att_row["dias_na_inferencia"] > 0 else None
    taxa_presenca = round((presencas_count / total_sessoes * 100), 1) if total_sessoes > 0 else None

    amostra_faltas = (
        db.execute(
            text(
                """
                SELECT p.data_sessao, p.tipo_codigo, p.justificativa, c.codigo AS casa
                FROM leg.presenca p JOIN ref.casa_legislativa c ON c.id = p.casa_id
                WHERE p.pessoa_id = :pid AND p.tipo_codigo <> 'PRESENTE'
                ORDER BY p.data_sessao DESC, c.codigo LIMIT 10
                """
            ),
            {"pid": pessoa_param},
        )
        .mappings()
        .all()
    )
    faltas_registros = [
        {
            "data": a["data_sessao"].isoformat(),
            "tipo": a["tipo_codigo"],
            "justificativa": a["justificativa"],
            "casa": a["casa"],
        }
        for a in amostra_faltas
    ]
    observacao_assiduidade = None
    if faltas_inferidas_count:
        observacao_assiduidade = (
            "Antes de 2020 a Câmara não publica falta nem justificativa. As faltas inferidas são dias de sessão "
            "deliberativa do plenário em que o deputado estava em exercício e não consta entre os presentes; não há "
            "justificativa para elas."
        )
    elif presencas_sem_falta:
        observacao_assiduidade = (
            f"{presencas_sem_falta} presenças anteriores a 2003 não entram na taxa: a Câmara não publica as faltas "
            "desse período."
        )

    # G. Evolução Patrimonial (TSE DivulgaCand)
    patrimonio_historico = [
        {**a, "valor_formatado": brl(a["valor"])} for a in financas_service.declaracoes_de_patrimonio(db, pessoas)
    ]

    crescimento_pct: Optional[float] = None
    crescimento_absoluto: Optional[float] = None
    if len(patrimonio_historico) >= 2:
        val_inicial = patrimonio_historico[0]["valor"]
        val_final = patrimonio_historico[-1]["valor"]
        crescimento_absoluto = round(val_final - val_inicial, 2)
        if val_inicial > 0:
            crescimento_pct = round(((val_final - val_inicial) / val_inicial) * 100, 1)

    has_assets = bool(patrimonio_historico)
    patrimonio_resumo = {
        "possui_dados": has_assets,
        "total_declaracoes": len(patrimonio_historico),
        "primeiro_ano": patrimonio_historico[0]["ano"] if has_assets else None,
        "primeiro_valor": patrimonio_historico[0]["valor"] if has_assets else None,
        "primeiro_valor_formatado": patrimonio_historico[0]["valor_formatado"] if has_assets else None,
        "ultimo_ano": patrimonio_historico[-1]["ano"] if has_assets else None,
        "ultimo_valor": patrimonio_historico[-1]["valor"] if has_assets else None,
        "ultimo_valor_formatado": patrimonio_historico[-1]["valor_formatado"] if has_assets else None,
        "crescimento_pct": crescimento_pct,
        "crescimento_absoluto": crescimento_absoluto,
    }

    # H. Custo do Mandato (CEAP): schema fin
    custos_ceap = financas_service.custos_ceap(db, pessoas) or financas_service.vazio_ceap()

    # I. Trilha do Dinheiro (Emendas Parlamentares)
    emendas_parlamentares = financas_service.emendas_do_parlamentar(db, pessoas) or financas_service.vazio_emendas()

    # J. Raio-X Judicial e Ficha Limpa
    ficha_limpa = _enrich_judicial_records(pol, financas_service.certidoes(db, pessoas), db)

    # K. Financiamento de Campanha (Doações Eleitorais TSE) — o CPF de doador pessoa física já vem mascarado do TSE
    doacoes_db = financas_service.doacoes_de_campanha(db, pessoas)
    financiamento_campanha = financas_service.financiamento_da_campanha(doacoes_db)

    # L. Indicadores avançados — calculados somente com dados reais; sem insumo, retornam null
    # 1. ROI do Cidadão: assiduidade (30%) + entrega legislativa em pontos IALP (40%) + custo por ponto IALP (30%).
    # A entrega vem do IALP (tipo x papel do autor x andamento), não da contagem de proposições: assinar
    # requerimentos ou apoiar projetos de outros vale pouco, e só avanço na tramitação pontua de verdade.
    # CEAP sem dado é None (não "gasto zero"): o custo só existe quando a CEAP, o subsídio e as sessões existem
    gasto_ceap: Optional[float] = custos_ceap.get("gasto_total_recente")
    # os pontos vêm da base inteira (não da lista truncada) e do mesmo cálculo dos rankings de autores e de ausências
    pontos_ialp = round(pontos_ialp_pessoa(db, pessoa_id) if pessoa_id is not None else total_score_ponderado, 1)
    projetos_autoria_estrutural = sum(
        1
        for m in materias_propostas
        if m["papel_autoria"] == "AUTOR_PRINCIPAL" and m["tipo"] in ("PEC", "PLP", "PL", "MPV")
    )
    roi_dados_ok = gasto_ceap is not None and salario_acumulado_registrado > 0 and total_sessoes > 0
    custo_total_operacional = (gasto_ceap or 0.0) + salario_acumulado_registrado if roi_dados_ok else None
    roi = calcular_roi(
        custo_total=custo_total_operacional or 0.0,
        pontos_ialp=pontos_ialp,
        taxa_presenca=taxa_presenca,
        dados_suficientes=roi_dados_ok,
    )
    roi_cidadao = {
        "score": roi["score"],
        "nota": roi["nota"],
        "custo_total_operacional": round(custo_total_operacional, 2) if custo_total_operacional is not None else None,
        "pontos_ialp": pontos_ialp,
        # abaixo de 1 ponto o custo "por ponto" seria o custo total: não é exibido
        "custo_por_ponto_ialp": roi["custo_por_ponto"] if pontos_ialp >= PISO_DE_PONTOS else None,
        "projetos_estruturantes": projetos_autoria_estrutural,
        "metodologia": ROI_METODOLOGIA,
        "diagnostico": roi["diagnostico"],
    }

    # 2. Concentração de Fornecedores da CEAP (Índice HHI)
    maiores_forn = custos_ceap.get("maiores_fornecedores") or []
    hhi: Optional[float]
    top1_pct: Optional[float]
    if gasto_ceap and gasto_ceap > 0 and maiores_forn:
        hhi = sum(((f["total_recebido"] / gasto_ceap * 100.0) ** 2) for f in maiores_forn)
        top1_forn = maiores_forn[0]
        top1_pct = round(top1_forn["total_recebido"] / gasto_ceap * 100.0, 1)

        if hhi >= 3500 or top1_pct >= 45.0:
            nivel_risco_ceap = "ALERTA"
            diag_hhi = f"Alerta de Risco: O fornecedor '{top1_forn['nome_fornecedor']}' concentrou {top1_pct}% de todas as despesas da cota parlamentar."
        elif hhi >= 1800 or top1_pct >= 25.0:
            nivel_risco_ceap = "MODERADO"
            diag_hhi = f"Concentração moderada de recursos em credores principais ({top1_pct}% com '{top1_forn['nome_fornecedor']}')."
        else:
            nivel_risco_ceap = "BAIXO"
            diag_hhi = "Gastos bem distribuídos entre múltiplos fornecedores sem dependência hegemônica."
    else:
        hhi = None  # sem despesa não há concentração a medir: desconhecido, não zero
        top1_pct = None
        top1_forn = None
        nivel_risco_ceap = None
        diag_hhi = "Sem despesas registradas para calcular concentração."

    concentracao_ceap = {
        "indice_hhi": round(hhi, 1) if hhi is not None else None,
        "nivel_risco": nivel_risco_ceap,
        "percentual_maior_fornecedor": top1_pct,
        "maior_fornecedor": top1_forn["nome_fornecedor"] if top1_forn else None,
        "cnpj_maior_fornecedor": top1_forn["cnpj_cpf"] if top1_forn else None,
        "diagnostico": diag_hhi,
    }

    # 3. Evolução patrimonial vs. remuneração oficial registrada: as duas pontas cobrem o MESMO período. A base é a última
    # declaração até o primeiro ano da remuneração, o fim é a última até o último ano dela, e o divisor soma só o subsídio
    # dentro da janela (não o acumulado do mandato inteiro, que alimenta o ROI).
    janela_patrimonio = financas_service.declaracoes_na_janela_da_remuneracao(
        patrimonio_historico, remun["primeiro_ano"], remun["ano"]
    )
    subsidio_da_janela = (
        financas_service.subsidio_na_janela(db, pessoas, janela_patrimonio[0]["ano"], janela_patrimonio[-1]["ano"])
        if janela_patrimonio
        else None
    )
    if subsidio_da_janela:
        delta_patrimonio: Optional[float] = round(janela_patrimonio[-1]["valor"] - janela_patrimonio[0]["valor"], 2)
        razao_patrimonio_renda: Optional[float] = round(delta_patrimonio / subsidio_da_janela, 2)

        if delta_patrimonio <= 0 or razao_patrimonio_renda <= 0.8:
            compat_patrimonial = "COMPATÍVEL"
            diag_patrimonio = (
                "Crescimento patrimonial compatível ou inferior ao somatório dos subsídios brutos registrados."
            )
        elif razao_patrimonio_renda <= 2.0:
            compat_patrimonial = "MODERADO"
            diag_patrimonio = "Evolução patrimonial compatível com rendimentos oficiais acrescidos de valorização imobiliária ou investimentos."
        else:
            compat_patrimonial = "ATÍPICO"
            diag_patrimonio = f"Variação atípica: o patrimônio declarado cresceu {razao_patrimonio_renda}x o total de subsídios registrados."
        periodo_comparado: Optional[Dict[str, int]] = {
            "de": janela_patrimonio[0]["ano"],
            "ate": janela_patrimonio[-1]["ano"],
            # o subsídio somado começa no ano seguinte ao da base e termina no ano do fim da janela
            "subsidio_de": janela_patrimonio[0]["ano"] + 1,
            "subsidio_ate": janela_patrimonio[-1]["ano"],
        }
    else:
        delta_patrimonio = None
        razao_patrimonio_renda = None
        compat_patrimonial = None
        periodo_comparado = None
        diag_patrimonio = "Dados insuficientes (requer uma declaração de bens até o início da remuneração registrada e outra depois dela, até o fim dela)."

    enriquecimento_patrimonial = {
        "delta_patrimonio": round(delta_patrimonio, 2) if delta_patrimonio is not None else None,
        "salario_acumulado_estimado": round(subsidio_da_janela, 2) if subsidio_da_janela else None,
        "razao_patrimonio_renda": razao_patrimonio_renda,
        "periodo_comparado": periodo_comparado,
        "compatibilidade": compat_patrimonial,
        "diagnostico": diag_patrimonio,
    }

    # 4. Estabilidade Partidária (período derivado das datas de filiação registradas)
    total_filiacoes = len(filiacoes_list)
    trocas_partidarias = max(0, total_filiacoes - 1)
    filiacao_anos = [a.start_date.year for a, _ in affiliations_db if a.start_date]
    if filiacao_anos:
        anos_totais = max(1, date.today().year - min(filiacao_anos))
        media_anos_partido: Optional[float] = round(anos_totais / max(total_filiacoes, 1), 1)
    else:
        media_anos_partido = None

    if total_filiacoes == 0:
        classif_fidelidade = None
        diag_fidelidade = "Sem filiações registradas."
    elif trocas_partidarias <= 1:
        classif_fidelidade = "ALTA_FIDELIDADE"
        diag_fidelidade = (
            f"Fidelidade partidária exemplar ({trocas_partidarias} troca de legenda ao longo da trajetória pública)."
        )
    elif trocas_partidarias <= 3:
        classif_fidelidade = "MODERADA"
        diag_fidelidade = f"Trajetória com movimentações pontuais de legenda ({trocas_partidarias} trocas), comum em janelas partidárias."
    else:
        classif_fidelidade = "ALTA_ROTATIVIDADE"
        diag_fidelidade = f"Alta rotatividade partidária ({trocas_partidarias} trocas de partido), indicando pragmatismo eleitoral frequente."

    estabilidade_partidaria = {
        "total_trocas": trocas_partidarias,
        "anos_medio_por_partido": media_anos_partido,
        "classificacao": classif_fidelidade,
        "taxa_governismo_pct": basometro["taxa_governismo_pct"],
        "diagnostico": diag_fidelidade,
    }

    # 5. Eficiência e Alocação de Emendas Parlamentares
    tot_emp_emendas = float(emendas_parlamentares.get("total_empenhado") or 0.0)
    tot_pago_emendas = float(emendas_parlamentares.get("total_pago") or 0.0)
    destinos = emendas_parlamentares.get("destinos_principais") or []
    top1_dest = destinos[0] if destinos else None
    dist_tipos = emendas_parlamentares.get("distribuicao_por_tipo") or []
    pix_item = next(
        (t for t in dist_tipos if "PIX" in t.get("tipo", "").upper() or "ESPECIAL" in t.get("tipo", "").upper()),
        None,
    )
    pct_pix = pix_item.get("percentual", 0.0) if pix_item else 0.0

    if tot_emp_emendas > 0:
        taxa_exec_emendas: Optional[float] = round((tot_pago_emendas / tot_emp_emendas * 100.0), 1)
        if taxa_exec_emendas >= 85.0:
            classif_emendas = "ALTA_EFICIÊNCIA"
            diag_emendas = f"Excelente índice de liberação: {taxa_exec_emendas}% dos recursos empenhados foram efetivamente pagos aos destinos."
        elif taxa_exec_emendas >= 60.0:
            classif_emendas = "MÉDIA_EFICIÊNCIA"
            diag_emendas = (
                f"Execução intermediária ({taxa_exec_emendas}% pago), com parcela significativa de restos a pagar."
            )
        else:
            classif_emendas = "BAIXA_EFICIÊNCIA"
            diag_emendas = f"Baixa conversão orçamentária: apenas {taxa_exec_emendas}% dos recursos alocados foram efetivamente liquidados."
    else:
        taxa_exec_emendas = None
        classif_emendas = None
        diag_emendas = "Sem emendas registradas."

    eficiencia_emendas = {
        "taxa_conversao_pct": taxa_exec_emendas,
        "total_empenhado": tot_emp_emendas,
        "total_pago": tot_pago_emendas,
        "percentual_pix": pct_pix,
        "municipio_predileto": top1_dest["localidade"] if top1_dest else None,
        "concentracao_municipio_predileto_pct": (top1_dest["percentual"] if top1_dest else 0.0),
        "classificacao": classif_emendas,
        "diagnostico": diag_emendas,
    }

    indices_inteligencia = {
        "roi_cidadao": roi_cidadao,
        "concentracao_ceap": concentracao_ceap,
        "enriquecimento_patrimonial": enriquecimento_patrimonial,
        "estabilidade_partidaria": estabilidade_partidaria,
        "eficiencia_emendas": eficiencia_emendas,
    }

    return {
        "perfil": {
            "id": str(pol.id),
            "nome_eleitoral": pol.electoral_name,
            "nome_civil": pol.civil_name,
            "genero": pol.gender,
            "data_nascimento": pol.birth_date.isoformat() if pol.birth_date else None,
            "naturalidade": (
                f"{pol.birthplace_city}/{pol.birthplace_state}"
                if pol.birthplace_city
                else pol.birthplace_state  # sem naturalidade cadastrada: null (nunca um valor genérico inventado)
            ),
            "foto_url": _format_photo_url(pol, bool(presidential_periods)),
            "cargo_atual": cargo_atual,
            "partido_atual": partido_atual_sigla,
            "uf": uf_atual,
            "email": pol.email,
            "gabinete_sala": pol.cabinet_room,
            "gabinete_telefone": pol.cabinet_phone,
            "biografia": pol.biography,
            "redes_sociais": pol.social_links,
            "camara_id": pol.camara_id,
            "senado_id": pol.senado_id,
            "possui_processos_declarados": pol.possui_processos_declarados,
        },
        "trajetoria_mandatos": mandatos_list,
        "filiacoes_partidarias": filiacoes_list,
        "remuneracao": {
            "resumo": {
                "salario_bruto_atual": sal_bruto_atual,
                "salario_liquido_atual": sal_liquido_atual,
                "media_ceap_mensal": media_ceap,
                "ano_referencia": ano_remuneracao,
                # Chaves *_2023 mantidas por compatibilidade: refletem o ano em "ano_referencia"
                "total_bruto_2023": total_bruto_ano,
                "total_ceap_2023": total_ceap_ano,
                "total_beneficios_2023": total_beneficios_ano,
            },
            "historico": remuneracao_historico,
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
        "resumo_votos": resumo_votos,
        "alinhamento_tematico": alinhamento_tematico_list,
        "assiduidade": {
            "total_sessoes": total_sessoes,
            "total_presencas": presencas_count,
            "faltas_justificadas": faltas_justif_count,
            "faltas_nao_justificadas": faltas_injustif_count,
            "faltas_inferidas": faltas_inferidas_count,
            "total_faltas": total_faltas,
            "observacao": observacao_assiduidade,
            "taxa_presenca_pct": taxa_presenca,
            "amostra_faltas": faltas_registros,
            "periodo_inicio": att_inicio.isoformat() if att_inicio else None,
            "periodo_fim": att_fim.isoformat() if att_fim else None,
            "unidade": _unidade_assiduidade(att_casas),
            "fonte": _fonte_assiduidade(att_casas),
        },
        "evolucao_patrimonial": {
            "resumo": patrimonio_resumo,
            "historico": patrimonio_historico,
        },
        "indices_inteligencia": indices_inteligencia,
    }


@router.get("/{politician_id}/ceap")
def get_politician_ceap(politician_id: str, db: Session = Depends(get_db)):
    """CEAP (Cota Parlamentar) do parlamentar: total e valor por ano e tipo de despesa."""
    pol = _resolve_politician(db, politician_id)
    return {
        "politico_id": str(pol.id),
        "nome": pol.electoral_name,
        **financas_service.ceap_por_ano_e_tipo(db, _pessoas_financas(db, pol)),
    }


@router.get("/{politician_id}/emendas")
def get_politician_emendas(politician_id: str, db: Session = Depends(get_db)):
    """Retorna as emendas parlamentares alocadas pelo deputado ou senador."""
    pol = _resolve_politician(db, politician_id)
    return {
        "politico_id": str(pol.id),
        "nome": pol.electoral_name,
        **financas_service.emendas_detalhadas(db, _pessoas_financas(db, pol)),
    }


@router.get("/{politician_id}/certidoes")
def get_politician_certidoes(politician_id: str, db: Session = Depends(get_db)):
    """Retorna as certidões judiciais e status perante a Lei da Ficha Limpa."""
    pol = _resolve_politician(db, politician_id)
    ficha_data = _enrich_judicial_records(pol, financas_service.certidoes(db, _pessoas_financas(db, pol)), db)
    return {"politico_id": str(pol.id), "nome": pol.electoral_name, **ficha_data}


@router.get("/{politician_id}/doacoes")
def get_politician_doacoes(
    politician_id: str,
    ano_eleicao: Optional[int] = Query(None, ge=1995, le=2100, description="Eleição; sem ela vale a mais recente."),
    db: Session = Depends(get_db),
):
    """
    Retorna as doações e o financiamento eleitoral de uma campanha (TSE): a eleição pedida ou a mais recente. Pedir uma
    eleição sem doações de quem TEM doações em outras dá 404; quem não tem nenhuma doação recebe 200 sem dados.
    """
    pol = _resolve_politician(db, politician_id)
    doacoes = financas_service.doacoes_de_campanha(db, _pessoas_financas(db, pol))
    bloco = financas_service.financiamento_da_campanha(doacoes, ano_eleicao)
    # só estes dois nomes diferem do bloco do dossiê (contrato antigo de `/doacoes`)
    return {
        "politico_id": str(pol.id),
        "nome": pol.electoral_name,
        **{k: v for k, v in bloco.items() if k not in ("top_doadores", "todas_doacoes")},
        "top_5": bloco["top_doadores"],
        "doacoes": bloco["todas_doacoes"],
    }
