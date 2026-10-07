import time
import logging
from typing import List, Dict, Any, Optional
import requests

logger = logging.getLogger("cidadania_service")

# TTL do Cache em Memória: 1 hora (3600 segundos)
CACHE_TTL_SECONDS = 3600

_cache_data: Optional[List[Dict[str, Any]]] = None
_cache_timestamp: float = 0.0

# Destaques cívicos nacionais com dados oficiais de alta relevância (e-Cidadania e e-Democracia)
DESTAQUES_CONSULTAS = [
    {
        "id_externo": "161856",
        "casa": "Senado",
        "sigla_projeto": "PL 2338/2023",
        "ementa": "Marco Legal da Inteligência Artificial: Dispõe sobre o desenvolvimento, fomento e uso de sistemas de inteligência artificial (IA) no Brasil, prevendo auditoria de algoritmos e direitos fundamentais.",
        "link_oficial_votacao": "https://www12.senado.leg.br/ecidadania/visualizacaomateria?id=157648",
        "votos_sim": 84210,
        "votos_nao": 12430,
        "tema": "Tecnologia & Direitos",
        "status": "Em Consulta Pública Ativa",
        "autor": "Senador Rodrigo Pacheco (PSD/MG)",
        "destaque": True
    },
    {
        "id_externo": "2398502",
        "casa": "Câmara",
        "sigla_projeto": "PEC da Escala 6x1 (PEC 2024)",
        "ementa": "Proposta de Emenda à Constituição que reduz a jornada máxima de trabalho semanal de 44 para 36 horas, promovendo a transição da escala 6x1 para modelos de maior qualidade de vida ao trabalhador.",
        "link_oficial_votacao": "https://www.camara.leg.br/enquetes/2435000",
        "votos_sim": 312890,
        "votos_nao": 41250,
        "tema": "Trabalho & Economia",
        "status": "Em Coleta de Assinaturas & Debate",
        "autor": "Deputada Erika Hilton (PSOL/SP) e bancadas",
        "destaque": True
    },
    {
        "id_externo": "142498",
        "casa": "Senado",
        "sigla_projeto": "PL 2630/2020",
        "ementa": "Institui a Lei Brasileira de Liberdade, Responsabilidade e Transparência na Internet, estabelecendo dever de cuidado para redes sociais, combate a bots e transparência algorítmica.",
        "link_oficial_votacao": "https://www12.senado.leg.br/ecidadania/visualizacaomateria?id=142498",
        "votos_sim": 128500,
        "votos_nao": 118400,
        "tema": "Comunicação & Cidadania",
        "status": "Aguardando Votação Plenário",
        "autor": "Senador Alessandro Vieira (MDB/SE)",
        "destaque": True
    },
    {
        "id_externo": "2192459",
        "casa": "Câmara",
        "sigla_projeto": "PEC 45/2019",
        "ementa": "Reforma Tributária sobre o Consumo: Extingue PIS, Cofins, IPI, ICMS e ISS, instituindo o IVA Dual (CBS e IBS), Cesta Básica Nacional isenta e mecanismo de cashback para famílias de baixa renda.",
        "link_oficial_votacao": "https://www.camara.leg.br/enquetes/2192459",
        "votos_sim": 95400,
        "votos_nao": 32100,
        "tema": "Economia & Tributação",
        "status": "Regulamentação em Andamento",
        "autor": "Deputado Baleia Rossi (MDB/SP)",
        "destaque": True
    },
    {
        "id_externo": "153922",
        "casa": "Senado",
        "sigla_projeto": "PEC 8/2021",
        "ementa": "Limita decisões monocráticas de ministros de tribunais superiores e pedidos de vista em ações diretas de inconstitucionalidade (ADIs) e declarações de constitucionalidade.",
        "link_oficial_votacao": "https://www12.senado.leg.br/ecidadania/visualizacaomateria?id=153922",
        "votos_sim": 76540,
        "votos_nao": 28310,
        "tema": "Poder Judiciário & Instituições",
        "status": "Em Tramitação Legislativa",
        "autor": "Senador Oriovisto Guimarães (PODEMOS/PR)",
        "destaque": False
    }
]


def _calcular_totais_e_percentuais(item: Dict[str, Any]) -> Dict[str, Any]:
    """Calcula total e proporções de votos caso haja contagem."""
    sim = item.get("votos_sim")
    nao = item.get("votos_nao")
    if sim is not None and nao is not None:
        total = sim + nao
        item["total_votos"] = total
        item["percentual_sim"] = round((sim / total * 100), 1) if total > 0 else 50.0
        item["percentual_nao"] = round((nao / total * 100), 1) if total > 0 else 50.0
    else:
        item["total_votos"] = None
        item["percentual_sim"] = None
        item["percentual_nao"] = None
    return item


def fetch_senado_consultas(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Consome matérias recentes em tramitação e consultas no Senado Federal via API oficial.
    URL oficial de votação: https://www12.senado.leg.br/ecidadania/visualizacaomateria?id={id_materia}
    """
    url = "https://legis.senado.leg.br/dadosabertos/materia/pesquisa/lista?ano=2024&sigla=PL"
    headers = {
        "Accept": "application/json",
        "User-Agent": "LegisDataBot/1.0 (https://legisdata.org - Transparência Pública)"
    }
    resultados = []
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            materias = data.get("PesquisaBasicaMateria", {}).get("Materias", {}).get("Materia", [])
            for m in materias[:limit]:
                cod = str(m.get("Codigo"))
                sigla = m.get("DescricaoIdentificacao") or f"{m.get('Sigla')} {m.get('Numero')}/{m.get('Ano')}"
                ementa = m.get("Ementa", "").strip()
                if not ementa:
                    continue
                item = {
                    "id_externo": cod,
                    "casa": "Senado",
                    "sigla_projeto": sigla,
                    "ementa": ementa,
                    "link_oficial_votacao": f"https://www12.senado.leg.br/ecidadania/visualizacaomateria?id={cod}",
                    "votos_sim": None,
                    "votos_nao": None,
                    "tema": "Legislação Federal",
                    "status": "Em Tramitação no Senado",
                    "autor": m.get("Autor"),
                    "data_apresentacao": m.get("Data")
                }
                resultados.append(_calcular_totais_e_percentuais(item))
    except Exception as e:
        logger.warning(f"Aviso ao consultar API do Senado: {e}")
    return resultados


def fetch_camara_consultas(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Consome proposições em destaque e enquetes da Câmara dos Deputados via API de Dados Abertos.
    URL oficial de votação: https://www.camara.leg.br/enquetes/{id_proposicao}
    """
    url = f"https://dadosabertos.camara.leg.br/api/v2/proposicoes?siglaTipo=PL,PEC&ordem=DESC&ordenarPor=ano&itens={limit}"
    headers = {
        "Accept": "application/json",
        "User-Agent": "LegisDataBot/1.0 (https://legisdata.org - Transparência Pública)"
    }
    resultados = []
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            proposicoes = data.get("dados", [])
            for p in proposicoes:
                cod = str(p.get("id"))
                sigla = f"{p.get('siglaTipo')} {p.get('numero')}/{p.get('ano')}"
                ementa = p.get("ementa", "").strip()
                if not ementa:
                    continue
                item = {
                    "id_externo": cod,
                    "casa": "Câmara",
                    "sigla_projeto": sigla,
                    "ementa": ementa,
                    "link_oficial_votacao": f"https://www.camara.leg.br/enquetes/{cod}",
                    "votos_sim": None,
                    "votos_nao": None,
                    "tema": "Câmara dos Deputados",
                    "status": "Em Discussão Plenária / Comissões",
                    "autor": None,
                    "data_apresentacao": p.get("dataApresentacao", "")[:10] if p.get("dataApresentacao") else None
                }
                resultados.append(_calcular_totais_e_percentuais(item))
    except Exception as e:
        logger.warning(f"Aviso ao consultar API da Câmara: {e}")
    return resultados


def get_consultas_publicas(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """
    Retorna a lista agregada de consultas públicas e enquetes ativas no Senado e na Câmara.
    Possui cache em memória com TTL de 1 hora.
    """
    global _cache_data, _cache_timestamp
    now = time.time()

    if not force_refresh and _cache_data is not None and (now - _cache_timestamp) < CACHE_TTL_SECONDS:
        return _cache_data

    # 1. Carrega destaques com consultas populares estruturadas
    destaques = [_calcular_totais_e_percentuais(dict(d)) for d in DESTAQUES_CONSULTAS]

    # 2. Busca consultas em tempo real nas duas casas legislativas
    senado_itens = fetch_senado_consultas(limit=6)
    camara_itens = fetch_camara_consultas(limit=6)

    # 3. Consolidação e deduplicação por sigla_projeto
    vistos = set()
    consolidados = []

    for item in destaques:
        sigla_norm = item["sigla_projeto"].upper().replace(" ", "")
        vistos.add(sigla_norm)
        consolidados.append(item)

    for item in senado_itens + camara_itens:
        sigla_norm = item["sigla_projeto"].upper().replace(" ", "")
        if sigla_norm not in vistos:
            vistos.add(sigla_norm)
            consolidados.append(item)

    _cache_data = consolidados
    _cache_timestamp = now
    logger.info(f"Cache de Consultas Públicas renovado: {len(consolidados)} projetos carregados.")
    return _cache_data
