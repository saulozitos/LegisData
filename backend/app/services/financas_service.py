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
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.core.errors import ErroDeDominio
from app.core.numeros import opt_float as _opt_float
from app.core.numeros import pct as _pct
from app.core.numeros import taxa_ou_desconhecida
from app.services.emendas_service import AREA_SEM_FUNCAO
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
    sem_resumo: Any
    total: Any
    sem_resumo, total = db.execute(
        text(
            "SELECT (SELECT count(DISTINCT d.pessoa_id) FROM fin.despesa_cota d WHERE d.pessoa_id = ANY(:ids) "
            "AND NOT EXISTS (SELECT 1 FROM fin.despesa_cota_resumo r WHERE r.pessoa_id = d.pessoa_id)), "
            "(SELECT sum(total_notas) FROM fin.despesa_cota_resumo WHERE pessoa_id = ANY(:ids))"
        ),
        {"ids": list(ids)},
    ).one()
    return None if total is None or sem_resumo else int(total)


# ── CEAP ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def custos_ceap(db: Session, pessoas: Sequence[int]) -> Optional[Dict[str, Any]]:
    """
    Resumo da CEAP: total, notas, gasto por tipo e por ano e maiores fornecedores. None se não há dado. A fonte traz só os
    15 maiores fornecedores de cada entrada (Câmara e Senado), então o total de um fornecedor que aparece no top 15 de uma
    casa e fora do da outra é subestimado, e a concentração calculada pelo dossiê parte dessa lista parcial.
    """
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
            "SELECT (array_agg(nome ORDER BY valor_total DESC, nome DESC))[1] AS nome, max(cnpj) AS cnpj, "
            "sum(valor_total) AS total, "
            "CASE WHEN bool_or(notas IS NULL) THEN NULL ELSE sum(notas) END AS notas FROM fin.despesa_cota_fornecedor "
            "WHERE pessoa_id = ANY(:ids) GROUP BY grupo ORDER BY total DESC, nome LIMIT 10"
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
                "num_notas": int(r.notas) if r.notas is not None else None,  # parcela desconhecida: total desconhecido
            }
            for r in fornecedores
        ],
    }


def vazio_ceap() -> Dict[str, Any]:
    """
    Resposta da CEAP de quem não tem dado, num dict novo a cada chamada (as listas não são compartilhadas). O total é
    nulo no dossiê e em `/ceap` avulso: zero afirmaria "gasto zero" onde a base simplesmente não tem a despesa.
    """
    return {
        "possui_dados": False,
        "gasto_total_recente": None,
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
        "possui_dados": total is not None,
        "total_gasto": round(float(total), 2) if total is not None else None,  # sem despesa o gasto é desconhecido
        "total_notas": _total_notas(db, ids) if ids else None,
        "despesas": [{"ano": r.ano, "tipo": r.tipo_despesa, "valor": round(float(r.valor), 2)} for r in linhas],
    }


# ── Emendas ──────────────────────────────────────────────────────────────────────────────────────────────────────────
_AGRUPAMENTOS = {
    "localidade": "SELECT localidade_destino AS chave, sum(valor_pago) AS total FROM fin.emenda "
    "WHERE pessoa_id = ANY(:ids) GROUP BY 1 ORDER BY total DESC, 1 LIMIT 20",
    "tipo": "SELECT tipo_emenda AS chave, sum(valor_pago) AS total FROM fin.emenda "
    "WHERE pessoa_id = ANY(:ids) GROUP BY 1 ORDER BY total DESC, 1",
    "area": "SELECT coalesce(funcao, :sem_funcao) AS chave, sum(valor_pago) AS total FROM fin.emenda "
    "WHERE pessoa_id = ANY(:ids) GROUP BY 1 ORDER BY total DESC, 1",
}


def _agrupado(db: Session, ids: List[int], rotulo: str, total_pago: float) -> List[Dict[str, Any]]:
    """Valor pago por localidade, tipo ou área (`rotulo` escolhe uma das consultas fixas acima)."""
    linhas = db.execute(text(_AGRUPAMENTOS[rotulo]), {"ids": ids, "sem_funcao": AREA_SEM_FUNCAO}).all()
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
        "percentual_execucao": taxa_ou_desconhecida(pago, empenhado),
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


def vazio_emendas() -> Dict[str, Any]:
    """
    Resposta das emendas de quem não tem nenhuma, num dict novo a cada chamada. Os totais e a taxa são desconhecidos
    (None), não zero: a base cobre só 2019 em diante, e quem é homônimo, não cadastrado ou do Senado sem vínculo também
    cai aqui, então "R$ 0 pagos" afirmaria mais do que a fonte sabe.
    """
    return {
        "possui_dados": False,
        "total_empenhado": None,
        "total_pago": None,
        "percentual_execucao": None,
        "destinos_principais": [],
        "distribuicao_por_tipo": [],
        "distribuicao_por_area": [],
        "total_emendas": 0,
        "lista_emendas": [],
    }


def vazio_emendas_detalhadas() -> Dict[str, Any]:
    """Resposta de `/emendas` de quem não tem pessoa nem emenda, num dict novo a cada chamada (totais desconhecidos)."""
    return {"possui_dados": False, "total_empenhado": None, "total_pago": None, "emendas": []}


def emendas_detalhadas(db: Session, pessoas: Sequence[int]) -> Dict[str, Any]:
    """Totais e linhas das emendas do parlamentar (rota `/emendas` do dossiê)."""
    ids = list(pessoas)
    if not ids:
        return vazio_emendas_detalhadas()
    empenhado, pago = db.execute(
        text("SELECT sum(valor_empenhado), sum(valor_pago) FROM fin.emenda WHERE pessoa_id = ANY(:ids)"),
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
        "possui_dados": len(linhas) > 0,
        "total_empenhado": _opt_float(empenhado),  # sem emenda a soma é NULL: desconhecido, não zero
        "total_pago": _opt_float(pago),
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
    """
    Os 12 registros mais recentes (12 meses COM remuneração, não 12 meses do calendário: lacunas de mandato entram como
    estão), os totais do ano do registro mais recente e o subsídio bruto acumulado. Tudo em float; o que a fonte não traz
    fica None, nunca zero.
    """
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
    primeiro_ano = (
        db.execute(text("SELECT min(ano) FROM fin.remuneracao WHERE pessoa_id = ANY(:ids)"), {"ids": ids}).scalar()
        if ids
        else None
    )
    total_bruto_ano: Optional[float] = None  # sem remuneração registrada o total é desconhecido, não zero
    total_ceap_ano: Optional[float] = None
    total_beneficios_ano: Optional[float] = None
    media_ceap: Optional[float] = None
    acumulado: Optional[float] = None
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
        total_bruto_ano = float(bruto)
        if qtd_ceap:
            total_ceap_ano = float(ceap)
            media_ceap = float((Decimal(ceap) / Decimal(qtd_ceap)).quantize(Decimal("0.01")))
        if qtd_beneficios:
            total_beneficios_ano = float(beneficios)
        acumulado = _opt_float(
            db.execute(
                text("SELECT sum(salario_bruto) FROM fin.remuneracao WHERE pessoa_id = ANY(:ids)"), {"ids": ids}
            ).scalar()
        )
    return {
        "historico": historico,
        "ano": ano,
        "primeiro_ano": primeiro_ano,
        "total_bruto_ano": total_bruto_ano,
        "total_ceap_ano": total_ceap_ano,
        "total_beneficios_ano": total_beneficios_ano,
        "media_ceap": media_ceap,
        "bruto_atual": historico[0]["salario_bruto"] if historico else None,
        "liquido_atual": historico[0]["salario_liquido"] if historico else None,
        "acumulado": acumulado,
    }


def declaracoes_na_janela_da_remuneracao(
    declaracoes: Sequence[Dict[str, Any]],
    primeiro_ano_remuneracao: Optional[int],
    ultimo_ano_remuneracao: Optional[int],
) -> List[Dict[str, Any]]:
    """
    Declarações de bens (da mais antiga para a mais nova) que cobrem o MESMO período do subsídio registrado, cortado nas
    DUAS pontas: a base é a última declarada até o primeiro ano da remuneração e o fim é a última declarada até o último
    ano dela. Comparar o patrimônio desde uma declaração de 1998 com um subsídio que só existe desde 2019 inflaria a
    razão; comparar uma declaração de 2026 com um subsídio que parou em 2023 também. A base também precisa estar colada
    no início do subsídio (no máximo um ano antes do primeiro ano registrado): com uma base mais antiga o patrimônio
    cresceu em anos cujo subsídio a fonte não tem, e a razão sairia inflada. Sem base, sem fim posterior à base, com base
    distante do início ou sem remuneração, a lista é vazia (a comparação não é possível).
    """
    if primeiro_ano_remuneracao is None or ultimo_ano_remuneracao is None:
        return []
    ate_a_base = [d for d in declaracoes if d["ano"] <= primeiro_ano_remuneracao]
    if not ate_a_base:
        return []
    base = ate_a_base[-1]
    if primeiro_ano_remuneracao > base["ano"] + 1:
        return []
    janela = [base] + [d for d in declaracoes if base["ano"] < d["ano"] <= ultimo_ano_remuneracao]
    return janela if len(janela) >= 2 else []


def subsidio_na_janela(
    db: Session, pessoas: Sequence[int], depois_do_ano: int, ate_o_ano: int
) -> Optional[Tuple[float, int]]:
    """
    (subsídio bruto, meses com folha) registrados nos anos `depois_do_ano < ano <= ate_o_ano`: o ano da declaração-base
    fica de fora porque a declaração dele já traz o patrimônio acumulado até ali. None (desconhecido, não zero) sem
    remuneração na faixa, com algum ano da faixa sem registro ou com algum ano INTERIOR (nem o primeiro nem o último da
    faixa, que podem ser parciais por posse ou fim de mandato) com menos de 12 meses: um buraco no meio deixaria o divisor
    menor que o período do patrimônio e a razão sairia inflada.
    """
    if not pessoas:
        return None
    anos = db.execute(
        text(
            "SELECT ano, count(DISTINCT mes) AS meses, sum(salario_bruto) AS soma FROM fin.remuneracao "
            "WHERE pessoa_id = ANY(:ids) AND ano > :depois AND ano <= :ate GROUP BY ano ORDER BY ano"
        ),
        {"ids": list(pessoas), "depois": depois_do_ano, "ate": ate_o_ano},
    ).all()
    if not anos or len(anos) != ate_o_ano - depois_do_ano:
        return None
    if any(r.meses < 12 for r in anos if depois_do_ano + 1 < r.ano < ate_o_ano):
        return None
    return float(sum(r.soma for r in anos)), int(sum(r.meses for r in anos))


def comparacao_patrimonial(
    db: Session,
    pessoas: Sequence[int],
    declaracoes: Sequence[Dict[str, Any]],
    primeiro_ano_remuneracao: Optional[int],
    ultimo_ano_remuneracao: Optional[int],
) -> Dict[str, Any]:
    """
    Evolução do patrimônio declarado contra o subsídio bruto registrado, as duas pontas no MESMO período: a base é a
    última declaração até o primeiro ano da remuneração, o fim é a última até o último ano dela, e o divisor soma só o
    subsídio dentro da janela (não o acumulado do mandato inteiro, que alimenta o ROI). Sem janela, sem subsídio na janela
    ou com subsídio zero (que não dá razão) tudo vem None, nunca zero.
    """
    janela = declaracoes_na_janela_da_remuneracao(declaracoes, primeiro_ano_remuneracao, ultimo_ano_remuneracao)
    subsidio = subsidio_na_janela(db, pessoas, janela[0]["ano"], janela[-1]["ano"]) if janela else None
    if subsidio is None or subsidio[0] <= 0:
        return {
            "delta_patrimonio": None,
            "salario_acumulado_estimado": None,
            "razao_patrimonio_renda": None,
            "periodo_comparado": None,
            "compatibilidade": None,
            "diagnostico": (
                "Dados insuficientes (requer uma declaração de bens até o início da remuneração registrada e outra "
                "depois dela, até o fim dela)."
            ),
        }
    soma, meses = subsidio
    delta = round(janela[-1]["valor"] - janela[0]["valor"], 2)
    razao = round(delta / soma, 2)
    if delta <= 0 or razao <= 0.8:
        compatibilidade = "COMPATÍVEL"
        diagnostico = "Crescimento patrimonial compatível ou inferior ao somatório dos subsídios brutos registrados."
    elif razao <= 2.0:
        compatibilidade = "MODERADO"
        diagnostico = "Evolução patrimonial compatível com rendimentos oficiais acrescidos de valorização imobiliária ou investimentos."
    else:
        compatibilidade = "ATÍPICO"
        diagnostico = f"Variação atípica: o patrimônio declarado cresceu {razao}x o total de subsídios registrados."
    return {
        "delta_patrimonio": delta,
        "salario_acumulado_estimado": round(soma, 2),
        "razao_patrimonio_renda": razao,
        "periodo_comparado": {
            "de": janela[0]["ano"],
            "ate": janela[-1]["ano"],
            # o subsídio somado começa no ano seguinte ao da base e termina no ano do fim da janela
            "subsidio_de": janela[0]["ano"] + 1,
            "subsidio_ate": janela[-1]["ano"],
            "meses_de_subsidio": meses,
        },
        "compatibilidade": compatibilidade,
        "diagnostico": diagnostico,
    }


# ── TSE ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
def declaracoes_de_patrimonio(db: Session, pessoas: Sequence[int]) -> List[Dict[str, Any]]:
    if not pessoas:
        return []
    linhas = db.execute(
        text(
            "SELECT ano_eleicao, valor_declarado, detalhes FROM fin.declaracao_patrimonio "
            "WHERE pessoa_id = ANY(:ids) ORDER BY ano_eleicao, valor_declarado DESC, id"
        ),
        {"ids": list(pessoas)},
    ).all()
    # a mesma eleição pode vir de duas pessoas ligadas ao parlamentar: fica uma declaração por ano (a de maior valor, depois a
    # de menor id), para a janela da comparação não depender da ordem em que o banco devolve as linhas
    por_ano: Dict[int, Dict[str, Any]] = {}
    for r in linhas:
        por_ano.setdefault(
            r.ano_eleicao, {"ano": r.ano_eleicao, "valor": float(r.valor_declarado), "detalhes": r.detalhes}
        )
    return list(por_ano.values())


def doacoes_de_campanha(db: Session, pessoas: Sequence[int]) -> List[Dict[str, Any]]:
    """Receitas de campanha, da maior para a menor. O CPF de pessoa física já está mascarado na origem."""
    if not pessoas:
        return []
    linhas = db.execute(
        text(
            "SELECT id, ano_eleicao, doador_nome, doador_documento, valor, tipo_receita, agregado, quantidade_doadores "
            "FROM fin.doacao_campanha "
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
            "agregado": r.agregado,
            "quantidade_doadores": r.quantidade_doadores,
        }
        for r in linhas
    ]


FORNECEDOR_NAO_IDENTIFICADO = "Fornecedor não identificado"  # idem, para o fornecedor sem nome na fonte
DOADOR_ANONIMO = "Doador não identificado"  # o mesmo rótulo que o ETL grava quando a fonte não informa o nome


def _chave_do_doador(doacao: Dict[str, Any]) -> Tuple[Any, ...]:
    """
    Quem é o doador de um recibo: o recibo inteiro quando não há nome nem documento (cada um é um desconhecido), o CNPJ
    sem pontuação quando há 14 dígitos (o mesmo CNPJ com e sem pontuação é um doador só) e, senão, o par nome e documento.
    Sem documento, o nome sozinho identifica: dois homônimos sem documento viram um doador (a quantidade pode sair menor),
    e a alternativa de tratar cada recibo como um doador contaria o mesmo doador várias vezes.
    """
    documento = doacao["cpf_cnpj_doador"]
    if documento is None and doacao["nome_doador"] == DOADOR_ANONIMO:
        return ("recibo", doacao["id"])
    digitos = re.sub(r"\D", "", documento or "")
    if len(digitos) == 14:
        return ("cnpj", digitos)
    return (doacao["nome_doador"], documento)


def resumo_das_doacoes(doacoes: Sequence[Dict[str, Any]], ano_eleicao: Optional[int] = None) -> Dict[str, Any]:
    """
    Resumo de UMA campanha da lista (já ordenada por valor): a eleição pedida ou, sem pedido, a mais recente. Traz as
    doações dela, o total, a quantidade de doadores distintos, os 5 maiores (com a participação de cada um) e as eleições
    disponíveis, já com os nomes de chave do dossiê. Eleições diferentes nunca se misturam no total.

    A fonte publica só os maiores doadores de cada candidato e uma linha agregada "Demais doadores (N)" que preserva o
    total. Essa linha (`agregado`) nunca entra no top 5 nem conta como um doador: ela soma N (`quantidade_doadores`) à
    quantidade, e vai separada em `demais_doadores`. Se N não veio, a quantidade é desconhecida (None), nunca um palpite.
    Um doador com vários recibos conta uma vez; doador sem nome e sem documento não se funde com outro.

    Levanta `ErroDeDominio` 404 quando a eleição pedida não tem doações MAS há doações de outras eleições; quem não tem
    nenhuma doação recebe o resumo vazio (`ano_eleicao` nulo) qualquer que seja a eleição pedida.
    """
    eleicoes = sorted({d["ano_eleicao"] for d in doacoes}, reverse=True)
    if not eleicoes:
        return {
            "ano_eleicao": None,
            "eleicoes_disponiveis": [],
            "total_arrecadado": None,  # sem doação registrada o total é desconhecido, não zero
            "total_doadores": None,
            "demais_doadores": None,
            "top_doadores": [],
            "todas_doacoes": [],
        }
    ano = ano_eleicao if ano_eleicao is not None else eleicoes[0]
    if ano not in eleicoes:
        raise ErroDeDominio(404, "Não há doações registradas para essa eleição.")
    da_campanha = [d for d in doacoes if d["ano_eleicao"] == ano]
    total = float(sum(d["valor_doado"] for d in da_campanha))
    por_doador: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    demais = [d for d in da_campanha if d["agregado"]]
    for d in da_campanha:
        if d["agregado"]:
            continue
        chave = _chave_do_doador(d)
        atual = por_doador.get(chave)
        if atual is None:
            por_doador[chave] = {**d, "maior": d["valor_doado"]}
            continue
        atual["valor_doado"] += d["valor_doado"]
        if d["valor_doado"] > atual["maior"]:  # o tipo do doador é o do maior recibo
            atual["maior"], atual["tipo_receita"] = d["valor_doado"], d["tipo_receita"]
    quantidades_demais = [d["quantidade_doadores"] for d in demais]
    desconhecida = any(q is None for q in quantidades_demais)
    quantidade = None if desconhecida else len(por_doador) + sum(q for q in quantidades_demais if q is not None)
    # valor arredondado em centavos (a soma em float de 0.10 + 0.20 não pode ficar à frente de 0.30), depois nome e documento
    maiores = sorted(
        por_doador.values(),
        key=lambda x: (-round(x["valor_doado"], 2), x["nome_doador"] or "", x["cpf_cnpj_doador"] or ""),
    )[:5]
    return {
        "ano_eleicao": ano,
        "eleicoes_disponiveis": eleicoes,
        "total_arrecadado": round(total, 2),
        "total_doadores": quantidade,
        "demais_doadores": (
            {
                "quantidade": None if desconhecida else sum(q for q in quantidades_demais if q is not None),
                "valor": round(float(sum(d["valor_doado"] for d in demais)), 2),
            }
            if demais
            else None
        ),
        "top_doadores": [
            {
                "nome_doador": d["nome_doador"],
                "cpf_cnpj_doador": d["cpf_cnpj_doador"],
                "valor_doado": round(d["valor_doado"], 2),
                "tipo_receita": d["tipo_receita"],
                "percentual": _pct(d["valor_doado"], total),
            }
            for d in maiores
        ],
        "todas_doacoes": da_campanha,
    }


def financiamento_da_campanha(doacoes: Sequence[Dict[str, Any]], ano_eleicao: Optional[int] = None) -> Dict[str, Any]:
    """Bloco de financiamento de campanha do dossiê (uma eleição); `/doacoes` reaproveita e só renomeia duas chaves."""
    return {"possui_dados": len(doacoes) > 0, **resumo_das_doacoes(doacoes, ano_eleicao)}


@dataclass(frozen=True)
class Certidao:
    """
    Linha de `fin.certidao` com os nomes que o Raio-X Judicial usa; o TSE não informa data, link nem autenticidade.
    Adaptador temporário: os nomes seguem o ORM legado (`court_agency`, `certificate_type`...) enquanto
    `_enrich_judicial_records` vive na rota; ambos mudam juntos na limpeza do legado (Fase 9).
    """

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


@dataclass(frozen=True)
class Processo:
    """
    Linha de `fin.processo_judicial` já com os nomes que o Raio-X Judicial usa. Os metadados vêm do DataJud (CNJ) e o
    vínculo com a pessoa vem do link da fonte oficial da curadoria. Nada aqui diz como o processo terminou: só o último
    movimento que o tribunal registrou (presunção de inocência).
    """

    numero_processo: str
    tribunal: Optional[str]
    grau: Optional[str]
    data_processo: Optional[str]
    classe_assunto: str
    orgao_julgador: Optional[str]
    ultimo_movimento: Optional[str]
    data_ultimo_movimento: Optional[str]
    link_comprovacao: str


def _classe_e_assuntos(classe: str, assuntos: Optional[Sequence[Optional[str]]]) -> str:
    """ "Classe / Assunto 1, Assunto 2"; um elemento NULL do `text[]` (o CHECK não o impede) é ignorado, não quebra o dossiê."""
    nomes = [a for a in (assuntos or []) if a]
    return f"{classe} / {', '.join(nomes)}" if nomes else classe


def processos(db: Session, pessoas: Sequence[int]) -> List[Processo]:
    if not pessoas:
        return []
    linhas = db.execute(
        text(
            "SELECT DISTINCT ON (numero_cnj) numero_cnj, tribunal, grau, classe, assuntos, orgao_julgador, "
            "data_ajuizamento, ultimo_movimento, data_ultimo_movimento, vinculo_url FROM fin.processo_judicial "
            "WHERE pessoa_id = ANY(:ids) ORDER BY numero_cnj, data_ultimo_movimento DESC NULLS LAST, id"
        ),
        {"ids": list(pessoas)},
    ).all()
    achados = [
        Processo(
            numero_processo=r.numero_cnj,
            tribunal=r.tribunal,
            grau=r.grau,
            data_processo=r.data_ajuizamento.isoformat() if r.data_ajuizamento else None,
            classe_assunto=_classe_e_assuntos(r.classe, r.assuntos),
            orgao_julgador=r.orgao_julgador,
            ultimo_movimento=r.ultimo_movimento,
            data_ultimo_movimento=r.data_ultimo_movimento.isoformat() if r.data_ultimo_movimento else None,
            link_comprovacao=r.vinculo_url,
        )
        for r in linhas
    ]
    return sorted(achados, key=lambda p: p.data_processo or "", reverse=True)
