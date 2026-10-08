"""
Desmatamento da Amazônia Legal — taxas anuais oficiais do PRODES/INPE (TerraBrasilis).

Fonte oficial: arquivo `ratesAAAA.json` publicado pelo painel TerraBrasilis
(https://terrabrasilis.dpi.inpe.br/app/prodes/dashboard/deforestation/files/), com a taxa consolidada de cada
período PRODES (1º ago do ano anterior a 31 jul do ano de referência) por Estado. A taxa da Amazônia Legal é a
soma dos Estados. O nome do arquivo traz o ano da última atualização (hoje `rates2025.json`): o extrator testa os
anos mais recentes até achar um.

Por que não somar as feições do WFS: a soma de `area_km` das geometrias NÃO reproduz a taxa oficial (diferenças de
até 12%), porque a taxa oficial é estimada com tratamento de áreas cobertas por nuvem.

As taxas de 1993 e 1994 são a média 1993-94 divulgada pelo INPE (mesmo valor nos dois anos).
"""

import json
import logging
import time
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from etl.config import PROCESSED_DATA_DIR, RAW_DATA_DIR
from etl.utils.http_client import HttpClient, HttpError
from etl.utils.io_utils import atomic_write_json

logger = logging.getLogger("INPEExtractor")

BASE_ARQUIVOS = "https://terrabrasilis.dpi.inpe.br/app/prodes/dashboard/deforestation/files"
CACHE_TTL_HORAS = 24 * 7
TIPO_TAXA = 1  # `type` 1 = taxa de desmatamento (km²)
FONTE = "INPE / PRODES — taxa anual consolidada (TerraBrasilis)"
# Faixa plausível (km²/ano) para recusar resposta corrompida; a série real fica entre ~4,5 mil e ~30 mil.
TAXA_MIN_KM2, TAXA_MAX_KM2 = 1_000.0, 60_000.0
NOTA_MEDIA_1993_94 = "Média 1993-94 divulgada pelo INPE (mesmo valor nos dois anos)"


def taxas_por_periodo(payload: Dict[str, Any]) -> Dict[int, float]:
    """{ano de referência PRODES: km²} somando os Estados de cada período."""
    periodos = payload.get("periods") if isinstance(payload, dict) else None
    if not isinstance(periodos, list) or not periodos:
        raise HttpError(BASE_ARQUIVOS, None, "Arquivo de taxas do PRODES sem 'periods'")
    serie: Dict[int, float] = {}
    for periodo in periodos:
        try:
            ano = int(periodo["endDate"]["year"])
            total = sum(
                float(area["area"])
                for feicao in periodo["features"]
                for area in feicao["areas"]
                if area.get("type") == TIPO_TAXA
            )
        except (KeyError, TypeError, ValueError):
            continue
        if not (TAXA_MIN_KM2 <= total <= TAXA_MAX_KM2):
            logger.warning("PRODES %s fora da faixa plausível (%.1f km²): descartado.", ano, total)
            continue
        serie[ano] = round(total, 1)
    return serie


class INPEExtractor:
    """Consome as taxas anuais oficiais de desmatamento da Amazônia Legal."""

    def __init__(
        self,
        raw_cache_dir: Path = RAW_DATA_DIR,
        processed_dir: Path = PROCESSED_DATA_DIR,
        http: Optional[HttpClient] = None,
        hoje: Optional[date] = None,
    ):
        self.cache_dir = Path(raw_cache_dir) / "prodes"
        self.processed_dir = Path(processed_dir)
        self.cache_file = self.cache_dir / "prodes_taxas_amazonia_legal.json"
        self.http = http or HttpClient(timeout=60.0, max_retries=3, min_interval=0.5)
        self.hoje = hoje or date.today()
        self._serie: Optional[Dict[int, float]] = None

    # ------------------------------------------------------------------ download
    def _baixar_payload(self) -> Dict[str, Any]:
        """Procura `rates{ano}.json` do ano seguinte para trás (o INPE publica o arquivo com o ano da revisão)."""
        for ano in range(self.hoje.year + 1, self.hoje.year - 4, -1):
            url = f"{BASE_ARQUIVOS}/rates{ano}.json"
            try:
                payload = self.http.get_json(url)
            except HttpError as exc:
                if exc.status == 404:
                    continue
                raise
            logger.info("Taxas PRODES obtidas de %s", url)
            return payload
        raise HttpError(BASE_ARQUIVOS, 404, "Nenhum arquivo ratesAAAA.json encontrado")

    def _ler_cache(self) -> Optional[Dict[int, float]]:
        if not self.cache_file.exists() or (time.time() - self.cache_file.stat().st_mtime) > CACHE_TTL_HORAS * 3600:
            return None
        return self._ler_arquivo_cache()

    def _ler_arquivo_cache(self) -> Optional[Dict[int, float]]:
        try:
            with open(self.cache_file, "r", encoding="utf-8") as fh:
                return {int(a): float(v) for a, v in json.load(fh).items()}
        except (OSError, ValueError, AttributeError):
            return None

    # ------------------------------------------------------------------ série
    def fetch_series(self, use_cache: bool = True) -> Dict[int, float]:
        """{ano-PRODES: km²}. Falha de rede usa o cache anterior; sem cache, levanta erro (nunca devolve vazio)."""
        if use_cache:
            cache = self._ler_cache()
            if cache:
                return cache
        try:
            serie = taxas_por_periodo(self._baixar_payload())
        except HttpError as exc:
            logger.error("TerraBrasilis indisponível: %s", exc)
            antigo = self._ler_arquivo_cache()
            if antigo:
                return antigo
            raise
        if not serie:
            raise HttpError(BASE_ARQUIVOS, None, "Nenhuma taxa PRODES válida obtida")
        atomic_write_json(self.cache_file, {str(a): v for a, v in sorted(serie.items())})
        return serie

    def fetch_deforestation_history(self, use_cache: bool = True) -> pd.DataFrame:
        serie = self.fetch_series(use_cache=use_cache)
        self._serie = serie
        registros: List[Dict[str, Any]] = []
        for ano, km2 in sorted(serie.items()):
            registro: Dict[str, Any] = {
                "ano": ano,
                "desmatamento_km2": km2,
                "fonte": FONTE,
                "unidade": "km²",
                "is_synthetic": False,
            }
            if ano in (1993, 1994):
                registro["nota"] = NOTA_MEDIA_1993_94
            registros.append(registro)
        return pd.DataFrame(registros)

    def get_deforestation_for_years(self, years: List[int]) -> Dict[str, Any]:
        """Total acumulado e média anual de desmatamento para os anos informados (ex.: um mandato)."""
        serie = self._serie if self._serie is not None else self.fetch_series()
        valores = [serie[y] for y in years if y in serie]
        if not valores:
            return {"desmatamento_acumulado_km2": None, "desmatamento_medio_anual_km2": None, "anos_com_dados": 0}
        total = round(float(sum(valores)), 1)
        return {
            "desmatamento_acumulado_km2": total,
            "desmatamento_medio_anual_km2": round(total / len(valores), 1),
            "anos_com_dados": len(valores),
        }
