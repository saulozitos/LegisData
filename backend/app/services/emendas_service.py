"""
Emendas orçamentárias lidas de `fin.emenda`: panorama, busca por localidade e por autor.

Os totais e as quebras (tipo de autor, área, ano, UF) são calculados no banco sobre todas as linhas; só a lista
detalhada é limitada. O tipo de autor e a UF de destino já vêm classificados pela carga do ETL.
"""

import unicodedata
from typing import Any, Dict, List

from app.core.errors import ErroDeDominio
from sqlalchemy import text
from sqlalchemy.orm import Session

DICIONARIO_ORCAMENTO = {
    "termos": {
        "custeio": {
            "termo_tecnico": "GND 3 — Despesas Correntes (Custeio)",
            "traducao": "Dinheiro para o dia a dia",
            "explicacao": "Recursos destinados à manutenção de serviços existentes: compra de remédios, merenda escolar, contas de energia de hospitais e insumos de saúde.",
        },
        "investimento": {
            "termo_tecnico": "GND 4 — Despesas de Capital (Investimentos)",
            "traducao": "Obras e Equipamentos",
            "explicacao": "Recursos aplicados na criação de bens duradouros: construção de postos de saúde, escolas, pavimentação de ruas, compra de ambulâncias e tratores.",
        },
        "empenhado": {
            "termo_tecnico": "Valor Empenhado",
            "traducao": "Dinheiro Reservado",
            "explicacao": "O Governo Federal aprovou o projeto e carimbou o recurso no orçamento. É a promessa formal de pagamento assim que a obra ou serviço for concluído.",
        },
        "pago": {
            "termo_tecnico": "Valor Liquidado / Pago",
            "traducao": "Dinheiro Entregue",
            "explicacao": "O serviço ou etapa da obra foi fiscalizado e o valor já caiu efetivamente na conta bancária da prefeitura ou instituição de destino.",
        },
    },
    "linha_do_tempo": [
        {
            "etapa": 1,
            "nome": "Orçado",
            "status": "Planejado",
            "descricao": "Previsto na Lei Orçamentária Anual do Congresso",
        },
        {
            "etapa": 2,
            "nome": "Reservado (Empenhado)",
            "status": "Garantido",
            "descricao": "Recurso aprovado e carimbado pelo Governo Federal",
        },
        {
            "etapa": 3,
            "nome": "Entregue (Pago)",
            "status": "Disponível na Ponta",
            "descricao": "Valor creditado na conta do município ou instituição beneficiada",
        },
    ],
    "areas_tematicas": {
        "Saúde": {"icone": "🩺", "rotulo": "Saúde e Cuidados Básicos"},
        "Educação": {"icone": "🏫", "rotulo": "Educação e Escolas"},
        "Agricultura": {"icone": "🚜", "rotulo": "Agricultura e Produtores Rurais"},
        "Urbanismo": {"icone": "🏙️", "rotulo": "Cidades, Asfalto e Habitação"},
        "Transporte": {"icone": "🛣️", "rotulo": "Estradas e Transportes"},
        "Segurança pública": {"icone": "🛡️", "rotulo": "Segurança e Proteção Comunitária"},
        "Assistência social": {"icone": "🤝", "rotulo": "Assistência Social e Família"},
        "Saneamento": {"icone": "💧", "rotulo": "Água Limpa e Saneamento Básico"},
        "Cultura": {"icone": "🎭", "rotulo": "Cultura e Patrimônio Histórico"},
        "Desporto e lazer": {"icone": "⚽", "rotulo": "Esporte e Lazer Comunitário"},
        "Defesa nacional": {"icone": "🎖️", "rotulo": "Defesa Nacional e Soberania"},
        "Outros": {"icone": "🏛️", "rotulo": "Desenvolvimento Regional e Outras Áreas"},
    },
}

_ESTADOS_MAP = {
    "ACRE": "AC",
    "ALAGOAS": "AL",
    "AMAPA": "AP",
    "AMAZONAS": "AM",
    "BAHIA": "BA",
    "CEARA": "CE",
    "DISTRITO FEDERAL": "DF",
    "ESPIRITO SANTO": "ES",
    "GOIAS": "GO",
    "MARANHAO": "MA",
    "MATO GROSSO": "MT",
    "MATO GROSSO DO SUL": "MS",
    "MINAS GERAIS": "MG",
    "PARA": "PA",
    "PARAIBA": "PB",
    "PARANA": "PR",
    "PERNAMBUCO": "PE",
    "PIAUI": "PI",
    "RIO DE JANEIRO": "RJ",
    "RIO GRANDE DO NORTE": "RN",
    "RIO GRANDE DO SUL": "RS",
    "RONDONIA": "RO",
    "RORAIMA": "RR",
    "SANTA CATARINA": "SC",
    "SAO PAULO": "SP",
    "SERGIPE": "SE",
    "TOCANTINS": "TO",
}


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn").upper()


def _extrair_uf_bancada(nome_limpo: str) -> str:
    for estado, uf in _ESTADOS_MAP.items():
        if estado in nome_limpo:
            return uf
    return "NACIONAL"


def _traduzir_comissao(nome_limpo: str) -> str:
    traducoes = {
        "SAUDE": "Comissão de Saúde",
        "EDUC": "Comissão de Educação e Cultura",
        "CONST": "Comissão de Constituição e Justiça",
        "ASSUNTOS ECONOMICOS": "Comissão de Assuntos Econômicos",
        "FINANCAS": "Comissão de Finanças e Tributação",
        "AGRICULTURA": "Comissão de Agricultura e Reforma Agrária",
        "MEIO AMBIENTE": "Comissão de Meio Ambiente",
        "SEGURANCA": "Comissão de Segurança Pública",
        "INFRA-ESTRUTURA": "Comissão de Serviços de Infraestrutura",
        "INTEGRACAO": "Comissão de Integração Nacional",
        "DIREITOS HUMANOS": "Comissão de Direitos Humanos",
        "VIACAO": "Comissão de Viação e Transportes",
        "DESENVOLVIMENTO URBANO": "Comissão de Desenvolvimento Urbano",
        "MULHER": "Comissão de Defesa dos Direitos da Mulher",
    }
    for termo, amigavel in traducoes.items():
        if termo in nome_limpo:
            return amigavel
    return "Comissão Temática do Congresso"


def perfil_do_autor(autor_nome: str, tipo_autor: str) -> Dict[str, Any]:
    """Descrição humanizada do autor, a partir do tipo que o ETL gravou em `fin.emenda.tipo_autor`."""
    norm = _strip_accents(autor_nome or "")
    if tipo_autor == "BANCADA_ESTADUAL":
        uf = _extrair_uf_bancada(norm)
        return {
            "tipo_autor": "BANCADA_ESTADUAL",
            "categoria": "Bancada Estadual",
            "nome_tecnico": autor_nome,
            "nome_amigavel": f"Bancada Estadual ({uf})",
            "uf_referencia": uf,
            "descricao_amigavel": "Recurso definido por votação coletiva de deputados e senadores da bancada deste estado.",
            "icone": "🗺️",
        }
    if tipo_autor == "RELATOR_GERAL":
        return {
            "tipo_autor": "RELATOR_GERAL",
            "categoria": "Relator-Geral do Orçamento",
            "nome_tecnico": autor_nome,
            "nome_amigavel": "Relator-Geral do Orçamento",
            "uf_referencia": "BR",
            "descricao_amigavel": "Recurso alocado pela Comissão Mista de Planos, Orçamentos Públicos e Fiscalização da União.",
            "icone": "⚖️",
        }
    if tipo_autor == "COMISSAO_INSTITUCIONAL":
        amigavel = _traduzir_comissao(norm)
        return {
            "tipo_autor": "COMISSAO_INSTITUCIONAL",
            "categoria": "Comissão Temática",
            "nome_tecnico": autor_nome,
            "nome_amigavel": amigavel,
            "uf_referencia": "BR",
            "descricao_amigavel": f"Verba institucional aprovada por consenso dos membros da {amigavel}.",
            "icone": "🏛️",
        }
    return {
        "tipo_autor": "INDIVIDUAL",
        "categoria": "Parlamentar Individual",
        "nome_tecnico": autor_nome,
        "nome_amigavel": (autor_nome or "").title(),
        "uf_referencia": None,
        "descricao_amigavel": "Recurso da cota orçamentária individual de livre indicação constitucional do parlamentar.",
        "icone": "👤",
    }


def _area(area: str) -> Dict[str, str]:
    return DICIONARIO_ORCAMENTO["areas_tematicas"].get(area, {"icone": "🏛️", "rotulo": area})


def _taxa(pago: float, empenhado: float) -> float:
    return round(pago / empenhado * 100.0, 1) if empenhado > 0 else 0.0


def _por_area(linhas: List[Any]) -> List[Dict[str, Any]]:
    return [
        {
            "area": r.area,
            "rotulo": _area(r.area)["rotulo"],
            "icone": _area(r.area)["icone"],
            "total_empenhado": float(r.empenhado),
            "total_pago": float(r.pago),
            "quantidade": int(r.quantidade),
        }
        for r in linhas
    ]


def resumo(db: Session) -> Dict[str, Any]:
    """Panorama geral das emendas: totais, tipo de autor, área, ano e as dez UFs mais beneficiadas."""
    total = db.execute(
        text("SELECT count(*) AS n, sum(valor_empenhado) AS emp, sum(valor_pago) AS pago FROM fin.emenda")
    ).one()
    if not total.n:
        raise ErroDeDominio(404, "Dados de emendas orçamentárias não encontrados.")
    empenhado, pago = float(total.emp), float(total.pago)

    por_tipo_autor: Dict[str, Any] = {}
    for r in db.execute(
        text(
            "SELECT tipo_autor, sum(valor_empenhado) AS emp, sum(valor_pago) AS pago, count(*) AS n FROM fin.emenda "
            "GROUP BY tipo_autor ORDER BY tipo_autor"
        )
    ):
        perfil = perfil_do_autor("", r.tipo_autor)
        por_tipo_autor[r.tipo_autor] = {
            "total_empenhado": float(r.emp),
            "total_pago": float(r.pago),
            "quantidade": int(r.n),
            "categoria": perfil["categoria"],
            "icone": perfil["icone"],
            "descricao": perfil["descricao_amigavel"],
        }

    areas = db.execute(
        text(
            "SELECT coalesce(funcao, 'Outros') AS area, sum(valor_empenhado) AS empenhado, sum(valor_pago) AS pago, "
            "count(*) AS quantidade FROM fin.emenda GROUP BY 1 ORDER BY pago DESC, 1"
        )
    ).all()
    anos = db.execute(
        text(
            "SELECT ano, sum(valor_empenhado) AS emp, sum(valor_pago) AS pago, count(*) AS n FROM fin.emenda "
            "GROUP BY ano ORDER BY ano"
        )
    ).all()
    ufs = db.execute(
        text(
            "SELECT uf, sum(valor_empenhado) AS emp, sum(valor_pago) AS pago, count(*) AS n FROM fin.emenda "
            "WHERE uf IS NOT NULL GROUP BY uf ORDER BY pago DESC, uf LIMIT 10"
        )
    ).all()
    return {
        "estatisticas_gerais": {
            "total_emendas": int(total.n),
            "total_reservado_empenhado_brl": round(empenhado, 2),
            "total_entregue_pago_brl": round(pago, 2),
            "taxa_execucao_pago_pct": _taxa(pago, empenhado),
        },
        "por_tipo_autor": por_tipo_autor,
        "por_area_tematica": _por_area(areas),
        "por_ano": {
            str(r.ano): {"total_empenhado": float(r.emp), "total_pago": float(r.pago), "quantidade": int(r.n)}
            for r in anos
        },
        "top_ufs": [
            {"uf": r.uf, "total_empenhado": float(r.emp), "total_pago": float(r.pago), "quantidade": int(r.n)}
            for r in ufs
        ],
        "dicionario": DICIONARIO_ORCAMENTO,
    }


def por_localidade(db: Session, localidade: str, limite: int) -> Dict[str, Any]:
    """Emendas destinadas a uma cidade ou estado (busca por trecho do nome, sem acento nem caixa)."""
    termo = localidade.strip()
    if not termo:
        raise ErroDeDominio(400, "Localidade não pode ser vazia.")
    total = db.execute(
        text(
            "SELECT count(*) AS n, sum(valor_empenhado) AS emp, sum(valor_pago) AS pago FROM fin.emenda "
            "WHERE strpos(ref.normalizar_texto(localidade_destino), ref.normalizar_texto(:termo)) > 0"
        ),
        {"termo": termo},
    ).one()
    if not total.n:
        raise ErroDeDominio(404, f"Nenhuma emenda encontrada para a localidade '{localidade}'.")
    empenhado, pago = float(total.emp), float(total.pago)
    areas = db.execute(
        text(
            "SELECT coalesce(funcao, 'Outros') AS area, sum(valor_empenhado) AS empenhado, sum(valor_pago) AS pago, "
            "count(*) AS quantidade FROM fin.emenda "
            "WHERE strpos(ref.normalizar_texto(localidade_destino), ref.normalizar_texto(:termo)) > 0 "
            "GROUP BY 1 ORDER BY pago DESC, 1"
        ),
        {"termo": termo},
    ).all()
    linhas = db.execute(
        text(
            "SELECT codigo_emenda, ano, coalesce(funcao, 'Outros') AS area, tipo_emenda, valor_empenhado, valor_pago, "
            "autor_texto, tipo_autor FROM fin.emenda "
            "WHERE strpos(ref.normalizar_texto(localidade_destino), ref.normalizar_texto(:termo)) > 0 "
            "ORDER BY ano DESC, valor_pago DESC, id LIMIT :limite"
        ),
        {"termo": termo, "limite": limite},
    ).all()
    return {
        "localidade_pesquisada": localidade,
        "total_emendas_encontradas": int(total.n),
        "total_reservado_empenhado_brl": round(empenhado, 2),
        "total_entregue_pago_brl": round(pago, 2),
        "taxa_execucao_pct": _taxa(pago, empenhado),
        "divisao_por_area": _por_area(areas),
        "emendas": [
            {
                "codigo_emenda": r.codigo_emenda,
                "ano": r.ano,
                "area_tematica": r.area,
                "area_rotulo": _area(r.area)["rotulo"],
                "area_icone": _area(r.area)["icone"],
                "valor_reservado_empenhado": float(r.valor_empenhado),
                "valor_entregue_pago": float(r.valor_pago),
                "estagio": "Dinheiro Entregue" if r.valor_pago > 0 else "Dinheiro Reservado",
                "tipo_recurso": (
                    "Obras e Equipamentos" if "Investimento" in r.tipo_emenda else "Dinheiro para o dia a dia"
                ),
                "autor": perfil_do_autor(r.autor_texto, r.tipo_autor),
            }
            for r in linhas
        ],
        "dicionario": DICIONARIO_ORCAMENTO["termos"],
    }


def por_autor(db: Session, autor: str, limite: int) -> Dict[str, Any]:
    """Emendas de um autor (parlamentar, comissão ou bancada), pelo trecho do nome ou pelo código do autor."""
    termo = autor.strip()
    if not termo:
        raise ErroDeDominio(400, "Autor não pode ser vazio.")
    total = db.execute(
        text(
            "SELECT count(*) AS n, sum(valor_empenhado) AS emp, sum(valor_pago) AS pago, min(autor_texto) AS autor, "
            "min(tipo_autor) AS tipo_autor FROM fin.emenda "
            "WHERE (strpos(ref.normalizar_texto(autor_texto), ref.normalizar_texto(:termo)) > 0 "
            "OR autor_codigo = :termo)"
        ),
        {"termo": termo},
    ).one()
    if not total.n:
        raise ErroDeDominio(404, f"Nenhuma emenda encontrada para o autor '{autor}'.")
    empenhado, pago = float(total.emp), float(total.pago)
    destinos = db.execute(
        text(
            "SELECT localidade_destino AS localidade, sum(valor_empenhado) AS total_empenhado, "
            "sum(valor_pago) AS total_pago, count(*) AS quantidade FROM fin.emenda "
            "WHERE (strpos(ref.normalizar_texto(autor_texto), ref.normalizar_texto(:termo)) > 0 "
            "OR autor_codigo = :termo) GROUP BY 1 ORDER BY total_pago DESC, 1 LIMIT 10"
        ),
        {"termo": termo},
    ).all()
    areas = db.execute(
        text(
            "SELECT coalesce(funcao, 'Outros') AS area, sum(valor_empenhado) AS empenhado, sum(valor_pago) AS pago, "
            "count(*) AS quantidade FROM fin.emenda "
            "WHERE (strpos(ref.normalizar_texto(autor_texto), ref.normalizar_texto(:termo)) > 0 "
            "OR autor_codigo = :termo) GROUP BY 1 ORDER BY pago DESC, 1"
        ),
        {"termo": termo},
    ).all()
    linhas = db.execute(
        text(
            "SELECT codigo_emenda, ano, localidade_destino, coalesce(funcao, 'Outros') AS area, valor_empenhado, "
            "valor_pago FROM fin.emenda "
            "WHERE (strpos(ref.normalizar_texto(autor_texto), ref.normalizar_texto(:termo)) > 0 "
            "OR autor_codigo = :termo) ORDER BY ano DESC, valor_pago DESC, id LIMIT :limite"
        ),
        {"termo": termo, "limite": limite},
    ).all()
    return {
        "autor_pesquisado": autor,
        "perfil_autor": perfil_do_autor(total.autor, total.tipo_autor),
        "total_emendas_enviadas": int(total.n),
        "total_reservado_empenhado_brl": round(empenhado, 2),
        "total_entregue_pago_brl": round(pago, 2),
        "taxa_execucao_pct": _taxa(pago, empenhado),
        "top_destinos": [
            {
                "localidade": r.localidade,
                "total_empenhado": float(r.total_empenhado),
                "total_pago": float(r.total_pago),
                "quantidade": int(r.quantidade),
            }
            for r in destinos
        ],
        "por_area_tematica": _por_area(areas),
        "emendas": [
            {
                "codigo_emenda": r.codigo_emenda,
                "ano": r.ano,
                "localidade_destino": r.localidade_destino,
                "area_tematica": r.area,
                "area_rotulo": _area(r.area)["rotulo"],
                "area_icone": _area(r.area)["icone"],
                "valor_reservado_empenhado": float(r.valor_empenhado),
                "valor_entregue_pago": float(r.valor_pago),
                "estagio": "Dinheiro Entregue" if r.valor_pago > 0 else "Dinheiro Reservado",
            }
            for r in linhas
        ],
    }
