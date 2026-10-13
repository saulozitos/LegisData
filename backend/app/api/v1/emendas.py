"""
API Oficial de Emendas Orçamentárias — LegisData.

Fornece consulta acessível, humanizada e estruturada das emendas parlamentares do Orçamento Federal:
- Classificação por tipo de autor: Individual (Político Específico), Bancada Estadual (Coletiva),
  Comissão Temática (Institucional) e Relator-Geral.
- Dicionário de termos que traduz a linguagem orçamentária técnica em termos do dia a dia do cidadão.
- Endpoints de resumo consolidado, busca por localidade (cidade/UF) e busca por autor.
"""

import json
import logging
import unicodedata
from collections import defaultdict
from typing import Any, Dict, List, Optional

from app.core.config import PROCESSED_DATA_DIR
from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter()

# Dicionário da API: traduz termos técnicos para linguagem simples do cidadão
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


def classificar_autor(autor_nome: str, tipo_emenda: str) -> Dict[str, Any]:
    norm = _strip_accents(autor_nome or "")

    if "BANCADA" in norm or tipo_emenda == "Emenda de Bancada":
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
    elif "RELATOR" in norm or tipo_emenda == "Emenda de Relator":
        return {
            "tipo_autor": "RELATOR_GERAL",
            "categoria": "Relator-Geral do Orçamento",
            "nome_tecnico": autor_nome,
            "nome_amigavel": "Relator-Geral do Orçamento",
            "uf_referencia": "BR",
            "descricao_amigavel": "Recurso alocado pela Comissão Mista de Planos, Orçamentos Públicos e Fiscalização da União.",
            "icone": "⚖️",
        }
    elif norm.startswith("COM.") or norm.startswith("COMISSAO") or tipo_emenda == "Emenda de Comissão":
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
    else:
        return {
            "tipo_autor": "INDIVIDUAL",
            "categoria": "Parlamentar Individual",
            "nome_tecnico": autor_nome,
            "nome_amigavel": (autor_nome or "").title(),
            "uf_referencia": None,
            "descricao_amigavel": "Recurso da cota orçamentária individual de livre indicação constitucional do parlamentar.",
            "icone": "👤",
        }


# Cache em memória para carregamento instantâneo do catálogo completo oficial
_EMENDAS_DATA: Optional[List[Dict[str, Any]]] = None


def _get_emendas_dataset() -> List[Dict[str, Any]]:
    global _EMENDAS_DATA
    if _EMENDAS_DATA is not None:
        return _EMENDAS_DATA

    filepath = PROCESSED_DATA_DIR / "emendas_parlamentares_2019_2026.json"
    if not filepath.exists():
        logger.warning("emendas_parlamentares_2019_2026.json não encontrado em %s", filepath)
        return []

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            raw = json.load(f)
            if isinstance(raw, list):
                _EMENDAS_DATA = raw
                return raw
    except Exception as exc:
        logger.error("Erro ao carregar emendas_parlamentares_2019_2026.json: %s", exc)

    return []


@router.get("/resumo")
def get_emendas_resumo():
    """
    Retorna o panorama geral do Orçamento das Emendas Parlamentares (2019–2026):
    - Valores consolidados (Total Empenhado/Reservado vs Total Pago/Entregue)
    - Divisão por tipo de autor (Individual, Bancada Estadual, Comissão Temática e Relator-Geral)
    - Divisão por áreas temáticas com ícones amigáveis
    - Divisão temporal por ano do orçamento
    - Top 10 UFs mais beneficiadas
    - Dicionário de tradução da linguagem orçamentária para o cidadão
    """
    emendas = _get_emendas_dataset()
    if not emendas:
        raise HTTPException(status_code=404, detail="Dados de emendas orçamentárias não encontrados.")

    total_empenhado = 0.0
    total_pago = 0.0

    por_tipo_autor = defaultdict(lambda: {"total_empenhado": 0.0, "total_pago": 0.0, "quantidade": 0})
    por_area = defaultdict(lambda: {"total_empenhado": 0.0, "total_pago": 0.0, "quantidade": 0})
    por_ano = defaultdict(lambda: {"total_empenhado": 0.0, "total_pago": 0.0, "quantidade": 0})
    por_uf = defaultdict(lambda: {"total_empenhado": 0.0, "total_pago": 0.0, "quantidade": 0})

    for item in emendas:
        emp = float(item.get("valor_empenhado") or 0.0)
        pago = float(item.get("valor_pago") or 0.0)
        total_empenhado += emp
        total_pago += pago

        # Tipo de autor
        tipo_autor_info = classificar_autor(item.get("politician_name", ""), item.get("tipo_emenda", ""))
        tipo_chave = tipo_autor_info["tipo_autor"]
        por_tipo_autor[tipo_chave]["total_empenhado"] += emp
        por_tipo_autor[tipo_chave]["total_pago"] += pago
        por_tipo_autor[tipo_chave]["quantidade"] += 1
        por_tipo_autor[tipo_chave]["categoria"] = tipo_autor_info["categoria"]
        por_tipo_autor[tipo_chave]["icone"] = tipo_autor_info["icone"]
        por_tipo_autor[tipo_chave]["descricao"] = tipo_autor_info["descricao_amigavel"]

        # Área temática
        area = item.get("funcao") or "Outros"
        por_area[area]["total_empenhado"] += emp
        por_area[area]["total_pago"] += pago
        por_area[area]["quantidade"] += 1

        # Ano
        ano = item.get("ano")
        if ano:
            por_ano[str(ano)]["total_empenhado"] += emp
            por_ano[str(ano)]["total_pago"] += pago
            por_ano[str(ano)]["quantidade"] += 1

        # UF Destino
        loc = item.get("localidade_destino") or ""
        uf_encontrada = None
        for estado, sigla in _ESTADOS_MAP.items():
            if sigla in loc or estado in loc.upper():
                uf_encontrada = sigla
                break
        if uf_encontrada:
            por_uf[uf_encontrada]["total_empenhado"] += emp
            por_uf[uf_encontrada]["total_pago"] += pago
            por_uf[uf_encontrada]["quantidade"] += 1

    # Ordena top UFs
    top_ufs = sorted(
        [{"uf": k, **v} for k, v in por_uf.items()],
        key=lambda x: x["total_pago"],
        reverse=True,
    )[:10]

    # Ordena áreas
    areas_formatadas = []
    for area, dados in sorted(por_area.items(), key=lambda x: x[1]["total_pago"], reverse=True):
        meta_area = DICIONARIO_ORCAMENTO["areas_tematicas"].get(area, {"icone": "🏛️", "rotulo": area})
        areas_formatadas.append(
            {
                "area": area,
                "rotulo": meta_area["rotulo"],
                "icone": meta_area["icone"],
                **dados,
            }
        )

    taxa_execucao = round((total_pago / total_empenhado * 100.0), 1) if total_empenhado > 0 else 0.0

    return {
        "estatisticas_gerais": {
            "total_emendas": len(emendas),
            "total_reservado_empenhado_brl": round(total_empenhado, 2),
            "total_entregue_pago_brl": round(total_pago, 2),
            "taxa_execucao_pago_pct": taxa_execucao,
        },
        "por_tipo_autor": dict(por_tipo_autor),
        "por_area_tematica": areas_formatadas,
        "por_ano": dict(sorted(por_ano.items())),
        "top_ufs": top_ufs,
        "dicionario": DICIONARIO_ORCAMENTO,
    }


@router.get("/localidade/{localidade}")
def get_emendas_por_localidade(
    localidade: str,
    limit: int = Query(50, ge=1, le=200, description="Quantidade máxima de emendas na lista detalhada"),
):
    """
    Busca todas as emendas destinadas a uma cidade ou Estado (ex: 'MG', 'Belo Horizonte', 'SP', 'Salvador'):
    - Total de dinheiro reservado (empenhado) e entregue (pago)
    - Barra de execução e divisão por áreas (Saúde, Educação, Obras)
    - Lista de emendas com autor humanizado (Deputado individual, Bancada Mineira, etc.)
    """
    termo = _strip_accents(localidade.strip())
    if not termo:
        raise HTTPException(status_code=400, detail="Localidade não pode ser vazia.")

    emendas = _get_emendas_dataset()
    filtradas = []
    total_emp = 0.0
    total_pago = 0.0
    por_area = defaultdict(lambda: {"total_empenhado": 0.0, "total_pago": 0.0, "quantidade": 0})

    for item in emendas:
        loc = _strip_accents(item.get("localidade_destino") or "")
        if termo in loc:
            emp = float(item.get("valor_empenhado") or 0.0)
            pago = float(item.get("valor_pago") or 0.0)
            total_emp += emp
            total_pago += pago

            area = item.get("funcao") or "Outros"
            por_area[area]["total_empenhado"] += emp
            por_area[area]["total_pago"] += pago
            por_area[area]["quantidade"] += 1

            filtradas.append(item)

    if not filtradas:
        raise HTTPException(
            status_code=404,
            detail=f"Nenhuma emenda encontrada para a localidade '{localidade}'.",
        )

    # Detalha as primeiras N emendas com formatação amigável
    itens_detalhados = []
    for item in filtradas[:limit]:
        emp = float(item.get("valor_empenhado") or 0.0)
        pago = float(item.get("valor_pago") or 0.0)
        autor_info = classificar_autor(item.get("politician_name", ""), item.get("tipo_emenda", ""))
        area = item.get("funcao") or "Outros"
        meta_area = DICIONARIO_ORCAMENTO["areas_tematicas"].get(area, {"icone": "🏛️", "rotulo": area})

        itens_detalhados.append(
            {
                "codigo_emenda": item.get("codigo_emenda"),
                "ano": item.get("ano"),
                "area_tematica": area,
                "area_rotulo": meta_area["rotulo"],
                "area_icone": meta_area["icone"],
                "valor_reservado_empenhado": emp,
                "valor_entregue_pago": pago,
                "estagio": "Dinheiro Entregue" if pago > 0 else "Dinheiro Reservado",
                "tipo_recurso": (
                    "Obras e Equipamentos"
                    if "Investimento" in item.get("tipo_emenda", "")
                    else "Dinheiro para o dia a dia"
                ),
                "autor": autor_info,
            }
        )

    taxa = round((total_pago / total_emp * 100.0), 1) if total_emp > 0 else 0.0

    return {
        "localidade_pesquisada": localidade,
        "total_emendas_encontradas": len(filtradas),
        "total_reservado_empenhado_brl": round(total_emp, 2),
        "total_entregue_pago_brl": round(total_pago, 2),
        "taxa_execucao_pct": taxa,
        "divisao_por_area": [
            {
                "area": k,
                "rotulo": DICIONARIO_ORCAMENTO["areas_tematicas"].get(k, {}).get("rotulo", k),
                "icone": DICIONARIO_ORCAMENTO["areas_tematicas"].get(k, {}).get("icone", "🏛️"),
                **v,
            }
            for k, v in por_area.items()
        ],
        "emendas": itens_detalhados,
        "dicionario": DICIONARIO_ORCAMENTO["termos"],
    }


@router.get("/autor/{autor}")
def get_emendas_por_autor(
    autor: str,
    limit: int = Query(50, ge=1, le=200, description="Quantidade máxima de emendas na lista detalhada"),
):
    """
    Busca emendas pelo nome do autor (político, comissão ou bancada):
    - Identifica o perfil institucional (Individual, Bancada, Comissão, Relator)
    - Totais acumulados reservados e entregues
    - Cidades e UFs que receberam os recursos
    """
    termo = _strip_accents(autor.strip())
    if not termo:
        raise HTTPException(status_code=400, detail="Autor não pode ser vazio.")

    emendas = _get_emendas_dataset()
    filtradas = []
    total_emp = 0.0
    total_pago = 0.0
    por_localidade = defaultdict(lambda: {"total_empenhado": 0.0, "total_pago": 0.0, "quantidade": 0})
    por_area = defaultdict(lambda: {"total_empenhado": 0.0, "total_pago": 0.0, "quantidade": 0})

    autor_classificado = None

    for item in emendas:
        nome_autor = _strip_accents(item.get("politician_name") or "")
        cod_autor = str(item.get("autor_codigo") or "")
        if termo in nome_autor or termo == cod_autor:
            emp = float(item.get("valor_empenhado") or 0.0)
            pago = float(item.get("valor_pago") or 0.0)
            total_emp += emp
            total_pago += pago

            loc = item.get("localidade_destino") or "Outras Localidades"
            por_localidade[loc]["total_empenhado"] += emp
            por_localidade[loc]["total_pago"] += pago
            por_localidade[loc]["quantidade"] += 1

            area = item.get("funcao") or "Outros"
            por_area[area]["total_empenhado"] += emp
            por_area[area]["total_pago"] += pago
            por_area[area]["quantidade"] += 1

            if autor_classificado is None:
                autor_classificado = classificar_autor(item.get("politician_name", ""), item.get("tipo_emenda", ""))

            filtradas.append(item)

    if not filtradas:
        raise HTTPException(
            status_code=404,
            detail=f"Nenhuma emenda encontrada para o autor '{autor}'.",
        )

    itens_detalhados = []
    for item in filtradas[:limit]:
        emp = float(item.get("valor_empenhado") or 0.0)
        pago = float(item.get("valor_pago") or 0.0)
        area = item.get("funcao") or "Outros"
        meta_area = DICIONARIO_ORCAMENTO["areas_tematicas"].get(area, {"icone": "🏛️", "rotulo": area})

        itens_detalhados.append(
            {
                "codigo_emenda": item.get("codigo_emenda"),
                "ano": item.get("ano"),
                "localidade_destino": item.get("localidade_destino"),
                "area_tematica": area,
                "area_rotulo": meta_area["rotulo"],
                "area_icone": meta_area["icone"],
                "valor_reservado_empenhado": emp,
                "valor_entregue_pago": pago,
                "estagio": "Dinheiro Entregue" if pago > 0 else "Dinheiro Reservado",
            }
        )

    taxa = round((total_pago / total_emp * 100.0), 1) if total_emp > 0 else 0.0

    return {
        "autor_pesquisado": autor,
        "perfil_autor": autor_classificado,
        "total_emendas_enviadas": len(filtradas),
        "total_reservado_empenhado_brl": round(total_emp, 2),
        "total_entregue_pago_brl": round(total_pago, 2),
        "taxa_execucao_pct": taxa,
        "top_destinos": sorted(
            [{"localidade": k, **v} for k, v in por_localidade.items()],
            key=lambda x: x["total_pago"],
            reverse=True,
        )[:10],
        "por_area_tematica": [
            {
                "area": k,
                "rotulo": DICIONARIO_ORCAMENTO["areas_tematicas"].get(k, {}).get("rotulo", k),
                "icone": DICIONARIO_ORCAMENTO["areas_tematicas"].get(k, {}).get("icone", "🏛️"),
                **v,
            }
            for k, v in por_area.items()
        ],
        "emendas": itens_detalhados,
    }
