"""
Identidades de parlamentares (CPF, data de nascimento, nome civil) para casar com os dados do TSE sem
depender de nome parecido.

Os dados vêm das APIs oficiais de detalhe (Câmara: `/deputados/{id}`; Senado: `/senador/{codigo}`). O CPF é dado
pessoal: fica SOMENTE no cache bruto (`etl/data/raw/`, ignorado pelo git) e na memória do processo de extração.
Os arquivos processados do ETL (versionados) nunca recebem CPF.
"""

import logging
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from etl.config import RAW_DATA_DIR
from etl.utils.datafiles import load_json
from etl.utils.http_client import HttpClient, HttpError
from etl.utils.io_utils import atomic_write_json

logger = logging.getLogger("Identidades")

CAMARA_DETALHE = "https://dadosabertos.camara.leg.br/api/v2/deputados/{id}"
SENADO_DETALHE = "https://legis.senado.leg.br/dadosabertos/senador/{id}"
CACHE_NAME = "identidades_parlamentares.json"


def only_digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def valid_cpf(value: Any) -> Optional[str]:
    """CPF com 11 dígitos que não seja a máscara do TSE (`-1`, `-4`, zeros) — senão None."""
    digits = only_digits(value)
    if len(digits) != 11 or len(set(digits)) == 1:
        return None
    return digits


def parse_date(value: Any) -> Optional[date]:
    """Aceita `YYYY-MM-DD` (APIs) e `DD/MM/YYYY` (TSE)."""
    text = str(value or "").strip()
    for pattern, order in ((r"^(\d{4})-(\d{2})-(\d{2})", (0, 1, 2)), (r"^(\d{2})/(\d{2})/(\d{4})", (2, 1, 0))):
        m = re.match(pattern, text)
        if m:
            parts = [int(g) for g in m.groups()]
            try:
                return date(parts[order[0]], parts[order[1]], parts[order[2]])
            except ValueError:
                return None
    return None


class IdentidadesParlamentares:
    """Cache de identidades por chave `camara:{id}` / `senado:{id}`; só consulta a API para o que falta."""

    def __init__(self, raw_dir: Path = RAW_DATA_DIR, http: Optional[HttpClient] = None, offline: bool = False):
        self.path = Path(raw_dir) / CACHE_NAME
        self.http = http or HttpClient(timeout=20.0, max_retries=3, min_interval=0.05)
        self.offline = offline
        self.data: Dict[str, Dict[str, Any]] = load_json(self.path, {}) or {}

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        return self.data.get(key)

    def _fetch_camara(self, camara_id: int) -> Optional[Dict[str, Any]]:
        try:
            dados = self.http.get_json(CAMARA_DETALHE.format(id=camara_id)).get("dados") or {}
        except HttpError as exc:
            logger.debug("Detalhe da Câmara indisponível para %s: %s", camara_id, exc)
            return None
        return {
            "nome_civil": dados.get("nomeCivil"),
            "cpf": valid_cpf(dados.get("cpf")),
            "data_nascimento": dados.get("dataNascimento"),
            "uf_nascimento": dados.get("ufNascimento"),
        }

    def _fetch_senado(self, senado_id: int) -> Optional[Dict[str, Any]]:
        try:
            parlamentar = self.http.get_json(SENADO_DETALHE.format(id=senado_id))["DetalheParlamentar"]["Parlamentar"]
        except (HttpError, KeyError, TypeError) as exc:
            logger.debug("Detalhe do Senado indisponível para %s: %s", senado_id, exc)
            return None
        basicos = parlamentar.get("DadosBasicosParlamentar") or {}
        ident = parlamentar.get("IdentificacaoParlamentar") or {}
        return {
            "nome_civil": ident.get("NomeCompletoParlamentar"),
            "cpf": None,
            "data_nascimento": basicos.get("DataNascimento"),
            "uf_nascimento": basicos.get("UfNaturalidade"),
        }

    def enrich(self, camara_ids: Iterable[int], senado_ids: Iterable[int]) -> int:
        """Busca as identidades que ainda não estão em cache. Devolve quantas foram obtidas agora."""
        obtidas = 0
        pendentes: List[tuple] = [("camara", i) for i in camara_ids if i and f"camara:{i}" not in self.data]
        pendentes += [("senado", i) for i in senado_ids if i and f"senado:{i}" not in self.data]
        if self.offline or not pendentes:
            return 0
        logger.info("Consultando %d identidades parlamentares nas APIs oficiais...", len(pendentes))
        for n, (casa, ident) in enumerate(pendentes, 1):
            registro = self._fetch_camara(ident) if casa == "camara" else self._fetch_senado(ident)
            if registro:
                self.data[f"{casa}:{ident}"] = registro
                obtidas += 1
            if n % 100 == 0:
                atomic_write_json(self.path, self.data, indent=None)
        if obtidas:
            atomic_write_json(self.path, self.data, indent=None)
        logger.info("Identidades obtidas: %d de %d.", obtidas, len(pendentes))
        return obtidas
