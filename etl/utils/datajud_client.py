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
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from etl.config import RAW_DATA_DIR
from etl.utils.io_utils import atomic_write_json

logger = logging.getLogger("DataJudClient")

DEFAULT_API_KEY = "ApiKey cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="
DATAJUD_BASE_URL = "https://api-publica.datajud.cnj.jus.br"

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
    "25": "sp",
    "26": "se",
    "27": "to",
}

_CNJ_RE = re.compile(r"(\d{7})-?(\d{2})\.?(\d{4})\.?(\d)\.?(\d{2})\.?(\d{4})")


def parse_cnj_parts(numero_processo: str) -> Optional[Dict[str, str]]:
    """Extrai os componentes da numeração única CNJ (Resolução CNJ nº 65/2008)."""
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
        # STF está fora do CNJ DataJud
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
        elif tr == "25":
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

    def consultar_processo(
        self,
        numero_processo: str,
        alias_forcado: Optional[str] = None,
        usar_cache: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Consulta um processo no DataJud e retorna o primeiro documento (_source) encontrado.
        Armazena em cache atômico para não repetir requisições onerosas à base nacional.
        """
        parsed = parse_cnj_parts(numero_processo)
        if not parsed:
            logger.debug("Número de processo não compatível com padrão CNJ: %s", numero_processo)
            return None

        limpo = parsed["limpo"]
        aliases = [alias_forcado] if alias_forcado else deduzir_aliases_datajud(parsed)

        for alias in aliases:
            caminho_cache = self._cache_path(limpo, alias)
            if usar_cache and caminho_cache.exists():
                try:
                    conteudo = json.loads(caminho_cache.read_text(encoding="utf-8"))
                    if conteudo.get("found"):
                        return conteudo.get("source")
                    continue
                except (OSError, json.JSONDecodeError):
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
                        logger.debug("DataJud %s HTTP %s: %s", alias, resp.status_code, resp.text[:200])
                        break

                    data = resp.json()
                    hits = (data.get("hits") or {}).get("hits") or []
                    if hits:
                        source = hits[0].get("_source") or {}
                        atomic_write_json(
                            caminho_cache,
                            {"found": True, "fetched_at": datetime.now().isoformat(), "alias": alias, "source": source},
                        )
                        logger.info("DataJud: processo %s localizado com sucesso em %s", parsed["formatado"], alias)
                        return source
                    else:
                        atomic_write_json(
                            caminho_cache,
                            {"found": False, "fetched_at": datetime.now().isoformat(), "alias": alias},
                        )
                    break
                except (requests.RequestException, TimeoutError) as exc:
                    logger.warning("Erro de requisição DataJud (%s, tentativa %d): %s", alias, tentativa, exc)
                    time.sleep(tentativa * 3.0)

        return None

    @staticmethod
    def consolidar_resumo_processo(source: Dict[str, Any]) -> Dict[str, Any]:
        """Extrai metadados estruturados e padronizados da resposta oficial do DataJud."""
        classe = source.get("classe") or {}
        assuntos = source.get("assuntos") or []
        orgao = source.get("orgaoJulgador") or {}
        movs = source.get("movimentos") or []

        movs_ordenados = sorted(movs, key=lambda m: m.get("dataHora", ""), reverse=True)
        ultimo_mov = movs_ordenados[0] if movs_ordenados else {}

        classe_nome = classe.get("nome") or "Processo Judicial"
        assuntos_nomes = [a.get("nome") for a in assuntos if isinstance(a, dict) and a.get("nome")]
        classe_assunto = f"{classe_nome} / {", ".join(assuntos_nomes)}" if assuntos_nomes else classe_nome

        data_ajuizamento = source.get("dataAjuizamento")
        if data_ajuizamento and "T" in str(data_ajuizamento):
            data_str = str(data_ajuizamento).split("T")[0]
        else:
            data_str = str(data_ajuizamento or "")[:10]

        return {
            "numero_processo": source.get("numeroProcesso"),
            "tribunal": source.get("tribunal"),
            "grau": source.get("grau"),
            "classe_assunto": classe_assunto,
            "classe_tpu_codigo": classe.get("codigo"),
            "classe_tpu_nome": classe_nome,
            "assuntos_tpu": assuntos_nomes,
            "orgao_julgador": orgao.get("nome"),
            "data_processo": data_str,
            "total_movimentacoes": len(movs),
            "ultimo_movimento": ultimo_mov.get("nome"),
            "data_ultimo_movimento": (ultimo_mov.get("dataHora") or "")[:10],
            "fonte": "CNJ / DataJud (Base Nacional de Dados do Poder Judiciário)",
            "is_synthetic": False,
        }
