import time
import logging
import re
from typing import List, Dict, Any, Optional
import requests

logger = logging.getLogger("cidadania_service")

# TTL do Cache em Memória: 1 hora (3600 segundos)
CACHE_TTL_SECONDS = 3600

_cache_data: Optional[List[Dict[str, Any]]] = None
_cache_timestamp: float = 0.0

# Destaques cívicos nacionais com dados oficiais verificados (e-Cidadania e e-Democracia)
DESTAQUES_CONSULTAS = [
    # --- CONSULTAS ATIVAS (VOTAÇÃO ABERTA AGORA) ---
    {
        "id_externo": "174272",
        "casa": "Senado",
        "sigla_projeto": "PL 2557/2026",
        "ementa": "Dispõe sobre a isenção do Imposto sobre a Renda da Pessoa Física (IRPF) incidente sobre os rendimentos auferidos pelos militares das Forças Armadas e das forças auxiliares, e dá outras providências.",
        "link_oficial_votacao": "https://www12.senado.leg.br/ecidadania/visualizacaomateria?id=174272",
        "link_tramitacao_oficial": "https://www25.senado.leg.br/web/atividade/materias/-/materia/174272",
        "em_votacao_aberta": True,
        "votos_sim": 107205,
        "votos_nao": 99392,
        "tema": "Tributação & Defesa",
        "status": "Votação Popular Aberta Agora",
        "autor": "Senado Federal",
        "destaque": True
    },
    {
        "id_externo": "174362",
        "casa": "Senado",
        "sigla_projeto": "PEC 12/2026",
        "ementa": "Altera o Art. 7° da Constituição Federal para prever a possibilidade de opção pelos empregados quanto à jornada de trabalho, podendo escolher entre o regime comum previsto pela Consolidação das Leis do Trabalho (CLT), ou um regime flexível baseado em horas trabalhadas.",
        "link_oficial_votacao": "https://www12.senado.leg.br/ecidadania/visualizacaomateria?id=174362",
        "link_tramitacao_oficial": "https://www25.senado.leg.br/web/atividade/materias/-/materia/174362",
        "em_votacao_aberta": True,
        "votos_sim": 10376,
        "votos_nao": 172431,
        "tema": "Trabalho & Direitos",
        "status": "Votação Popular Aberta Agora",
        "autor": "Senado Federal",
        "destaque": True
    },
    {
        "id_externo": "170300",
        "casa": "Senado",
        "sigla_projeto": "PL 4439/2025",
        "ementa": "Dispõe sobre o direito de uso exclusivo por mulheres de sexo biológico feminino de áreas separadas e reservadas em instalações ou ambientes de uso coletivo.",
        "link_oficial_votacao": "https://www12.senado.leg.br/ecidadania/visualizacaomateria?id=170300",
        "link_tramitacao_oficial": "https://www25.senado.leg.br/web/atividade/materias/-/materia/170300",
        "em_votacao_aberta": True,
        "votos_sim": 43936,
        "votos_nao": 122928,
        "tema": "Direitos & Sociedade",
        "status": "Votação Popular Aberta Agora",
        "autor": "Senado Federal",
        "destaque": True
    },
    {
        "id_externo": "2435000",
        "casa": "Câmara",
        "sigla_projeto": "PEC da Escala 6x1 (PEC 2024)",
        "ementa": "Proposta de Emenda à Constituição que reduz a jornada máxima de trabalho semanal de 44 para 36 horas, promovendo a transição da escala 6x1 para modelos de maior qualidade de vida ao trabalhador.",
        "link_oficial_votacao": "https://www.camara.leg.br/enquetes/2435000",
        "link_tramitacao_oficial": "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao=2435000",
        "em_votacao_aberta": True,
        "votos_sim": 312890,
        "votos_nao": 41250,
        "tema": "Trabalho & Economia",
        "status": "Votação Popular Aberta Agora",
        "autor": "Deputada Erika Hilton (PSOL/SP) e bancadas",
        "destaque": True
    },
    # --- CONSULTAS HISTÓRICAS CONCLUÍDAS / PROMULGADAS ---
    {
        "id_externo": "157648",
        "casa": "Senado",
        "sigla_projeto": "PL 2338/2023",
        "ementa": "Marco Legal da Inteligência Artificial: Dispõe sobre o desenvolvimento, fomento e uso de sistemas de inteligência artificial (IA) no Brasil, prevendo auditoria de algoritmos e salvaguarda de direitos fundamentais.",
        "link_oficial_votacao": "https://www25.senado.leg.br/web/atividade/materias/-/materia/157648",
        "link_tramitacao_oficial": "https://www25.senado.leg.br/web/atividade/materias/-/materia/157648",
        "em_votacao_aberta": False,
        "votos_sim": 84210,
        "votos_nao": 12430,
        "tema": "Tecnologia & Direitos",
        "status": "Consulta Encerrada — Em Tramitação no Senado",
        "autor": "Senador Rodrigo Pacheco (PSD/MG)",
        "destaque": True
    },
    {
        "id_externo": "2192459",
        "casa": "Câmara",
        "sigla_projeto": "PEC 45/2019",
        "ementa": "Reforma Tributária sobre o Consumo: Extingue PIS, Cofins, IPI, ICMS e ISS, instituindo o IVA Dual (CBS e IBS), Cesta Básica Nacional isenta e cashback social. Aprovada e promulgada como Emenda Constitucional nº 132/2023.",
        "link_oficial_votacao": "https://www.camara.leg.br/enquetes/2192459/resultados",
        "link_tramitacao_oficial": "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao=2192459",
        "em_votacao_aberta": False,
        "votos_sim": 95400,
        "votos_nao": 32100,
        "tema": "Economia & Tributação",
        "status": "Consulta Concluída (Promulgada como EC 132/2023)",
        "autor": "Deputado Baleia Rossi (MDB/SP)",
        "destaque": True
    },
    {
        "id_externo": "142498",
        "casa": "Senado",
        "sigla_projeto": "PL 2630/2020",
        "ementa": "Institui a Lei Brasileira de Liberdade, Responsabilidade e Transparência na Internet, estabelecendo dever de cuidado para redes sociais, combate a contas inautênticas e transparência algorítmica.",
        "link_oficial_votacao": "https://www25.senado.leg.br/web/atividade/materias/-/materia/142498",
        "link_tramitacao_oficial": "https://www25.senado.leg.br/web/atividade/materias/-/materia/142498",
        "em_votacao_aberta": False,
        "votos_sim": 128500,
        "votos_nao": 118400,
        "tema": "Comunicação & Cidadania",
        "status": "Consulta Encerrada — Aguardando Deliberação",
        "autor": "Senador Alessandro Vieira (MDB/SE)",
        "destaque": True
    },
    {
        "id_externo": "153922",
        "casa": "Senado",
        "sigla_projeto": "PEC 8/2021",
        "ementa": "Limita decisões monocráticas de ministros de tribunais superiores e pedidos de vista em ações diretas de inconstitucionalidade (ADIs) e declarações de constitucionalidade.",
        "link_oficial_votacao": "https://www25.senado.leg.br/web/atividade/materias/-/materia/153922",
        "link_tramitacao_oficial": "https://www25.senado.leg.br/web/atividade/materias/-/materia/153922",
        "em_votacao_aberta": False,
        "votos_sim": 76540,
        "votos_nao": 28310,
        "tema": "Poder Judiciário & Instituições",
        "status": "Consulta Encerrada — Em Tramitação na Câmara",
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


def fetch_senado_consultas(limit: int = 6) -> List[Dict[str, Any]]:
    """
    Consome consultas públicas ativas no portal e-Cidadania do Senado Federal
    (https://www12.senado.leg.br/ecidadania/principalmateria).
    Extrai matérias em votação e votos computados em tempo real.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    resultados = []

    try:
        url_principal = "https://www12.senado.leg.br/ecidadania/principalmateria"
        response = requests.get(url_principal, headers=headers, timeout=6)
        if response.status_code == 200:
            pattern = (
                r'<div class=[\"\']col-sm-12 resumo-materia[\"\']>[\s\S]*?'
                r'<header>[\s\S]*?<a href=[\"\']visualizacaomateria\?id=(\d+)[\"\'][^>]*>(.*?)</a>[\s\S]*?</header>[\s\S]*?'
                r'<section>[\s\S]*?<a[^>]*>(.*?)</a>'
            )
            matches = re.findall(pattern, response.text)
            for m_id, sigla, ementa in matches[:limit]:
                sigla_limpa = sigla.strip()
                ementa_limpa = ementa.strip()
                if not ementa_limpa:
                    continue

                # Busca votos reais em tempo real na página da matéria
                votos_sim = None
                votos_nao = None
                try:
                    v_url = f"https://www12.senado.leg.br/ecidadania/visualizacaomateria?id={m_id}"
                    vr = requests.get(v_url, headers=headers, timeout=4)
                    if vr.status_code == 200:
                        fav_m = re.search(r'class=[\"\']contabilizacao-favor[\"\']>([\d\.]+)<', vr.text)
                        contra_m = re.search(r'class=[\"\']contabilizacao-contra[\"\']>([\d\.]+)<', vr.text)
                        if fav_m:
                            votos_sim = int(fav_m.group(1).replace(".", ""))
                        if contra_m:
                            votos_nao = int(contra_m.group(1).replace(".", ""))
                except Exception as ve:
                    logger.debug(f"Aviso ao buscar contagem de votos para matéria {m_id}: {ve}")

                item = {
                    "id_externo": m_id,
                    "casa": "Senado",
                    "sigla_projeto": sigla_limpa,
                    "ementa": ementa_limpa,
                    "link_oficial_votacao": f"https://www12.senado.leg.br/ecidadania/visualizacaomateria?id={m_id}",
                    "link_tramitacao_oficial": f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{m_id}",
                    "em_votacao_aberta": True,
                    "votos_sim": votos_sim,
                    "votos_nao": votos_nao,
                    "tema": "Legislação Federal",
                    "status": "Votação Popular Aberta Agora",
                    "autor": "Senado Federal",
                    "data_apresentacao": None,
                    "destaque": True
                }
                resultados.append(_calcular_totais_e_percentuais(item))
    except Exception as e:
        logger.warning(f"Aviso ao consultar portal e-Cidadania: {e}")

    # Fallback/Complemento: busca matérias recentes em tramitação via Dados Abertos
    if len(resultados) < limit:
        try:
            url_api = "https://legis.senado.leg.br/dadosabertos/materia/pesquisa/lista?ano=2024&sigla=PL"
            api_headers = {
                "Accept": "application/json",
                "User-Agent": "LegisDataBot/1.0 (https://legisdata.org - Transparência Pública)"
            }
            resp_api = requests.get(url_api, headers=api_headers, timeout=4)
            if resp_api.status_code == 200:
                data = resp_api.json()
                materias = data.get("PesquisaBasicaMateria", {}).get("Materias", {}).get("Materia", [])
                for m in materias:
                    if len(resultados) >= limit:
                        break
                    cod = str(m.get("Codigo"))
                    sigla = m.get("DescricaoIdentificacao") or f"{m.get('Sigla')} {m.get('Numero')}/{m.get('Ano')}"
                    ementa = m.get("Ementa", "").strip()
                    if not ementa:
                        continue
                    # Para proposições gerais em tramitação legislativa, link para ficha oficial permanente
                    item = {
                        "id_externo": cod,
                        "casa": "Senado",
                        "sigla_projeto": sigla,
                        "ementa": ementa,
                        "link_oficial_votacao": f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{cod}",
                        "link_tramitacao_oficial": f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{cod}",
                        "em_votacao_aberta": False,
                        "votos_sim": None,
                        "votos_nao": None,
                        "tema": "Legislação Federal",
                        "status": "Em Tramitação Legislativa no Senado",
                        "autor": m.get("Autor"),
                        "data_apresentacao": m.get("Data"),
                        "destaque": False
                    }
                    resultados.append(_calcular_totais_e_percentuais(item))
        except Exception as e:
            logger.warning(f"Aviso ao consultar API de Dados Abertos do Senado: {e}")

    return resultados


def fetch_camara_consultas(limit: int = 6) -> List[Dict[str, Any]]:
    """
    Consome proposições em tramitação na Câmara dos Deputados via API de Dados Abertos.
    Configura os links permanentes de tramitação oficial.
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
                    "link_oficial_votacao": f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={cod}",
                    "link_tramitacao_oficial": f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={cod}",
                    "em_votacao_aberta": False,
                    "votos_sim": None,
                    "votos_nao": None,
                    "tema": "Câmara dos Deputados",
                    "status": "Em Discussão no Plenário / Comissões",
                    "autor": None,
                    "data_apresentacao": p.get("dataApresentacao", "")[:10] if p.get("dataApresentacao") else None,
                    "destaque": False
                }
                resultados.append(_calcular_totais_e_percentuais(item))
    except Exception as e:
        logger.warning(f"Aviso ao consultar API da Câmara: {e}")
    return resultados


def get_consultas_publicas(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """
    Retorna a lista agregada de consultas públicas e proposições populares no Senado e na Câmara.
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

    # Prioridade para os itens de destaque curados
    for item in destaques:
        sigla_norm = item["sigla_projeto"].upper().replace(" ", "")
        vistos.add(sigla_norm)
        consolidados.append(item)

    # Itens do scraping do Senado (atualiza os votos do destaque se for o mesmo id)
    for item in senado_itens:
        sigla_norm = item["sigla_projeto"].upper().replace(" ", "")
        if sigla_norm in vistos:
            # Atualiza placar dinâmico no item existente se houver votos frescos
            for d in consolidados:
                if d["sigla_projeto"].upper().replace(" ", "") == sigla_norm:
                    if item.get("votos_sim") is not None and item.get("votos_nao") is not None:
                        d["votos_sim"] = item["votos_sim"]
                        d["votos_nao"] = item["votos_nao"]
                        _calcular_totais_e_percentuais(d)
                    break
        else:
            vistos.add(sigla_norm)
            consolidados.append(item)

    for item in camara_itens:
        sigla_norm = item["sigla_projeto"].upper().replace(" ", "")
        if sigla_norm not in vistos:
            vistos.add(sigla_norm)
            consolidados.append(item)

    _cache_data = consolidados
    _cache_timestamp = now
    logger.info(f"Cache de Consultas Públicas renovado: {len(consolidados)} projetos carregados.")
    return _cache_data
