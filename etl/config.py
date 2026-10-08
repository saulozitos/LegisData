"""
Configurações Globais do Pipeline de ETL - Política e Economia Brasileira
"""

import os
from pathlib import Path
from datetime import date

# Diretórios base
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"

RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Parâmetros temporais padrão (Início do governo Itamar Franco até o presente)
DATA_INICIO_PADRAO = "02/10/1992"  # Posse interina de Itamar Franco
DATA_FIM_PADRAO = date.today().strftime("%d/%m/%Y")

# Anos da Cota Parlamentar (CEAP/CEAPS) carregados pelo db_loader a partir dos
# arquivos anuais oficiais. Configurável por variável de ambiente.
CEAP_ANO_INICIO = int(os.getenv("CEAP_ANO_INICIO", "2023"))
CEAP_ANO_FIM = int(os.getenv("CEAP_ANO_FIM", str(date.today().year)))

# Mapa revisável autor da emenda (Portal da Transparência) -> parlamentar
REFERENCE_DATA_DIR = DATA_DIR / "reference"

# User-Agent oficial do projeto para consumo de APIs públicas
DEFAULT_USER_AGENT = "LegisDataBot/1.0 (Transparência Pública; contato@legisdata.org)"

# URLs Base das APIs Públicas
BCB_SGS_API_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
IBGE_SIDRA_API_URL = "https://servicodados.ibge.gov.br/api/v3/agregados"

# Catálogo de Séries Temporais do Banco Central (SGS)
BCB_SERIES = {
    "ipca_mensal": {
        "codigo": 433,
        "nome": "IPCA - Variação mensal",
        "unidade": "%",
        "categoria": "INFLACAO",
        "frequencia": "MENSAL",
        "data_inicio": "01/01/1980"
    },
    "ipca_acumulado_12m": {
        "codigo": 13522,
        "nome": "IPCA - Acumulado em 12 meses",
        "unidade": "%",
        "categoria": "INFLACAO",
        "frequencia": "MENSAL",
        "data_inicio": "01/01/1995"
    },
    "selic_meta_ano": {
        "codigo": 432,
        "nome": "Taxa Selic - Meta anual fixada pelo Copom",
        "unidade": "% a.a.",
        "categoria": "JUROS_SELIC",
        "frequencia": "DIARIA_OU_REUNIAO",
        "data_inicio": "04/03/1999"
    },
    "selic_acumulada_mes": {
        "codigo": 4390,
        "nome": "Taxa Selic acumulada no mês",
        "unidade": "% a.m.",
        "categoria": "JUROS_SELIC",
        "frequencia": "MENSAL",
        "data_inicio": "01/07/1986"
    },
    "cambio_usd_brl_venda": {
        "codigo": 3698,
        "nome": "Taxa de Câmbio - USD / Moeda Nacional (Venda - Média mensal)",
        "unidade": "BRL/USD",
        "categoria": "CAMBIO_DOLAR",
        "frequencia": "MENSAL",
        "data_inicio": "01/01/1985"
    },
    "dolar_ptax_fechamento": {
        "codigo": 10813,
        "nome": "Taxa de Câmbio - Livre - USD / Moeda Nacional (Venda - Fim de período)",
        "unidade": "BRL/USD",
        "categoria": "CAMBIO_DOLAR",
        "frequencia": "MENSAL",
        "data_inicio": "01/01/1985"
    },
    "pib_mensal_corrente": {
        "codigo": 4380,
        "nome": "PIB mensal em valores correntes",
        "unidade": "R$ milhões",
        "categoria": "PIB",
        "frequencia": "MENSAL",
        "data_inicio": "01/01/1990"
    },
    "pib_variacao_anual": {
        "codigo": 7326,
        "nome": "PIB - Taxa de variação real anual",
        "unidade": "% a.a.",
        "categoria": "PIB",
        "frequencia": "ANUAL",
        "data_inicio": "01/01/1996"
    },
    "divida_liquida_pib": {
        "codigo": 4513,
        "nome": "Dívida Líquida do Setor Público (% PIB)",
        "unidade": "% do PIB",
        "categoria": "DIVIDA_PUBLICA",
        "frequencia": "MENSAL",
        "data_inicio": "01/12/2001"
    },
    "divida_bruta_governo_pib": {
        "codigo": 4536,
        "nome": "Dívida Bruta do Governo Geral (% PIB)",
        "unidade": "% do PIB",
        "categoria": "DIVIDA_PUBLICA",
        "frequencia": "MENSAL",
        "data_inicio": "01/12/2001"
    },
    "salario_minimo_nominal": {
        "codigo": 1619,
        "nome": "Salário Mínimo Nominal",
        "unidade": "R$ / Moeda Vigente",
        "categoria": "SALARIO_MINIMO",
        "frequencia": "MENSAL",
        "data_inicio": "01/01/1980"
    },
    "ibovespa_fechamento": {
        "codigo": 7,
        "nome": "Índice Bovespa (Ibovespa) - Fechamento",
        "unidade": "Pontos",
        "categoria": "MERCADO_FINANCEIRO",
        "frequencia": "DIARIA",
        "data_inicio": "01/01/1990"
    },
    "desemprego_pnad": {
        "codigo": 24369,
        "nome": "Taxa de desocupação - PNAD Contínua",
        "unidade": "%",
        "categoria": "DESEMPREGO",
        "frequencia": "MENSAL",
        "data_inicio": "01/01/2012"
    }
}
