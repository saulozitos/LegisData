"""Diário do Congresso: dias em que houve votação nominal, com as matérias deliberadas em cada data."""

from datetime import date, datetime
from typing import Any, Dict, Optional

from app.core.errors import ErroDeDominio
from app.core.links import url_oficial_proposicao
from app.core.query_utils import BRT, to_brt
from app.models.leg import Proposicao, Votacao
from app.services.placar import contagens_por_votacao, placar_para_tela, placares_das_votacoes
from app.services.votos_proposicao_service import TIPOS_SESSAO, casa_codigo, titulo_votacao
from sqlalchemy import desc, extract
from sqlalchemy.orm import Session

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


def _dias_no_ano(ano: int) -> int:
    return 366 if (ano % 4 == 0 and (ano % 100 != 0 or ano % 400 == 0)) else 365


def calendario_de_votacoes(db: Session, ano: Optional[int]) -> Dict[str, Any]:
    """Calendário do ano pedido (sem ano, o mais recente com votações), com estatística de dias ativos."""
    coluna_ano = extract("year", Votacao.data_hora)
    anos_disponiveis = sorted(
        (int(r[0]) for r in db.query(coluna_ano).filter(Votacao.tipo_deliberacao.in_(TIPOS_SESSAO)).distinct().all()),
        reverse=True,
    )

    if not anos_disponiveis:
        ano_vazio = ano or date.today().year
        total_dias = _dias_no_ano(ano_vazio)
        return {
            "ano_selecionado": ano_vazio,
            "anos_disponiveis": [],
            "estatisticas_anuais": {
                "ano": ano_vazio,
                "total_dias_ano": total_dias,
                "dias_com_votacao": 0,
                "percentual_dias_ativos": 0.0,
                "total_sessoes_ano": 0,
                "texto_estatistica": (
                    f"Em {ano_vazio}, de {total_dias} dias, o Congresso realizou sessões de votação nominal em 0 dias."
                ),
            },
            "dias": [],
        }

    if ano is not None and ano not in anos_disponiveis:
        raise ErroDeDominio(404, f"Sem votações registradas em {ano}.")
    selecionado = ano if ano is not None else anos_disponiveis[0]

    # filtro de ano feito no banco (não carrega as sessões de todos os anos)
    filtro_ano = (
        Votacao.data_hora >= datetime(selecionado, 1, 1, tzinfo=BRT),
        Votacao.data_hora < datetime(selecionado + 1, 1, 1, tzinfo=BRT),
        Votacao.tipo_deliberacao.in_(TIPOS_SESSAO),
    )
    sessoes_ano = (
        db.query(Votacao, Proposicao)
        .join(Proposicao, Votacao.proposicao_id == Proposicao.id)
        .filter(*filtro_ano)
        .order_by(desc(Votacao.data_hora), Votacao.id)
        .all()
    )
    placares = placares_das_votacoes([s for s, _ in sessoes_ano], contagens_por_votacao(db, *filtro_ano))

    dias: Dict[str, Dict[str, Any]] = {}
    for sessao, prop in sessoes_ano:
        local = to_brt(sessao.data_hora)
        chave = local.strftime("%Y-%m-%d")
        if chave not in dias:
            d = local.date()
            dias[chave] = {
                "data": chave,
                "dia": d.day,
                "mes": d.month,
                "ano": d.year,
                "dia_semana": DIAS_SEMANA_PT.get(d.weekday(), ""),
                "data_formatada": f"{d.day:02d} de {MESES_PT.get(d.month, '')} de {d.year}",
                "total_votacoes": 0,
                "camara_count": 0,
                "senado_count": 0,
                "sessoes": [],
            }

        placar = placar_para_tela(placares[sessao.id])
        casa = casa_codigo(sessao)
        dias[chave]["camara_count" if casa == "CAMARA_DOS_DEPUTADOS" else "senado_count"] += 1
        dias[chave]["total_votacoes"] += 1
        dias[chave]["sessoes"].append(
            {
                "sessao_id": str(sessao.uid),
                "casa": casa,
                "casa_nome": "Câmara dos Deputados" if casa == "CAMARA_DOS_DEPUTADOS" else "Senado Federal",
                "hora": local.strftime("%H:%M"),
                "titulo": titulo_votacao(sessao),
                "descricao": sessao.descricao or titulo_votacao(sessao),
                "aprovada": sessao.aprovada,
                "is_votacao_secreta": bool(sessao.secreta),
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
                    "url_oficial": url_oficial_proposicao(prop),
                },
            }
        )

    lista = sorted(dias.values(), key=lambda d: d["data"], reverse=True)
    total_dias_ano = _dias_no_ano(selecionado)
    dias_com_votacao = len(lista)
    percentual = round(dias_com_votacao / total_dias_ano * 100, 1)
    return {
        "ano_selecionado": selecionado,
        "anos_disponiveis": anos_disponiveis,
        "estatisticas_anuais": {
            "ano": selecionado,
            "total_dias_ano": total_dias_ano,
            "dias_com_votacao": dias_com_votacao,
            "percentual_dias_ativos": percentual,
            "total_sessoes_ano": len(sessoes_ano),
            "texto_estatistica": (
                f"Em {selecionado}, de {total_dias_ano} dias, o Congresso realizou "
                f"sessões de votação nominal em apenas {dias_com_votacao} dias ({percentual}% do ano)."
            ),
        },
        "dias": lista,
    }
