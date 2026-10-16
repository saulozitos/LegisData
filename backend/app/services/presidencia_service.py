"""Presidentes da República e seus mandatos, lidos de `core` (substitui o arquivo `presidentes_historico.json`)."""

from datetime import date
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from app.services.periodos import SLUG_MANDATO, nome_do_mandato
from sqlalchemy import text
from sqlalchemy.orm import Session

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


def mandatos_presidenciais(db: Session) -> List[Dict[str, Any]]:
    """Linhas cruas dos mandatos presidenciais (com o id interno), do mais antigo ao mais recente."""
    return [dict(r) for r in db.execute(_MANDATOS_SQL).mappings()]


def ministros_da_economia(db: Session) -> Dict[int, List[Dict[str, Any]]]:
    """Ministros da Fazenda/Economia nomeados por cada mandato (chave: id interno do mandato), em ordem de posse."""
    ministros: Dict[int, List[Dict[str, Any]]] = {}
    for r in db.execute(_MINISTROS_SQL).mappings():
        ministros.setdefault(r["mandato_id"], []).append(
            {"nome": r["nome_exibicao"], "inicio": _data(r["inicio"]), "fim": _data(r["fim"]), "papel": r["papel"]}
        )
    return ministros


def marcos_por_mandato(db: Session) -> Dict[int, List[str]]:
    marcos: Dict[int, List[str]] = {}
    for mandato_id, texto in db.execute(_MARCOS_SQL):
        marcos.setdefault(mandato_id, []).append(texto)
    return marcos


def listar_presidentes(db: Session) -> List[Dict[str, Any]]:
    """Todos os mandatos presidenciais desde 1995, do mais antigo ao mais recente."""
    ministros = ministros_da_economia(db)
    marcos = marcos_por_mandato(db)

    lista = []
    for r in mandatos_presidenciais(db):
        sexo = (r["sexo"] or "").upper()
        lista.append(
            {
                "id_referencia": r["slug"],
                "db_id": str(r["uid"]),
                "nome_civil": r["nome_civil"] or r["nome_exibicao"],
                "nome_eleitoral": nome_do_mandato(r["nome_exibicao"], r["rotulo"]),
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


def _referencia_valida(referencia: str) -> Optional[Tuple[str, Optional[str]]]:
    """(slug em minúsculas, uid normalizado se for UUID); None se não for nem slug nem UUID."""
    limpo = referencia.strip().lower()
    try:
        return limpo, str(UUID(limpo))
    except ValueError:
        return (limpo, None) if SLUG_MANDATO.match(limpo) else None


def presidente_por_referencia(db: Session, referencia: str) -> Optional[Dict[str, Any]]:
    """Busca por identificador público (`lula-2023`) ou pelo `uid` do mandato."""
    chave = _referencia_valida(referencia)
    if chave is None:
        return None
    slug, uid = chave
    for presidente in listar_presidentes(db):
        if presidente["id_referencia"] == slug or (uid and presidente["db_id"] == uid):
            return presidente
    return None


def periodo_do_mandato(db: Session, referencia: str) -> Optional[Tuple[date, date]]:
    """(início, fim) do mandato; o mandato em curso termina hoje. Lê só as datas, sem montar o presidente."""
    chave = _referencia_valida(referencia)
    if chave is None:
        return None
    slug, uid = chave
    for r in mandatos_presidenciais(db):
        if r["slug"] == slug or (uid and str(r["uid"]) == uid):
            return r["inicio"], r["fim"] or date.today()
    return None
