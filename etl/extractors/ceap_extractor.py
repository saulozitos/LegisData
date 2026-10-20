"""
Extrator de Despesas da Cota para o Exercício da Atividade Parlamentar (CEAP)
API da Câmara dos Deputados (v2).
"""

import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from etl.config import PROCESSED_DATA_DIR, RAW_DATA_DIR
from etl.utils.http_client import HttpClient, HttpError
from etl.utils.provenance import mark_official, mark_synthetic

logger = logging.getLogger("CeapExtractor")

DEFAULT_ANOS = (2023, 2024, 2025)
ITENS_POR_PAGINA = 100
FONTE_CAMARA = "API Dados Abertos da Câmara dos Deputados (CEAP)"


class CeapExtractor:
    """Extrai notas fiscais e gastos da Cota Parlamentar (CEAP)."""

    def __init__(
        self, raw_dir: Path = RAW_DATA_DIR, processed_dir: Path = PROCESSED_DATA_DIR, http: Optional[HttpClient] = None
    ):
        self.raw_dir = raw_dir
        self.processed_dir = processed_dir
        self.http = http or HttpClient(timeout=20.0, max_retries=3, min_interval=0.1)

    def fetch_deputado_despesas(self, camara_id: int, anos: Optional[List[int]] = None) -> List[Dict[str, Any]]:
        """
        Busca TODAS as despesas (todas as páginas) de um deputado nos anos pedidos.
        Falha em um ano não aborta os demais; a falha é registrada e o ano segue sem dados.
        """
        despesas: List[Dict[str, Any]] = []
        for ano in anos or list(DEFAULT_ANOS):
            pagina = 1
            while True:
                url = (
                    f"https://dadosabertos.camara.leg.br/api/v2/deputados/{camara_id}/despesas"
                    f"?ano={ano}&itens={ITENS_POR_PAGINA}&pagina={pagina}&ordem=ASC&ordenarPor=mes"
                )
                try:
                    data = self.http.get_json(url)
                except HttpError as exc:
                    logger.warning("CEAP do deputado %s (ano %s, página %s) falhou: %s", camara_id, ano, pagina, exc)
                    break

                itens = data.get("dados", []) or []
                for item in itens:
                    val_liq = item.get("valorLiquido")
                    if val_liq is None:
                        val_liq = item.get("valorDocumento")
                    if not val_liq or float(val_liq) <= 0:
                        continue
                    mes = item.get("mes")
                    despesas.append(
                        mark_official(
                            {
                                "ano": int(item.get("ano") or ano),
                                "mes": int(mes) if mes else None,
                                "tipo_despesa": item.get("tipoDespesa") or "NÃO INFORMADO",
                                "valor_liquido": float(val_liq),
                                "nome_fornecedor": item.get("nomeFornecedor") or "Fornecedor não informado",
                                "cnpj_cpf_fornecedor": item.get("cnpjCpfFornecedor"),
                                "data_emissao": item.get("dataDocumento"),
                                "documento_url": item.get("urlDocumento"),
                            },
                            FONTE_CAMARA,
                        )
                    )

                tem_proxima = any(link.get("rel") == "next" for link in data.get("links", []) or [])
                if not tem_proxima or len(itens) < ITENS_POR_PAGINA:
                    break
                pagina += 1

        return despesas

    def generate_representative_ceap(
        self, politician_name: str, uf: str = "DF", allow_synthetic: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Amostra SINTÉTICA de gastos (fornecedores e valores fictícios). Desligada por padrão: só existe
        para demonstrações locais e todos os registros saem com `is_synthetic=True`.
        """
        if not allow_synthetic:
            return []

        fornecedores_tipicos = [
            ("FORNECEDOR FICTÍCIO DE PASSAGENS AÉREAS", None, "PASSAGEM AÉREA", 2450.80),
            ("FORNECEDOR FICTÍCIO DE COMBUSTÍVEIS", None, "COMBUSTÍVEIS E LUBRIFICANTES", 450.00),
            ("FORNECEDOR FICTÍCIO DE DIVULGAÇÃO", None, "DIVULGAÇÃO DA ATIVIDADE PARLAMENTAR", 8500.00),
            ("FORNECEDOR FICTÍCIO DE LOCAÇÃO DE VEÍCULOS", None, "LOCAÇÃO DE VEÍCULOS AUTOMOTORES", 4200.00),
        ]
        gastos = []
        for ano in DEFAULT_ANOS:
            for mes in (2, 4, 6, 8, 10, 12):
                for f_nome, f_cnpj, tipo, base_val in fornecedores_tipicos:
                    digest = hashlib.sha1(f"{politician_name}|{ano}|{mes}|{f_nome}".encode("utf-8")).hexdigest()[:8]
                    gastos.append(
                        mark_synthetic(
                            {
                                "ano": ano,
                                "mes": mes,
                                "tipo_despesa": tipo,
                                "valor_liquido": round(base_val * (0.9 + mes * 0.03), 2),
                                "nome_fornecedor": f_nome,
                                "cnpj_cpf_fornecedor": f_cnpj,
                                "data_emissao": None,
                                "documento_url": None,
                                "id_sintetico": digest,
                            }
                        )
                    )
        return gastos
