"""Votos nominais de uma proposição: lista por sessão (`/votes`) e divisão em sim, não, abstenção e obstrução."""

import uuid
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from app.core.errors import ErroDeDominio
from app.core.links import url_oficial_proposicao
from app.core.query_utils import contains, is_filter_all, to_brt
from app.models import Casa, CasaLegislativaEnum, VotoOpcaoEnum
from app.models.core import Partido, Pessoa, PessoaNome
from app.models.leg import Proposicao, Votacao, Voto
from app.services.deliberacoes_service import get_proposicao_deliberacoes
from app.services.placar import (
    contagens_por_votacao,
    placar_para_tela,
    placares_das_votacoes,
    sessao_principal,
)
from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

MAX_VOTOS_NOMINAIS = 600
# Votações que a API trata como "sessões": votação nominal (ou secreta, só com totais) em plenário.
# Deliberações simbólicas e de comissão têm endpoints próprios (/deliberacoes).
TIPOS_SESSAO = ("NOMINAL", "SECRETA")

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
_ESPECTRO_SQL = text("SELECT id, espectro_politico FROM core.vw_partido WHERE id = ANY(:ids)")


def titulo_votacao(v: Votacao) -> str:
    return v.titulo_pauta or v.resumo_decisao or v.local_deliberacao or "Votação"


def casa_codigo(v: Votacao) -> Optional[str]:
    return v.casa.codigo if v.casa else None


def resolver_proposicao(db: Session, prop_id: str) -> Proposicao:
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

    raise ErroDeDominio(404, f"Proposição '{prop_id}' não encontrada.")


def parse_casa(casa: Optional[str]) -> Optional[CasaLegislativaEnum]:
    if is_filter_all(casa):
        return None
    chave = str(casa).strip().upper()
    if chave.startswith("CAMARA"):
        return CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS
    if chave.startswith("SENADO"):
        return CasaLegislativaEnum.SENADO_FEDERAL
    raise ErroDeDominio(422, "Casa inválida. Use CAMARA ou SENADO.")


def parse_enum(enum_cls: Any, value: Optional[str], rotulo: str) -> Any:
    if is_filter_all(value):
        return None
    try:
        return enum_cls[str(value).strip().upper()]
    except KeyError:
        validos = ", ".join(e.name for e in enum_cls)
        raise ErroDeDominio(422, f"{rotulo} inválido '{str(value)[:40]}'. Valores aceitos: {validos}.")


def sessoes_da_casa(query: Any, casa: Optional[CasaLegislativaEnum]) -> Any:
    query = query.filter(Votacao.tipo_deliberacao.in_(TIPOS_SESSAO))
    if casa:
        query = query.join(Casa, Casa.id == Votacao.casa_id).filter(Casa.codigo == casa.value)
    return query


def contexto_mandato(db: Session, pessoa_ids: List[int], data_ref: Optional[date] = None) -> Dict[int, Tuple[str, str]]:
    """
    (UF, cargo) por pessoa. Escolhe o mandato vigente na data de referência; sem ele, o mais recente.
    Não existe valor padrão inventado: pessoa sem mandato simplesmente não aparece no mapa.
    """
    if not pessoa_ids:
        return {}
    resultado: Dict[int, Tuple[str, str]] = {}
    cobrindo: set = set()
    for pid, uf, cargo, inicio, fim in db.execute(_MANDATO_CONTEXTO_SQL, {"ids": list(pessoa_ids)}):
        cobre = bool(data_ref and inicio and inicio <= data_ref and (fim is None or fim >= data_ref))
        if pid not in resultado or (cobre and pid not in cobrindo):
            resultado[pid] = (uf, cargo)
        if cobre:
            cobrindo.add(pid)
    return resultado


def _sessao_pelo_id(db: Session, sessoes: List[Votacao], sessao_uid: uuid.UUID) -> Optional[Votacao]:
    """A sessão pelo id público; links antigos (ids do legado) ainda resolvem pela tabela de correspondência."""
    achada = next((s for s in sessoes if s.uid == sessao_uid), None)
    if achada is not None:
        return achada
    votacao_id = db.execute(
        text("SELECT votacao_id FROM leg.votacao_legado WHERE legado_id = :id LIMIT 1"), {"id": sessao_uid}
    ).scalar()
    return next((s for s in sessoes if s.id == votacao_id), None) if votacao_id is not None else None


def _consulta_votos(db: Session, sessao: Votacao, busca: Optional[str] = None) -> Tuple[Any, Any]:
    """Votos da sessão com pessoa, partido do voto e nome civil; a busca vale para nome, nome civil e sigla."""
    nome_civil = (
        select(PessoaNome.nome)
        .where(PessoaNome.pessoa_id == Pessoa.id, PessoaNome.tipo == "CIVIL")
        .limit(1)
        .scalar_subquery()
    )
    consulta = (
        db.query(Voto, Pessoa, Partido, nome_civil)
        .join(Pessoa, Voto.pessoa_id == Pessoa.id)
        .outerjoin(Partido, Voto.partido_id == Partido.id)
        .filter(Voto.votacao_id == sessao.id)
    )
    if busca and busca.strip():
        consulta = consulta.filter(
            or_(contains(Pessoa.nome_exibicao, busca), contains(nome_civil, busca), contains(Partido.sigla, busca))
        )
    return consulta, nome_civil


def _item_voto(voto: Voto, pessoa: Pessoa, partido: Optional[Partido], civil: Optional[str]) -> Dict[str, Any]:
    return {
        "politico_id": str(pessoa.uid),
        "nome_eleitoral": pessoa.nome_exibicao,
        "nome_civil": civil or pessoa.nome_exibicao,
        "partido_sigla": partido.sigla if partido else "S.PART.",
        "foto_url": pessoa.foto_url,
        "decisao": voto.opcao_codigo,
    }


def _resumo_proposicao(prop: Proposicao) -> Dict[str, Any]:
    return {
        "id": str(prop.uid),
        "titulo": prop.titulo,
        "numero": prop.numero,
        "ano": prop.ano,
        "autor_nome": prop.autor_nome or ("Poder Executivo" if prop.iniciativa_executivo else None),
    }


def _sessao_disponivel(s: Votacao) -> Dict[str, Any]:
    return {
        "id": str(s.uid),
        "titulo": titulo_votacao(s),
        "data_hora": s.data_hora.isoformat(),
        "casa": casa_codigo(s),
        "aprovada": s.aprovada,
        "is_votacao_secreta": s.secreta,
    }


def votos_da_proposicao(
    db: Session,
    prop_id: str,
    casa: Optional[str] = None,
    session_id: Optional[str] = None,
    busca: Optional[str] = None,
    voto: Optional[str] = None,
) -> Dict[str, Any]:
    """Votos nominais de uma sessão da proposição (a de maior quórum, se nenhuma for pedida)."""
    prop = resolver_proposicao(db, prop_id)
    casa_enum = parse_casa(casa)
    opcao = parse_enum(VotoOpcaoEnum, voto, "Voto")

    sessoes = (
        sessoes_da_casa(db.query(Votacao), casa_enum)
        .filter(Votacao.proposicao_id == prop.id)
        .order_by(Votacao.data_hora.desc())
        .all()
    )
    resumo = _resumo_proposicao(prop)
    if not sessoes:
        return {"proposicao": resumo, "sessoes_disponiveis": [], "sessao_ativa": None, "total": 0, "votos": []}

    disponiveis = [_sessao_disponivel(s) for s in sessoes]
    placares = placares_das_votacoes(sessoes, contagens_por_votacao(db, Votacao.id.in_([s.id for s in sessoes])))

    selecionada: Optional[Votacao] = None
    if session_id:
        try:
            sessao_uid = uuid.UUID(session_id)
        except (ValueError, TypeError):
            raise ErroDeDominio(422, "session_id inválido.")
        selecionada = _sessao_pelo_id(db, sessoes, sessao_uid)
        if selecionada is None:
            raise ErroDeDominio(404, "Sessão não pertence a esta proposição/casa.")
    if selecionada is None:
        selecionada = sessao_principal(sessoes, placares) or sessoes[0]

    prop_com_area = {**resumo, "area_tematica": prop.area_tematica}
    placar = placar_para_tela(placares[selecionada.id])
    descricao = selecionada.descricao or titulo_votacao(selecionada)
    if selecionada.secreta:
        return {
            "proposicao": prop_com_area,
            "sessao_ativa": {
                "id": str(selecionada.uid),
                "titulo": titulo_votacao(selecionada),
                "descricao": descricao,
                "data_hora": selecionada.data_hora.isoformat(),
                "casa": casa_codigo(selecionada),
                "aprovada": selecionada.aprovada,
                "is_votacao_secreta": True,
                "placar": placar,
            },
            "sessoes_disponiveis": disponiveis,
            "is_votacao_secreta": True,
            "aviso": (
                "Votação secreta: conforme o Regimento Interno do Senado Federal, os votos individuais não são "
                "divulgados nominalmente. O resultado oficial acima reflete a apuração agregada da urna."
            ),
            "placar": placar,
            "total": placar["TOTAL"],
            "total_correspondente": placar["TOTAL"],
            "truncado": False,
            "votos": [],
        }

    consulta, _ = _consulta_votos(db, selecionada, busca)
    if opcao:
        consulta = consulta.filter(Voto.opcao_codigo == opcao.value)
    total_correspondente = consulta.count()
    linhas = consulta.order_by(Pessoa.nome_exibicao.asc(), Pessoa.id).limit(MAX_VOTOS_NOMINAIS).all()

    contexto = contexto_mandato(db, [p.id for _, p, _, _ in linhas], to_brt(selecionada.data_hora).date())
    casa_sessao = casa_codigo(selecionada)
    itens = []
    for v, pessoa, partido, civil in linhas:
        uf, cargo = contexto.get(pessoa.id, (None, None))
        itens.append(
            {
                "voto_id": f"{selecionada.uid}:{pessoa.uid}",
                **_item_voto(v, pessoa, partido, civil),
                "uf": uf,
                "cargo": cargo,
                "sessao_id": str(selecionada.uid),
                "sessao_titulo": titulo_votacao(selecionada),
                "casa_legislativa": casa_sessao,
                "data_sessao": selecionada.data_hora.isoformat(),
            }
        )

    return {
        "proposicao": prop_com_area,
        "sessao_ativa": {
            "id": str(selecionada.uid),
            "titulo": titulo_votacao(selecionada),
            "descricao": descricao,
            "data_hora": selecionada.data_hora.isoformat(),
            "casa": casa_sessao,
            "aprovada": selecionada.aprovada,
        },
        "sessoes_disponiveis": disponiveis,
        "total": len(itens),
        "total_correspondente": total_correspondente,
        "truncado": total_correspondente > len(itens),
        "votos": itens,
    }


def votos_nominais_divididos(db: Session, prop_id: str, busca: Optional[str] = None) -> Dict[str, Any]:
    """Quem votou SIM, NÃO, abstenção e obstrução na sessão de maior quórum, com foto, partido e UF."""
    prop = resolver_proposicao(db, prop_id)
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
        "url_oficial": url_oficial_proposicao(prop),
    }
    deliberacoes = get_proposicao_deliberacoes(db, prop.id)
    vazio = {
        "proposicao": prop_info,
        "sessao": None,
        "placar": {"sim": 0, "nao": 0, "abstencao": 0, "obstrucao": 0, "total": 0},
        "votos_sim": [],
        "votos_nao": [],
        "votos_abstencao": [],
        "votos_obstrucao": [],
        "deliberacoes": deliberacoes.get("deliberacoes", []) if deliberacoes else [],
    }

    sessoes = sessoes_da_casa(db.query(Votacao), None).filter(Votacao.proposicao_id == prop.id).all()
    if not sessoes:
        return vazio
    placares = placares_das_votacoes(sessoes, contagens_por_votacao(db, Votacao.id.in_([s.id for s in sessoes])))
    selecionada = sessao_principal(sessoes, placares) or sessoes[0]

    consulta, _ = _consulta_votos(db, selecionada, busca)
    todos = consulta.order_by(Pessoa.nome_exibicao.asc(), Pessoa.id).all()
    contexto = contexto_mandato(db, [p.id for _, p, _, _ in todos], to_brt(selecionada.data_hora).date())
    espectros = {
        r[0]: r[1] for r in db.execute(_ESPECTRO_SQL, {"ids": [p.id for _, _, p, _ in todos if p is not None]})
    }

    baldes: Dict[str, List[Dict[str, Any]]] = {"SIM": [], "NAO": [], "ABSTENCAO": [], "OBSTRUCAO": []}
    for v, pessoa, partido, civil in todos:
        balde = baldes.get(v.opcao_codigo)
        if balde is None:  # AUSENTE / Art. 17 não votaram
            continue
        uf, cargo = contexto.get(pessoa.id, (None, None))
        balde.append(
            {
                **_item_voto(v, pessoa, partido, civil),
                "espectro_politico": espectros.get(partido.id) if partido else None,
                "uf": uf,
                "cargo": cargo,
            }
        )

    total_votantes = sum(len(lista) for lista in baldes.values())
    return {
        "proposicao": prop_info,
        "sessao": {
            "id": str(selecionada.uid),
            "titulo": titulo_votacao(selecionada),
            "descricao": selecionada.descricao or titulo_votacao(selecionada),
            "data_hora": selecionada.data_hora.isoformat(),
            "casa_legislativa": casa_codigo(selecionada),
            "aprovada": selecionada.aprovada,
            "total_votos": total_votantes,
        },
        "placar": {
            "sim": len(baldes["SIM"]),
            "nao": len(baldes["NAO"]),
            "abstencao": len(baldes["ABSTENCAO"]),
            "obstrucao": len(baldes["OBSTRUCAO"]),
            "total": total_votantes,
        },
        "votos_sim": baldes["SIM"],
        "votos_nao": baldes["NAO"],
        "votos_abstencao": baldes["ABSTENCAO"],
        "votos_obstrucao": baldes["OBSTRUCAO"],
    }
