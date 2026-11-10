"""
Cobertura dos painéis: de onde vêm os dados, que período a base cobre, quando foi a última carga e se está completa.

Quem lê uma tela não deve tomar o que a base tem pelo que aconteceu no mundo: "1 dia com votação cadastrado" é cobertura, não
a atividade inteira do Congresso. O nome da fonte, as fontes do ETL e o ano-alvo ficam em `ref.cobertura_painel`; o período e
a contagem saem das tabelas de domínio. Painel sem registro devolve `situacao = SEM_DADOS`, nunca um período inventado.
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

COMPLETA = "COMPLETA"
PARCIAL = "PARCIAL"
SEM_DADOS = "SEM_DADOS"

# painel -> (consulta de período e quantidade, o que a quantidade conta); SQL literal, sem parâmetros do usuário
_CONSULTAS: Dict[str, Tuple[str, str]] = {
    "votacoes": (
        "SELECT min(data_hora)::date, max(data_hora)::date, count(*) FROM leg.votacao "
        "WHERE tipo_deliberacao IN ('NOMINAL', 'SECRETA')",
        "votações",
    ),
    "proposicoes": (
        "SELECT make_date(min(ano)::int, 1, 1), max(data_apresentacao)::date, count(*) FROM leg.proposicao",
        "proposições",
    ),
    "parlamentares": (
        "SELECT min(inicio)::date, least(max(coalesce(fim, current_date)), current_date)::date, count(*) FROM core.mandato",
        "mandatos",
    ),
    "presenca": (
        "SELECT min(data_sessao)::date, max(data_sessao)::date, count(*) FROM leg.presenca",
        "registros de presença",
    ),
    "gastos": (
        "SELECT make_date(min(ano)::int, 1, 1), least(make_date(max(ano)::int, 12, 31), current_date), count(*) FROM fin.despesa_cota",
        "despesas",
    ),
}


def _situacao(inicio: Optional[date], inicio_alvo: int) -> str:
    if inicio is None:
        return SEM_DADOS
    return COMPLETA if inicio.year <= inicio_alvo else PARCIAL


def _nota(situacao: str, titulo: str, inicio: Optional[date], inicio_alvo: int) -> str:
    if situacao == SEM_DADOS:
        return f"A base ainda não tem dados de {titulo.lower()}."
    if situacao == PARCIAL and inicio is not None:
        return (
            f"Base parcial: tem dados de {titulo.lower()} a partir de {inicio.year}; "
            f"o que veio antes de {inicio.year} não está cadastrado, e a ausência não significa que não houve atividade."
        )
    return f"Base completa desde {inicio_alvo}, até a data da última carga."


def cobertura_dos_paineis(db: Session) -> List[Dict[str, Any]]:
    linhas = db.execute(
        text(
            "SELECT painel, titulo, fontes_texto, inicio_alvo, atualizado_em FROM ref.vw_cobertura_painel ORDER BY painel"
        )
    ).all()
    resultado: List[Dict[str, Any]] = []
    for painel, titulo, fontes, inicio_alvo, atualizado_em in linhas:
        consulta = _CONSULTAS.get(str(painel))
        inicio = fim = None
        registros = 0
        unidade = ""
        if consulta is not None:
            sql, unidade = consulta
            inicio, fim, registros = db.execute(text(sql)).one()
            registros = int(registros or 0)
        situacao = _situacao(inicio, inicio_alvo)
        resultado.append(
            {
                "painel": painel,
                "titulo": titulo,
                "fonte": fontes,
                "periodo_inicio": inicio.isoformat() if inicio else None,
                "periodo_fim": fim.isoformat() if fim else None,
                "registros": registros,
                "unidade": unidade,
                "atualizado_em": _iso(atualizado_em),
                "situacao": situacao,
                "nota": _nota(situacao, titulo, inicio, inicio_alvo),
            }
        )
    return resultado


def _iso(valor: Optional[datetime]) -> Optional[str]:
    return valor.isoformat() if valor else None
