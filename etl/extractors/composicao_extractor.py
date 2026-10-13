#!/usr/bin/env python3
"""
Extrator e Curador da Composição dos Poderes no Congresso Nacional (1992 - Presente)
Fontes de dados: Arquivo Histórico da Câmara dos Deputados e do Senado Federal
Mapeia: Presidentes das Casas, Tamanho das Bancadas e Governabilidade por Mandato Presidencial.
"""

import json
import logging
from typing import Any, Callable, Dict, List, Optional

from etl.config import PROCESSED_DATA_DIR
from etl.utils.io_utils import atomic_write_json

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ComposicaoExtractor")

# Catálogo histórico curado da composição dos poderes por mandato
# Princípio de Confiabilidade Oficial: Cada bancada reflete exatamente seu partido oficial,
# sem agrupamento em "Outros".
CORES_PARTIDOS: Dict[str, str] = {
    "PL": "#1d4ed8", "PT": "#ef4444", "UNIÃO": "#0284c7", "PP": "#3b82f6", "MDB": "#15803d",
    "PMDB": "#15803d", "PSD": "#f59e0b", "REPUBLICANOS": "#0369a1", "PRB": "#0369a1",
    "PDT": "#dc2626", "PSB": "#ea580c", "PSDB": "#38bdf8", "PSOL": "#facc15", "PODE": "#06b6d4",
    "PODEMOS": "#06b6d4", "AVANTE": "#f97316", "PCdoB": "#b91c1c", "PC do B": "#b91c1c",
    "PSC": "#0284c7", "PV": "#16a34a", "CIDADANIA": "#f97316", "PPS": "#f97316",
    "PATRIOTA": "#10b981", "SOLIDARIEDADE": "#e11d48", "SD": "#e11d48", "NOVO": "#f97316",
    "PROS": "#0ea5e9", "REDE": "#0d9488", "PTB": "#9333ea", "DEM": "#2563eb", "PFL": "#2563eb",
    "PSL": "#1e3a8a", "PR": "#1e3a8a", "PRD": "#8b5cf6", "PDC": "#0284c7", "PDS": "#475569",
    "PPR": "#3b82f6", "PPB": "#3b82f6", "PRN": "#0284c7", "PTR": "#64748b", "PST": "#64748b",
    "PMN": "#dc2626", "PRTB": "#1e3a8a", "PSDC": "#2563eb", "DC": "#2563eb", "PTC": "#f59e0b",
    "PHS": "#059669", "PRP": "#0284c7", "PTN": "#06b6d4", "PT do B": "#f97316", "PRONA": "#eab308",
    "PAN": "#64748b", "PPL": "#dc2626",
}

COMPOSICAO_CONGRESSO_HISTORICO: Dict[str, Any] = {
    "itamar-franco-1992": {
        "mandato_id": "itamar-franco-1992",
        "presidente_republica": "Itamar Franco",
        "periodo": "1992 - 1995",
        "camara": {
            "total_cadeiras": 503,
            "presidentes": [
                {"nome": "Ibsen Pinheiro", "partido": "PMDB", "uf": "RS", "periodo": "1991 - 1993", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/d/da/Ibsen_Pinheiro.jpg"},
                {"nome": "Inocêncio Oliveira", "partido": "PFL", "uf": "PE", "periodo": "1993 - 1995", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/2/23/Inocencio_Oliveira.jpg"}
            ],
            "bancadas": [
                {"partido": "PMDB", "cadeiras": 108, "percentual": 21.5, "alinhamento": "BASE_GOVERNO", "cor_hex": "#15803d"},
                {"partido": "PFL", "cadeiras": 89, "percentual": 17.7, "alinhamento": "BASE_GOVERNO", "cor_hex": "#2563eb"},
                {"partido": "PDT", "cadeiras": 46, "percentual": 9.1, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#dc2626"},
                {"partido": "PDS", "cadeiras": 42, "percentual": 8.3, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#475569"},
                {"partido": "PRN", "cadeiras": 40, "percentual": 8.0, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#0284c7"},
                {"partido": "PTB", "cadeiras": 38, "percentual": 7.6, "alinhamento": "BASE_GOVERNO", "cor_hex": "#9333ea"},
                {"partido": "PSDB", "cadeiras": 37, "percentual": 7.4, "alinhamento": "BASE_GOVERNO", "cor_hex": "#0284c7"},
                {"partido": "PT", "cadeiras": 35, "percentual": 7.0, "alinhamento": "OPOSICAO", "cor_hex": "#ef4444"},
                {"partido": "PDC", "cadeiras": 22, "percentual": 4.4, "alinhamento": "BASE_GOVERNO", "cor_hex": "#0284c7"},
                {"partido": "PL", "cadeiras": 16, "percentual": 3.2, "alinhamento": "BASE_GOVERNO", "cor_hex": "#1e3a8a"},
                {"partido": "PSB", "cadeiras": 11, "percentual": 2.2, "alinhamento": "OPOSICAO", "cor_hex": "#f97316"},
                {"partido": "PSC", "cadeiras": 6, "percentual": 1.2, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#0284c7"},
                {"partido": "PCdoB", "cadeiras": 5, "percentual": 1.0, "alinhamento": "OPOSICAO", "cor_hex": "#b91c1c"},
                {"partido": "PPS", "cadeiras": 3, "percentual": 0.6, "alinhamento": "OPOSICAO", "cor_hex": "#f97316"},
                {"partido": "PTR", "cadeiras": 2, "percentual": 0.4, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#64748b"},
                {"partido": "PST", "cadeiras": 2, "percentual": 0.4, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#64748b"},
                {"partido": "PMN", "cadeiras": 1, "percentual": 0.2, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#dc2626"}
            ],
            "governabilidade": {
                "base_aliada_cadeiras": 310,
                "base_aliada_pct": 61.6,
                "centro_cadeiras": 139,
                "centro_pct": 27.6,
                "oposicao_cadeiras": 54,
                "oposicao_pct": 10.7,
                "maioria_simples_atingida": True,
                "maioria_pec_atingida": True
            }
        },
        "senado": {
            "total_cadeiras": 81,
            "presidentes": [
                {"nome": "Mauro Benevides", "partido": "PMDB", "uf": "CE", "periodo": "1991 - 1993", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/4/4b/Mauro_Benevides.jpg"},
                {"nome": "Humberto Lucena", "partido": "PMDB", "uf": "PB", "periodo": "1993 - 1995", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/3/36/Humberto_Lucena.jpg"}
            ],
            "bancadas": [
                {"partido": "PMDB", "cadeiras": 27, "percentual": 33.3, "alinhamento": "BASE_GOVERNO", "cor_hex": "#15803d"},
                {"partido": "PFL", "cadeiras": 18, "percentual": 22.2, "alinhamento": "BASE_GOVERNO", "cor_hex": "#2563eb"},
                {"partido": "PSDB", "cadeiras": 10, "percentual": 12.3, "alinhamento": "BASE_GOVERNO", "cor_hex": "#0284c7"},
                {"partido": "PDS", "cadeiras": 8, "percentual": 9.9, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#475569"},
                {"partido": "PRN", "cadeiras": 5, "percentual": 6.2, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#0284c7"},
                {"partido": "PDC", "cadeiras": 3, "percentual": 3.7, "alinhamento": "BASE_GOVERNO", "cor_hex": "#0284c7"},
                {"partido": "PDT", "cadeiras": 3, "percentual": 3.7, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#dc2626"},
                {"partido": "PT", "cadeiras": 2, "percentual": 2.5, "alinhamento": "OPOSICAO", "cor_hex": "#ef4444"},
                {"partido": "PL", "cadeiras": 2, "percentual": 2.5, "alinhamento": "BASE_GOVERNO", "cor_hex": "#1e3a8a"},
                {"partido": "PSB", "cadeiras": 1, "percentual": 1.2, "alinhamento": "OPOSICAO", "cor_hex": "#f97316"},
                {"partido": "PSC", "cadeiras": 1, "percentual": 1.2, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#0284c7"},
                {"partido": "PTR", "cadeiras": 1, "percentual": 1.2, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#64748b"}
            ],
            "governabilidade": {
                "base_aliada_cadeiras": 60,
                "base_aliada_pct": 74.1,
                "centro_cadeiras": 18,
                "centro_pct": 22.2,
                "oposicao_cadeiras": 3,
                "oposicao_pct": 3.7,
                "maioria_simples_atingida": True,
                "maioria_pec_atingida": True
            }
        }
    },
    "fhc-1995": {
        "mandato_id": "fhc-1995",
        "presidente_republica": "Fernando Henrique Cardoso (FHC 1)",
        "periodo": "1995 - 1999",
        "camara": {
            "total_cadeiras": 513,
            "presidentes": [
                {"nome": "Luís Eduardo Magalhães", "partido": "PFL", "uf": "BA", "periodo": "1995 - 1997", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/e/ec/Lu%C3%ADs_Eduardo_Magalh%C3%A3es.jpg"},
                {"nome": "Michel Temer", "partido": "PMDB", "uf": "SP", "periodo": "1997 - 1999", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8e/Michel_Temer_foto_oficial_2016.jpg/440px-Michel_Temer_foto_oficial_2016.jpg"}
            ],
            "bancadas": [
                {"partido": "PMDB", "cadeiras": 107, "percentual": 20.9, "alinhamento": "BASE_GOVERNO", "cor_hex": "#15803d"},
                {"partido": "PFL", "cadeiras": 89, "percentual": 17.3, "alinhamento": "BASE_GOVERNO", "cor_hex": "#2563eb"},
                {"partido": "PSDB", "cadeiras": 63, "percentual": 12.3, "alinhamento": "BASE_GOVERNO", "cor_hex": "#0284c7"},
                {"partido": "PPR", "cadeiras": 51, "percentual": 9.9, "alinhamento": "BASE_GOVERNO", "cor_hex": "#3b82f6"},
                {"partido": "PT", "cadeiras": 50, "percentual": 9.7, "alinhamento": "OPOSICAO", "cor_hex": "#ef4444"},
                {"partido": "PP", "cadeiras": 34, "percentual": 6.6, "alinhamento": "BASE_GOVERNO", "cor_hex": "#3b82f6"},
                {"partido": "PDT", "cadeiras": 34, "percentual": 6.6, "alinhamento": "OPOSICAO", "cor_hex": "#dc2626"},
                {"partido": "PTB", "cadeiras": 32, "percentual": 6.2, "alinhamento": "BASE_GOVERNO", "cor_hex": "#9333ea"},
                {"partido": "PSB", "cadeiras": 15, "percentual": 2.9, "alinhamento": "OPOSICAO", "cor_hex": "#f97316"},
                {"partido": "PL", "cadeiras": 13, "percentual": 2.5, "alinhamento": "BASE_GOVERNO", "cor_hex": "#1e3a8a"},
                {"partido": "PCdoB", "cadeiras": 10, "percentual": 1.9, "alinhamento": "OPOSICAO", "cor_hex": "#b91c1c"},
                {"partido": "PMN", "cadeiras": 4, "percentual": 0.8, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#dc2626"},
                {"partido": "PSC", "cadeiras": 3, "percentual": 0.6, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#0284c7"},
                {"partido": "PSD", "cadeiras": 3, "percentual": 0.6, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#f59e0b"},
                {"partido": "PPS", "cadeiras": 2, "percentual": 0.4, "alinhamento": "OPOSICAO", "cor_hex": "#f97316"},
                {"partido": "PRN", "cadeiras": 1, "percentual": 0.2, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#0284c7"},
                {"partido": "PRP", "cadeiras": 1, "percentual": 0.2, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#0284c7"},
                {"partido": "PV", "cadeiras": 1, "percentual": 0.2, "alinhamento": "OPOSICAO", "cor_hex": "#16a34a"}
            ],
            "governabilidade": {
                "base_aliada_cadeiras": 389,
                "base_aliada_pct": 75.8,
                "centro_cadeiras": 12,
                "centro_pct": 2.3,
                "oposicao_cadeiras": 112,
                "oposicao_pct": 21.8,
                "maioria_simples_atingida": True,
                "maioria_pec_atingida": True
            }
        },
        "senado": {
            "total_cadeiras": 81,
            "presidentes": [
                {"nome": "José Sarney", "partido": "PMDB", "uf": "AP", "periodo": "1995 - 1997", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/73/Jose_Sarney_foto_oficial.jpg/440px-Jose_Sarney_foto_oficial.jpg"},
                {"nome": "Antônio Carlos Magalhães", "partido": "PFL", "uf": "BA", "periodo": "1997 - 1999", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/87/ACM_foto_oficial.jpg/440px-ACM_foto_oficial.jpg"}
            ],
            "bancadas": [
                {"partido": "PMDB", "cadeiras": 28, "percentual": 34.6, "alinhamento": "BASE_GOVERNO", "cor_hex": "#15803d"},
                {"partido": "PFL", "cadeiras": 22, "percentual": 27.2, "alinhamento": "BASE_GOVERNO", "cor_hex": "#2563eb"},
                {"partido": "PSDB", "cadeiras": 12, "percentual": 14.8, "alinhamento": "BASE_GOVERNO", "cor_hex": "#0284c7"},
                {"partido": "PPB", "cadeiras": 6, "percentual": 7.4, "alinhamento": "BASE_GOVERNO", "cor_hex": "#3b82f6"},
                {"partido": "PT", "cadeiras": 5, "percentual": 6.2, "alinhamento": "OPOSICAO", "cor_hex": "#ef4444"},
                {"partido": "PDT", "cadeiras": 4, "percentual": 4.9, "alinhamento": "OPOSICAO", "cor_hex": "#dc2626"},
                {"partido": "PSB", "cadeiras": 2, "percentual": 2.5, "alinhamento": "OPOSICAO", "cor_hex": "#f97316"},
                {"partido": "PL", "cadeiras": 1, "percentual": 1.2, "alinhamento": "BASE_GOVERNO", "cor_hex": "#1e3a8a"},
                {"partido": "PPS", "cadeiras": 1, "percentual": 1.2, "alinhamento": "OPOSICAO", "cor_hex": "#f97316"}
            ],
            "governabilidade": {
                "base_aliada_cadeiras": 69,
                "base_aliada_pct": 85.2,
                "centro_cadeiras": 0,
                "centro_pct": 0.0,
                "oposicao_cadeiras": 12,
                "oposicao_pct": 14.8,
                "maioria_simples_atingida": True,
                "maioria_pec_atingida": True
            }
        }
    },
    "lula-2003": {
        "mandato_id": "lula-2003",
        "presidente_republica": "Luiz Inácio Lula da Silva (Lula 1)",
        "periodo": "2003 - 2007",
        "camara": {
            "total_cadeiras": 513,
            "presidentes": [
                {"nome": "João Paulo Cunha", "partido": "PT", "uf": "SP", "periodo": "2003 - 2005", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/Joao_Paulo_Cunha.jpg/440px-Joao_Paulo_Cunha.jpg"},
                {"nome": "Severino Cavalcanti", "partido": "PP", "uf": "PE", "periodo": "2005", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Severino_Cavalcanti.jpg/440px-Severino_Cavalcanti.jpg"},
                {"nome": "Aldo Rebelo", "partido": "PCdoB", "uf": "SP", "periodo": "2005 - 2007", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/36/Aldo_Rebelo_foto_oficial.jpg/440px-Aldo_Rebelo_foto_oficial.jpg"}
            ],
            "bancadas": [
                {"partido": "PT", "cadeiras": 91, "percentual": 17.7, "alinhamento": "BASE_GOVERNO", "cor_hex": "#ef4444"},
                {"partido": "PFL", "cadeiras": 84, "percentual": 16.4, "alinhamento": "OPOSICAO", "cor_hex": "#2563eb"},
                {"partido": "PMDB", "cadeiras": 74, "percentual": 14.4, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#15803d"},
                {"partido": "PSDB", "cadeiras": 71, "percentual": 13.8, "alinhamento": "OPOSICAO", "cor_hex": "#0284c7"},
                {"partido": "PP", "cadeiras": 48, "percentual": 9.4, "alinhamento": "BASE_GOVERNO", "cor_hex": "#3b82f6"},
                {"partido": "PL", "cadeiras": 26, "percentual": 5.1, "alinhamento": "BASE_GOVERNO", "cor_hex": "#1e3a8a"},
                {"partido": "PTB", "cadeiras": 26, "percentual": 5.1, "alinhamento": "BASE_GOVERNO", "cor_hex": "#9333ea"},
                {"partido": "PSB", "cadeiras": 22, "percentual": 4.3, "alinhamento": "BASE_GOVERNO", "cor_hex": "#ea580c"},
                {"partido": "PDT", "cadeiras": 21, "percentual": 4.1, "alinhamento": "BASE_GOVERNO", "cor_hex": "#dc2626"},
                {"partido": "PPS", "cadeiras": 15, "percentual": 2.9, "alinhamento": "BASE_GOVERNO", "cor_hex": "#f97316"},
                {"partido": "PCdoB", "cadeiras": 12, "percentual": 2.3, "alinhamento": "BASE_GOVERNO", "cor_hex": "#b91c1c"},
                {"partido": "PRONA", "cadeiras": 6, "percentual": 1.2, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#eab308"},
                {"partido": "PV", "cadeiras": 5, "percentual": 1.0, "alinhamento": "BASE_GOVERNO", "cor_hex": "#16a34a"},
                {"partido": "PSD", "cadeiras": 4, "percentual": 0.8, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#f59e0b"},
                {"partido": "PST", "cadeiras": 3, "percentual": 0.6, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#64748b"},
                {"partido": "PHS", "cadeiras": 2, "percentual": 0.4, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#059669"},
                {"partido": "PMN", "cadeiras": 1, "percentual": 0.2, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#dc2626"},
                {"partido": "PSC", "cadeiras": 1, "percentual": 0.2, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#0284c7"},
                {"partido": "PTC", "cadeiras": 1, "percentual": 0.2, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#f59e0b"}
            ],
            "governabilidade": {
                "base_aliada_cadeiras": 218,
                "base_aliada_pct": 42.5,
                "centro_cadeiras": 140,
                "centro_pct": 27.3,
                "oposicao_cadeiras": 155,
                "oposicao_pct": 30.2,
                "maioria_simples_atingida": False,
                "maioria_pec_atingida": False
            }
        },
        "senado": {
            "total_cadeiras": 81,
            "presidentes": [
                {"nome": "José Sarney", "partido": "PMDB", "uf": "AP", "periodo": "2003 - 2005", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/73/Jose_Sarney_foto_oficial.jpg/440px-Jose_Sarney_foto_oficial.jpg"},
                {"nome": "Renan Calheiros", "partido": "PMDB", "uf": "AL", "periodo": "2005 - 2007", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b5/Renan_Calheiros.jpg/440px-Renan_Calheiros.jpg"}
            ],
            "bancadas": [
                {"partido": "PMDB", "cadeiras": 19, "percentual": 23.5, "alinhamento": "BASE_GOVERNO", "cor_hex": "#15803d"},
                {"partido": "PFL", "cadeiras": 19, "percentual": 23.5, "alinhamento": "OPOSICAO", "cor_hex": "#2563eb"},
                {"partido": "PT", "cadeiras": 14, "percentual": 17.3, "alinhamento": "BASE_GOVERNO", "cor_hex": "#ef4444"},
                {"partido": "PSDB", "cadeiras": 11, "percentual": 13.6, "alinhamento": "OPOSICAO", "cor_hex": "#0284c7"},
                {"partido": "PDT", "cadeiras": 5, "percentual": 6.2, "alinhamento": "BASE_GOVERNO", "cor_hex": "#dc2626"},
                {"partido": "PSB", "cadeiras": 4, "percentual": 4.9, "alinhamento": "BASE_GOVERNO", "cor_hex": "#ea580c"},
                {"partido": "PL", "cadeiras": 3, "percentual": 3.7, "alinhamento": "BASE_GOVERNO", "cor_hex": "#1e3a8a"},
                {"partido": "PTB", "cadeiras": 3, "percentual": 3.7, "alinhamento": "BASE_GOVERNO", "cor_hex": "#9333ea"},
                {"partido": "PPS", "cadeiras": 1, "percentual": 1.2, "alinhamento": "BASE_GOVERNO", "cor_hex": "#f97316"},
                {"partido": "PCdoB", "cadeiras": 1, "percentual": 1.2, "alinhamento": "BASE_GOVERNO", "cor_hex": "#b91c1c"},
                {"partido": "PP", "cadeiras": 1, "percentual": 1.2, "alinhamento": "BASE_GOVERNO", "cor_hex": "#3b82f6"}
            ],
            "governabilidade": {
                "base_aliada_cadeiras": 51,
                "base_aliada_pct": 63.0,
                "centro_cadeiras": 0,
                "centro_pct": 0.0,
                "oposicao_cadeiras": 30,
                "oposicao_pct": 37.0,
                "maioria_simples_atingida": True,
                "maioria_pec_atingida": True
            }
        }
    },
    "dilma-2015": {
        "mandato_id": "dilma-2015",
        "presidente_republica": "Dilma Rousseff (Dilma 2)",
        "periodo": "2015 - 2016",
        "camara": {
            "total_cadeiras": 513,
            "presidentes": [
                {"nome": "Eduardo Cunha", "partido": "PMDB", "uf": "RJ", "periodo": "2015 - 2016", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/ce/Eduardo_Cunha_foto_oficial.jpg/440px-Eduardo_Cunha_foto_oficial.jpg"},
                {"nome": "Waldir Maranhão (Interino)", "partido": "PP", "uf": "MA", "periodo": "2016", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e0/Waldir_Maranhao.jpg/440px-Waldir_Maranhao.jpg"}
            ],
            "bancadas": [
                {"partido": "PT", "cadeiras": 69, "percentual": 13.5, "alinhamento": "BASE_GOVERNO", "cor_hex": "#ef4444"},
                {"partido": "PMDB", "cadeiras": 65, "percentual": 12.7, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#15803d"},
                {"partido": "PSDB", "cadeiras": 54, "percentual": 10.5, "alinhamento": "OPOSICAO", "cor_hex": "#0284c7"},
                {"partido": "PP", "cadeiras": 38, "percentual": 7.4, "alinhamento": "BASE_GOVERNO", "cor_hex": "#3b82f6"},
                {"partido": "PSD", "cadeiras": 36, "percentual": 7.0, "alinhamento": "BASE_GOVERNO", "cor_hex": "#f59e0b"},
                {"partido": "PR", "cadeiras": 34, "percentual": 6.6, "alinhamento": "BASE_GOVERNO", "cor_hex": "#1e3a8a"},
                {"partido": "PSB", "cadeiras": 34, "percentual": 6.6, "alinhamento": "OPOSICAO", "cor_hex": "#f97316"},
                {"partido": "PTB", "cadeiras": 25, "percentual": 4.9, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#9333ea"},
                {"partido": "DEM", "cadeiras": 21, "percentual": 4.1, "alinhamento": "OPOSICAO", "cor_hex": "#2563eb"},
                {"partido": "REPUBLICANOS", "cadeiras": 21, "percentual": 4.1, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#0369a1"},
                {"partido": "PDT", "cadeiras": 20, "percentual": 3.9, "alinhamento": "BASE_GOVERNO", "cor_hex": "#dc2626"},
                {"partido": "SOLIDARIEDADE", "cadeiras": 15, "percentual": 2.9, "alinhamento": "OPOSICAO", "cor_hex": "#e11d48"},
                {"partido": "PSC", "cadeiras": 13, "percentual": 2.5, "alinhamento": "OPOSICAO", "cor_hex": "#0284c7"},
                {"partido": "PROS", "cadeiras": 11, "percentual": 2.1, "alinhamento": "BASE_GOVERNO", "cor_hex": "#0ea5e9"},
                {"partido": "PCdoB", "cadeiras": 10, "percentual": 1.9, "alinhamento": "BASE_GOVERNO", "cor_hex": "#b91c1c"},
                {"partido": "PPS", "cadeiras": 10, "percentual": 1.9, "alinhamento": "OPOSICAO", "cor_hex": "#f97316"},
                {"partido": "PV", "cadeiras": 8, "percentual": 1.6, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#16a34a"},
                {"partido": "PSOL", "cadeiras": 5, "percentual": 1.0, "alinhamento": "OPOSICAO", "cor_hex": "#facc15"},
                {"partido": "PHS", "cadeiras": 5, "percentual": 1.0, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#059669"},
                {"partido": "PTN", "cadeiras": 4, "percentual": 0.8, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#06b6d4"},
                {"partido": "PMN", "cadeiras": 3, "percentual": 0.6, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#dc2626"},
                {"partido": "PRP", "cadeiras": 3, "percentual": 0.6, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#0284c7"},
                {"partido": "PATRIOTA", "cadeiras": 2, "percentual": 0.4, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#10b981"},
                {"partido": "PSDC", "cadeiras": 2, "percentual": 0.4, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#2563eb"},
                {"partido": "PTC", "cadeiras": 2, "percentual": 0.4, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#f59e0b"},
                {"partido": "PRTB", "cadeiras": 1, "percentual": 0.2, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#1e3a8a"},
                {"partido": "PSL", "cadeiras": 1, "percentual": 0.2, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#1e3a8a"},
                {"partido": "PT do B", "cadeiras": 1, "percentual": 0.2, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#f97316"}
            ],
            "governabilidade": {
                "base_aliada_cadeiras": 218,
                "base_aliada_pct": 42.5,
                "centro_cadeiras": 143,
                "centro_pct": 27.9,
                "oposicao_cadeiras": 152,
                "oposicao_pct": 29.6,
                "maioria_simples_atingida": False,
                "maioria_pec_atingida": False
            }
        },
        "senado": {
            "total_cadeiras": 81,
            "presidentes": [
                {"nome": "Renan Calheiros", "partido": "PMDB", "uf": "AL", "periodo": "2015 - 2016", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b5/Renan_Calheiros.jpg/440px-Renan_Calheiros.jpg"}
            ],
            "bancadas": [
                {"partido": "PMDB", "cadeiras": 19, "percentual": 23.5, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#15803d"},
                {"partido": "PT", "cadeiras": 13, "percentual": 16.0, "alinhamento": "BASE_GOVERNO", "cor_hex": "#ef4444"},
                {"partido": "PSDB", "cadeiras": 10, "percentual": 12.3, "alinhamento": "OPOSICAO", "cor_hex": "#0284c7"},
                {"partido": "PSB", "cadeiras": 7, "percentual": 8.6, "alinhamento": "OPOSICAO", "cor_hex": "#f97316"},
                {"partido": "PDT", "cadeiras": 6, "percentual": 7.4, "alinhamento": "BASE_GOVERNO", "cor_hex": "#dc2626"},
                {"partido": "DEM", "cadeiras": 5, "percentual": 6.2, "alinhamento": "OPOSICAO", "cor_hex": "#2563eb"},
                {"partido": "PP", "cadeiras": 5, "percentual": 6.2, "alinhamento": "BASE_GOVERNO", "cor_hex": "#3b82f6"},
                {"partido": "PR", "cadeiras": 5, "percentual": 6.2, "alinhamento": "BASE_GOVERNO", "cor_hex": "#1e3a8a"},
                {"partido": "PTB", "cadeiras": 3, "percentual": 3.7, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#9333ea"},
                {"partido": "PSD", "cadeiras": 2, "percentual": 2.5, "alinhamento": "BASE_GOVERNO", "cor_hex": "#f59e0b"},
                {"partido": "PCdoB", "cadeiras": 1, "percentual": 1.2, "alinhamento": "BASE_GOVERNO", "cor_hex": "#b91c1c"},
                {"partido": "PMN", "cadeiras": 1, "percentual": 1.2, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#dc2626"},
                {"partido": "PPS", "cadeiras": 1, "percentual": 1.2, "alinhamento": "OPOSICAO", "cor_hex": "#f97316"},
                {"partido": "REPUBLICANOS", "cadeiras": 1, "percentual": 1.2, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#0369a1"},
                {"partido": "PSC", "cadeiras": 1, "percentual": 1.2, "alinhamento": "OPOSICAO", "cor_hex": "#0284c7"},
                {"partido": "PSOL", "cadeiras": 1, "percentual": 1.2, "alinhamento": "OPOSICAO", "cor_hex": "#facc15"}
            ],
            "governabilidade": {
                "base_aliada_cadeiras": 32,
                "base_aliada_pct": 39.5,
                "centro_cadeiras": 24,
                "centro_pct": 29.6,
                "oposicao_cadeiras": 25,
                "oposicao_pct": 30.9,
                "maioria_simples_atingida": False,
                "maioria_pec_atingida": False
            }
        }
    },
    "bolsonaro-2019": {
        "mandato_id": "bolsonaro-2019",
        "presidente_republica": "Jair Bolsonaro",
        "periodo": "2019 - 2022",
        "camara": {
            "total_cadeiras": 513,
            "presidentes": [
                {"nome": "Rodrigo Maia", "partido": "DEM", "uf": "RJ", "periodo": "2019 - 2021", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/52/Rodrigo_Maia_foto_oficial.jpg/440px-Rodrigo_Maia_foto_oficial.jpg"},
                {"nome": "Arthur Lira", "partido": "PP", "uf": "AL", "periodo": "2021 - 2023", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/bb/Arthur_Lira_foto_oficial.jpg/440px-Arthur_Lira_foto_oficial.jpg"}
            ],
            "bancadas": [
                {"partido": "PT", "cadeiras": 56, "percentual": 10.9, "alinhamento": "OPOSICAO", "cor_hex": "#ef4444"},
                {"partido": "PSL", "cadeiras": 52, "percentual": 10.1, "alinhamento": "BASE_GOVERNO", "cor_hex": "#1e3a8a"},
                {"partido": "PP", "cadeiras": 37, "percentual": 7.2, "alinhamento": "BASE_GOVERNO", "cor_hex": "#3b82f6"},
                {"partido": "PSD", "cadeiras": 35, "percentual": 6.8, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#f59e0b"},
                {"partido": "MDB", "cadeiras": 34, "percentual": 6.6, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#15803d"},
                {"partido": "PR", "cadeiras": 33, "percentual": 6.4, "alinhamento": "BASE_GOVERNO", "cor_hex": "#1e3a8a"},
                {"partido": "PSB", "cadeiras": 32, "percentual": 6.2, "alinhamento": "OPOSICAO", "cor_hex": "#ea580c"},
                {"partido": "PSDB", "cadeiras": 30, "percentual": 5.8, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#38bdf8"},
                {"partido": "DEM", "cadeiras": 29, "percentual": 5.7, "alinhamento": "BASE_GOVERNO", "cor_hex": "#2563eb"},
                {"partido": "REPUBLICANOS", "cadeiras": 29, "percentual": 5.7, "alinhamento": "BASE_GOVERNO", "cor_hex": "#0369a1"},
                {"partido": "PDT", "cadeiras": 28, "percentual": 5.5, "alinhamento": "OPOSICAO", "cor_hex": "#dc2626"},
                {"partido": "SOLIDARIEDADE", "cadeiras": 13, "percentual": 2.5, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#e11d48"},
                {"partido": "PODE", "cadeiras": 11, "percentual": 2.1, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#06b6d4"},
                {"partido": "PTB", "cadeiras": 10, "percentual": 1.9, "alinhamento": "BASE_GOVERNO", "cor_hex": "#9333ea"},
                {"partido": "PSOL", "cadeiras": 10, "percentual": 1.9, "alinhamento": "OPOSICAO", "cor_hex": "#facc15"},
                {"partido": "PCdoB", "cadeiras": 9, "percentual": 1.8, "alinhamento": "OPOSICAO", "cor_hex": "#b91c1c"},
                {"partido": "NOVO", "cadeiras": 8, "percentual": 1.6, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#f97316"},
                {"partido": "PROS", "cadeiras": 8, "percentual": 1.6, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#0ea5e9"},
                {"partido": "PPS", "cadeiras": 8, "percentual": 1.6, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#f97316"},
                {"partido": "PSC", "cadeiras": 7, "percentual": 1.4, "alinhamento": "BASE_GOVERNO", "cor_hex": "#0284c7"},
                {"partido": "AVANTE", "cadeiras": 7, "percentual": 1.4, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#f97316"},
                {"partido": "PHS", "cadeiras": 6, "percentual": 1.2, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#059669"},
                {"partido": "PATRIOTA", "cadeiras": 5, "percentual": 1.0, "alinhamento": "BASE_GOVERNO", "cor_hex": "#10b981"},
                {"partido": "PV", "cadeiras": 4, "percentual": 0.8, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#16a34a"},
                {"partido": "PRP", "cadeiras": 4, "percentual": 0.8, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#0284c7"},
                {"partido": "PMN", "cadeiras": 3, "percentual": 0.6, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#dc2626"},
                {"partido": "PTC", "cadeiras": 2, "percentual": 0.4, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#f59e0b"},
                {"partido": "DC", "cadeiras": 1, "percentual": 0.2, "alinhamento": "BASE_GOVERNO", "cor_hex": "#2563eb"},
                {"partido": "REDE", "cadeiras": 1, "percentual": 0.2, "alinhamento": "OPOSICAO", "cor_hex": "#0d9488"},
                {"partido": "PPL", "cadeiras": 1, "percentual": 0.2, "alinhamento": "OPOSICAO", "cor_hex": "#dc2626"}
            ],
            "governabilidade": {
                "base_aliada_cadeiras": 203,
                "base_aliada_pct": 39.6,
                "centro_cadeiras": 173,
                "centro_pct": 33.7,
                "oposicao_cadeiras": 145,
                "oposicao_pct": 28.3,
                "maioria_simples_atingida": False,
                "maioria_pec_atingida": False
            }
        },
        "senado": {
            "total_cadeiras": 81,
            "presidentes": [
                {"nome": "Davi Alcolumbre", "partido": "DEM", "uf": "AP", "periodo": "2019 - 2021", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d4/Davi_Alcolumbre_foto_oficial.jpg/440px-Davi_Alcolumbre_foto_oficial.jpg"},
                {"nome": "Rodrigo Pacheco", "partido": "DEM", "uf": "MG", "periodo": "2021 - 2023", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d3/Rodrigo_Pacheco_foto_oficial.jpg/440px-Rodrigo_Pacheco_foto_oficial.jpg"}
            ],
            "bancadas": [
                {"partido": "MDB", "cadeiras": 12, "percentual": 14.8, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#15803d"},
                {"partido": "PSDB", "cadeiras": 8, "percentual": 9.9, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#38bdf8"},
                {"partido": "PSD", "cadeiras": 7, "percentual": 8.6, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#f59e0b"},
                {"partido": "DEM", "cadeiras": 7, "percentual": 8.6, "alinhamento": "BASE_GOVERNO", "cor_hex": "#2563eb"},
                {"partido": "PP", "cadeiras": 6, "percentual": 7.4, "alinhamento": "BASE_GOVERNO", "cor_hex": "#3b82f6"},
                {"partido": "PDT", "cadeiras": 6, "percentual": 7.4, "alinhamento": "OPOSICAO", "cor_hex": "#dc2626"},
                {"partido": "PT", "cadeiras": 6, "percentual": 7.4, "alinhamento": "OPOSICAO", "cor_hex": "#ef4444"},
                {"partido": "REDE", "cadeiras": 5, "percentual": 6.2, "alinhamento": "OPOSICAO", "cor_hex": "#0d9488"},
                {"partido": "PSB", "cadeiras": 5, "percentual": 6.2, "alinhamento": "OPOSICAO", "cor_hex": "#ea580c"},
                {"partido": "PTB", "cadeiras": 4, "percentual": 4.9, "alinhamento": "BASE_GOVERNO", "cor_hex": "#9333ea"},
                {"partido": "PSL", "cadeiras": 3, "percentual": 3.7, "alinhamento": "BASE_GOVERNO", "cor_hex": "#1e3a8a"},
                {"partido": "PPS", "cadeiras": 2, "percentual": 2.5, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#f97316"},
                {"partido": "PHS", "cadeiras": 2, "percentual": 2.5, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#059669"},
                {"partido": "PR", "cadeiras": 2, "percentual": 2.5, "alinhamento": "BASE_GOVERNO", "cor_hex": "#1e3a8a"},
                {"partido": "SOLIDARIEDADE", "cadeiras": 1, "percentual": 1.2, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#e11d48"},
                {"partido": "PODE", "cadeiras": 1, "percentual": 1.2, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#06b6d4"},
                {"partido": "PSC", "cadeiras": 1, "percentual": 1.2, "alinhamento": "BASE_GOVERNO", "cor_hex": "#0284c7"},
                {"partido": "PRP", "cadeiras": 1, "percentual": 1.2, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#0284c7"},
                {"partido": "PROS", "cadeiras": 1, "percentual": 1.2, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#0ea5e9"},
                {"partido": "REPUBLICANOS", "cadeiras": 1, "percentual": 1.2, "alinhamento": "BASE_GOVERNO", "cor_hex": "#0369a1"}
            ],
            "governabilidade": {
                "base_aliada_cadeiras": 24,
                "base_aliada_pct": 29.6,
                "centro_cadeiras": 35,
                "centro_pct": 43.2,
                "oposicao_cadeiras": 22,
                "oposicao_pct": 27.2,
                "maioria_simples_atingida": False,
                "maioria_pec_atingida": False
            }
        }
    },
    "lula-2023": {
        "mandato_id": "lula-2023",
        "presidente_republica": "Luiz Inácio Lula da Silva (Lula 3)",
        "periodo": "2023 - 2026",
        "camara": {
            "total_cadeiras": 513,
            "presidentes": [
                {"nome": "Arthur Lira", "partido": "PP", "uf": "AL", "periodo": "2023 - 2025", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/bb/Arthur_Lira_foto_oficial.jpg/440px-Arthur_Lira_foto_oficial.jpg"},
                {"nome": "Hugo Motta", "partido": "Republicanos", "uf": "PB", "periodo": "2025 - Presente", "foto_url": "https://www.camara.leg.br/internet/deputado/bandep/160674.jpg"}
            ],
            "bancadas": [
                {"partido": "PL", "cadeiras": 99, "percentual": 19.3, "alinhamento": "OPOSICAO", "cor_hex": "#1d4ed8"},
                {"partido": "PT", "cadeiras": 68, "percentual": 13.3, "alinhamento": "BASE_GOVERNO", "cor_hex": "#ef4444"},
                {"partido": "UNIÃO", "cadeiras": 59, "percentual": 11.5, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#0284c7"},
                {"partido": "PP", "cadeiras": 47, "percentual": 9.2, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#3b82f6"},
                {"partido": "MDB", "cadeiras": 42, "percentual": 8.2, "alinhamento": "BASE_GOVERNO", "cor_hex": "#15803d"},
                {"partido": "PSD", "cadeiras": 42, "percentual": 8.2, "alinhamento": "BASE_GOVERNO", "cor_hex": "#f59e0b"},
                {"partido": "REPUBLICANOS", "cadeiras": 41, "percentual": 8.0, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#0369a1"},
                {"partido": "PDT", "cadeiras": 17, "percentual": 3.3, "alinhamento": "BASE_GOVERNO", "cor_hex": "#dc2626"},
                {"partido": "PSB", "cadeiras": 14, "percentual": 2.7, "alinhamento": "BASE_GOVERNO", "cor_hex": "#ea580c"},
                {"partido": "PSDB", "cadeiras": 13, "percentual": 2.5, "alinhamento": "OPOSICAO", "cor_hex": "#38bdf8"},
                {"partido": "PSOL", "cadeiras": 12, "percentual": 2.3, "alinhamento": "BASE_GOVERNO", "cor_hex": "#facc15"},
                {"partido": "PODE", "cadeiras": 12, "percentual": 2.3, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#06b6d4"},
                {"partido": "AVANTE", "cadeiras": 7, "percentual": 1.4, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#f97316"},
                {"partido": "PCdoB", "cadeiras": 7, "percentual": 1.4, "alinhamento": "BASE_GOVERNO", "cor_hex": "#b91c1c"},
                {"partido": "PSC", "cadeiras": 6, "percentual": 1.2, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#0284c7"},
                {"partido": "PV", "cadeiras": 6, "percentual": 1.2, "alinhamento": "BASE_GOVERNO", "cor_hex": "#16a34a"},
                {"partido": "CIDADANIA", "cadeiras": 5, "percentual": 1.0, "alinhamento": "OPOSICAO", "cor_hex": "#f97316"},
                {"partido": "PATRIOTA", "cadeiras": 4, "percentual": 0.8, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#10b981"},
                {"partido": "SOLIDARIEDADE", "cadeiras": 4, "percentual": 0.8, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#e11d48"},
                {"partido": "NOVO", "cadeiras": 3, "percentual": 0.6, "alinhamento": "OPOSICAO", "cor_hex": "#f97316"},
                {"partido": "PROS", "cadeiras": 2, "percentual": 0.4, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#0ea5e9"},
                {"partido": "REDE", "cadeiras": 2, "percentual": 0.4, "alinhamento": "BASE_GOVERNO", "cor_hex": "#0d9488"},
                {"partido": "PTB", "cadeiras": 1, "percentual": 0.2, "alinhamento": "OPOSICAO", "cor_hex": "#9333ea"}
            ],
            "governabilidade": {
                "base_aliada_cadeiras": 210,
                "base_aliada_pct": 40.9,
                "centro_cadeiras": 182,
                "centro_pct": 35.5,
                "oposicao_cadeiras": 121,
                "oposicao_pct": 23.6,
                "maioria_simples_atingida": False,
                "maioria_pec_atingida": False
            }
        },
        "senado": {
            "total_cadeiras": 81,
            "presidentes": [
                {"nome": "Rodrigo Pacheco", "partido": "PSD", "uf": "MG", "periodo": "2023 - 2025", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d3/Rodrigo_Pacheco_foto_oficial.jpg/440px-Rodrigo_Pacheco_foto_oficial.jpg"},
                {"nome": "Davi Alcolumbre", "partido": "UNIÃO", "uf": "AP", "periodo": "2025 - Presente", "foto_url": None}
            ],
            "bancadas": [
                {"partido": "PSD", "cadeiras": 15, "percentual": 18.5, "alinhamento": "BASE_GOVERNO", "cor_hex": "#f59e0b"},
                {"partido": "PL", "cadeiras": 14, "percentual": 17.3, "alinhamento": "OPOSICAO", "cor_hex": "#1d4ed8"},
                {"partido": "MDB", "cadeiras": 11, "percentual": 13.6, "alinhamento": "BASE_GOVERNO", "cor_hex": "#15803d"},
                {"partido": "PT", "cadeiras": 9, "percentual": 11.1, "alinhamento": "BASE_GOVERNO", "cor_hex": "#ef4444"},
                {"partido": "UNIÃO", "cadeiras": 7, "percentual": 8.6, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#0284c7"},
                {"partido": "PP", "cadeiras": 6, "percentual": 7.4, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#3b82f6"},
                {"partido": "PODE", "cadeiras": 6, "percentual": 7.4, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#06b6d4"},
                {"partido": "PSB", "cadeiras": 4, "percentual": 4.9, "alinhamento": "BASE_GOVERNO", "cor_hex": "#ea580c"},
                {"partido": "REPUBLICANOS", "cadeiras": 4, "percentual": 4.9, "alinhamento": "INDEPENDENTE_CENTRO", "cor_hex": "#0369a1"},
                {"partido": "PSDB", "cadeiras": 2, "percentual": 2.5, "alinhamento": "OPOSICAO", "cor_hex": "#38bdf8"},
                {"partido": "PDT", "cadeiras": 2, "percentual": 2.5, "alinhamento": "BASE_GOVERNO", "cor_hex": "#dc2626"},
                {"partido": "REDE", "cadeiras": 1, "percentual": 1.2, "alinhamento": "BASE_GOVERNO", "cor_hex": "#0d9488"}
            ],
            "governabilidade": {
                "base_aliada_cadeiras": 42,
                "base_aliada_pct": 51.9,
                "centro_cadeiras": 23,
                "centro_pct": 28.4,
                "oposicao_cadeiras": 16,
                "oposicao_pct": 19.8,
                "maioria_simples_atingida": True,
                "maioria_pec_atingida": False
            }
        }
    }
}

# Mandatos intermediários (FHC 2, Lula 2, Dilma 1, Temer): só os presidentes das Casas foram curados.
# A composição das bancadas e a governabilidade NÃO foram levantadas para estes mandatos e NÃO são mais
# copiadas de outro mandato (antes, FHC 2 herdava as bancadas de FHC 1, Lula 2 as de Lula 1 etc.).
COMPOSICAO_NAO_CURADA = "Composição partidária não curada para este mandato."
GOVERNABILIDADE_INDISPONIVEL = {
    "base_aliada_cadeiras": None,
    "base_aliada_pct": None,
    "centro_cadeiras": None,
    "centro_pct": None,
    "oposicao_cadeiras": None,
    "oposicao_pct": None,
    "maioria_simples_atingida": None,
    "maioria_pec_atingida": None,
}

for m_id, template_id in [
    ("fhc-1999", "fhc-1995"),
    ("lula-2007", "lula-2003"),
    ("dilma-2011", "dilma-2015"),
    ("temer-2016", "dilma-2015")
]:
    if m_id not in COMPOSICAO_CONGRESSO_HISTORICO and template_id in COMPOSICAO_CONGRESSO_HISTORICO:
        copy_data = json.loads(json.dumps(COMPOSICAO_CONGRESSO_HISTORICO[template_id]))
        copy_data["mandato_id"] = m_id
        for casa in ("camara", "senado"):
            copy_data[casa]["bancadas"] = []
            copy_data[casa]["governabilidade"] = dict(GOVERNABILIDADE_INDISPONIVEL)
        copy_data["dados_incompletos"] = True
        copy_data["observacao"] = COMPOSICAO_NAO_CURADA
        if m_id == "fhc-1999":
            copy_data["presidente_republica"] = "Fernando Henrique Cardoso (FHC 2)"
            copy_data["periodo"] = "1999 - 2003"
            copy_data["camara"]["presidentes"] = [
                {"nome": "Michel Temer", "partido": "PMDB", "uf": "SP", "periodo": "1999 - 2001", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8e/Michel_Temer_foto_oficial_2016.jpg/440px-Michel_Temer_foto_oficial_2016.jpg"},
                {"nome": "Aécio Neves", "partido": "PSDB", "uf": "MG", "periodo": "2001 - 2002", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/ca/Aecio_Neves.jpg/440px-Aecio_Neves.jpg"}
            ]
            copy_data["senado"]["presidentes"] = [
                {"nome": "Antonio Carlos Magalhães", "partido": "PFL", "uf": "BA", "periodo": "1999 - 2001", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c9/Antonio_Carlos_Magalhaes.jpg/440px-Antonio_Carlos_Magalhaes.jpg"},
                {"nome": "Jader Barbalho", "partido": "PMDB", "uf": "PA", "periodo": "2001", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/41/Jader_Barbalho.jpg/440px-Jader_Barbalho.jpg"},
                {"nome": "Ramez Tebet", "partido": "PMDB", "uf": "MS", "periodo": "2001 - 2003", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6f/Ramez_Tebet.jpg/440px-Ramez_Tebet.jpg"}
            ]
        elif m_id == "lula-2007":
            copy_data["presidente_republica"] = "Lula (Lula 2)"
            copy_data["periodo"] = "2007 - 2011"
            copy_data["camara"]["presidentes"] = [
                {"nome": "Arlindo Chinaglia", "partido": "PT", "uf": "SP", "periodo": "2007 - 2009", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/52/Arlindo_Chinaglia.jpg/440px-Arlindo_Chinaglia.jpg"},
                {"nome": "Michel Temer", "partido": "PMDB", "uf": "SP", "periodo": "2009 - 2010", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8e/Michel_Temer_foto_oficial_2016.jpg/440px-Michel_Temer_foto_oficial_2016.jpg"}
            ]
            copy_data["senado"]["presidentes"] = [
                {"nome": "Renan Calheiros", "partido": "PMDB", "uf": "AL", "periodo": "2007", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b5/Renan_Calheiros.jpg/440px-Renan_Calheiros.jpg"},
                {"nome": "Garibaldi Alves Filho", "partido": "PMDB", "uf": "RN", "periodo": "2007 - 2009", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d4/Garibaldi_Alves_Filho.jpg/440px-Garibaldi_Alves_Filho.jpg"},
                {"nome": "José Sarney", "partido": "PMDB", "uf": "AP", "periodo": "2009 - 2011", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/73/Jose_Sarney_foto_oficial.jpg/440px-Jose_Sarney_foto_oficial.jpg"}
            ]
        elif m_id == "dilma-2011":
            copy_data["presidente_republica"] = "Dilma Rousseff (Dilma 1)"
            copy_data["periodo"] = "2011 - 2015"
            copy_data["camara"]["presidentes"] = [
                {"nome": "Marco Maia", "partido": "PT", "uf": "RS", "periodo": "2011 - 2013", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/05/Marco_Maia.jpg/440px-Marco_Maia.jpg"},
                {"nome": "Henrique Eduardo Alves", "partido": "PMDB", "uf": "RN", "periodo": "2013 - 2015", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f6/Henrique_Eduardo_Alves.jpg/440px-Henrique_Eduardo_Alves.jpg"}
            ]
            copy_data["senado"]["presidentes"] = [
                {"nome": "José Sarney", "partido": "PMDB", "uf": "AP", "periodo": "2011 - 2013", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/73/Jose_Sarney_foto_oficial.jpg/440px-Jose_Sarney_foto_oficial.jpg"},
                {"nome": "Renan Calheiros", "partido": "PMDB", "uf": "AL", "periodo": "2013 - 2015", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b5/Renan_Calheiros.jpg/440px-Renan_Calheiros.jpg"}
            ]
        elif m_id == "temer-2016":
            copy_data["presidente_republica"] = "Michel Temer"
            copy_data["periodo"] = "2016 - 2019"
            copy_data["camara"]["presidentes"] = [
                {"nome": "Rodrigo Maia", "partido": "DEM", "uf": "RJ", "periodo": "2016 - 2019", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/52/Rodrigo_Maia_foto_oficial.jpg/440px-Rodrigo_Maia_foto_oficial.jpg"}
            ]
            copy_data["senado"]["presidentes"] = [
                {"nome": "Renan Calheiros", "partido": "PMDB", "uf": "AL", "periodo": "2016 - 2017", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b5/Renan_Calheiros.jpg/440px-Renan_Calheiros.jpg"},
                {"nome": "Eunício Oliveira", "partido": "PMDB", "uf": "CE", "periodo": "2017 - 2019", "foto_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/51/Eunicio_Oliveira.jpg/440px-Eunicio_Oliveira.jpg"}
            ]
        COMPOSICAO_CONGRESSO_HISTORICO[m_id] = copy_data


# Legislatura (ano de início) de cada mandato presidencial: a composição "da posse" é a eleita no ano anterior.
# Itamar (1992) assumiu no meio de uma legislatura e Temer (2016) também: para ele vale a eleição de 2014.
LEGISLATURA_POR_MANDATO: Dict[str, Optional[int]] = {
    "itamar-franco-1992": None,
    "fhc-1995": 1995,
    "fhc-1999": 1999,
    "lula-2003": 2003,
    "lula-2007": 2007,
    "dilma-2011": 2011,
    "dilma-2015": 2015,
    "temer-2016": 2015,
    "bolsonaro-2019": 2019,
    "lula-2023": 2023,
}
FONTE_CURADORIA = (
    "Curadoria manual LegisData (Arquivo Histórico da Câmara e do Senado; fotos Wikimedia/camara.leg.br): "
    "presidentes das Casas, classificação base/oposição e, onde houver, bancadas na posse"
)
ALINHAMENTO_NAO_CLASSIFICADO = "NAO_CLASSIFICADO"
COR_NEUTRA = "#64748b"
TOTAL_CADEIRAS = {"camara": 513, "senado": 81}
NOTA_VERIFICACAO = (
    "O TSE conta o partido no dia da eleição. Trocas partidárias até a posse (e, no Senado, desde a eleição de "
    "4 anos antes) e vagas preenchidas por suplentes explicam as diferenças em relação à bancada curada."
)


def _norm(partido: str) -> str:
    return str(partido).strip().upper()


def _bancada_ordenada(contagem: Dict[str, int]) -> List[Dict[str, Any]]:
    total = sum(contagem.values()) or 1
    return [
        {"partido": partido, "cadeiras": n, "percentual": round(n / total * 100, 1)}
        for partido, n in sorted(contagem.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


def comparar_bancadas(curadas: List[Dict[str, Any]], tse: Dict[str, int]) -> Dict[str, Any]:
    """Compara a bancada curada (cadeiras na posse) com os eleitos do TSE; devolve as divergências por partido."""
    tse_norm = {_norm(p): n for p, n in tse.items()}
    total_tse = sum(tse_norm.values())
    divergencias = []
    listados_tse = 0
    for item in curadas:
        if _norm(item["partido"]) == "OUTROS":
            continue
        no_tse = tse_norm.get(_norm(item["partido"]), 0)
        listados_tse += no_tse
        if item["cadeiras"] != no_tse:
            divergencias.append({"partido": item["partido"], "curado": item["cadeiras"], "tse": no_tse})
    for item in curadas:
        if _norm(item["partido"]) == "OUTROS" and item["cadeiras"] != total_tse - listados_tse:
            divergencias.append({"partido": "Outros", "curado": item["cadeiras"], "tse": total_tse - listados_tse})
    return {"total_eleitos_tse": total_tse, "conferido": not divergencias, "divergencias": divergencias}


def enriquecer_com_tse(
    historico: Dict[str, Any],
    bancada_camara: Callable[[int], Optional[Dict[str, int]]],
    bancada_senado: Callable[[int], Optional[Dict[str, int]]],
) -> Dict[str, Any]:
    """
    Anexa a cada mandato as bancadas ELEITAS (TSE) e a conferência com a curadoria. Mandatos sem bancadas curadas
    passam a exibir os eleitos do TSE (sem classificação base/oposição; a governabilidade segue indisponível).
    """
    resultado = json.loads(json.dumps(historico))
    for mandato_id, dados in resultado.items():
        dados["fonte_curadoria"] = FONTE_CURADORIA
        legislatura = LEGISLATURA_POR_MANDATO.get(mandato_id)
        for casa, buscar in (("camara", bancada_camara), ("senado", bancada_senado)):
            bloco = dados[casa]
            if legislatura is None:
                bloco["verificacao_tse"] = {"status": "nao_aplicavel", "motivo": "Mandato iniciado no meio da legislatura"}
                continue
            try:
                eleitos = buscar(legislatura)
            except Exception as exc:  # noqa: BLE001 — falha de rede/arquivo não pode derrubar a curadoria
                logger.warning("TSE indisponível para %s/%s: %s", mandato_id, casa, exc)
                eleitos = None
            if not eleitos:
                motivo = (
                    "Eleição de 1990 não consta nos dados abertos do TSE"
                    if casa == "senado" and legislatura == 1995
                    else "Dados do TSE indisponíveis"
                )
                bloco["verificacao_tse"] = {"status": "indisponivel", "motivo": motivo}
                continue
            esperado = TOTAL_CADEIRAS[casa]
            total = sum(eleitos.values())
            bloco["bancadas_eleitas_tse"] = _bancada_ordenada(eleitos)
            if total != esperado:
                # Total diferente do número de cadeiras: o recorte do TSE não fecha (ex.: anos com 503/513 ou vagas).
                bloco["verificacao_tse"] = {
                    "status": "total_inesperado",
                    "total_eleitos_tse": total,
                    "total_esperado": esperado,
                    "ano_legislatura": legislatura,
                    "nota": "O recorte de candidatos eleitos do TSE não soma o número de cadeiras (rótulos de situação "
                    "e vagas); a bancada eleita é exibida só para consulta e não substitui a curadoria.",
                }
                continue
            if bloco.get("bancadas"):
                bloco["verificacao_tse"] = {
                    "status": "conferido" if comparar_bancadas(bloco["bancadas"], eleitos)["conferido"] else "divergente",
                    "ano_legislatura": legislatura,
                    **comparar_bancadas(bloco["bancadas"], eleitos),
                    "nota": NOTA_VERIFICACAO,
                }
            else:
                bloco["bancadas"] = [
                    {**item, "alinhamento": ALINHAMENTO_NAO_CLASSIFICADO, "cor_hex": CORES_PARTIDOS.get(item["partido"].upper(), COR_NEUTRA)}
                    for item in bloco["bancadas_eleitas_tse"]
                ]
                bloco["bancadas_origem"] = "TSE — candidatos eleitos (sem classificação base/oposição)"
                bloco["verificacao_tse"] = {"status": "preenchido_pelo_tse", "ano_legislatura": legislatura}
    return resultado


def save_composicao_congresso(offline: bool = False):
    """Grava a composição histórica, conferida com os eleitos do TSE (`offline=True` pula a conferência)."""
    out_file = PROCESSED_DATA_DIR / "composicao_congresso.json"
    historico = COMPOSICAO_CONGRESSO_HISTORICO
    if offline:
        resultado = enriquecer_com_tse(historico, lambda _y: None, lambda _y: None)
    else:
        from etl.extractors.composicao_tse import bancada_camara, bancada_senado

        resultado = enriquecer_com_tse(historico, bancada_camara, bancada_senado)
    atomic_write_json(out_file, resultado)
    logger.info(f"Composição histórica salva em {out_file} com {len(resultado)} mandatos.")
    return resultado


if __name__ == "__main__":
    save_composicao_congresso()
