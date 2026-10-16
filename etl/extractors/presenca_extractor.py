"""
Extrator de presença em plenário (Câmara dos Deputados e Senado Federal) — SOMENTE dados oficiais.

Fontes
------
* Câmara: relatório oficial "Presença em Plenário" de cada deputado, publicado no portal da Câmara
  (https://www.camara.leg.br/deputados/{id}/presenca-plenario/{ano}). A página traz, por dia com sessão
  deliberativa, o status oficial (Presença, Ausência, Missão Autorizada, Licença..., Decisão da Mesa...) e um
  resumo anual conforme o Ato da Mesa nº 191/2017. A lista de deputados vem da API de Dados Abertos
  (`/deputados?idLegislatura=`). O portal só publica a série a partir de 2020 ("Não há dados" para 2019).
* Senado: o Senado não expõe um relatório de presença consumível. A presença é DERIVADA das votações nominais
  de plenário (https://legis.senado.leg.br/dadosabertos/plenario/lista/votacao/{ini}/{fim}), onde cada uma das
  votações lista todos os senadores com o voto (Sim/Não/Votou/P-NRV = presente) ou o código de justificativa
  (AP, MIS, LS, LP) ou "NCom" (não compareceu = ausência não justificada). A unidade é o "dia com votação nominal em
  plenário". Códigos sem significado confirmado (REP, LA, LAP, LG, MERC, P-OD) não entram na contagem.

Nada aqui é sorteado ou estimado: o que a fonte não informa permanece ausente.
"""

import gzip
import json
import logging
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from html import unescape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from etl.config import PROCESSED_DATA_DIR, RAW_DATA_DIR
from etl.utils.http_client import HttpClient, HttpError
from etl.utils.io_utils import EmptyResultError, atomic_write_bytes, atomic_write_json

logger = logging.getLogger("PresencaExtractor")

# Status canônicos = valores de TipoPresencaEnum do backend
PRESENTE = "PRESENTE"
AUSENCIA_JUSTIFICADA = "AUSENCIA_JUSTIFICADA"
AUSENCIA_NAO_JUSTIFICADA = "AUSENCIA_NAO_JUSTIFICADA"
LICENCA_MEDICA = "LICENCA_MEDICA"
MISSAO_OFICIAL = "MISSAO_OFICIAL"
STATUS_JUSTIFICADOS = frozenset({AUSENCIA_JUSTIFICADA, LICENCA_MEDICA, MISSAO_OFICIAL})

CAMARA = "CAMARA"
SENADO = "SENADO"

# O portal da Câmara só publica o relatório de presença a partir de 2020.
CAMARA_PRIMEIRO_ANO = 2020
SENADO_PRIMEIRO_ANO = 1995
# Legislatura -> (primeiro ano, último ano) de sessões legislativas
LEGISLATURAS = {56: (2019, 2022), 57: (2023, 2026)}

URL_CAMARA_API = "https://dadosabertos.camara.leg.br/api/v2"
URL_CAMARA_PRESENCA = "https://www.camara.leg.br/deputados/{id}/presenca-plenario/{ano}"
URL_SENADO_VOTACOES = "https://legis.senado.leg.br/dadosabertos/plenario/lista/votacao/{ini}/{fim}"

FONTE_CAMARA = (
    "Câmara dos Deputados — Portal: Presença em Plenário (relatório oficial por deputado; "
    "critério do Ato da Mesa nº 191/2017)"
)
FONTE_SENADO = "Senado Federal — Dados Abertos: votações nominais de plenário (presença derivada dos registros de voto)"

UNIDADE_CAMARA = "dia com sessão deliberativa"
UNIDADE_SENADO = "dia com votação nominal em plenário"

ARQ_RESUMO = "presenca_plenario_resumo.json"
ARQ_DIAS = "presenca_plenario_dias.json.gz"

# --------------------------------------------------------------------------------------------------------------------
# Câmara: parsing do relatório HTML
# --------------------------------------------------------------------------------------------------------------------

_RE_LINHA_DIA = re.compile(r'<tr class="info-data">(.*?)</tr>', re.S)
_RE_LINHA_SESSAO = re.compile(r'<tr class="info-data__child">(.*?)</tr>', re.S)
_RE_CELULA = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_RE_DATA_BR = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
_RE_TAGS = re.compile(r"<[^>]+>")
_RE_SCRIPT_STYLE = re.compile(r"<script\b[^>]*>.*?</script[^>]*>|<style\b[^>]*>.*?</style[^>]*>", re.S | re.I)
_RE_ESPACOS = re.compile(r"\s+")
_RE_OBS = re.compile(r"\s*Observações\s*\?\s*", re.I)

_RESUMO_ROTULOS = {
    "total_sessoes": "Total de sessões deliberativas com Ordem do Dia iniciada",
    "ausencias_nao_justificadas_sessoes": "Total de ausências não justificadas em sessões deliberativas com Ordem do Dia",
    "total_dias": "Total de dias com sessões deliberativas realizadas no período",
    "dias_presenca": "Total de dias com presença nas sessões deliberativas",
    "dias_ausencia_justificada": "Total de dias com ausências justificadas em sessões deliberativas",
    "dias_ausencia_nao_justificada": "Total de dias com ausências não justificadas em sessões deliberativas",
}


def _texto(fragmento: str) -> str:
    return _RE_ESPACOS.sub(" ", unescape(_RE_TAGS.sub(" ", fragmento))).strip()


def _limpa_rotulo(texto: str) -> str:
    return _RE_ESPACOS.sub(" ", _RE_OBS.sub(" ", texto)).strip()


def _data_iso(texto: str) -> Optional[str]:
    m = _RE_DATA_BR.search(texto)
    if not m:
        return None
    dia, mes, ano = m.groups()
    try:
        return date(int(ano), int(mes), int(dia)).isoformat()
    except ValueError:
        return None


def classificar_rotulo_camara(rotulo: str) -> Tuple[str, Optional[str]]:
    """
    Converte o rótulo oficial do relatório da Câmara em (status canônico, justificativa).

    "Presença" e "Presença (~)" -> PRESENTE; "Ausência" (sem justificativa) -> AUSENCIA_NAO_JUSTIFICADA;
    "Missão Autorizada" -> MISSAO_OFICIAL; licença para tratamento de saúde -> LICENCA_MEDICA; qualquer outro
    rótulo de afastamento (Decisão da Mesa, licença-maternidade, etc.) é uma justificativa regimental ->
    AUSENCIA_JUSTIFICADA com o próprio rótulo como justificativa.
    """
    r = _limpa_rotulo(rotulo)
    baixo = r.lower()
    if not r:
        raise ValueError("rótulo de presença vazio")
    if baixo.startswith("presen"):
        return PRESENTE, None
    if baixo in ("ausência", "ausencia", "falta", "ausência não justificada"):
        return AUSENCIA_NAO_JUSTIFICADA, None
    if baixo.startswith("missão") or baixo.startswith("missao"):
        return MISSAO_OFICIAL, r
    if "saúde" in baixo or "saude" in baixo:
        return LICENCA_MEDICA, r
    return AUSENCIA_JUSTIFICADA, r


def parse_presenca_camara(html_text: str) -> Optional[Dict[str, Any]]:
    """
    Interpreta a página "Presença em Plenário". Retorna None quando o portal informa que não há dados para o ano.

    Retorno: {"dias": [{"data", "rotulo"}], "sessoes": [{"data", "descricao", "rotulo"}], "resumo": {...}}
    """
    if "Não há dados disponíveis" in html_text:
        return None

    dias: List[Dict[str, str]] = []
    for bloco in _RE_LINHA_DIA.findall(html_text):
        celulas = [_texto(c) for c in _RE_CELULA.findall(bloco)]
        data_iso = _data_iso(celulas[0]) if celulas else None
        if not data_iso or len(celulas) < 3:
            continue  # linha do cabeçalho do resumo anual ("2024")
        rotulo = _limpa_rotulo(celulas[2])
        if rotulo:
            dias.append({"data": data_iso, "rotulo": rotulo})

    sessoes: List[Dict[str, str]] = []
    for bloco in _RE_LINHA_SESSAO.findall(html_text):
        celulas = [_texto(c) for c in _RE_CELULA.findall(bloco)]
        if len(celulas) < 2:
            continue
        data_iso = _data_iso(celulas[0])
        if data_iso:
            sessoes.append({"data": data_iso, "descricao": celulas[0], "rotulo": _limpa_rotulo(celulas[1])})

    resumo: Dict[str, Optional[int]] = {}
    corpo = _texto(_RE_SCRIPT_STYLE.sub("", html_text))
    for chave, rotulo in _RESUMO_ROTULOS.items():
        m = re.search(re.escape(rotulo) + r"[^0-9]{0,40}?(\d+)", corpo)
        resumo[chave] = int(m.group(1)) if m else None

    if not dias and not sessoes and all(v is None for v in resumo.values()):
        return None
    return {"dias": dias, "sessoes": sessoes, "resumo": resumo}


def registros_dia_camara(parsed: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Counter]:
    """Dias classificados (status canônico) e a contagem de rótulos desconhecidos/justificados para auditoria."""
    registros: List[Dict[str, Any]] = []
    rotulos: Counter = Counter()
    for dia in parsed["dias"]:
        try:
            status, justificativa = classificar_rotulo_camara(dia["rotulo"])
        except ValueError:
            continue
        rotulos[dia["rotulo"]] += 1
        registros.append({"data": dia["data"], "status": status, "justificativa": justificativa})
    return registros, rotulos


def contagens_camara(registros: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    c = Counter(r["status"] for r in registros)
    total = sum(c.values())
    return {
        "total_dias": total,
        "presencas": c.get(PRESENTE, 0),
        "faltas_justificadas": sum(c.get(s, 0) for s in STATUS_JUSTIFICADOS),
        "faltas_nao_justificadas": c.get(AUSENCIA_NAO_JUSTIFICADA, 0),
    }


def taxa_presenca(presencas: int, total: int) -> Optional[float]:
    return round(presencas / total * 100, 2) if total > 0 else None


# --------------------------------------------------------------------------------------------------------------------
# Senado: presença derivada das votações nominais
# --------------------------------------------------------------------------------------------------------------------

_VOTOS_PRESENTE = frozenset({"sim", "não", "nao", "abstenção", "abstencao", "votou", "p-nrv", "obstrução", "obstrucao"})
_VOTO_JUSTIFICADO = {
    "ap": (AUSENCIA_JUSTIFICADA, "Atividade parlamentar"),
    "mis": (MISSAO_OFICIAL, "Missão da Casa no País/exterior"),
    "ls": (LICENCA_MEDICA, "Licença saúde"),
    "lp": (AUSENCIA_JUSTIFICADA, "Licença particular"),
}
# "NCom" = não compareceu (código do painel do Senado): ausência sem justificativa
_VOTO_NAO_JUSTIFICADO = frozenset({"ausente", "aus", "falta", "ncom"})
# "NA" = dispositivo não citado: não informa presença nem ausência (ignorado).
_VOTOS_NEUTROS = frozenset({"na"})
# Presidente da sessão (art. 51 RISF) conduz os trabalhos: está presente.
_PRESIDENTE = "presidente"
_PRIORIDADE_JUSTIFICATIVA = ("mis", "ls", "lp", "ap")


def classificar_voto_senado(voto: str) -> Optional[Tuple[str, Optional[str], str]]:
    """(status, justificativa, código normalizado) ou None quando o código não informa presença."""
    v = (voto or "").strip()
    chave = v.lower()
    if chave in _VOTOS_PRESENTE or chave.startswith(_PRESIDENTE):
        return PRESENTE, None, chave
    if chave in _VOTO_JUSTIFICADO:
        status, texto = _VOTO_JUSTIFICADO[chave]
        return status, texto, chave
    if chave in _VOTO_NAO_JUSTIFICADO:
        return AUSENCIA_NAO_JUSTIFICADA, None, chave
    return None


def _lista(valor: Any) -> List[Any]:
    if valor is None:
        return []
    return valor if isinstance(valor, list) else [valor]


def parse_votacoes_senado(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extrai de `ListaVotacoes` apenas o necessário: [{"codigo": <CodigoSessaoVotacao>, "data": "AAAA-MM-DD",
    "votos": [[codigo_parlamentar, nome, voto], ...]}]. Votações sem votos nominais (secretas) são descartadas.
    """
    votacoes = ((payload or {}).get("ListaVotacoes") or {}).get("Votacoes") or {}
    saida: List[Dict[str, Any]] = []
    for v in _lista(votacoes.get("Votacao")):
        data = (v.get("DataSessao") or "")[:10]
        votos_raw = _lista((v.get("Votos") or {}).get("VotoParlamentar"))
        votos = [
            [int(x["CodigoParlamentar"]), x.get("NomeParlamentar") or "", x.get("Voto") or ""]
            for x in votos_raw
            if isinstance(x, dict) and str(x.get("CodigoParlamentar") or "").isdigit()
        ]
        if not data or not votos:
            continue
        partidos = {
            int(x["CodigoParlamentar"]): x["SiglaPartido"].strip()
            for x in votos_raw
            if isinstance(x, dict) and str(x.get("CodigoParlamentar") or "").isdigit() and x.get("SiglaPartido")
        }
        saida.append(
            {"codigo": str(v.get("CodigoSessaoVotacao") or ""), "data": data, "votos": votos, "partidos": partidos}
        )
    return saida


def agregar_dias_senado(votacoes: Iterable[Dict[str, Any]]) -> Tuple[Dict[Tuple[int, str], Dict[str, Any]], Counter]:
    """
    Reduz as votações a um status por (senador, dia): PRESENTE se registrou presença em ao menos uma votação do dia;
    senão a justificativa de maior prioridade (MIS > LS > LP > AP); senão ausência não justificada (se a fonte
    algum dia a expuser). Retorna também a contagem de códigos de voto desconhecidos (auditoria).
    """
    por_dia: Dict[Tuple[int, str], List[Tuple[str, Optional[str], str]]] = defaultdict(list)
    nomes: Dict[int, str] = {}
    desconhecidos: Counter = Counter()
    vistos = set()
    for vot in votacoes:
        chave_vot = (vot["data"], vot["codigo"])
        if vot["codigo"] and chave_vot in vistos:
            continue
        vistos.add(chave_vot)
        for codigo, nome, voto in vot["votos"]:
            nomes.setdefault(codigo, nome)
            classe = classificar_voto_senado(voto)
            if classe is None:
                if (voto or "").strip().lower() not in _VOTOS_NEUTROS:
                    desconhecidos[voto] += 1
                continue
            por_dia[(codigo, vot["data"])].append(classe)

    dias: Dict[Tuple[int, str], Dict[str, Any]] = {}
    for (codigo, data), classes in por_dia.items():
        status_set = {c[0] for c in classes}
        if PRESENTE in status_set:
            status, just = PRESENTE, None
        else:
            just_codes = [c[2] for c in classes if c[0] in STATUS_JUSTIFICADOS]
            if just_codes:
                escolhido = next((k for k in _PRIORIDADE_JUSTIFICATIVA if k in just_codes), just_codes[0])
                status, just = _VOTO_JUSTIFICADO[escolhido]
            else:
                status, just = AUSENCIA_NAO_JUSTIFICADA, None
        dias[(codigo, data)] = {"status": status, "justificativa": just, "nome": nomes.get(codigo, "")}
    return dias, desconhecidos


def partidos_por_data(votacoes: Iterable[Dict[str, Any]]) -> List[List[Any]]:
    """Pontos de mudança de partido de cada senador: [codigo, 'AAAA-MM-DD' da primeira aparição, sigla]."""
    por_senador: Dict[int, List[Tuple[str, str]]] = defaultdict(list)
    for vot in sorted(votacoes, key=lambda v: v["data"]):
        for codigo, sigla in (vot.get("partidos") or {}).items():
            por_senador[codigo].append((vot["data"], sigla))
    saida: List[List[Any]] = []
    for codigo in sorted(por_senador):
        anterior = None
        for data, sigla in por_senador[codigo]:
            if sigla != anterior:
                saida.append([codigo, data, sigla])
                anterior = sigla
    return saida


def janelas_mensais(ano: int, hoje: Optional[date] = None) -> List[Tuple[date, date]]:
    """Janelas [primeiro, último dia] de cada mês do ano, cortadas em `hoje` (sem meses futuros)."""
    hoje = hoje or date.today()
    janelas: List[Tuple[date, date]] = []
    for mes in range(1, 13):
        ini = date(ano, mes, 1)
        if ini > hoje:
            break
        prox = date(ano + (mes == 12), (mes % 12) + 1, 1)
        janelas.append((ini, min(prox - timedelta(days=1), hoje)))
    return janelas


# --------------------------------------------------------------------------------------------------------------------
# Extrator
# --------------------------------------------------------------------------------------------------------------------


def _agora() -> datetime:
    return datetime.now()


class PoliteHttpClient(HttpClient):
    """
    Cliente que respeita o limite de taxa do servidor. O portal da Câmara responde 429 a rajadas e não informa a
    cota: ao receber 429 a requisição ESPERA um período de resfriamento longo (45s, dobrando até 10 min a cada 429
    seguido) antes de tentar de novo — insistir em intervalos curtos prolonga a penalidade. Cada sucesso zera o
    resfriamento. O espaçamento entre requisições é fixo (`base_interval`) e a identificação (User-Agent) é a do projeto.
    """

    def __init__(
        self,
        base_interval: float = 0.25,
        cooldown_inicial: float = 15.0,
        cooldown_max: float = 300.0,
        tentativas_429: int = 6,
        user_agent: str = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 (LegisData Collector)",
        **kwargs,
    ):
        kwargs.setdefault("max_retries", 1)
        kwargs.setdefault("timeout", 30.0)
        super().__init__(min_interval=base_interval, user_agent=user_agent, **kwargs)
        self.cooldown_inicial = cooldown_inicial
        self.cooldown_max = cooldown_max
        self.tentativas_429 = tentativas_429
        self._cooldown = cooldown_inicial

    def get_bytes(self, url, headers=None, timeout=None):  # type: ignore[override]
        for tentativa in range(1, self.tentativas_429 + 1):
            try:
                corpo = super().get_bytes(url, headers=headers, timeout=timeout)
            except HttpError as exc:
                if exc.status != 429:
                    raise
                espera = self._cooldown
                self._cooldown = min(self.cooldown_max, self._cooldown * 2)
                logger.warning("429 em %s: aguardando %.0fs (tentativa %d)", url, espera, tentativa)
                self._sleep(espera)
                continue
            self._cooldown = self.cooldown_inicial
            return corpo
        raise HttpError(url, 429, "Limite de taxa persistente (429)")


def _cache_vale(fetched_at: Optional[str], ano_dados: int, hoje: date) -> bool:
    """Anos encerrados nunca expiram; o ano corrente é refeito se o cache tem mais de 24h."""
    if ano_dados < hoje.year:
        return True
    if not fetched_at:
        return False
    try:
        return _agora() - datetime.fromisoformat(fetched_at) < timedelta(hours=24)
    except ValueError:
        return False


class PresencaExtractor:
    """Extrai a presença em plenário da Câmara e do Senado e grava os arquivos processados (atomicamente)."""

    def __init__(
        self,
        raw_dir: Path = RAW_DATA_DIR,
        processed_dir: Path = PROCESSED_DATA_DIR,
        http: Optional[HttpClient] = None,
        workers: int = 1,
        hoje: Optional[date] = None,
        intervalo: float = 2.0,
    ):
        self.raw_dir = Path(raw_dir) / "presenca"
        self.processed_dir = Path(processed_dir)
        # O portal da Câmara responde 429 a rajadas: 1 requisição/s, uma por vez, com backoff longo.
        self.http = http or PoliteHttpClient(base_interval=intervalo)
        self.workers = max(1, workers)
        self.hoje = hoje or date.today()

    # ------------------------------------------------------------------ utilidades de cache
    def _ler_cache(self, caminho: Path) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(caminho.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    # ------------------------------------------------------------------ Câmara
    def listar_deputados(self, legislatura: int, usar_cache: bool = True) -> List[Dict[str, Any]]:
        """Deputados (inclusive suplentes em exercício) da legislatura, via API de Dados Abertos."""
        caminho = self.raw_dir / "camara" / f"deputados_legislatura_{legislatura}.json"
        cache = self._ler_cache(caminho) if usar_cache else None
        if cache and cache.get("legislatura") == legislatura:
            encerrada = LEGISLATURAS.get(legislatura, (0, 0))[1] < self.hoje.year
            if encerrada or _cache_vale(cache.get("fetched_at"), self.hoje.year, self.hoje):
                return cache["deputados"]

        deputados: Dict[int, Dict[str, Any]] = {}
        pagina = 1
        while True:
            url = (
                f"{URL_CAMARA_API}/deputados?idLegislatura={legislatura}&itens=100&pagina={pagina}"
                "&ordem=ASC&ordenarPor=id"
            )
            dados = self.http.get_json(url)
            for d in dados.get("dados", []):
                deputados[int(d["id"])] = {"id": int(d["id"]), "nome": d.get("nome", "")}
            if not any(link.get("rel") == "next" for link in dados.get("links", [])):
                break
            pagina += 1
        lista = sorted(deputados.values(), key=lambda x: x["id"])
        if not lista:
            raise EmptyResultError(f"A API da Câmara não retornou deputados da legislatura {legislatura}.")
        atomic_write_json(caminho, {"legislatura": legislatura, "fetched_at": _agora().isoformat(), "deputados": lista})
        return lista

    def _pagina_presenca(self, camara_id: int, ano: int, usar_cache: bool) -> Optional[Dict[str, Any]]:
        caminho = self.raw_dir / "camara" / str(ano) / f"{camara_id}.json"
        if usar_cache:
            cache = self._ler_cache(caminho)
            if cache and _cache_vale(cache.get("fetched_at"), ano, self.hoje):
                return cache.get("parsed")
        bruto = self.http.get_bytes(URL_CAMARA_PRESENCA.format(id=camara_id, ano=ano))
        parsed = parse_presenca_camara(bruto.decode("utf-8", errors="replace"))
        atomic_write_json(
            caminho, {"fetched_at": _agora().isoformat(), "parsed": parsed}, indent=None, separators=(",", ":")
        )
        return parsed

    def extrair_camara(
        self,
        anos: Optional[List[int]] = None,
        usar_cache: bool = True,
        ids_permitidos: Optional[Iterable[int]] = None,
        max_paginas_novas: Optional[int] = None,
        flush_cada: int = 200,
    ) -> Dict[str, Any]:
        """
        `ids_permitidos` restringe a extração aos deputados conhecidos (ex.: os já carregados no banco).
        `max_paginas_novas` limita as páginas buscadas na rede nesta execução (as do cache são grátis); a extração é
        retomável: rodar de novo continua do cache. A cada `flush_cada` páginas novas um resultado parcial é gravado.
        """
        anos = sorted(anos or range(CAMARA_PRIMEIRO_ANO, self.hoje.year + 1))
        permitidos = set(ids_permitidos) if ids_permitidos is not None else None
        tarefas: List[Tuple[int, str, int]] = []
        # Legislatura atual e anos recentes primeiro: se a execução for interrompida, o mais útil já está pronto.
        for legislatura, (ini, fim) in sorted(LEGISLATURAS.items(), reverse=True):
            anos_leg = sorted((a for a in anos if ini <= a <= min(fim, self.hoje.year)), reverse=True)
            if not anos_leg:
                continue
            for dep in self.listar_deputados(legislatura, usar_cache):
                if permitidos is not None and dep["id"] not in permitidos:
                    continue
                for ano in anos_leg:
                    tarefas.append((dep["id"], dep["nome"], ano))
        tarefas.sort(key=lambda t: -t[2])
        logger.info("Câmara: %d páginas (deputado × ano) a consultar", len(tarefas))

        resumos: List[Dict[str, Any]] = []
        dias: List[List[Any]] = []
        rotulos: Counter = Counter()
        falhas: List[str] = []
        divergencias = 0
        pendentes = 0
        novas = 0

        def em_cache(cid: int, ano: int) -> bool:
            cache = self._ler_cache(self.raw_dir / "camara" / str(ano) / f"{cid}.json") if usar_cache else None
            return bool(cache and _cache_vale(cache.get("fetched_at"), ano, self.hoje))

        def snapshot() -> Dict[str, Any]:
            return {
                "resumos": sorted(resumos, key=lambda r: (r["ano"], r["parlamentar_id"])),
                "dias": sorted(dias, key=lambda r: (r[0], r[1])),
                "falhas": list(falhas),
            }

        for i, (cid, nome, ano) in enumerate(tarefas, start=1):
            cacheada = em_cache(cid, ano)
            if not cacheada and max_paginas_novas is not None and novas >= max_paginas_novas:
                pendentes += 1
                continue
            try:
                parsed = self._pagina_presenca(cid, ano, usar_cache)
            except HttpError as exc:
                falhas.append(f"{cid}/{ano}: {exc}")
                continue
            if not cacheada:
                novas += 1
                if flush_cada and novas % flush_cada == 0 and resumos:
                    logger.info("Câmara: %d páginas novas (%d/%d tarefas); gravando parcial", novas, i, len(tarefas))
                    self._gravar({CAMARA: snapshot()})
            if not parsed:
                continue
            regs, rot = registros_dia_camara(parsed)
            if not regs:
                continue
            rotulos.update(rot)
            cont = contagens_camara(regs)
            oficial = parsed.get("resumo") or {}
            if oficial.get("total_dias") is not None and (
                oficial["total_dias"] != cont["total_dias"] or oficial.get("dias_presenca") != cont["presencas"]
            ):
                divergencias += 1
                logger.warning("Resumo oficial diverge das linhas de %s/%s: %s vs %s", cid, ano, oficial, cont)
            resumos.append(
                {
                    "casa": CAMARA,
                    "parlamentar_id": cid,
                    "nome": nome,
                    "ano": ano,
                    "unidade": UNIDADE_CAMARA,
                    **cont,
                    "taxa_presenca_pct": taxa_presenca(cont["presencas"], cont["total_dias"]),
                    "resumo_oficial": oficial,
                }
            )
            dias.extend([cid, r["data"], r["status"], r["justificativa"]] for r in regs)

        resumos.sort(key=lambda r: (r["ano"], r["parlamentar_id"]))
        dias.sort(key=lambda r: (r[0], r[1]))
        return {
            "resumos": resumos,
            "dias": dias,
            "rotulos": dict(rotulos),
            "falhas": falhas,
            "divergencias_resumo_oficial": divergencias,
            "paginas_pendentes": pendentes,
            "paginas_novas": novas,
            "anos": anos,
        }

    # ------------------------------------------------------------------ Senado
    def _votacoes_mes(self, ini: date, fim: date, usar_cache: bool) -> List[Dict[str, Any]]:
        caminho = self.raw_dir / "senado" / f"votacoes_{ini:%Y%m}.json"
        if usar_cache:
            cache = self._ler_cache(caminho)
            # cache gravado antes de existir o partido por votação não serve: deixaria o partido do dia em branco
            if cache and all("partidos" in v for v in cache.get("votacoes") or []):
                mes_fechado = fim < date(self.hoje.year, self.hoje.month, 1)
                recente = _cache_vale(cache.get("fetched_at"), self.hoje.year, self.hoje)
                if mes_fechado or (recente and cache.get("ate") == fim.isoformat()):
                    return cache["votacoes"]
        url = URL_SENADO_VOTACOES.format(ini=f"{ini:%Y%m%d}", fim=f"{fim:%Y%m%d}")
        payload = self.http.get_json(url, timeout=90.0)
        votacoes = parse_votacoes_senado(payload)
        atomic_write_json(
            caminho,
            {"fetched_at": _agora().isoformat(), "ate": fim.isoformat(), "votacoes": votacoes},
            indent=None,
            separators=(",", ":"),
        )
        return votacoes

    def extrair_senado(self, anos: Optional[List[int]] = None, usar_cache: bool = True) -> Dict[str, Any]:
        anos = sorted(anos or range(SENADO_PRIMEIRO_ANO, self.hoje.year + 1))
        janelas = [(ini, fim) for ano in anos for ini, fim in janelas_mensais(ano, self.hoje)]
        votacoes: List[Dict[str, Any]] = []
        falhas: List[str] = []
        for ini, fim in janelas:
            try:
                votacoes.extend(self._votacoes_mes(ini, fim, usar_cache))
            except HttpError as exc:
                falhas.append(f"{ini:%Y-%m}: {exc}")
        por_dia, desconhecidos = agregar_dias_senado(votacoes)

        dias = sorted(
            ([cod, data, d["status"], d["justificativa"]] for (cod, data), d in por_dia.items()),
            key=lambda r: (r[0], r[1]),
        )
        nomes = {cod: d["nome"] for (cod, _), d in por_dia.items()}
        acum: Dict[Tuple[int, int], Counter] = defaultdict(Counter)
        for (cod, data), d in por_dia.items():
            acum[(cod, int(data[:4]))][d["status"]] += 1

        resumos: List[Dict[str, Any]] = []
        for (cod, ano), c in sorted(acum.items(), key=lambda kv: (kv[0][1], kv[0][0])):
            total = sum(c.values())
            resumos.append(
                {
                    "casa": SENADO,
                    "parlamentar_id": cod,
                    "nome": nomes.get(cod, ""),
                    "ano": ano,
                    "unidade": UNIDADE_SENADO,
                    "total_dias": total,
                    "presencas": c.get(PRESENTE, 0),
                    "faltas_justificadas": sum(c.get(s, 0) for s in STATUS_JUSTIFICADOS),
                    "faltas_nao_justificadas": c.get(AUSENCIA_NAO_JUSTIFICADA, 0),
                    "taxa_presenca_pct": taxa_presenca(c.get(PRESENTE, 0), total),
                }
            )
        return {
            "resumos": resumos,
            "dias": dias,
            "partidos": partidos_por_data(votacoes),
            "votos_desconhecidos": dict(desconhecidos),
            "falhas": falhas,
            "votacoes": len({(v["data"], v["codigo"]) for v in votacoes}),
            "anos": anos,
        }

    # ------------------------------------------------------------------ orquestração
    def run(
        self,
        anos_camara: Optional[List[int]] = None,
        anos_senado: Optional[List[int]] = None,
        usar_cache: bool = True,
        camara: bool = True,
        senado: bool = True,
        ids_camara: Optional[Iterable[int]] = None,
        max_paginas_novas: Optional[int] = None,
    ) -> Dict[str, Any]:
        resultado: Dict[str, Any] = {}
        if camara:
            resultado[CAMARA] = self.extrair_camara(
                anos_camara, usar_cache, ids_camara, max_paginas_novas=max_paginas_novas
            )
        if senado:
            resultado[SENADO] = self.extrair_senado(anos_senado, usar_cache)

        total_resumos = sum(len(v["resumos"]) for v in resultado.values())
        if total_resumos == 0:
            raise EmptyResultError("Nenhum registro de presença foi extraído; arquivos existentes preservados.")
        self._gravar(resultado)
        return resultado

    def _gravar(self, resultado: Dict[str, Any]) -> None:
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        # Preserva a casa não reextraída (ex.: `--presenca` só da Câmara não apaga o Senado já gravado).
        anterior = self._ler_existente()
        casas = {**anterior, **{k: v for k, v in resultado.items() if v["resumos"]}}

        resumos = [r for casa in (CAMARA, SENADO) if casa in casas for r in casas[casa]["resumos"]]
        cobertura = {
            casa: {
                "anos": sorted({r["ano"] for r in casas[casa]["resumos"]}),
                "parlamentares": len({r["parlamentar_id"] for r in casas[casa]["resumos"]}),
                "falhas": casas[casa].get("falhas", []),
                "paginas_pendentes": casas[casa].get("paginas_pendentes"),
            }
            for casa in casas
        }
        cabecalho = {
            "gerado_em": _agora().isoformat(timespec="seconds"),
            "is_synthetic": False,
            "fonte": " | ".join(f for c, f in ((CAMARA, FONTE_CAMARA), (SENADO, FONTE_SENADO)) if c in casas),
            "metodologia": {
                CAMARA: f"Unidade: {UNIDADE_CAMARA}. Presença = dia com presença registrada; faltas justificadas = "
                "missão autorizada, licença e demais justificativas regimentais; não justificada = 'Ausência'. "
                "Série publicada pelo portal a partir de 2020.",
                SENADO: f"Unidade: {UNIDADE_SENADO}. Presença derivada das votações nominais (voto, P-NRV ou "
                "presidência = presente; AP/MIS/LS/LP = ausência justificada; NCom = não compareceu, ausência não "
                "justificada).",
            },
            "cobertura": cobertura,
        }
        atomic_write_json(self.processed_dir / ARQ_RESUMO, {**cabecalho, "resumos": resumos})

        dias = {casa: casas[casa]["dias"] for casa in casas}
        partidos_senado = casas[SENADO].get("partidos", []) if SENADO in casas else []
        corpo = {
            "is_synthetic": False,
            "fonte": cabecalho["fonte"],
            "formato": "[parlamentar_id, 'AAAA-MM-DD', status, justificativa|null]",
            **{casa.lower(): linhas for casa, linhas in dias.items()},
            "senado_partidos": partidos_senado,
        }
        atomic_write_bytes(
            self.processed_dir / ARQ_DIAS,
            gzip.compress(json.dumps(corpo, ensure_ascii=False, separators=(",", ":")).encode("utf-8")),
        )

    def _ler_existente(self) -> Dict[str, Dict[str, Any]]:
        """Reconstrói resumos+dias já gravados para não perder a casa que não foi reextraída."""
        existente: Dict[str, Dict[str, Any]] = {}
        try:
            resumo = json.loads((self.processed_dir / ARQ_RESUMO).read_text(encoding="utf-8"))
            dias = json.loads(gzip.decompress((self.processed_dir / ARQ_DIAS).read_bytes()).decode("utf-8"))
        except (OSError, json.JSONDecodeError, EOFError, gzip.BadGzipFile):
            return existente
        for casa in (CAMARA, SENADO):
            rs = [r for r in resumo.get("resumos", []) if r.get("casa") == casa]
            if rs and casa.lower() in dias:
                existente[casa] = {
                    "resumos": rs,
                    "dias": dias[casa.lower()],
                    "partidos": dias.get("senado_partidos", []) if casa == SENADO else [],
                    "falhas": (resumo.get("cobertura", {}).get(casa, {}) or {}).get("falhas", []),
                }
        return existente


def carregar_dias(processed_dir: Path = PROCESSED_DATA_DIR) -> Optional[Dict[str, Any]]:
    """Lê o arquivo compacto de presença por dia (None se não existir ou for ilegível)."""
    try:
        return json.loads(gzip.decompress((Path(processed_dir) / ARQ_DIAS).read_bytes()).decode("utf-8"))
    except (OSError, json.JSONDecodeError, EOFError, gzip.BadGzipFile):
        return None


def ids_deputados_conhecidos(processed_dir: Path = PROCESSED_DATA_DIR) -> Optional[set]:
    """IDs de deputados de `deputados_camara.json` (None se o arquivo não existir)."""
    try:
        dados = json.loads((Path(processed_dir) / "deputados_camara.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    ids = {int(d["camara_id"]) for d in dados if isinstance(d, dict) and d.get("camara_id")}
    return ids or None


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Extrai a presença em plenário (Câmara e Senado).")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--so-camara", action="store_true")
    parser.add_argument("--so-senado", action="store_true")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--todos", action="store_true", help="Todos os deputados das legislaturas (não só os conhecidos)"
    )
    parser.add_argument(
        "--max-paginas", type=int, default=None, help="Máximo de páginas novas da Câmara nesta execução"
    )
    parser.add_argument("--intervalo", type=float, default=2.0, help="Segundos entre requisições ao portal (padrão 2)")
    args = parser.parse_args()
    ext = PresencaExtractor(workers=args.workers, intervalo=args.intervalo)
    res = ext.run(
        usar_cache=not args.no_cache,
        camara=not args.so_senado,
        senado=not args.so_camara,
        ids_camara=None if args.todos else ids_deputados_conhecidos(),
        max_paginas_novas=args.max_paginas,
    )
    for casa, dados in res.items():
        print(casa, len(dados["resumos"]), "resumos;", len(dados["dias"]), "dias;", len(dados["falhas"]), "falhas")


if __name__ == "__main__":
    main()
