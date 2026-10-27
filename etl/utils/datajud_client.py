"""
Cliente da API Pública do DataJud (Conselho Nacional de Justiça - CNJ).

Base Nacional de Dados do Poder Judiciário (Portaria CNJ nº 160/2020).
Permite consulta oficial aos metadados de processos públicos (capas, classes TPU,
assuntos TPU, órgãos julgadores e movimentações processuais).
"""

import json
import logging
import os
import re
import time
from datetime import datetime
from datetime import time as hora_do_dia
from datetime import timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from etl.config import RAW_DATA_DIR
from etl.utils.io_utils import atomic_write_json

logger = logging.getLogger("DataJudClient")

DEFAULT_API_KEY = "ApiKey cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="
DATAJUD_BASE_URL = "https://api-publica.datajud.cnj.jus.br"
# "Não encontrado" só vale por este tempo: o tribunal pode indexar o processo depois, e um miss guardado para sempre o
# esconderia até alguém apagar o cache à mão.
CACHE_NEGATIVO_DIAS = 7
# O achado também vence: um processo muda (um julgamento depois do primeiro registro), e um último movimento congelado no
# cache faria o dossiê mostrar o andamento antigo como se fosse o atual. Um dia basta para repetir a extração sem martelar a API.
CACHE_POSITIVO_DIAS = 1
PROVENIENCIA_DATAJUD = "CNJ / DataJud (Base Nacional de Dados do Poder Judiciário)"


def _fuso_de_brasilia():
    """Horário de Brasília; sem a base de fusos do sistema, o deslocamento fixo de -03:00 (sem horário de verão desde 2019)."""
    try:
        return ZoneInfo("America/Sao_Paulo")
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=-3))


_FUSO = _fuso_de_brasilia()
# Quanto o relógio gravado no cache pode estar à frente do desta máquina sem o cache deixar de valer.
_DERIVA_DO_RELOGIO = timedelta(minutes=5)
_DATA_COMPACTA = re.compile(r"([0-9]{8})([0-9]{6})?", re.ASCII)


def _como_escrito(valor: Any) -> Optional[datetime]:
    """
    A data/hora do DataJud como veio: ISO (com ou sem hora, com `Z` ou deslocamento) ou compacta (`AAAAMMDD` e
    `AAAAMMDDHHMMSS`, as duas aparecem nos tribunais). Sem fuso no texto, vale o de Brasília. Não é data: None.
    """
    if valor is None or isinstance(valor, (bool, float)):
        return None
    bruto = str(valor).strip()
    if not bruto:
        return None
    try:
        compacta = _DATA_COMPACTA.fullmatch(bruto)
        if compacta:
            return datetime.strptime(compacta.group(1) + (compacta.group(2) or "000000"), "%Y%m%d%H%M%S").replace(
                tzinfo=_FUSO
            )
        instante = datetime.fromisoformat(bruto)
    except ValueError:
        return None
    return instante if instante.tzinfo else instante.replace(tzinfo=_FUSO)


def _dia_do_datajud(valor: Any) -> Optional[str]:
    """
    O dia (`AAAA-MM-DD`) no horário de Brasília, ou None quando não é data. O DataJud grava em UTC (`...Z`): `01:15Z` é
    o dia anterior em Brasília. Meia-noite em UTC, porém, é como ele escreve uma data sem hora (`2018-10-29T00:00:00.000Z`
    é o dia 29), então vale o dia escrito.
    """
    escrito = _como_escrito(valor)
    if escrito is None:
        return None
    if escrito.utcoffset() == timedelta(0) and escrito.time() == hora_do_dia(0):
        return escrito.date().isoformat()
    return escrito.astimezone(_FUSO).date().isoformat()


def _agora_em_brasilia() -> str:
    """O instante de agora, ISO com o deslocamento de Brasília (o cache não depende do fuso da máquina)."""
    return datetime.now(_FUSO).isoformat()


def _hoje_em_brasilia() -> str:
    return datetime.now(_FUSO).date().isoformat()


def _chave_de_instante(valor: Any) -> float:
    """Ordem cronológica do movimento (`dataHora` ilegível vai para o fim)."""
    escrito = _como_escrito(valor)
    return escrito.timestamp() if escrito is not None else float("-inf")


class ErroDoDataJud(RuntimeError):
    """
    O DataJud não deu uma resposta conclusiva (429 esgotado, HTTP diferente de 200, timeout, corpo ilegível). Não é "o
    processo não existe": quem trata os dois como o mesmo caso apaga processos reais por causa de uma falha de rede.
    """


# Código do tribunal (TR) da Resolução CNJ nº 65/2008 para a Justiça Estadual (J=8) e a Eleitoral (J=6): ordem alfabética da
# sigla da UF, então 25 é Sergipe e 26 é São Paulo (a tabela estava com os dois trocados e mandava os processos do TJSP ao TJSE).
UF_CODE_MAP = {
    "01": "ac",
    "02": "al",
    "03": "ap",
    "04": "am",
    "05": "ba",
    "06": "ce",
    "07": "dft",
    "08": "es",
    "09": "go",
    "10": "ma",
    "11": "mt",
    "12": "ms",
    "13": "mg",
    "14": "pa",
    "15": "pb",
    "16": "pr",
    "17": "pe",
    "18": "pi",
    "19": "rj",
    "20": "rn",
    "21": "rs",
    "22": "ro",
    "23": "rr",
    "24": "sc",
    "25": "se",
    "26": "sp",
    "27": "to",
}

_CNJ_RE = re.compile(r"(\d{7})-?(\d{2})\.?(\d{4})\.?(\d)\.?(\d{2})\.?(\d{4})")


def parse_cnj_parts(numero_processo: str) -> Optional[Dict[str, str]]:
    """
    Extrai os componentes da numeração única CNJ (Resolução CNJ nº 65/2008). É tolerante de propósito (aceita texto em
    volta e 20 dígitos soltos, sem conferir o dígito verificador); a validação rígida do número que entra na carga é
    `loader_helpers.cnj_valido`, e o extrator só consulta o que ela aceitou.
    """
    m = _CNJ_RE.search(numero_processo or "")
    if not m:
        digitos = re.sub(r"\D", "", numero_processo or "")
        if len(digitos) == 20:
            return {
                "sequencial": digitos[:7],
                "digito": digitos[7:9],
                "ano": digitos[9:13],
                "segmento": digitos[13],
                "tribunal": digitos[14:16],
                "origem": digitos[16:20],
                "limpo": digitos,
                "formatado": f"{digitos[:7]}-{digitos[7:9]}.{digitos[9:13]}.{digitos[13]}.{digitos[14:16]}.{digitos[16:20]}",
            }
        return None
    seq, dig, ano, seg, trib, orig = m.groups()
    limpo = f"{seq}{dig}{ano}{seg}{trib}{orig}"
    return {
        "sequencial": seq,
        "digito": dig,
        "ano": ano,
        "segmento": seg,
        "tribunal": trib,
        "origem": orig,
        "limpo": limpo,
        "formatado": f"{seq}-{dig}.{ano}.{seg}.{trib}.{orig}",
    }


def deduzir_aliases_datajud(parsed_cnj: Dict[str, str]) -> List[str]:
    """
    Deduz os endpoints/aliases possíveis do DataJud a partir do ramo da Justiça (J) e tribunal (TR).
    Retorna uma lista ordenada de candidatos mais prováveis.
    """
    seg = parsed_cnj["segmento"]
    tr = parsed_cnj["tribunal"]
    uf = UF_CODE_MAP.get(tr)

    aliases: List[str] = []
    if seg == "1":
        # o STF não está no DataJud: a lista fica vazia e o extrator conta o processo como sem cobertura
        pass
    elif seg == "3":
        aliases.append("api_publica_stj")
    elif seg == "4":
        # Justiça Federal: TRF1 a TRF6
        try:
            num_trf = int(tr)
            if 1 <= num_trf <= 6:
                aliases.append(f"api_publica_trf{num_trf}")
        except ValueError:
            pass
    elif seg == "5":
        # Justiça do Trabalho: TST ou TRTs
        if tr == "00":
            aliases.append("api_publica_tst")
        else:
            try:
                num_trt = int(tr)
                if 1 <= num_trt <= 24:
                    aliases.append(f"api_publica_trt{num_trt}")
            except ValueError:
                pass
    elif seg == "6":
        # Justiça Eleitoral: TSE ou TREs
        if tr == "00":
            aliases.append("api_publica_tse")
        elif uf:
            aliases.append(f"api_publica_tre-{uf}")
            aliases.append("api_publica_tse")
    elif seg == "7":
        aliases.append("api_publica_stm")
    elif seg == "8":
        # Justiça Estadual: TJs
        if uf:
            aliases.append(f"api_publica_tj{uf}")
    elif seg == "9":
        # Justiça Militar Estadual
        if tr == "13":
            aliases.append("api_publica_tjmmg")
        elif tr == "21":
            aliases.append("api_publica_tjmrs")
        elif tr == "26":  # mesma numeração por UF da Justiça Estadual: 13 MG, 21 RS, 26 SP
            aliases.append("api_publica_tjmsp")

    return aliases


class DataJudClient:
    """Cliente oficial para consulta ao DataJud CNJ com cache local atômico."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = DATAJUD_BASE_URL,
        raw_dir: Optional[Path] = None,
        timeout: float = 90.0,
    ):
        self.api_key = api_key or os.getenv("DATAJUD_API_KEY", DEFAULT_API_KEY)
        if self.api_key and not self.api_key.startswith("ApiKey "):
            self.api_key = f"ApiKey {self.api_key}"
        self.base_url = base_url.rstrip("/")
        self.raw_dir = Path(raw_dir or RAW_DATA_DIR) / "datajud"
        self.timeout = timeout
        self._consultas: Dict[str, str] = {}
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": self.api_key,
                "Content-Type": "application/json",
                "User-Agent": "LegisData/2.0 (ETL CNJ DataJud Integrator; +https://github.com/saulozitos/LegisData)",
            }
        )

    def _cache_path(self, clean_number: str, alias: str) -> Path:
        return self.raw_dir / alias / f"{clean_number}.json"

    @staticmethod
    def _cache_vigente(conteudo: Dict[str, Any], dias: int) -> bool:
        """
        O cache tem menos de `dias`. Data ilegível (ou sem fuso comparável) conta como vencida, e a do futuro também: um
        cache copiado de outra máquina, ou de um relógio que andou para trás, ficaria congelado até a data gravada e o
        dossiê mostraria um andamento antigo como atual. A folga de `_DERIVA_DO_RELOGIO` cobre só a diferença normal de
        relógio entre máquinas.
        """
        try:
            gravado = datetime.fromisoformat(str(conteudo.get("fetched_at")))
            idade = datetime.now(gravado.tzinfo) - gravado
        except (ValueError, TypeError):
            return False
        return -_DERIVA_DO_RELOGIO <= idade < timedelta(days=dias)

    @staticmethod
    def _dia_da_gravacao(conteudo: Dict[str, Any]) -> Optional[str]:
        """O dia (Brasília) em que o cache foi gravado; sem fuso no texto vale o dia escrito; ilegível, None."""
        try:
            gravado = datetime.fromisoformat(str(conteudo.get("fetched_at")))
        except (ValueError, TypeError):
            return None
        return (gravado.astimezone(_FUSO) if gravado.tzinfo else gravado).date().isoformat()

    def dia_da_consulta(self, numero: str) -> Optional[str]:
        """
        O dia (`AAAA-MM-DD`, Brasília) em que o documento devolvido por `consultar_processo(numero)` foi lido do
        DataJud: o da gravação do cache quando veio dele, o de hoje quando veio da rede. None se ainda não consultou.
        """
        return self._consultas.get(re.sub(r"[^0-9]", "", str(numero)))

    @staticmethod
    def _documento_do_numero(hits: List[Any], limpo: str) -> Optional[Dict[str, Any]]:
        """
        O documento a usar entre os hits: o mesmo número pode vir uma vez por grau (G1, G2, JE), e a ordem por relevância
        da busca é arbitrária. Entre os do número pedido vale o de atualização mais recente (empate: o primeiro); sem
        nenhum documento legível, None (o chamador trata como inconclusivo).
        """
        fontes = [h.get("_source") for h in hits if isinstance(h, dict)]
        docs = [f for f in fontes if isinstance(f, dict) and f]
        do_numero = [d for d in docs if re.sub(r"[^0-9]", "", str(d.get("numeroProcesso") or "")) == limpo]
        candidatos = do_numero or docs
        return max(candidatos, key=lambda d: _chave_de_instante(d.get("dataHoraUltimaAtualizacao")), default=None)

    def consultar_processo(
        self,
        numero_processo: str,
        alias_forcado: Optional[str] = None,
        usar_cache: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Consulta um processo no DataJud e retorna o documento (_source) encontrado, ou None quando TODOS os
        tribunais consultados responderam e nenhum o tem. Se algum não deu resposta conclusiva e o processo não apareceu
        em outro, levanta `ErroDoDataJud` (inconclusivo, não "inexistente"). Achado (CACHE_POSITIVO_DIAS) e "não encontrado"
        (CACHE_NEGATIVO_DIAS) ficam em cache atômico por tempo limitado, para não repetir requisições onerosas à base
        nacional nem congelar o andamento de um processo.
        """
        parsed = parse_cnj_parts(numero_processo)
        if not parsed:
            logger.debug("Número de processo não compatível com padrão CNJ: %s", numero_processo)
            return None

        limpo = parsed["limpo"]
        aliases = [alias_forcado] if alias_forcado else deduzir_aliases_datajud(parsed)
        inconclusivo: List[str] = []

        for alias in aliases:
            caminho_cache = self._cache_path(limpo, alias)
            if usar_cache and caminho_cache.exists():
                try:
                    conteudo = json.loads(caminho_cache.read_text(encoding="utf-8"))
                    if conteudo.get("found"):
                        if isinstance(conteudo.get("source"), dict) and self._cache_vigente(
                            conteudo, CACHE_POSITIVO_DIAS
                        ):
                            self._consultas[limpo] = self._dia_da_gravacao(conteudo) or _hoje_em_brasilia()
                            return conteudo["source"]
                    elif self._cache_vigente(conteudo, CACHE_NEGATIVO_DIAS):
                        continue
                except (OSError, ValueError, AttributeError):
                    pass

            url = f"{self.base_url}/{alias}/_search"
            payload = {"query": {"match": {"numeroProcesso": limpo}}}

            for tentativa in range(1, 4):
                try:
                    resp = self.session.post(url, json=payload, timeout=self.timeout)
                    if resp.status_code == 429:
                        wait = tentativa * 15.0
                        logger.warning("DataJud 429 em %s; aguardando %.1fs...", alias, wait)
                        time.sleep(wait)
                        continue
                    if resp.status_code != 200:
                        logger.warning("DataJud %s HTTP %s: %s", alias, resp.status_code, resp.text[:200])
                        inconclusivo.append(alias)
                        break

                    hits = ((resp.json() or {}).get("hits") or {}).get("hits") or []
                    if hits:
                        source = self._documento_do_numero(hits, limpo)
                        if source is None:
                            inconclusivo.append(alias)
                            break
                        atomic_write_json(
                            caminho_cache,
                            {"found": True, "fetched_at": _agora_em_brasilia(), "alias": alias, "source": source},
                        )
                        self._consultas[limpo] = _hoje_em_brasilia()
                        logger.info("DataJud: processo %s localizado com sucesso em %s", parsed["formatado"], alias)
                        return source
                    atomic_write_json(
                        caminho_cache,
                        {"found": False, "fetched_at": _agora_em_brasilia(), "alias": alias},
                    )
                    break
                except (requests.RequestException, TimeoutError, ValueError, AttributeError) as exc:
                    logger.warning("Erro de requisição DataJud (%s, tentativa %d): %s", alias, tentativa, exc)
                    time.sleep(tentativa * 3.0)
            else:  # as três tentativas terminaram em 429 ou erro de rede
                inconclusivo.append(alias)

        if inconclusivo:
            raise ErroDoDataJud(
                f"DataJud sem resposta conclusiva para {parsed['formatado']} em: {', '.join(sorted(set(inconclusivo)))}"
            )
        return None

    @staticmethod
    def consolidar_resumo_processo(source: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extrai metadados estruturados e padronizados da resposta oficial do DataJud. Campo ausente ou de tipo inesperado
        fica `None` (a classe também: nada é inventado); um movimento malformado é ignorado, não derruba a extração.
        """

        def _dict(valor: Any) -> Dict[str, Any]:
            return valor if isinstance(valor, dict) else {}

        def _nome(valor: Any) -> Optional[str]:
            nome = _dict(valor).get("nome")
            return nome.strip() if isinstance(nome, str) and nome.strip() else None

        classe = _dict(source.get("classe"))
        assuntos = source.get("assuntos")
        movs = (
            [m for m in (source.get("movimentos") or []) if isinstance(m, dict)]
            if isinstance(source.get("movimentos"), list)
            else []
        )

        # cronológica por instante (ISO e compacto se misturam; a ordem por texto errava), o mais recente primeiro
        movs_ordenados = sorted(movs, key=lambda m: _chave_de_instante(m.get("dataHora")), reverse=True)
        ultimo_mov = movs_ordenados[0] if movs_ordenados else {}

        classe_nome = _nome(classe)
        assuntos_nomes = [n for n in (_nome(a) for a in assuntos) if n] if isinstance(assuntos, list) else []
        if classe_nome is None:
            classe_assunto = None
        else:
            classe_assunto = f"{classe_nome} / {', '.join(assuntos_nomes)}" if assuntos_nomes else classe_nome

        nome_mov = ultimo_mov.get("nome")

        return {
            "numero_processo": source.get("numeroProcesso"),
            "tribunal": source.get("tribunal"),
            "grau": source.get("grau"),
            "nivel_sigilo": source.get("nivelSigilo"),
            "classe_assunto": classe_assunto,
            "classe_tpu_codigo": classe.get("codigo"),
            "classe_tpu_nome": classe_nome,
            "assuntos_tpu": assuntos_nomes,
            "orgao_julgador": _nome(source.get("orgaoJulgador")),
            "data_processo": _dia_do_datajud(source.get("dataAjuizamento")),
            "total_movimentacoes": len(movs),
            "ultimo_movimento": nome_mov if isinstance(nome_mov, str) and nome_mov.strip() else None,
            "data_ultimo_movimento": _dia_do_datajud(ultimo_mov.get("dataHora")),
            "fonte": PROVENIENCIA_DATAJUD,
            "is_synthetic": False,
        }
