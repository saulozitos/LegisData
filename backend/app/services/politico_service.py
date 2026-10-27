"""
Cadastro do político lido de `core`: a pessoa, os identificadores da Câmara/Senado, a foto e o nome civil. É a base da
busca e do dossiê, no lugar do cadastro legado (`politicos`). O identificador público é o `uid` da pessoa.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional

from app.core.errors import ErroDeDominio
from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class Politico:
    """
    A pessoa com os nomes dos campos que o dossiê já usava (`id` é o uid público). Campo que a fonte não informa é None.
    """

    id: uuid.UUID
    pessoa_id: int
    electoral_name: str
    civil_name: str
    gender: Optional[str]
    birth_date: Optional[date]
    birthplace_city: Optional[str]
    birthplace_state: Optional[str]
    photo_url: Optional[str]
    email: Optional[str]
    cabinet_room: Optional[str]
    cabinet_phone: Optional[str]
    biography: Optional[str]
    social_links: Optional[Dict[str, Any]]
    camara_id: Optional[int]
    senado_id: Optional[int]


# O nome civil é o primeiro cadastrado; o identificador oficial, o menor (uma pessoa pode ter mais de um).
_CARREGAR = text(
    """
    SELECT pe.uid AS id, pe.id AS pessoa_id, pe.nome_exibicao AS electoral_name,
           coalesce((SELECT n.nome FROM core.pessoa_nome n WHERE n.pessoa_id = pe.id AND n.tipo = 'CIVIL'
                      ORDER BY n.id LIMIT 1), pe.nome_exibicao) AS civil_name,
           pe.sexo AS gender, pe.data_nascimento AS birth_date, pe.municipio_nascimento AS birthplace_city,
           pe.uf_nascimento AS birthplace_state, fm.url_origem AS photo_url, pe.email,
           pe.gabinete_sala AS cabinet_room, pe.gabinete_telefone AS cabinet_phone, pe.biografia AS biography,
           pe.redes_sociais AS social_links,
           (SELECT min(valor::int) FROM core.pessoa_identificador
             WHERE pessoa_id = pe.id AND tipo = 'CAMARA_ID' AND valor ~ '^[0-9]+$') AS camara_id,
           (SELECT min(valor::int) FROM core.pessoa_identificador
             WHERE pessoa_id = pe.id AND tipo = 'SENADO_ID' AND valor ~ '^[0-9]+$') AS senado_id
    FROM core.pessoa pe LEFT JOIN core.midia fm ON fm.id = pe.foto_midia_id
    WHERE pe.id = ANY(:ids)
    """
)


def carregar(db: Session, pessoas: List[int]) -> List[Politico]:
    """Os políticos das pessoas `pessoas`, na mesma ordem (pessoa inexistente fica de fora)."""
    por_id = {linha["pessoa_id"]: Politico(**linha) for linha in db.execute(_CARREGAR, {"ids": pessoas}).mappings()}
    return [por_id[i] for i in pessoas if i in por_id]


def _primeiro(db: Session, consulta: Any, parametros: Dict[str, Any]) -> Optional[Politico]:
    achados = carregar(db, list(db.execute(consulta, parametros).scalars()))
    return achados[0] if achados else None


def por_uid(db: Session, uid: uuid.UUID) -> Optional[Politico]:
    return _primeiro(db, text("SELECT id FROM core.pessoa WHERE uid = :uid"), {"uid": uid})


def por_identificador_oficial(db: Session, numero: int) -> Optional[Politico]:
    """Pelo ID da Câmara ou do Senado; se os dois casarem, quem tem ID da Câmara vem antes, depois o nome."""
    return _primeiro(
        db,
        text(
            """
            SELECT pe.id FROM core.pessoa pe
            WHERE pe.id IN (SELECT pessoa_id FROM core.pessoa_identificador
                             WHERE tipo IN ('CAMARA_ID', 'SENADO_ID') AND valor = CAST(:numero AS text))
            ORDER BY NOT EXISTS (SELECT 1 FROM core.pessoa_identificador i
                                  WHERE i.pessoa_id = pe.id AND i.tipo = 'CAMARA_ID'),
                     pe.nome_exibicao, pe.uid
            LIMIT 1
            """
        ),
        {"numero": numero},
    )


def por_nome_exato(db: Session, nome: str) -> List[Politico]:
    """Até duas pessoas cujo nome de exibição ou civil é exatamente `nome` (sem diferenciar maiúsculas)."""
    ids = db.execute(
        text(
            """
            SELECT pe.id FROM core.pessoa pe
            WHERE lower(pe.nome_exibicao) = :nome
               OR pe.id IN (SELECT pessoa_id FROM core.pessoa_nome WHERE tipo = 'CIVIL' AND lower(nome) = :nome)
            ORDER BY pe.nome_exibicao, pe.uid
            LIMIT 2
            """
        ),
        {"nome": nome},
    ).scalars()
    return carregar(db, list(ids))


def resolver(db: Session, identificador: str) -> Politico:
    """
    Resolve o político por UUID, ID da Câmara/Senado ou nome exato (slug). Nunca por substring: se o nome for ambíguo
    levanta 409 em vez de escolher um registro arbitrário.
    """
    try:
        achado = por_uid(db, uuid.UUID(identificador))
        if achado:
            return achado
    except ValueError:
        pass

    if identificador.isdigit():
        achado = por_identificador_oficial(db, int(identificador))
        if achado:
            return achado

    slug = identificador.replace("-", " ").strip().lower()
    if slug:
        candidatos = por_nome_exato(db, slug)
        if len(candidatos) == 1:
            return candidatos[0]
        if len(candidatos) > 1:
            raise ErroDeDominio(409, f"Identificador '{identificador}' é ambíguo; use o ID.")

    raise ErroDeDominio(404, f"Político '{identificador}' não encontrado.")


@dataclass(frozen=True)
class FiltroDeBusca:
    """O que a busca de políticos aceita; campo None não filtra."""

    texto: Optional[str] = None
    cargo: Optional[str] = None
    siglas: Optional[List[str]] = None  # partido: qualquer uma das siglas (maiúsculas)
    uf: Optional[str] = None
    inicio: Optional[date] = None  # período de um mandato presidencial (início e fim juntos)
    fim: Optional[date] = None


# Mandato de nomeação (ministro) não conta como mandato eletivo na busca; a pessoa só nomeada ainda é listada.
_BUSCA = text(
    """
    SELECT count(*) OVER () AS total, pe.id
    FROM core.pessoa pe
    WHERE EXISTS (SELECT 1 FROM core.mandato m0 WHERE m0.pessoa_id = pe.id)
      AND (CAST(:texto AS text) IS NULL
           OR pe.nome_exibicao ILIKE :texto ESCAPE '\\'
           OR EXISTS (SELECT 1 FROM core.pessoa_nome n
                       WHERE n.pessoa_id = pe.id AND n.tipo = 'CIVIL' AND n.nome ILIKE :texto ESCAPE '\\'))
      AND (CAST(:siglas AS text[]) IS NULL
           OR EXISTS (SELECT 1 FROM core.mandato m JOIN core.partido pa ON pa.id = m.partido_id
                       WHERE m.pessoa_id = pe.id AND m.condicao <> 'NOMEADO' AND upper(pa.sigla) = ANY(:siglas)
                         AND (CASE WHEN CAST(:inicio AS date) IS NOT NULL
                                   THEN m.inicio <= :fim AND (m.fim IS NULL OR m.fim >= :inicio)
                                   ELSE m.fim IS NULL OR m.fim >= :hoje END))
           OR EXISTS (SELECT 1 FROM core.filiacao f JOIN core.partido pa ON pa.id = f.partido_id
                       WHERE f.pessoa_id = pe.id AND upper(pa.sigla) = ANY(:siglas)
                         AND (CASE WHEN CAST(:inicio AS date) IS NOT NULL
                                   THEN lower(f.periodo) <= :fim AND (upper_inf(f.periodo) OR upper(f.periodo) - 1 >= :inicio)
                                   ELSE upper_inf(f.periodo) END)))
      AND (CAST(:cargo AS text) IS NULL
           OR EXISTS (SELECT 1 FROM core.mandato m JOIN ref.cargo c ON c.id = m.cargo_id
                       WHERE m.pessoa_id = pe.id AND m.condicao <> 'NOMEADO' AND c.codigo = :cargo))
      AND (CAST(:uf AS text) IS NULL
           OR EXISTS (SELECT 1 FROM core.mandato m JOIN ref.circunscricao ci ON ci.id = m.circunscricao_id
                       WHERE m.pessoa_id = pe.id AND m.condicao <> 'NOMEADO' AND ci.uf = :uf))
      AND (CAST(:inicio AS date) IS NULL
           OR EXISTS (SELECT 1 FROM core.mandato m JOIN ref.cargo c ON c.id = m.cargo_id
                       WHERE m.pessoa_id = pe.id AND m.condicao <> 'NOMEADO'
                         AND m.inicio <= :fim AND (m.fim IS NULL OR m.fim >= :inicio)
                         AND (CAST(:cargo AS text) IS NULL OR c.codigo = :cargo)))
    ORDER BY pe.nome_exibicao, pe.uid
    LIMIT :limite OFFSET :deslocamento
    """
)
_MANDATOS_DA_PAGINA = text(
    """
    SELECT m.pessoa_id, c.codigo AS cargo, coalesce(ci.uf, 'BR') AS uf, pa.sigla AS partido_sigla,
           pa.nome AS partido_nome
    FROM core.mandato m
    JOIN ref.cargo c ON c.id = m.cargo_id
    JOIN ref.circunscricao ci ON ci.id = m.circunscricao_id
    LEFT JOIN core.partido pa ON pa.id = m.partido_id
    WHERE m.pessoa_id = ANY(:ids) AND m.condicao <> 'NOMEADO'
    ORDER BY m.pessoa_id, m.inicio DESC, m.id DESC
    """
)
_FILIACAO_VIGENTE = text(
    """
    SELECT DISTINCT ON (f.pessoa_id) f.pessoa_id, pa.sigla AS partido_sigla, pa.nome AS partido_nome
    FROM core.filiacao f JOIN core.partido pa ON pa.id = f.partido_id
    WHERE f.pessoa_id = ANY(:ids) AND upper_inf(f.periodo)
    ORDER BY f.pessoa_id, lower(f.periodo) DESC, f.id DESC
    """
)


def _parecido(texto: Optional[str]) -> Optional[str]:
    """`%texto%` com os curingas do usuário (`%`, `_`, `\\`) tratados como texto."""
    if not texto or not texto.strip():
        return None
    limpo = texto.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{limpo}%"


def buscar(db: Session, filtro: FiltroDeBusca, limite: int, deslocamento: int) -> Dict[str, Any]:
    """
    Uma página de políticos (quem tem algum mandato), ordenada por nome. Devolve `total` (de todo o filtro), os
    `politicos`, os `mandatos` de cada um (do mais novo ao mais antigo, sem nomeações) e o `partido_vigente`, o da
    filiação em aberto, por `pessoa_id`.
    """
    parametros = {
        "texto": _parecido(filtro.texto),
        "siglas": filtro.siglas,
        "cargo": filtro.cargo,
        "uf": filtro.uf,
        "inicio": filtro.inicio,
        "fim": filtro.fim,
        "hoje": date.today(),
        "limite": limite,
        "deslocamento": deslocamento,
    }
    linhas = db.execute(_BUSCA, parametros).all()
    if linhas:
        total = int(linhas[0][0])
    elif deslocamento > 0:  # página além do fim: o total ainda vale
        total = int(db.execute(_BUSCA, {**parametros, "limite": 1, "deslocamento": 0}).scalar() or 0)
    else:
        total = 0
    ids = [linha[1] for linha in linhas]
    mandatos: Dict[int, List[Dict[str, Any]]] = {}
    vigente: Dict[int, Dict[str, Any]] = {}
    if ids:
        for linha in db.execute(_MANDATOS_DA_PAGINA, {"ids": ids}).mappings():
            mandatos.setdefault(linha["pessoa_id"], []).append(dict(linha))
        for linha in db.execute(_FILIACAO_VIGENTE, {"ids": ids}).mappings():
            vigente[linha["pessoa_id"]] = dict(linha)
    return {"total": total, "politicos": carregar(db, ids), "mandatos": mandatos, "partido_vigente": vigente}
