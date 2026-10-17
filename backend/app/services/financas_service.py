"""
Finanças do parlamentar lidas do schema `fin`: CEAP, emendas, remuneração, patrimônio, doações e certidões do TSE.

O dossiê é endereçado pelo `uid` do cadastro do legado, mas o dado de finanças é gravado na pessoa que tem o
identificador oficial (Câmara ou Senado). Enquanto as pessoas duplicadas não são unificadas (`docs/PESSOAS_DUPLICADAS.md`),
`pessoas_do_parlamentar` junta as duas pontas pelo `camara_id`/`senado_id` do político.

Nada aqui inventa dado: sem linha no banco a função devolve None (ou lista vazia) e a API mostra "sem dados".
"""

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from app.core.numeros import opt_float as _opt_float
from app.core.numeros import pct as _pct
from sqlalchemy import text
from sqlalchemy.orm import Session

MAX_EMENDAS_LISTADAS = 500
MAX_EMENDAS_DETALHADAS = 2000
MAX_DESPESAS_LISTADAS = 2000


def formatar_cnpj(cnpj: Optional[str]) -> Optional[str]:
    digitos = re.sub(r"\D", "", cnpj or "")
    if len(digitos) != 14:
        return None
    return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"


def pessoas_do_parlamentar(db: Session, uid: Any, camara_id: Optional[int], senado_id: Optional[int]) -> List[int]:
    """Cadastros de `core.pessoa` que são o mesmo parlamentar: o do `uid` e os que têm o mesmo identificador oficial."""
    linhas = db.execute(
        text(
            """
            SELECT id FROM core.pessoa WHERE uid = :uid
            UNION
            SELECT pessoa_id FROM core.pessoa_identificador
             WHERE (tipo = 'CAMARA_ID' AND valor = CAST(:camara AS text))
                OR (tipo = 'SENADO_ID' AND valor = CAST(:senado AS text))
            """
        ),
        {"uid": uid, "camara": camara_id, "senado": senado_id},
    )
    return [r[0] for r in linhas]


def _total_notas(db: Session, ids: Sequence[int]) -> Optional[int]:
    """
    Quantidade de notas da CEAP. É None (desconhecida) quando alguma das pessoas com despesa não tem linha de resumo:
    somar só as que têm mostraria uma contagem parcial ao lado de um gasto completo.
    """
    com_despesa: Any
    com_resumo: Any
    total: Any
    com_despesa, com_resumo, total = db.execute(
        text(
            "SELECT (SELECT count(DISTINCT pessoa_id) FROM fin.despesa_cota WHERE pessoa_id = ANY(:ids)), "
            "(SELECT count(*) FROM fin.despesa_cota_resumo WHERE pessoa_id = ANY(:ids)), "
            "(SELECT sum(total_notas) FROM fin.despesa_cota_resumo WHERE pessoa_id = ANY(:ids))"
        ),
        {"ids": list(ids)},
    ).one()
    return None if total is None or com_resumo < com_despesa else int(total)


# ── CEAP ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def custos_ceap(db: Session, pessoas: Sequence[int]) -> Optional[Dict[str, Any]]:
    """Resumo da CEAP: total, notas, gasto por tipo e por ano e maiores fornecedores. None se não há dado."""
    if not pessoas:
        return None
    ids = list(pessoas)
    por_tipo = db.execute(
        text(
            "SELECT tipo_despesa, sum(valor_liquido) AS total FROM fin.despesa_cota WHERE pessoa_id = ANY(:ids) "
            "GROUP BY tipo_despesa ORDER BY total DESC, tipo_despesa"
        ),
        {"ids": ids},
    ).all()
    if not por_tipo:
        return None
    total = float(sum(r.total for r in por_tipo))
    por_ano = db.execute(
        text(
            "SELECT ano, sum(valor_liquido) AS total FROM fin.despesa_cota WHERE pessoa_id = ANY(:ids) "
            "GROUP BY ano ORDER BY ano DESC"
        ),
        {"ids": ids},
    ).all()
    fornecedores = db.execute(
        text(
            "SELECT nome, cnpj, sum(valor_total) AS total, sum(notas) AS notas FROM fin.despesa_cota_fornecedor "
            "WHERE pessoa_id = ANY(:ids) GROUP BY nome, cnpj ORDER BY total DESC, nome LIMIT 10"
        ),
        {"ids": ids},
    ).all()
    return {
        "possui_dados": True,
        "gasto_total_recente": round(total, 2),
        "total_notas": _total_notas(db, ids),  # sem linha de resumo a quantidade é desconhecida
        "gastos_por_tipo": [
            {
                "tipo_despesa": r.tipo_despesa,
                "total_gasto": round(float(r.total), 2),
                "percentual": _pct(float(r.total), total),
            }
            for r in por_tipo
        ],
        "gastos_por_ano": [{"ano": r.ano, "total_gasto": round(float(r.total), 2)} for r in por_ano],
        "maiores_fornecedores": [
            {
                "nome_fornecedor": r.nome,
                "cnpj_cpf": formatar_cnpj(r.cnpj),
                "total_recebido": round(float(r.total), 2),
                "num_notas": int(r.notas),
            }
            for r in fornecedores
        ],
    }


VAZIO_CEAP: Dict[str, Any] = {
    "possui_dados": False,
    "gasto_total_recente": 0.0,
    "total_notas": None,
    "gastos_por_tipo": [],
    "gastos_por_ano": [],
    "maiores_fornecedores": [],
}


def ceap_por_ano_e_tipo(db: Session, pessoas: Sequence[int]) -> Dict[str, Any]:
    """Total da CEAP por ano e tipo de despesa (a fonte publicada pelo ETL não traz nota por nota)."""
    ids = list(pessoas)
    linhas = (
        db.execute(
            text(
                "SELECT ano, tipo_despesa, sum(valor_liquido) AS valor FROM fin.despesa_cota "
                "WHERE pessoa_id = ANY(:ids) GROUP BY ano, tipo_despesa ORDER BY ano DESC, valor DESC, tipo_despesa "
                "LIMIT :limite"
            ),
            {"ids": ids, "limite": MAX_DESPESAS_LISTADAS},
        ).all()
        if ids
        else []
    )
    total = None
    if ids:
        total = db.execute(
            text("SELECT sum(valor_liquido) FROM fin.despesa_cota WHERE pessoa_id = ANY(:ids)"), {"ids": ids}
        ).scalar()
    return {
        "total_gasto": round(float(total), 2) if total is not None else 0.0,
        "total_notas": _total_notas(db, ids) if ids else None,
        "despesas": [{"ano": r.ano, "tipo": r.tipo_despesa, "valor": round(float(r.valor), 2)} for r in linhas],
    }


# ── Emendas ──────────────────────────────────────────────────────────────────────────────────────────────────────────
_AGRUPAMENTOS = {
    "localidade": "SELECT localidade_destino AS chave, sum(valor_pago) AS total FROM fin.emenda "
    "WHERE pessoa_id = ANY(:ids) GROUP BY 1 ORDER BY total DESC, 1",
    "tipo": "SELECT tipo_emenda AS chave, sum(valor_pago) AS total FROM fin.emenda "
    "WHERE pessoa_id = ANY(:ids) GROUP BY 1 ORDER BY total DESC, 1",
    "area": "SELECT coalesce(funcao, 'Outras Funções') AS chave, sum(valor_pago) AS total FROM fin.emenda "
    "WHERE pessoa_id = ANY(:ids) GROUP BY 1 ORDER BY total DESC, 1",
}


def _agrupado(db: Session, ids: List[int], rotulo: str, total_pago: float) -> List[Dict[str, Any]]:
    """Valor pago por localidade, tipo ou área (`rotulo` escolhe uma das consultas fixas acima)."""
    linhas = db.execute(text(_AGRUPAMENTOS[rotulo]), {"ids": ids}).all()
    return [
        {rotulo: r.chave, "valor_pago": round(float(r.total), 2), "percentual": _pct(float(r.total), total_pago)}
        for r in linhas
    ]


def emendas_do_parlamentar(db: Session, pessoas: Sequence[int]) -> Optional[Dict[str, Any]]:
    """Resumo e lista (as mais recentes e de maior valor pago) das emendas do parlamentar. None se não há emenda."""
    if not pessoas:
        return None
    ids = list(pessoas)
    resumo = db.execute(
        text(
            "SELECT coalesce(sum(valor_empenhado), 0), coalesce(sum(valor_pago), 0), count(*) FROM fin.emenda "
            "WHERE pessoa_id = ANY(:ids)"
        ),
        {"ids": ids},
    ).one()
    empenhado, pago, quantidade = float(resumo[0]), float(resumo[1]), int(resumo[2])
    if not quantidade:
        return None
    lista = db.execute(
        text(
            "SELECT uid, ano, codigo_emenda, tipo_emenda, valor_empenhado, valor_pago, localidade_destino, funcao "
            "FROM fin.emenda WHERE pessoa_id = ANY(:ids) ORDER BY ano DESC, valor_pago DESC, id LIMIT :limite"
        ),
        {"ids": ids, "limite": MAX_EMENDAS_LISTADAS},
    ).all()
    return {
        "possui_dados": True,
        "total_empenhado": round(empenhado, 2),
        "total_pago": round(pago, 2),
        "percentual_execucao": _pct(pago, empenhado),
        "destinos_principais": _agrupado(db, ids, "localidade", pago),
        "distribuicao_por_tipo": _agrupado(db, ids, "tipo", pago),
        "distribuicao_por_area": _agrupado(db, ids, "area", pago),
        "total_emendas": quantidade,
        "lista_emendas": [
            {
                "id": str(r.uid),
                "ano": r.ano,
                "codigo_emenda": r.codigo_emenda,
                "tipo_emenda": r.tipo_emenda,
                "valor_empenhado": float(r.valor_empenhado),
                "valor_pago": float(r.valor_pago),
                "localidade_destino": r.localidade_destino,
                "funcao": r.funcao,
            }
            for r in lista
        ],
    }


VAZIO_EMENDAS: Dict[str, Any] = {
    "possui_dados": False,
    "total_empenhado": 0.0,
    "total_pago": 0.0,
    "percentual_execucao": 0.0,
    "destinos_principais": [],
    "distribuicao_por_tipo": [],
    "distribuicao_por_area": [],
    "total_emendas": 0,
    "lista_emendas": [],
}


def emendas_detalhadas(db: Session, pessoas: Sequence[int]) -> Dict[str, Any]:
    """Totais e linhas das emendas do parlamentar (rota `/emendas` do dossiê)."""
    ids = list(pessoas)
    if not ids:
        return {"total_empenhado": 0.0, "total_pago": 0.0, "emendas": []}
    empenhado, pago = db.execute(
        text(
            "SELECT coalesce(sum(valor_empenhado), 0), coalesce(sum(valor_pago), 0) FROM fin.emenda "
            "WHERE pessoa_id = ANY(:ids)"
        ),
        {"ids": ids},
    ).one()
    linhas = db.execute(
        text(
            "SELECT ano, codigo_emenda, tipo_emenda, valor_empenhado, valor_pago, localidade_destino, funcao "
            "FROM fin.emenda WHERE pessoa_id = ANY(:ids) ORDER BY ano DESC, valor_pago DESC, id LIMIT :limite"
        ),
        {"ids": ids, "limite": MAX_EMENDAS_DETALHADAS},
    ).all()
    return {
        "total_empenhado": float(empenhado),
        "total_pago": float(pago),
        "emendas": [
            {
                "ano": r.ano,
                "codigo": r.codigo_emenda,
                "tipo": r.tipo_emenda,
                "valor_empenhado": float(r.valor_empenhado),
                "valor_pago": float(r.valor_pago),
                "destino": r.localidade_destino,
                "area": r.funcao,
            }
            for r in linhas
        ],
    }


# ── Remuneração ──────────────────────────────────────────────────────────────────────────────────────────────────────
def remuneracao(db: Session, pessoas: Sequence[int]) -> Dict[str, Any]:
    """Últimos 12 meses, totais do ano mais recente e subsídio bruto acumulado; campos que a fonte não traz ficam None."""
    ids = list(pessoas)
    meses = (
        db.execute(
            text(
                "SELECT r.ano, r.mes, r.salario_bruto, r.salario_liquido, r.cota_ceap, r.auxilio_moradia, "
                "r.outros_beneficios, f.nome AS fonte FROM fin.remuneracao r JOIN etl.fonte f ON f.id = r.fonte_id "
                "WHERE r.pessoa_id = ANY(:ids) ORDER BY r.ano DESC, r.mes DESC LIMIT 12"
            ),
            {"ids": ids},
        ).all()
        if ids
        else []
    )
    historico = [
        {
            "ano": r.ano,
            "mes": r.mes,
            "salario_bruto": float(r.salario_bruto),
            "salario_liquido": _opt_float(r.salario_liquido),
            "cota_ceap": _opt_float(r.cota_ceap),
            "auxilio_moradia": _opt_float(r.auxilio_moradia),
            "outros_beneficios": _opt_float(r.outros_beneficios),
            "fonte": r.fonte,
        }
        for r in meses
    ]
    ano = meses[0].ano if meses else None
    total_bruto_ano: Optional[Decimal] = None  # sem remuneração registrada o total é desconhecido, não zero
    total_ceap_ano: Optional[Decimal] = None
    total_beneficios_ano: Optional[Decimal] = None
    media_ceap: Optional[float] = None
    acumulado = Decimal("0.00")
    if ano is not None:
        bruto, ceap, qtd_ceap, beneficios, qtd_beneficios = db.execute(
            text(
                "SELECT coalesce(sum(salario_bruto), 0), sum(cota_ceap), count(cota_ceap), "
                "sum(coalesce(auxilio_moradia, 0) + coalesce(outros_beneficios, 0)), "
                "count(auxilio_moradia) + count(outros_beneficios) FROM fin.remuneracao "
                "WHERE pessoa_id = ANY(:ids) AND ano = :ano"
            ),
            {"ids": ids, "ano": ano},
        ).one()
        total_bruto_ano = Decimal(bruto)
        if qtd_ceap:
            total_ceap_ano = Decimal(ceap)
            media_ceap = float((Decimal(ceap) / Decimal(qtd_ceap)).quantize(Decimal("0.01")))
        if qtd_beneficios:
            total_beneficios_ano = Decimal(beneficios)
        acumulado = Decimal(
            db.execute(
                text("SELECT coalesce(sum(salario_bruto), 0) FROM fin.remuneracao WHERE pessoa_id = ANY(:ids)"),
                {"ids": ids},
            ).scalar()
            or 0
        )
    return {
        "historico": historico,
        "ano": ano,
        "total_bruto_ano": total_bruto_ano,
        "total_ceap_ano": total_ceap_ano,
        "total_beneficios_ano": total_beneficios_ano,
        "media_ceap": media_ceap,
        "bruto_atual": historico[0]["salario_bruto"] if historico else None,
        "liquido_atual": historico[0]["salario_liquido"] if historico else None,
        "acumulado": float(acumulado),
    }


# ── TSE ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
def declaracoes_de_patrimonio(db: Session, pessoas: Sequence[int]) -> List[Dict[str, Any]]:
    if not pessoas:
        return []
    linhas = db.execute(
        text(
            "SELECT ano_eleicao, valor_declarado, detalhes FROM fin.declaracao_patrimonio "
            "WHERE pessoa_id = ANY(:ids) ORDER BY ano_eleicao"
        ),
        {"ids": list(pessoas)},
    ).all()
    return [{"ano": r.ano_eleicao, "valor": float(r.valor_declarado), "detalhes": r.detalhes} for r in linhas]


def doacoes_de_campanha(db: Session, pessoas: Sequence[int]) -> List[Dict[str, Any]]:
    """Receitas de campanha, da maior para a menor. O CPF de pessoa física já está mascarado na origem."""
    if not pessoas:
        return []
    linhas = db.execute(
        text(
            "SELECT id, ano_eleicao, doador_nome, doador_documento, valor, tipo_receita FROM fin.doacao_campanha "
            "WHERE pessoa_id = ANY(:ids) ORDER BY valor DESC, id"
        ),
        {"ids": list(pessoas)},
    ).all()
    return [
        {
            "id": str(r.id),
            "ano_eleicao": r.ano_eleicao,
            "nome_doador": r.doador_nome,
            "cpf_cnpj_doador": r.doador_documento,
            "valor_doado": float(r.valor),
            "tipo_receita": r.tipo_receita,
        }
        for r in linhas
    ]


@dataclass(frozen=True)
class Certidao:
    """Linha de `fin.certidao` com os nomes que o Raio-X Judicial usa; o TSE não informa data, link nem autenticidade."""

    id: int
    court_agency: str
    certificate_type: str
    status: str
    details: Optional[str]
    process_number: Optional[str]
    issue_date: Optional[str] = None
    proof_url: Optional[str] = None
    auth_code: Optional[str] = None


def certidoes(db: Session, pessoas: Sequence[int]) -> List[Certidao]:
    if not pessoas:
        return []
    linhas = db.execute(
        text(
            "SELECT id, orgao, tipo, situacao, detalhes, numero_processo FROM fin.certidao "
            "WHERE pessoa_id = ANY(:ids) ORDER BY orgao, tipo"
        ),
        {"ids": list(pessoas)},
    ).all()
    return [Certidao(r.id, r.orgao, r.tipo, r.situacao, r.detalhes, r.numero_processo) for r in linhas]
