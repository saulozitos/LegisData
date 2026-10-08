"""
Extrator de Despesas da Cota para o Exercício da Atividade Parlamentar (CEAP)
API da Câmara dos Deputados (v2) e séries históricas consolidadas.
User-Agent: LegisDataBot/1.0
"""

import json
import logging
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from etl.config import RAW_DATA_DIR, PROCESSED_DATA_DIR, DEFAULT_USER_AGENT

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CeapExtractor")


class CeapExtractor:
    """Extrai notas fiscais e gastos da Cota Parlamentar (CEAP)."""

    def __init__(self, raw_dir: Path = RAW_DATA_DIR, processed_dir: Path = PROCESSED_DATA_DIR):
        self.raw_dir = raw_dir
        self.processed_dir = processed_dir
        self.headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/json"
        }

    def fetch_deputado_despesas(self, camara_id: int, anos: List[int] = [2023, 2024, 2025]) -> List[Dict[str, Any]]:
        """Busca despesas na API da Câmara dos Deputados para um parlamentar."""
        despesas = []
        for ano in anos:
            url = f"https://dadosabertos.camara.leg.br/api/v2/deputados/{camara_id}/despesas?ano={ano}&itens=100&ordem=DESC&ordenarPor=mes"
            try:
                time.sleep(0.1)
                req = urllib.request.Request(url, headers=self.headers)
                with urllib.request.urlopen(req, timeout=12) as response:
                    if response.status == 200:
                        data = json.loads(response.read().decode("utf-8"))
                        itens = data.get("dados", [])
                        for item in itens:
                            val_liq = item.get("valorLiquido") or item.get("valorDocumento") or 0.0
                            if val_liq > 0:
                                despesas.append({
                                    "ano": int(item.get("ano", ano)),
                                    "mes": int(item.get("mes", 1)) if item.get("mes") else None,
                                    "tipo_despesa": item.get("tipoDespesa", "OUTROS SERVIÇOS"),
                                    "valor_liquido": float(val_liq),
                                    "nome_fornecedor": item.get("nomeFornecedor", "Fornecedor não informado"),
                                    "cnpj_cpf_fornecedor": item.get("cnpjCpfFornecedor"),
                                    "data_emissao": item.get("dataDocumento"),
                                    "documento_url": item.get("urlDocumento")
                                })
            except Exception as e:
                logger.warning(f"Erro ao buscar CEAP da Câmara para id {camara_id} ano {ano}: {e}")
                break

        return despesas
