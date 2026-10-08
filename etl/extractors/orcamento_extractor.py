#!/usr/bin/env python3
"""
ATENÇÃO: este módulo NÃO extrai dados — ele MODELA repasses (volume fixo por
mandato x peso populacional/FPE x pesos fixos por área). A saída é exibida como
estimativa (`dados_estimados`). Substituir por Tesouro Transparente / Portal da
Transparência (transferências por UF) é trabalho futuro.

Extrator de Execução Orçamentária e Repasses Federais por Estado (UF)
Fontes de dados: Portal da Transparência do Governo Federal / Tesouro Nacional (Siga Brasil / SIAFI)
Áreas temáticas: Saúde, Educação, Infraestrutura e Segurança Pública
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any
import pandas as pd

from etl.config import PROCESSED_DATA_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("OrcamentoExtractor")

# Catálogo oficial das 27 Unidades da Federação e População Estimada (IBGE)
ESTADOS_BRASIL = [
    {"uf": "AC", "nome": "Acre", "regiao": "Norte", "populacao": 830026, "peso_fpe": 0.044},
    {"uf": "AL", "nome": "Alagoas", "regiao": "Nordeste", "populacao": 3127511, "peso_fpe": 0.041},
    {"uf": "AP", "nome": "Amapá", "regiao": "Norte", "populacao": 733508, "peso_fpe": 0.034},
    {"uf": "AM", "nome": "Amazonas", "regiao": "Norte", "populacao": 3941175, "peso_fpe": 0.028},
    {"uf": "BA", "nome": "Bahia", "regiao": "Nordeste", "populacao": 14136417, "peso_fpe": 0.093},
    {"uf": "CE", "nome": "Ceará", "regiao": "Nordeste", "populacao": 8791688, "peso_fpe": 0.073},
    {"uf": "DF", "nome": "Distrito Federal", "regiao": "Centro-Oeste", "populacao": 2817068, "peso_fpe": 0.007},
    {"uf": "ES", "nome": "Espírito Santo", "regiao": "Sudeste", "populacao": 3833486, "peso_fpe": 0.015},
    {"uf": "GO", "nome": "Goiás", "regiao": "Centro-Oeste", "populacao": 7055228, "peso_fpe": 0.028},
    {"uf": "MA", "nome": "Maranhão", "regiao": "Nordeste", "populacao": 6775152, "peso_fpe": 0.072},
    {"uf": "MT", "nome": "Mato Grosso", "regiao": "Centro-Oeste", "populacao": 3658813, "peso_fpe": 0.023},
    {"uf": "MS", "nome": "Mato Grosso do Sul", "regiao": "Centro-Oeste", "populacao": 2756700, "peso_fpe": 0.013},
    {"uf": "MG", "nome": "Minas Gerais", "regiao": "Sudeste", "populacao": 20538718, "peso_fpe": 0.045},
    {"uf": "PA", "nome": "Pará", "regiao": "Norte", "populacao": 8116132, "peso_fpe": 0.061},
    {"uf": "PB", "nome": "Paraíba", "regiao": "Nordeste", "populacao": 3974495, "peso_fpe": 0.048},
    {"uf": "PR", "nome": "Paraná", "regiao": "Sul", "populacao": 11443208, "peso_fpe": 0.029},
    {"uf": "PE", "nome": "Pernambuco", "regiao": "Nordeste", "populacao": 9058155, "peso_fpe": 0.065},
    {"uf": "PI", "nome": "Piauí", "regiao": "Nordeste", "populacao": 3269200, "peso_fpe": 0.043},
    {"uf": "RJ", "nome": "Rio de Janeiro", "regiao": "Sudeste", "populacao": 16054524, "peso_fpe": 0.015},
    {"uf": "RN", "nome": "Rio Grande do Norte", "regiao": "Nordeste", "populacao": 3302406, "peso_fpe": 0.042},
    {"uf": "RS", "nome": "Rio Grande do Sul", "regiao": "Sul", "populacao": 10880506, "peso_fpe": 0.023},
    {"uf": "RO", "nome": "Rondônia", "regiao": "Norte", "populacao": 1581016, "peso_fpe": 0.028},
    {"uf": "RR", "nome": "Roraima", "regiao": "Norte", "populacao": 636303, "peso_fpe": 0.025},
    {"uf": "SC", "nome": "Santa Catarina", "regiao": "Sul", "populacao": 7609601, "peso_fpe": 0.013},
    {"uf": "SP", "nome": "São Paulo", "regiao": "Sudeste", "populacao": 44420459, "peso_fpe": 0.010},
    {"uf": "SE", "nome": "Sergipe", "regiao": "Nordeste", "populacao": 2209558, "peso_fpe": 0.042},
    {"uf": "TO", "nome": "Tocantins", "regiao": "Norte", "populacao": 1511459, "peso_fpe": 0.043}
]

# Orçamento anual médio federal repassado a estados/municípios por mandato (em Bilhões de R$ correntes)
ORCAMENTO_MANDATOS = {
    "itamar-franco-1992": {"ano_referencia": 1994, "fator_escala": 18.5},
    "fhc-1995": {"ano_referencia": 1997, "fator_escala": 42.0},
    "fhc-1999": {"ano_referencia": 2001, "fator_escala": 78.5},
    "lula-2003": {"ano_referencia": 2005, "fator_escala": 135.0},
    "lula-2007": {"ano_referencia": 2009, "fator_escala": 210.0},
    "dilma-2011": {"ano_referencia": 2013, "fator_escala": 295.0},
    "dilma-2015": {"ano_referencia": 2015, "fator_escala": 340.0},
    "temer-2016": {"ano_referencia": 2017, "fator_escala": 365.0},
    "bolsonaro-2019": {"ano_referencia": 2021, "fator_escala": 480.0},
    "lula-2023": {"ano_referencia": 2023, "fator_escala": 560.0}
}

# Distribuição média das áreas no Orçamento da União para estados/municípios
AREAS_PESOS = {
    "Saúde": 0.42,          # FNS, Repasses SUS, Teto MAC, Atenção Básica
    "Educação": 0.33,       # FUNDEB complementação, FNDE, Merenda, Transporte Escolar
    "Infraestrutura": 0.16, # Cidades, Saneamento, Rodovias, Habitação
    "Segurança Pública": 0.09 # FNSP, Fundo Penitenciário, SUSP
}


class OrcamentoExtractor:
    """Extrai e modela repasses e execução orçamentária federal por UF."""

    def __init__(self, output_dir: Path = PROCESSED_DATA_DIR):
        self.output_dir = output_dir

    def generate_federal_transfers(self) -> List[Dict[str, Any]]:
        """Gera dataset estruturado de transferências federais por estado para todos os mandatos."""
        logger.info("Iniciando processamento de repasses federais por UF e áreas temáticas...")
        records = []

        total_populacao_brasil = sum(e["populacao"] for e in ESTADOS_BRASIL)

        for mandate_id, info in ORCAMENTO_MANDATOS.items():
            ano = info["ano_referencia"]
            volume_bilhoes = info["fator_escala"] # Em Bilhões de R$

            for est in ESTADOS_BRASIL:
                # O repasse combina peso populacional (70%) com critérios de equalização regional/FPE (30%)
                peso_pop = est["populacao"] / total_populacao_brasil
                peso_fpe = est["peso_fpe"]
                peso_combinado = (peso_pop * 0.70) + (peso_fpe * 0.30)

                recurso_total_estado = (volume_bilhoes * 1_000_000_000.0) * peso_combinado

                for area, peso_area in AREAS_PESOS.items():
                    valor_area = round(recurso_total_estado * peso_area, 2)
                    per_capita = round(valor_area / est["populacao"], 2)

                    records.append({
                        "mandato_id_ref": mandate_id,
                        "ano": ano,
                        "uf": est["uf"],
                        "estado_nome": est["nome"],
                        "regiao": est["regiao"],
                        "area_tematica": area,
                        "valor_pago_brl": valor_area,
                        "populacao_estimada": est["populacao"],
                        "valor_per_capita_brl": per_capita
                    })

        logger.info(f"Gerados {len(records)} registros de repasses federais por UF.")
        return records

    def run(self) -> Dict[str, Any]:
        """Salva os datasets em JSON e CSV."""
        transfers = self.generate_federal_transfers()

        json_path = self.output_dir / "repasses_federais_uf.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(transfers, f, ensure_ascii=False, indent=2)

        csv_path = self.output_dir / "repasses_federais_uf.csv"
        df = pd.DataFrame(transfers)
        df.to_csv(csv_path, index=False)

        logger.info(f"Arquivos salvos em {json_path} e {csv_path}")
        return {"total_registros": len(transfers), "json_path": str(json_path)}


if __name__ == "__main__":
    extractor = OrcamentoExtractor()
    extractor.run()
