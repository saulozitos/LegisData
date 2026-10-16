"""Explorador legislativo: lista de proposições com autor, tema, status e placar de votação."""

import json
import math
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import PROCESSED_DATA_DIR
from app.core.errors import ErroDeDominio
from app.core.links import url_oficial_proposicao
from app.core.query_utils import contains, escape_like, is_filter_all
from app.models import CasaLegislativaEnum
from app.models.core import Mandato
from app.models.leg import Autoria, Proposicao, Votacao
from app.services.ialp_pesos import carregar_pesos_ialp
from app.services.party_catalog_service import SEM_PARTIDO_SIGLA
from app.services.placar import contagens_por_votacao, placar_para_tela, placares_das_votacoes, sessao_principal
from app.services.votos_proposicao_service import TIPOS_SESSAO, casa_codigo, sessoes_da_casa, titulo_votacao
from sqlalchemy import and_, exists, func, or_, select, text
from sqlalchemy.orm import Session

DATA_DIR = PROCESSED_DATA_DIR
STATUS_LEI = ("APROVADA_E_SANCIONADA", "APROVADA_E_PROMULGADA")
PLACAR_TELA_VAZIO = {"SIM": 0, "NAO": 0, "ABSTENCAO": 0, "TOTAL": 0}
_PARTIDO_NA_AUTORIA_RE = re.compile(r"\(([A-ZÀ-Ú0-9_ -]+)(?:/[A-Z]{2})?\)")

_TABELAS_DE_CODIGOS = {
    "tipo": text("SELECT codigo FROM ref.tipo_proposicao ORDER BY codigo"),
    "status": text("SELECT codigo FROM ref.status_tramitacao ORDER BY codigo"),
}
_ALIAS_PARTIDO_SQL = text("SELECT tipo FROM ref.alias_filtro_partido WHERE alias = :alias")

_AUTOR_PRINCIPAL_SQL = text(
    """
    SELECT p.id AS proposicao_id, pe.uid AS pessoa_uid, pe.nome_exibicao, fm.url_origem AS foto,
           coalesce(pc.canonico_sigla,
                    (SELECT pa.canonico_sigla FROM core.vw_partido_atual pa WHERE pa.pessoa_id = pe.id)) AS partido,
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


def parse_codigo(db: Session, tabela: str, valor: Optional[str], rotulo: str) -> Optional[str]:
    """Valida um código de referência (tipo de proposição ou status) contra a tabela, sem lista fixa no código."""
    if is_filter_all(valor):
        return None
    codigo = str(valor).strip().upper()
    validos = [r[0] for r in db.execute(_TABELAS_DE_CODIGOS[tabela])]
    if codigo not in validos:
        raise ErroDeDominio(422, f"{rotulo} inválido '{str(valor)[:40]}'. Valores aceitos: {', '.join(validos)}.")
    return codigo


def resumo_da_casa(
    sessoes: List[Votacao], placares: Dict[int, Dict[str, int]]
) -> Tuple[Dict[str, int], Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """(placar da sessão principal, resumo dela, detalhe de todas as sessões da Casa)."""
    principal = sessao_principal(sessoes, placares)
    if principal is None:
        return dict(PLACAR_TELA_VAZIO), None, []
    ordenadas = sorted(
        sessoes, key=lambda s: (placares[s.id]["total"], 1 if s.aprovada else 0, s.data_hora), reverse=True
    )
    detalhes = [
        {
            "sessao_id": str(s.uid),
            "external_id": s.id_externo,
            "data_hora": s.data_hora.isoformat(),
            "titulo": titulo_votacao(s),
            "descricao": s.descricao or titulo_votacao(s),
            "aprovada": s.aprovada,
            "is_votacao_secreta": s.secreta,
            "placar": placar_para_tela(placares[s.id]),
        }
        for s in ordenadas
    ]
    resumo = {
        "sessao_id": str(principal.uid),
        "data_hora": principal.data_hora.isoformat(),
        "titulo": titulo_votacao(principal),
        "descricao": principal.descricao or titulo_votacao(principal),
        "aprovada": principal.aprovada,
        "is_votacao_secreta": principal.secreta,
    }
    return placar_para_tela(placares[principal.id]), resumo, detalhes


def proposicoes_com_votacao(db: Session, limite: int, deslocamento: int) -> Tuple[int, List[Dict[str, Any]]]:
    """Proposições com o placar de votação por Casa, as votadas primeiro. Devolve (total, página)."""
    total = db.query(func.count(Proposicao.id)).scalar() or 0
    if not total:
        return 0, []
    tem_sessao = exists().where(Votacao.proposicao_id == Proposicao.id, Votacao.tipo_deliberacao.in_(TIPOS_SESSAO))
    props = (
        db.query(Proposicao)
        .order_by(tem_sessao.desc(), Proposicao.data_apresentacao.desc(), Proposicao.id)
        .offset(deslocamento)
        .limit(limite)
        .all()
    )
    if not props:
        return total, []

    ids = [p.id for p in props]
    sessoes = sessoes_da_casa(db.query(Votacao), None).filter(Votacao.proposicao_id.in_(ids)).all()
    por_proposicao: Dict[int, List[Votacao]] = defaultdict(list)
    for s in sessoes:
        por_proposicao[s.proposicao_id].append(s)
    placares = placares_das_votacoes(
        sessoes, contagens_por_votacao(db, Votacao.proposicao_id.in_(ids), Votacao.tipo_deliberacao.in_(TIPOS_SESSAO))
    )

    resultado = []
    for p in props:
        da_proposicao = por_proposicao.get(p.id, [])
        camara = [s for s in da_proposicao if casa_codigo(s) == CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS.value]
        senado = [s for s in da_proposicao if casa_codigo(s) == CasaLegislativaEnum.SENADO_FEDERAL.value]
        placar_camara, sessao_camara, lista_camara = resumo_da_casa(camara, placares)
        placar_senado, sessao_senado, lista_senado = resumo_da_casa(senado, placares)

        # placar consolidado padrão: prioriza a Casa onde houve votação com quórum
        if placar_camara["TOTAL"] > 0:
            placar_padrao, sessao_padrao = placar_camara, sessao_camara
        elif placar_senado["TOTAL"] > 0:
            placar_padrao, sessao_padrao = placar_senado, sessao_senado
        else:
            placar_padrao, sessao_padrao = dict(PLACAR_TELA_VAZIO), None

        resultado.append(
            {
                "id": str(p.uid),
                "camara_id": p.id_camara,
                "tipo": p.tipo_codigo,
                "numero": p.numero,
                "ano": p.ano,
                "titulo": p.titulo,
                "ementa": p.ementa,
                "autor_nome": p.autor_nome
                or ("Poder Executivo" if p.iniciativa_executivo else "Comissão / Parlamentares"),
                "area_tematica": p.area_tematica,
                "data_apresentacao": p.data_apresentacao.isoformat(),
                "status": p.status_codigo,
                "is_reforma_estrutural": p.reforma_estrutural,
                "iniciativa_executivo": p.iniciativa_executivo,
                "placar": placar_padrao,
                "sessao": sessao_padrao,
                "placar_camara": placar_camara,
                "sessao_camara": sessao_camara,
                "sessoes_camara_lista": lista_camara,
                "placar_senado": placar_senado,
                "sessao_senado": sessao_senado,
                "sessoes_senado_lista": lista_senado,
                "url_oficial": url_oficial_proposicao(p),
            }
        )
    return total, resultado


def proposicoes_de_arquivos_locais() -> List[Dict[str, Any]]:
    """Fallback de desenvolvimento: banco vazio (ainda não carregado). Dados do arquivo do ETL, sem datas inventadas."""
    arq_props = DATA_DIR / "proposicoes_2023.json"
    arq_sessoes = DATA_DIR / "sessoes_votacao_2023.json"
    arq_votos = DATA_DIR / "votos_nominais_2023.json"
    if not arq_props.exists():
        return []

    with open(arq_props, "r", encoding="utf-8") as f:
        proposicoes = json.load(f)

    sessoes_por_proposicao: Dict[Any, Any] = {}
    if arq_sessoes.exists():
        with open(arq_sessoes, "r", encoding="utf-8") as f:
            for s in json.load(f):
                if s.get("proposicao_camara_id") is not None:
                    sessoes_por_proposicao[s["proposicao_camara_id"]] = s

    contagem: Dict[Any, Dict[str, int]] = {}
    if arq_votos.exists():
        with open(arq_votos, "r", encoding="utf-8") as f:
            for v in json.load(f):
                pid = v.get("proposicao_camara_id")
                if pid is None:
                    continue
                c = contagem.setdefault(pid, {"SIM": 0, "NAO": 0, "ABSTENCAO": 0, "TOTAL": 0})
                opcao = v.get("voto", "OUTROS")
                if opcao in ("SIM", "NAO", "ABSTENCAO", "OBSTRUCAO"):
                    c["ABSTENCAO" if opcao == "OBSTRUCAO" else opcao] += 1
                    c["TOTAL"] += 1

    resultado = []
    for p in proposicoes:
        cid = p.get("camara_id")
        if cid is None:
            continue
        resultado.append(
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
                "placar": contagem.get(cid, dict(PLACAR_TELA_VAZIO)),
                "sessao": sessoes_por_proposicao.get(cid),
            }
        )
    return resultado


def _filtrar_por_partido(db: Session, query: Any, partido: str) -> Any:
    limpo = partido.strip().upper()
    tipo_alias = db.execute(_ALIAS_PARTIDO_SQL, {"alias": limpo}).scalar()
    if tipo_alias == "EXECUTIVO":
        return query.filter(Proposicao.iniciativa_executivo.is_(True))
    if tipo_alias == "SEM_PARTIDO":
        return query.filter(
            and_(
                Proposicao.autor_pessoa_id.is_(None),
                Proposicao.iniciativa_executivo.is_(False),
                ~exists().where(and_(Autoria.proposicao_id == Proposicao.id, Autoria.partido_id.isnot(None))),
            )
        )
    # partido vigente da linhagem: PMDB e MDB, por exemplo, respondem ao mesmo filtro
    linhagem = (
        select(text("c.id"))
        .select_from(text("core.vw_partido_canonico c"))
        .where(text("c.canonico_sigla_normalizada = ref.normalizar_texto(:sigla)").bindparams(sigla=limpo))
    )
    sigla = escape_like(limpo)
    return query.filter(
        or_(
            exists().where(
                and_(
                    Autoria.proposicao_id == Proposicao.id,
                    Autoria.tipo_codigo == "AUTOR_PRINCIPAL",
                    Autoria.partido_id.in_(linhagem),
                )
            ),
            Proposicao.autor_pessoa_id.in_(select(Mandato.pessoa_id).where(Mandato.partido_id.in_(linhagem))),
            Proposicao.autor_nome.ilike(f"%({sigla}/%", escape="\\"),
            Proposicao.autor_nome.ilike(f"%/{sigla})%", escape="\\"),
        )
    )


def explorar(
    db: Session,
    busca: Optional[str],
    setor: Optional[str],
    partido: Optional[str],
    tipo: Optional[str],
    status: Optional[str],
    apenas_votadas: bool,
    pagina: int,
    limite: int,
) -> Dict[str, Any]:
    """Proposições filtradas, cruzadas com tema, autor e placar geral (sim/não)."""
    tipo_codigo = parse_codigo(db, "tipo", tipo, "Tipo")
    status_codigo = parse_codigo(db, "status", status, "Status")

    query = db.query(Proposicao)
    if busca and busca.strip():
        query = query.filter(
            or_(
                contains(Proposicao.titulo, busca),
                contains(Proposicao.ementa, busca),
                contains(Proposicao.autor_nome, busca),
                contains(Proposicao.area_tematica, busca),
            )
        )
    if not is_filter_all(setor):
        query = query.filter(contains(Proposicao.area_tematica, str(setor)))
    if not is_filter_all(partido):
        query = _filtrar_por_partido(db, query, str(partido))
    if tipo_codigo:
        query = query.filter(Proposicao.tipo_codigo == tipo_codigo)
    if status_codigo:
        query = query.filter(Proposicao.status_codigo == status_codigo)
    if apenas_votadas:
        # EXISTS evita a duplicação de linhas de um JOIN com várias votações por proposição
        query = query.filter(
            exists().where(Votacao.proposicao_id == Proposicao.id, Votacao.tipo_deliberacao.in_(TIPOS_SESSAO))
        )

    total = query.count()
    setores = [
        row[0]
        for row in db.query(Proposicao.area_tematica)
        .filter(Proposicao.area_tematica.isnot(None))
        .distinct()
        .order_by(Proposicao.area_tematica.asc())
        .all()
    ]
    proposicoes = (
        query.order_by(Proposicao.data_apresentacao.desc(), Proposicao.numero.desc(), Proposicao.id)
        .offset((pagina - 1) * limite)
        .limit(limite)
        .all()
    )

    pesos = carregar_pesos_ialp(db)
    ids = [p.id for p in proposicoes]
    sessoes_por_proposicao: Dict[int, List[Votacao]] = defaultdict(list)
    deliberacoes: Dict[int, List[Votacao]] = defaultdict(list)
    placares: Dict[int, Dict[str, int]] = {}
    autores: Dict[int, Any] = {}
    if ids:
        votacoes = db.query(Votacao).filter(Votacao.proposicao_id.in_(ids)).order_by(Votacao.data_hora.desc()).all()
        for v in votacoes:
            deliberacoes[v.proposicao_id].append(v)
            if v.tipo_deliberacao in TIPOS_SESSAO:
                sessoes_por_proposicao[v.proposicao_id].append(v)
        sessoes = [s for lista in sessoes_por_proposicao.values() for s in lista]
        placares = placares_das_votacoes(
            sessoes,
            contagens_por_votacao(db, Votacao.proposicao_id.in_(ids), Votacao.tipo_deliberacao.in_(TIPOS_SESSAO)),
        )
        autores = {r.proposicao_id: r for r in db.execute(_AUTOR_PRINCIPAL_SQL, {"ids": ids})}

    itens = []
    for p in proposicoes:
        placar, sessao, _ = resumo_da_casa(sessoes_por_proposicao.get(p.id, []), placares)
        tem_votacao = placar["TOTAL"] > 0

        autor = autores.get(p.id)
        if autor is not None and autor.partido:
            partido_sigla = autor.partido
        elif p.iniciativa_executivo:
            partido_sigla = "GOV"
        elif p.autor_nome:
            m = _PARTIDO_NA_AUTORIA_RE.search(p.autor_nome)
            partido_sigla = m.group(1).strip() if m else SEM_PARTIDO_SIGLA
        else:
            partido_sigla = SEM_PARTIDO_SIGLA
        autor_exibido = p.autor_nome or (
            autor.nome_exibicao
            if autor is not None and autor.nome_exibicao
            else ("Poder Executivo" if p.iniciativa_executivo else "Parlamentar")
        )

        peso_complexidade = pesos.peso_tipo(p.tipo_codigo)
        multiplicador = pesos.peso_status(p.status_codigo)
        resultado = "EM_TRAMITACAO"
        if sessao:
            resultado = "APROVADA" if sessao.get("aprovada") else "REJEITADA"
        elif p.status_codigo in STATUS_LEI:
            resultado = "APROVADA"

        delibs = deliberacoes.get(p.id, [])
        tipo_deliberacao = (
            ("NOMINAL" if delibs[0].tipo_deliberacao == "SECRETA" else delibs[0].tipo_deliberacao)
            if delibs
            else ("NOMINAL" if tem_votacao else None)
        )
        itens.append(
            {
                "id": str(p.uid),
                "tipo_deliberacao": tipo_deliberacao,
                "total_deliberacoes": len(delibs) or (1 if tem_votacao else 0),
                "camara_id": p.id_camara,
                "tipo": p.tipo_codigo,
                "numero": p.numero,
                "ano": p.ano,
                "titulo": p.titulo,
                "ementa": p.ementa,
                "setor": p.area_tematica or "Não classificado",
                "eixo_impacto": p.eixo_impacto or "Geral",
                "autor_nome": autor_exibido,
                "autor_politico_id": str(autor.pessoa_uid) if autor is not None and autor.pessoa_uid else None,
                "autor_partido": partido_sigla,
                "autor_uf": autor.uf if autor is not None else None,
                "autor_foto": autor.foto if autor is not None else None,
                "status": p.status_codigo,
                "data_apresentacao": p.data_apresentacao.isoformat(),
                "is_reforma_estrutural": p.reforma_estrutural,
                "iniciativa_executivo": p.iniciativa_executivo,
                "peso_complexidade": peso_complexidade,
                "multiplicador_tramitacao": multiplicador,
                "score_base": round(peso_complexidade * multiplicador, 2),
                "url_oficial": url_oficial_proposicao(p),
                "tem_votacao": tem_votacao,
                "sessao_id": sessao["sessao_id"] if sessao else None,
                "placar": {
                    "sim": placar["SIM"],
                    "nao": placar["NAO"],
                    "abstencao": placar["ABSTENCAO"],
                    "total": placar["TOTAL"],
                    "resultado": resultado,
                },
            }
        )

    return {
        "total": total,
        "page": pagina,
        "limit": limite,
        "total_pages": math.ceil(total / limite) if total > 0 else 1,
        "setores_disponiveis": setores,
        "items": itens,
    }
