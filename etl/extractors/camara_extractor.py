"""
Extrator de Dados Abertos da Câmara dos Deputados (API v2)
Documentação oficial: https://dadosabertos.camara.leg.br/api/v2/
Coleta de Proposições, Setorização Temática e Contagem de Autoria.
"""

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from etl.config import PROCESSED_DATA_DIR, RAW_DATA_DIR
from etl.utils.http_client import HttpClient, HttpError
from etl.utils.io_utils import atomic_write_json, write_json_if_valid

logger = logging.getLogger("CamaraExtractor")

BASE_URL = "https://dadosabertos.camara.leg.br/api/v2"

# Mapeamento oficial dos Códigos de Tema da Câmara para Setores Padronizados
MAPA_TEMAS_SETORES = {
    56: "Saúde",
    46: "Educação",
    57: "Segurança Pública",
    43: "Segurança Pública",
    40: "Economia & Finanças",
    70: "Economia & Finanças",
    72: "Homenagens & Datas Comemorativas",
    58: "Trabalho & Previdência",
    52: "Trabalho & Previdência",
    48: "Meio Ambiente & Clima",
    44: "Direitos Humanos & Minorias",
    62: "Tecnologia & Inovação",
    37: "Tecnologia & Inovação",
    61: "Infraestrutura & Cidades",
    41: "Infraestrutura & Cidades",
    64: "Agricultura & Agropecuária",
    34: "Administração & Justiça",
    76: "Administração & Justiça",
}


def classificar_setor_por_texto(titulo: str, ementa: str, tema_padrao: Optional[str] = None) -> str:
    """Classifica o setor com base no conteúdo textual caso o codTema não esteja presente."""
    t = f"{titulo} {ementa}".lower()
    if any(k in t for k in ["homenagem", "comemorativ", "dia nacional", "patrono", "capital nacional de", "denomina"]):
        return "Homenagens & Datas Comemorativas"
    if any(
        k in t for k in ["saúde", "sus", "hospital", "médic", "medicamento", "enferm", "vacina", "psicolog", "doença"]
    ):
        return "Saúde"
    if any(k in t for k in ["escola", "educa", "ensino", "professor", "estudante", "universidade", "bolsa de estudo"]):
        return "Educação"
    if any(
        k in t
        for k in ["segurança", "polícia", "crime", "penal", "porte de arma", "tráfico", "pena", "prisão", "presídio"]
    ):
        return "Segurança Pública"
    if any(
        k in t
        for k in [
            "imposto",
            "tribut",
            "fiscal",
            "orçamento",
            "banco",
            "crédito",
            "reforma tributária",
            "taxa",
            "receita",
            "finança",
            "dívida",
        ]
    ):
        return "Economia & Finanças"
    if any(
        k in t for k in ["trabalho", "clt", "salário", "emprego", "previdência", "inss", "aposentad", "trabalhador"]
    ):
        return "Trabalho & Previdência"
    if any(
        k in t
        for k in [
            "meio ambiente",
            "clima",
            "floresta",
            "carbono",
            "desmatamento",
            "fauna",
            "sustentável",
            "amazônia",
            "cerrado",
        ]
    ):
        return "Meio Ambiente & Clima"
    if any(
        k in t
        for k in ["indígena", "mulher", "direitos humanos", "discrimina", "racial", "lgbt", "igualdade", "quilombola"]
    ):
        return "Direitos Humanos & Minorias"
    if any(
        k in t
        for k in ["internet", "tecnologia", "inteligência artificial", "software", "comunicação", "digital", "inovação"]
    ):
        return "Tecnologia & Inovação"
    if any(
        k in t for k in ["rodovia", "transporte", "trânsito", "ferrovia", "porto", "aeroporto", "obras", "saneamento"]
    ):
        return "Infraestrutura & Cidades"
    if any(k in t for k in ["agricultura", "pecuária", "safra", "agro", "rural", "pesca", "produtor rural"]):
        return "Agricultura & Agropecuária"
    if any(
        k in t
        for k in [
            "eleitoral",
            "partido",
            "mandato",
            "servidor público",
            "licitação",
            "tribunal",
            "administração pública",
        ]
    ):
        return "Administração & Justiça"

    return tema_padrao or "Administração & Cidadania"


# Matérias estruturantes buscadas por (tipo, número, ano) — nunca apenas pelo número.
MATERIAS_EMBLEMATICAS = [
    {
        "tipo": "PLP",
        "numero": 93,
        "ano": 2023,
        "titulo": "Novo Arcabouço Fiscal",
        "reforma": True,
        "tema": "Economia & Finanças",
        "executivo": True,
    },
    {
        "tipo": "PEC",
        "numero": 45,
        "ano": 2019,
        "titulo": "Reforma Tributária do Consumo",
        "reforma": True,
        "tema": "Economia & Finanças",
        "executivo": False,
    },
    {
        "tipo": "MPV",
        "numero": 1172,
        "ano": 2023,
        "titulo": "Reajuste do Salário Mínimo e Isenção do IRPF",
        "reforma": True,
        "tema": "Trabalho & Previdência",
        "executivo": True,
    },
    {
        "tipo": "MPV",
        "numero": 1184,
        "ano": 2023,
        "titulo": "Tributação de Fundos Exclusivos e Offshores",
        "reforma": True,
        "tema": "Economia & Finanças",
        "executivo": True,
    },
    {
        "tipo": "PL",
        "numero": 1085,
        "ano": 2023,
        "titulo": "Igualdade Salarial entre Homens e Mulheres",
        "reforma": True,
        "tema": "Trabalho & Previdência",
        "executivo": True,
    },
    {
        "tipo": "PL",
        "numero": 2685,
        "ano": 2023,
        "titulo": "Desenrola Brasil e Teto dos Juros do Rotativo",
        "reforma": True,
        "tema": "Economia & Finanças",
        "executivo": False,
    },
    {
        "tipo": "PL",
        "numero": 3626,
        "ano": 2023,
        "titulo": "Tributação e Regulação de Apostas Esportivas (Bets)",
        "reforma": True,
        "tema": "Economia & Finanças",
        "executivo": True,
    },
    {
        "tipo": "PL",
        "numero": 334,
        "ano": 2023,
        "titulo": "Prorrogação da Desoneração da Folha de Pagamentos",
        "reforma": True,
        "tema": "Economia & Finanças",
        "executivo": False,
    },
    {
        "tipo": "PL",
        "numero": 2384,
        "ano": 2023,
        "titulo": "Retomada do Voto de Qualidade no CARF",
        "reforma": True,
        "tema": "Economia & Finanças",
        "executivo": True,
    },
    {
        "tipo": "PL",
        "numero": 490,
        "ano": 2007,
        "titulo": "Marco Temporal de Terras Indígenas",
        "reforma": True,
        "tema": "Direitos Humanos & Minorias",
        "executivo": False,
    },
]

# Descrições de votações que NÃO são a votação de mérito da matéria (requerimentos, destaques, emendas isoladas,
# redação final...). "Mantido o texto" é o resultado de um DESTAQUE, não da matéria.
_NAO_MERITO = re.compile(
    r"requerimento|destaque|mantido o texto|emenda|subemenda|reda[cç][aã]o final|prefer[eê]ncia|adiamento|"
    r"retirada de pauta|encerramento da discuss|invers[aã]o de pauta|urg[eê]ncia",
    re.IGNORECASE,
)
# Resultado sobre o objeto principal: "Aprovado o Substitutivo...", "Aprovada a Proposta de Emenda...",
# "Rejeitado o Projeto...". Vem ANTES de _NAO_MERITO porque descrições de mérito citam "ressalvados os destaques".
_MERITO = re.compile(
    r"^\s*(aprovad[oa]s?|rejeitad[oa]s?)\s+(o|a)?\s*(substitutivo|projeto|proposta|medida provis[oó]ria|texto[- ]base)",
    re.IGNORECASE,
)
_APROVADA = re.compile(r"\baprovad[oa]s?\b", re.IGNORECASE)
_REJEITADA = re.compile(r"\brejeitad[oa]s?\b|\bdesaprovad[oa]s?\b", re.IGNORECASE)

FONTE_AUTORIA_CAMARA = "API Dados Abertos da Câmara (/proposicoes/{id}/autores)"
TTL_CACHE_DEPUTADOS_DIAS = 7


def chave_materia(tipo: Any, numero: Any, ano: Any) -> Tuple[str, int, int]:
    """Chave canônica (SIGLA, número, ano) de uma proposição."""
    try:
        return (str(tipo or "").upper().strip(), int(numero), int(ano))
    except (TypeError, ValueError):
        return ("", 0, 0)


CHAVES_EMBLEMATICAS = {chave_materia(m["tipo"], m["numero"], m["ano"]) for m in MATERIAS_EMBLEMATICAS}


def interpretar_aprovacao(votacao: Dict[str, Any]) -> Optional[bool]:
    """
    Resultado da votação: usa o campo estruturado `aprovacao` (0/1) quando existir; na falta dele,
    só conclui a partir da descrição se ela não for de requerimento/destaque. Caso contrário devolve None
    ("indeterminado") — nunca presume aprovação por substring solta.
    """
    estruturado = votacao.get("aprovacao")
    if estruturado in (0, 1):
        return bool(estruturado)
    desc = votacao.get("descricao") or ""
    if not _MERITO.search(desc) and _NAO_MERITO.search(desc):
        return None
    if _REJEITADA.search(desc):
        return False
    if _APROVADA.search(desc):
        return True
    return None


def classificar_voto(tipo_voto_raw: Optional[str]) -> Optional[str]:
    """Mapeia o tipoVoto da API para VotoOpcaoEnum. None = valor desconhecido (não presumir)."""
    raw = (tipo_voto_raw or "").strip().upper()
    if not raw:
        return "AUSENTE"
    if "ART" in raw and "17" in raw:
        return "ARTIGO_17"
    if raw.startswith("SIM"):
        return "SIM"
    if raw.startswith("NÃO") or raw.startswith("NAO"):
        return "NAO"
    if raw.startswith("ABST"):
        return "ABSTENCAO"
    if raw.startswith("OBST"):
        return "OBSTRUCAO"
    return None


def deduplicar_deputados(deputados: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Mantém um registro por camara_id (o último vence, preservando campos já enriquecidos)."""
    por_id: Dict[Any, Dict[str, Any]] = {}
    for d in deputados:
        cid = d.get("camara_id")
        if cid is None:
            continue
        anterior = por_id.get(cid, {})
        merged = {**anterior, **{k: v for k, v in d.items() if v is not None}}
        por_id[cid] = merged
    return list(por_id.values())


class CamaraExtractor:
    """Consome os endpoints de deputados, proposições, temas e votações da Câmara dos Deputados."""

    def __init__(self, raw_cache_dir=RAW_DATA_DIR, request_delay: float = 0.15, http: Optional[HttpClient] = None):
        self.raw_dir = raw_cache_dir
        self.delay = request_delay
        # Um único limitador compartilhado entre todas as threads evita rajadas que geram 429.
        self.http = http or HttpClient(timeout=25.0, max_retries=4, min_interval=request_delay)

    def _get_json(self, url: str) -> Optional[Dict[str, Any]]:
        """GET com retry/backoff (429/5xx). Devolve None se a requisição falhar de forma definitiva."""
        try:
            return self.http.get_json(url)
        except HttpError as exc:
            logger.warning("Falha ao consultar %s: %s", url, exc)
            return None

    def fetch_deputados(self, legislatura: int = 57, limite_total: Optional[int] = None) -> List[Dict[str, Any]]:
        """Extrai lista completa dos deputados da legislatura, sem duplicatas por camara_id."""
        logger.info(f"Iniciando extração de deputados da Legislatura {legislatura}...")
        pagina = 1
        itens_por_pagina = 100
        todos_deputados: List[Dict[str, Any]] = []

        while True:
            url = f"{BASE_URL}/deputados?idLegislatura={legislatura}&pagina={pagina}&itens={itens_por_pagina}&ordem=ASC&ordenarPor=nome"
            data = self._get_json(url)
            if not data or "dados" not in data or not data["dados"]:
                break

            for d in data["dados"]:
                todos_deputados.append(
                    {
                        "camara_id": d["id"],
                        "nome_eleitoral": d.get("nome"),
                        "partido_sigla": d.get("siglaPartido"),
                        "uf": d.get("siglaUf"),
                        "foto_url": d.get("urlFoto"),
                        "email": d.get("email"),
                        "id_legislatura": d.get("idLegislatura"),
                    }
                )

            if limite_total and len(todos_deputados) >= limite_total:
                todos_deputados = todos_deputados[:limite_total]
                break

            links = {link.get("rel"): link.get("href") for link in data.get("links", [])}
            if "next" not in links:
                break
            pagina += 1

        deduplicados = deduplicar_deputados(todos_deputados)
        logger.info(
            f"Total de {len(deduplicados)} deputados únicos extraídos da Câmara ({len(todos_deputados)} registros brutos)."
        )
        return deduplicados

    def fetch_detalhes_deputado(self, camara_id: int) -> Dict[str, Any]:
        """
        Dados cadastrais reais de um deputado (endpoint de detalhe): nome civil, naturalidade e gabinete.
        Campos ausentes na API ficam ausentes aqui — nunca são inventados.
        """
        data = self._get_json(f"{BASE_URL}/deputados/{camara_id}")
        if not data or not data.get("dados"):
            return {}

        dados = data["dados"]
        status = dados.get("ultimoStatus") or {}
        gab = status.get("gabinete") or {}

        predio = gab.get("predio")
        sala = gab.get("sala") or gab.get("nome")
        sala_fmt = f"Anexo {predio}, Gabinete {sala}" if predio and sala else (f"Gabinete {sala}" if sala else None)

        tel = gab.get("telefone")
        tel_fmt = f"(61) {tel}" if tel and not str(tel).startswith("(") else tel

        detalhes = {
            "email": gab.get("email") or status.get("email") or dados.get("email"),
            "gabinete_sala": sala_fmt,
            "gabinete_telefone": tel_fmt,
            "nome_civil": dados.get("nomeCivil"),
            "sexo": dados.get("sexo"),
            "data_nascimento": dados.get("dataNascimento"),
            "uf_nascimento": dados.get("ufNascimento"),
            "municipio_nascimento": dados.get("municipioNascimento"),
        }
        return {k: v for k, v in detalhes.items() if v}

    # Compatibilidade com o nome anterior.
    fetch_detalhes_gabinete = fetch_detalhes_deputado

    def enriquecer_deputados(self, deputados: List[Dict[str, Any]], max_workers: int = 6) -> List[Dict[str, Any]]:
        """Preenche contato/gabinete/nome civil/naturalidade a partir da API de detalhe (somente quem ainda não tem)."""
        pendentes = [d for d in deputados if not d.get("nome_civil") or not d.get("_detalhado")]
        if not pendentes:
            return deputados

        logger.info(f"Enriquecendo {len(pendentes)} deputados com dados de detalhe da API...")
        por_id = {d["camara_id"]: d for d in deputados}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futuros = {executor.submit(self.fetch_detalhes_deputado, d["camara_id"]): d["camara_id"] for d in pendentes}
            for futuro in as_completed(futuros):
                cid = futuros[futuro]
                try:
                    det = futuro.result()
                except Exception as exc:  # falha isolada não derruba a extração
                    logger.warning("Detalhe do deputado %s falhou: %s", cid, exc)
                    continue
                if det:
                    por_id[cid].update(det)
                    por_id[cid]["_detalhado"] = True
        return deputados

    def fetch_autores_proposicao(self, proposicao_id: int) -> Dict[str, Any]:
        """
        Busca o primeiro autor da proposição. Falha da API devolve `falha_api=True` com autor None —
        jamais um autor presumido (antes, erro/429 virava "Poder Executivo").
        """
        data = self._get_json(f"{BASE_URL}/proposicoes/{proposicao_id}/autores")
        if data is None:
            return {"autor_nome": None, "autor_camara_id": None, "autor_partido": None, "falha_api": True}
        autores = data.get("dados") or []
        if not autores:
            return {"autor_nome": None, "autor_camara_id": None, "autor_partido": None, "falha_api": False}

        primeiro = autores[0]
        uri = primeiro.get("uri") or ""
        camara_id = None
        if "/deputados/" in uri:
            try:
                camara_id = int(uri.split("/deputados/")[-1])
            except (ValueError, TypeError):
                camara_id = None

        return {
            "autor_nome": primeiro.get("nome"),
            "autor_camara_id": camara_id,
            "autor_partido": primeiro.get("siglaPartido"),
            "total_assinaturas": len(autores),
            "falha_api": False,
        }

    def _salvar_checkpoint(self, arquivo, proposicoes_dict: Dict[int, Dict[str, Any]]) -> None:
        try:
            atomic_write_json(arquivo, list(proposicoes_dict.values()), indent=None)
        except OSError as exc:
            logger.warning("Não foi possível gravar checkpoint %s: %s", arquivo, exc)

    @staticmethod
    def _registro_proposicao(p: Dict[str, Any], setor: str, data_padrao: Optional[str] = None) -> Dict[str, Any]:
        pid = p["id"]
        data_apr = (p.get("dataApresentacao") or "")[:10] or None
        return {
            "camara_id": pid,
            "tipo": p.get("siglaTipo"),
            "numero": p.get("numero"),
            "ano": p.get("ano"),
            "titulo": f"{p.get('siglaTipo')} {p.get('numero')}/{p.get('ano')}",
            "ementa": p.get("ementa") or "",
            "area_tematica": setor,
            "data_apresentacao": data_apr or data_padrao,
            "is_reforma_estrutural": False,
            "iniciativa_executivo": False,
            "autor_nome": None,
            "autor_camara_id": None,
            "autor_partido": None,
            "url_oficial": f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={pid}",
        }

    def fetch_proposicoes_ampliadas(
        self, deputados_map: Optional[Dict[int, Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Extrai um catálogo amplo de proposições legislativas (1995-presente), cruzando eixos setoriais,
        autoria real (endpoint /autores) e grandes reformas.
        """
        logger.info("Iniciando extração ampliada de proposições...")
        proposicoes_dict: Dict[int, Dict[str, Any]] = {}

        # 1. Matérias estruturantes — buscadas por (tipo, número, ano)
        for m in MATERIAS_EMBLEMATICAS:
            url_busca = f"{BASE_URL}/proposicoes?siglaTipo={m['tipo']}&numero={m['numero']}&ano={m['ano']}"
            resp = self._get_json(url_busca)
            if resp and resp.get("dados"):
                item = resp["dados"][0]
                pid = item["id"]
                reg = self._registro_proposicao(item, m["tema"], data_padrao=None)
                reg.update(
                    {
                        "titulo": m["titulo"],
                        "is_reforma_estrutural": m["reforma"],
                        "iniciativa_executivo": m["executivo"],
                    }
                )
                proposicoes_dict[pid] = reg

        # 2. Checkpoint restaurado (escrito de forma atômica)
        checkpoint_camara_file = self.raw_dir / "checkpoint_camara_proposicoes.json"
        if checkpoint_camara_file.exists():
            try:
                with open(checkpoint_camara_file, "r", encoding="utf-8") as f:
                    cached_props = json.load(f)
                for cp in cached_props:
                    proposicoes_dict.setdefault(cp["camara_id"], cp)
                logger.info(f"Checkpoint restaurado: {len(cached_props)} proposições recuperadas do disco.")
            except (OSError, ValueError, KeyError) as ex:
                logger.warning(f"Checkpoint da Câmara ilegível, ignorando: {ex}")

        eras_historicas = [
            ("Lula III (2023-2026)", [2023, 2024, 2025, 2026], 10),
            ("Jair Bolsonaro (2019-2022)", [2019, 2020, 2021, 2022], 3),
            ("Dilma Rousseff / Michel Temer (2011-2018)", [2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018], 3),
            ("Lula I e II (2003-2010)", [2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010], 3),
            ("Fernando Henrique Cardoso - FHC (1995-2002)", [1995, 1996, 1997, 1998, 1999, 2000, 2001, 2002], 3),
        ]

        for era_nome, anos_bloco, max_pags in eras_historicas:
            anos_str = ",".join(str(a) for a in anos_bloco)
            logger.info(f"[Histórico] Extraindo ciclo: {era_nome}...")
            for pagina in range(1, max_pags + 1):
                url_lote = f"{BASE_URL}/proposicoes?ano={anos_str}&siglaTipo=PL,PEC,PLP,MPV&itens=100&pagina={pagina}&ordem=DESC&ordenarPor=id"
                resp = self._get_json(url_lote)
                if not resp or not resp.get("dados"):
                    break
                for p in resp["dados"]:
                    pid = p["id"]
                    if pid not in proposicoes_dict:
                        setor = classificar_setor_por_texto(
                            f"{p.get('siglaTipo')} {p.get('numero')}", p.get("ementa", "")
                        )
                        proposicoes_dict[pid] = self._registro_proposicao(p, setor, data_padrao=None)
                self._salvar_checkpoint(checkpoint_camara_file, proposicoes_dict)

        # 3. Busca setorial complementar por tema
        setores_alvo = [
            (56, "Saúde"),
            (46, "Educação"),
            (57, "Segurança Pública"),
            (40, "Economia & Finanças"),
            (72, "Homenagens & Datas Comemorativas"),
            (58, "Trabalho & Previdência"),
            (48, "Meio Ambiente & Clima"),
            (44, "Direitos Humanos & Minorias"),
            (62, "Tecnologia & Inovação"),
            (61, "Infraestrutura & Cidades"),
            (64, "Agricultura & Agropecuária"),
            (34, "Administração & Justiça"),
        ]
        for cod_tema, setor_nome in setores_alvo:
            url = f"{BASE_URL}/proposicoes?ano=2023,2024,2025,2026&siglaTipo=PL,PLP,PEC&codTema={cod_tema}&itens=30&ordem=DESC&ordenarPor=id"
            resp = self._get_json(url)
            if not resp or not resp.get("dados"):
                continue
            for p in resp["dados"]:
                if p["id"] not in proposicoes_dict:
                    proposicoes_dict[p["id"]] = self._registro_proposicao(p, setor_nome, data_padrao=None)

        # 4. Descoberta por deputado (idDeputadoAutor também devolve proposições em que ele é COAUTOR).
        #    Por isso aqui só se descobrem proposições: a autoria é decidida na etapa 5, pelo endpoint /autores.
        if deputados_map:
            logger.info("Descobrindo proposições adicionais por deputado (autoria será resolvida em /autores)...")
            for dep_id in list(deputados_map)[:120]:
                url_autor = f"{BASE_URL}/proposicoes?idDeputadoAutor={dep_id}&ano=2023,2024,2025,2026&siglaTipo=PL,PLP,PEC&itens=15&ordem=DESC&ordenarPor=id"
                resp = self._get_json(url_autor)
                if not resp or not resp.get("dados"):
                    continue
                for p in resp["dados"]:
                    if p["id"] not in proposicoes_dict:
                        setor = classificar_setor_por_texto(
                            f"{p.get('siglaTipo')} {p.get('numero')}", p.get("ementa", "")
                        )
                        proposicoes_dict[p["id"]] = self._registro_proposicao(p, setor, data_padrao=None)

        # 5. Autoria real via /autores para quem ainda não tem autor resolvido
        pendentes = [pid for pid, p in proposicoes_dict.items() if not p.get("autor_nome")]
        logger.info(f"Resolvendo autoria de {len(pendentes)} proposições via /autores...")

        with ThreadPoolExecutor(max_workers=6) as executor:
            futuros = {executor.submit(self.fetch_autores_proposicao, pid): pid for pid in pendentes}
            for futuro in as_completed(futuros):
                pid = futuros[futuro]
                try:
                    aut = futuro.result()
                except Exception as ex:
                    logger.warning("Autoria da proposição %s falhou: %s", pid, ex)
                    continue
                if aut.get("falha_api") or not aut.get("autor_nome"):
                    continue  # mantém sem autor: desconhecido é melhor que errado
                cid = aut.get("autor_camara_id")
                nome_aut = aut["autor_nome"]
                partido_aut = aut.get("autor_partido")
                if deputados_map and cid and cid in deputados_map:
                    nome_aut = deputados_map[cid].get("nome_eleitoral") or nome_aut
                    partido_aut = deputados_map[cid].get("partido_sigla") or partido_aut
                registro = proposicoes_dict[pid]
                registro["autor_nome"] = nome_aut
                registro["autor_camara_id"] = cid
                registro["autor_partido"] = partido_aut
                registro["autor_fonte"] = FONTE_AUTORIA_CAMARA
                if str(nome_aut).strip().lower() == "poder executivo":
                    registro["iniciativa_executivo"] = True

        lista_final = list(proposicoes_dict.values())
        sem_autor = sum(1 for p in lista_final if not p.get("autor_nome"))
        logger.info(f"Total de {len(lista_final)} proposições setorizadas ({sem_autor} sem autor identificado).")
        return lista_final

    def _escolher_votacao_de_merito(self, votacoes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Ordena as votações da proposição, da mais provável votação de MÉRITO para a menos provável:
        plenário primeiro; dentro dele, descrições "Aprovado o Substitutivo/Projeto/Proposta..." antes das neutras
        e estas antes de requerimentos/destaques/redação final; empate => a mais antiga (aprovação do texto principal).
        """

        def ordem(v: Dict[str, Any]):
            desc = v.get("descricao") or ""
            if _MERITO.search(desc):
                rank = 0
            elif _NAO_MERITO.search(desc):
                rank = 2
            else:
                rank = 1
            data = re.sub(r"\D", "", str(v.get("dataHoraRegistro") or v.get("data") or "")) or "0"
            return ((v.get("siglaOrgao") or "").upper() != "PLEN", rank, int(data))

        return sorted(votacoes, key=ordem)

    def fetch_votacoes_e_votos(self, proposicoes: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Para matérias estruturantes, escolhe a votação de mérito em plenário e coleta os votos nominais
        (Sim, Não, Abstenção, Obstrução, Art. 17). Totais por opção são calculados e gravados na sessão.
        """
        logger.info("Iniciando mapeamento de votações nominais para matérias de plenário...")
        sessoes_votacao: List[Dict[str, Any]] = []
        votos_nominais: List[Dict[str, Any]] = []

        props_para_voto = [
            p
            for p in proposicoes
            if p.get("is_reforma_estrutural")
            or chave_materia(p.get("tipo"), p.get("numero"), p.get("ano")) in CHAVES_EMBLEMATICAS
        ]

        for prop in props_para_voto:
            prop_id = prop["camara_id"]
            data_vot = self._get_json(f"{BASE_URL}/proposicoes/{prop_id}/votacoes")
            if not data_vot or not data_vot.get("dados"):
                continue

            escolhida = None
            lista_votos: List[Dict[str, Any]] = []
            for v in self._escolher_votacao_de_merito(data_vot["dados"])[:4]:
                data_votos = self._get_json(f"{BASE_URL}/votacoes/{v['id']}/votos")
                itens = (data_votos or {}).get("dados") or []
                if itens:
                    escolhida, lista_votos = v, itens
                    break
            if not escolhida:
                continue

            vot_id = str(escolhida["id"])
            desc = escolhida.get("descricao", "") or ""
            totais = {"SIM": 0, "NAO": 0, "ABSTENCAO": 0, "OBSTRUCAO": 0, "ARTIGO_17": 0, "AUSENTE": 0}

            registros_votos = []
            for item_voto in lista_votos:
                dep_obj = item_voto.get("deputado_") or item_voto.get("deputado") or {}
                opcao = classificar_voto(item_voto.get("tipoVoto"))
                if opcao is None:
                    logger.warning(
                        "tipoVoto desconhecido %r na votação %s — registro ignorado.", item_voto.get("tipoVoto"), vot_id
                    )
                    continue
                totais[opcao] += 1
                registros_votos.append(
                    {
                        "sessao_externa_id": vot_id,
                        "proposicao_camara_id": prop_id,
                        "deputado_camara_id": dep_obj.get("id"),
                        "deputado_nome": dep_obj.get("nome"),
                        "partido_sigla": dep_obj.get("siglaPartido"),
                        "uf": dep_obj.get("siglaUf"),
                        "voto": opcao,
                        "data_registro": item_voto.get("dataRegistroVoto"),
                    }
                )

            data_hora = escolhida.get("dataHoraRegistro") or (
                f"{escolhida['data']}T00:00:00" if escolhida.get("data") else None
            )
            sessoes_votacao.append(
                {
                    "sessao_externa_id": vot_id,
                    "proposicao_camara_id": prop_id,
                    "proposicao_titulo": prop["titulo"],
                    "proposicao_tipo": prop.get("tipo"),
                    "proposicao_numero": prop.get("numero"),
                    "proposicao_ano": prop.get("ano"),
                    "data_hora": data_hora,
                    "titulo_pauta": f"Votação sobre {prop['titulo']}",
                    "descricao": desc,
                    "aprovada": interpretar_aprovacao(escolhida),
                    "total_sim": totais["SIM"],
                    "total_nao": totais["NAO"],
                    "total_abstencao": totais["ABSTENCAO"],
                    "total_obstrucao": totais["OBSTRUCAO"],
                    "total_votos_registrados": len(registros_votos),
                }
            )
            votos_nominais.extend(registros_votos)
            logger.info(f"Votação {vot_id} da matéria {prop['titulo']}: {len(registros_votos)} votos coletados.")

        logger.info(f"Finalizado: {len(sessoes_votacao)} sessões de votação e {len(votos_nominais)} votos nominais.")
        return {"sessoes_votacao": sessoes_votacao, "votos_nominais": votos_nominais}

    def _carregar_deputados(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Cache de deputados com TTL: não reutiliza o arquivo para sempre."""
        dep_file = PROCESSED_DATA_DIR / "deputados_camara.json"
        if dep_file.exists() and not force_refresh:
            idade_dias = (time.time() - dep_file.stat().st_mtime) / 86400.0
            if idade_dias <= TTL_CACHE_DEPUTADOS_DIAS:
                with open(dep_file, "r", encoding="utf-8") as f:
                    deputados = deduplicar_deputados(json.load(f))
                logger.info(f"Carregados {len(deputados)} deputados únicos do cache local ({idade_dias:.1f} dia(s)).")
                return deputados
            logger.info("Cache de deputados expirou (> %d dias); atualizando pela API.", TTL_CACHE_DEPUTADOS_DIAS)

        novos = self.fetch_deputados(legislatura=57)
        if novos:
            return novos
        if dep_file.exists():
            logger.error("API da Câmara indisponível; mantendo o cache anterior de deputados.")
            with open(dep_file, "r", encoding="utf-8") as f:
                return deduplicar_deputados(json.load(f))
        return []

    def run_full_extraction(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Executa a extração completa e persiste os arquivos (atômicos, nunca vazios) em etl/data/processed/."""
        logger.info("=" * 70)
        logger.info("EXTRAÇÃO AMPLIADA DA CÂMARA: PROPOSIÇÕES, SETORES E PRODUTIVIDADE")
        logger.info("=" * 70)

        deputados = self._carregar_deputados(force_refresh=force_refresh)
        if not deputados:
            raise RuntimeError("Nenhum deputado obtido da API da Câmara nem do cache local.")
        deputados = self.enriquecer_deputados(deputados)
        write_json_if_valid(PROCESSED_DATA_DIR / "deputados_camara.json", deputados)

        deputados_map = {d["camara_id"]: d for d in deputados}

        proposicoes = self.fetch_proposicoes_ampliadas(deputados_map=deputados_map)
        write_json_if_valid(PROCESSED_DATA_DIR / "proposicoes_2023.json", proposicoes)

        resultado_votacoes = self.fetch_votacoes_e_votos(proposicoes)
        sessoes = resultado_votacoes["sessoes_votacao"]
        votos = resultado_votacoes["votos_nominais"]
        write_json_if_valid(PROCESSED_DATA_DIR / "sessoes_votacao_2023.json", sessoes)
        write_json_if_valid(PROCESSED_DATA_DIR / "votos_nominais_2023.json", votos)

        logger.info("Arquivos da Câmara salvos com sucesso em etl/data/processed/!")
        return {
            "total_deputados": len(deputados),
            "total_proposicoes": len(proposicoes),
            "total_sessoes": len(sessoes),
            "total_votos": len(votos),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    extractor = CamaraExtractor(request_delay=0.1)
    res = extractor.run_full_extraction()
    print("Resultado da extração da Câmara:", res)
