"""
Segurança pública: taxa nacional de homicídios a partir do Atlas da Violência (IPEA) — dados do SIM/DataSUS.

Fonte: API de dados do Atlas da Violência (https://www.ipea.gov.br/atlasviolencia), séries
  - 328 "Homicídios registrados" (contagem por UF e ano);
  - 20  "Taxa de homicídios registrados" (por 100 mil habitantes, por UF e ano).
A taxa NACIONAL é calculada como Σ homicídios / Σ população × 100 mil, onde a população de cada UF é a implícita
nas duas séries do próprio Atlas (população = homicídios ÷ taxa × 100 mil): numerador e denominador vêm da mesma
fonte e do mesmo ano, sem misturar com estimativas externas.

FEMINICÍDIO: não há fonte oficial aberta e automatizável (a tipificação é de 2015 e os dados estão em relatórios do
FBSP/Sinesp, sem API). Por isso `taxa_feminicidios` fica None em todos os anos — antes eram valores digitados e,
até 2014, retroações estimadas. O Atlas só publica HOMICÍDIOS DE MULHERES, conceito diferente, e não é usado aqui.
"""

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from etl.config import PROCESSED_DATA_DIR, RAW_DATA_DIR
from etl.utils.http_client import HttpClient, HttpError
from etl.utils.io_utils import atomic_write_json, atomic_write_text, write_json_if_valid
from etl.utils.provenance import mark_official
from etl.utils.sidra import UF_POR_CODIGO_IBGE

logger = logging.getLogger("SegurancaExtractor")

ATLAS_API = "https://www.ipea.gov.br/dados-api"
SERIE_HOMICIDIOS = 328
SERIE_TAXA_HOMICIDIOS = 20
ABRANGENCIA_UF = 3
PRIMEIRO_ANO = 1992
CACHE_TTL_HORAS = 24 * 7
FONTE = "IPEA — Atlas da Violência (SIM/DataSUS), séries 328 e 20"

# Faixa plausível da taxa nacional (por 100 mil) — protege contra resposta corrompida
TAXA_MIN, TAXA_MAX = 5.0, 80.0


class SegurancaExtractor:
    """Taxa nacional de homicídios por ano calculada a partir das séries por UF do Atlas da Violência."""

    def __init__(
        self,
        raw_cache_dir: Path = RAW_DATA_DIR,
        processed_dir: Path = PROCESSED_DATA_DIR,
        http: Optional[HttpClient] = None,
    ):
        self.raw_dir = Path(raw_cache_dir) / "atlas_violencia"
        self.processed_dir = Path(processed_dir)
        self.output_json = self.processed_dir / "seguranca_publica_historico.json"
        self.output_csv = self.processed_dir / "seguranca_publica_historico.csv"
        self.http = http or HttpClient(timeout=120.0, max_retries=4, min_interval=0.3)
        self._registros: Optional[List[Dict[str, Any]]] = None

    # ------------------------------------------------------------------ Atlas
    def _serie_uf(self, serie: int, use_cache: bool = True) -> List[Dict[str, Any]]:
        cache = self.raw_dir / f"serie_{serie}_uf.json"
        if use_cache and cache.exists() and (time.time() - cache.stat().st_mtime) < CACHE_TTL_HORAS * 3600:
            try:
                import json

                with open(cache, "r", encoding="utf-8") as fh:
                    dados = json.load(fh)
                if isinstance(dados, list) and dados:
                    return dados
            except (OSError, ValueError):
                pass
        dados = self.http.get_json(f"{ATLAS_API}/series-values/{serie}/{ABRANGENCIA_UF}/")
        if not isinstance(dados, list) or not dados:
            raise HttpError(f"{ATLAS_API}/series-values/{serie}/{ABRANGENCIA_UF}/", None, "Resposta vazia do Atlas")
        atomic_write_json(cache, dados, indent=None)
        return dados

    @staticmethod
    def _por_uf_ano(dados: List[Dict[str, Any]]) -> Dict[tuple, float]:
        saida: Dict[tuple, float] = {}
        for r in dados:
            try:
                uf = UF_POR_CODIGO_IBGE[int(r["regiao_id"])]
                ano = int(str(r["periodo"])[:4])
                valor = float(r["valor"])
            except (KeyError, ValueError, TypeError):
                continue
            saida[(uf, ano)] = valor
        return saida

    def calcular_taxas_nacionais(
        self, homicidios: Dict[tuple, float], taxas: Dict[tuple, float]
    ) -> List[Dict[str, Any]]:
        """Σ homicídios / Σ população implícita × 100 mil; só anos com as 27 UFs presentes nas duas séries."""
        anos = sorted({a for (_, a) in homicidios if a >= PRIMEIRO_ANO})
        resultado: List[Dict[str, Any]] = []
        for ano in anos:
            total_hom = 0.0
            total_pop = 0.0
            ufs = 0
            for uf in UF_POR_CODIGO_IBGE.values():
                h = homicidios.get((uf, ano))
                t = taxas.get((uf, ano))
                if h is None or not t:
                    continue
                total_hom += h
                total_pop += h / t * 100_000.0
                ufs += 1
            if ufs != len(UF_POR_CODIGO_IBGE) or total_pop <= 0:
                logger.warning("Ano %s ignorado: %d/27 UFs com dados nas duas séries.", ano, ufs)
                continue
            taxa = total_hom / total_pop * 100_000.0
            if not (TAXA_MIN <= taxa <= TAXA_MAX):
                logger.error("Ano %s com taxa implausível (%.2f): ignorado.", ano, taxa)
                continue
            resultado.append(
                {
                    "ano": ano,
                    "taxa_homicidios": round(taxa, 2),
                    "homicidios_total": int(round(total_hom)),
                    "taxa_feminicidios": None,
                    "status_dado": "oficial",
                }
            )
        return resultado

    # ------------------------------------------------------------------ API pública (compatível)
    def fetch_seguranca_history(self, use_cache: bool = True) -> pd.DataFrame:
        """Consulta o Atlas, calcula a série nacional e a grava (JSON/CSV atômicos; nunca grava vazio)."""
        logger.info("Consultando o Atlas da Violência (IPEA) — homicídios por UF...")
        try:
            homicidios = self._por_uf_ano(self._serie_uf(SERIE_HOMICIDIOS, use_cache))
            taxas = self._por_uf_ano(self._serie_uf(SERIE_TAXA_HOMICIDIOS, use_cache))
        except HttpError as exc:
            logger.error("Atlas da Violência indisponível: %s. Arquivos anteriores preservados.", exc)
            self._registros = self._ler_existente()
            return pd.DataFrame(self._registros)

        registros = [mark_official(r, FONTE) for r in self.calcular_taxas_nacionais(homicidios, taxas)]
        if write_json_if_valid(self.output_json, registros, label="seguranca_publica_historico.json"):
            atomic_write_text(self.output_csv, pd.DataFrame(registros).to_csv(index=False))
            logger.info("-> %d anos de homicídios (oficiais) em %s", len(registros), self.output_json)
            self._registros = registros
        else:
            self._registros = self._ler_existente()
        return pd.DataFrame(self._registros)

    def _ler_existente(self) -> List[Dict[str, Any]]:
        from etl.utils.datafiles import load_json

        return load_json(self.output_json, []) or []

    def _garantir(self) -> List[Dict[str, Any]]:
        if self._registros is None:
            self.fetch_seguranca_history()
        return self._registros or []

    def get_annual_homicide_rates(self) -> Dict[int, float]:
        """{ano: taxa de homicídios por 100 mil hab.} dos anos com dado oficial."""
        return {r["ano"]: r["taxa_homicidios"] for r in self._garantir() if r.get("taxa_homicidios") is not None}

    def get_annual_feminicide_rates(self) -> Dict[int, float]:
        """Sempre vazio: não há fonte oficial aberta e automatizável de feminicídios (ver docstring do módulo)."""
        return {}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    extractor = SegurancaExtractor()
    print(extractor.fetch_seguranca_history(use_cache=False).tail(10))
