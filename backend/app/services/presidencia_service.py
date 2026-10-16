"""Presidentes da República e seus mandatos, lidos de `core` (substitui o arquivo `presidentes_historico.json`)."""

import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

_SLUG = re.compile(r"^[a-z0-9-]{1,60}$")

_MANDATOS_SQL = text(
    """
    SELECT m.id, m.uid, mp.slug, mp.rotulo, mp.status, mp.vice_texto, mp.motivo_inicio, m.inicio, m.fim,
           m.numero_mandato, e.ano AS ano_eleicao,
           pe.nome_exibicao, pe.data_nascimento, pe.data_falecimento, pe.sexo, pe.municipio_nascimento,
           pe.uf_nascimento,
           (SELECT n.nome FROM core.pessoa_nome n WHERE n.pessoa_id = pe.id AND n.tipo = 'CIVIL' LIMIT 1) AS nome_civil,
           pt.sigla AS partido_sigla, pt.nome AS partido_nome, mi.url_origem AS foto_url
    FROM core.mandato_presidencial mp
    JOIN core.mandato m ON m.id = mp.mandato_id
    JOIN core.pessoa pe ON pe.id = m.pessoa_id
    LEFT JOIN core.eleicao e ON e.id = m.eleicao_id
    LEFT JOIN core.vw_partido pt ON pt.id = m.partido_id
    LEFT JOIN core.midia mi ON mi.id = pe.foto_midia_id
    ORDER BY m.inicio
    """
)

_MINISTROS_SQL = text(
    """
    SELECT m.nomeado_por_mandato_id AS mandato_id, pe.nome_exibicao, m.inicio, m.fim, m.papel
    FROM core.mandato m JOIN core.pessoa pe ON pe.id = m.pessoa_id
    WHERE m.funcao_destaque = 'ECONOMIA' AND m.nomeado_por_mandato_id IS NOT NULL
    ORDER BY m.nomeado_por_mandato_id, m.inicio
    """
)

_MARCOS_SQL = text("SELECT mandato_id, texto FROM core.marco_governo ORDER BY mandato_id, ordem")

_GENERO = {"M": "MASCULINO", "F": "FEMININO"}


def _data(valor: Optional[date]) -> Optional[str]:
    return valor.isoformat() if valor else None


def listar_presidentes(db: Session) -> List[Dict[str, Any]]:
    """Todos os mandatos presidenciais desde 1995, do mais antigo ao mais recente."""
    ministros: Dict[int, List[Dict[str, Any]]] = {}
    for r in db.execute(_MINISTROS_SQL).mappings():
        ministros.setdefault(r["mandato_id"], []).append(
            {"nome": r["nome_exibicao"], "inicio": _data(r["inicio"]), "fim": _data(r["fim"]), "papel": r["papel"]}
        )
    marcos: Dict[int, List[str]] = {}
    for mandato_id, texto in db.execute(_MARCOS_SQL):
        marcos.setdefault(mandato_id, []).append(texto)

    lista = []
    for r in db.execute(_MANDATOS_SQL).mappings():
        sexo = (r["sexo"] or "").upper()
        lista.append(
            {
                "id_referencia": r["slug"],
                "db_id": str(r["uid"]),
                "nome_civil": r["nome_civil"] or r["nome_exibicao"],
                "nome_eleitoral": f"{r['nome_exibicao']} ({r['rotulo']})" if r["rotulo"] else r["nome_exibicao"],
                "cpf": None,
                "data_nascimento": _data(r["data_nascimento"]),
                "data_falecimento": _data(r["data_falecimento"]),
                "genero": _GENERO.get(sexo, sexo or None),
                "naturalidade_municipio": r["municipio_nascimento"],
                "naturalidade_uf": r["uf_nascimento"],
                "partido_eleicao": r["partido_sigla"],
                "partido_sigla": r["partido_sigla"],
                "partido_nome": r["partido_nome"],
                "mandato_numero": r["numero_mandato"],
                "ano_eleicao": r["ano_eleicao"],
                "data_inicio": _data(r["inicio"]),
                "data_fim": _data(r["fim"]),
                "status_mandato": r["status"],
                "motivo_inicio": r["motivo_inicio"],
                "vice_presidente": r["vice_texto"],
                "ministros_fazenda_chave": ministros.get(r["id"], []),
                "marcos_economicos": marcos.get(r["id"], []),
                "foto_url": r["foto_url"],
            }
        )
    return lista


def presidente_por_referencia(db: Session, referencia: str) -> Optional[Dict[str, Any]]:
    """Busca por identificador público (`lula-2023`) ou pelo `uid` do mandato."""
    limpo = referencia.strip().lower()
    candidato_uid: Optional[str] = None
    try:
        candidato_uid = str(UUID(limpo))
    except ValueError:
        if not _SLUG.match(limpo):
            return None
    for presidente in listar_presidentes(db):
        if presidente["id_referencia"] == limpo or (candidato_uid and presidente["db_id"] == candidato_uid):
            return presidente
    return None


def periodo_do_mandato(db: Session, referencia: str) -> Optional[Tuple[date, date]]:
    """(início, fim) do mandato; o mandato em curso termina hoje."""
    presidente = presidente_por_referencia(db, referencia)
    if not presidente:
        return None
    fim = date.fromisoformat(presidente["data_fim"]) if presidente["data_fim"] else date.today()
    return date.fromisoformat(presidente["data_inicio"]), fim
