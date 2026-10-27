"""
Configurações Globais do Pipeline de ETL - Política e Economia Brasileira
"""

import os
from datetime import date
from pathlib import Path

# Diretórios base
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"


def ensure_data_dirs() -> None:
    """Cria os diretórios de dados sob demanda (não mais como efeito colateral do import)."""
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)


# Parâmetros temporais padrão (início da janela de dados, 1995-01-01, até o presente)
DATA_INICIO_PADRAO = "01/01/1995"  # Posse de Fernando Henrique Cardoso; primeiro ano completo após o Plano Real


def data_fim_padrao() -> str:
    """Data de hoje no formato DD/MM/AAAA, calculada no momento da chamada (não no import)."""
    return date.today().strftime("%d/%m/%Y")


# Mantido por compatibilidade; prefira data_fim_padrao() em processos de longa duração.
DATA_FIM_PADRAO = data_fim_padrao()

# User-Agent do projeto para consumo de APIs públicas.
# O contato deve ser um canal real mantido pelo projeto: defina LEGISDATA_CONTACT no ambiente.
CONTACT_EMAIL = os.environ.get("LEGISDATA_CONTACT", "")
DEFAULT_USER_AGENT = "LegisDataBot/1.0 (Transparencia Publica" + (f"; {CONTACT_EMAIL})" if CONTACT_EMAIL else ")")

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
        "data_inicio": "01/01/1980",
    },
    "ipca_acumulado_12m": {
        "codigo": 13522,
        "nome": "IPCA - Acumulado em 12 meses",
        "unidade": "%",
        "categoria": "INFLACAO",
        "frequencia": "MENSAL",
        "data_inicio": "01/01/1995",
    },
    "selic_meta_ano": {
        "codigo": 432,
        "nome": "Taxa Selic - Meta anual fixada pelo Copom",
        "unidade": "% a.a.",
        "categoria": "JUROS_SELIC",
        "frequencia": "DIARIA_OU_REUNIAO",
        "data_inicio": "04/03/1999",
    },
    "selic_acumulada_mes": {
        "codigo": 4390,
        "nome": "Taxa Selic acumulada no mês",
        "unidade": "% a.m.",
        "categoria": "JUROS_SELIC",
        "frequencia": "MENSAL",
        "data_inicio": "01/07/1986",
    },
    "cambio_usd_brl_venda": {
        "codigo": 3698,
        "nome": "Taxa de Câmbio - USD / Moeda Nacional (Venda - Média mensal)",
        "unidade": "BRL/USD",
        "categoria": "CAMBIO_DOLAR",
        "frequencia": "MENSAL",
        "data_inicio": "01/01/1985",
    },
    "dolar_ptax_fechamento": {
        "codigo": 10813,
        "nome": "Taxa de Câmbio - Livre - USD / Moeda Nacional (Venda - Fim de período)",
        "unidade": "BRL/USD",
        "categoria": "CAMBIO_DOLAR",
        "frequencia": "MENSAL",
        "data_inicio": "01/01/1985",
    },
    "pib_mensal_corrente": {
        "codigo": 4380,
        "nome": "PIB mensal em valores correntes",
        "unidade": "R$ milhões",
        "categoria": "PIB",
        "frequencia": "MENSAL",
        "data_inicio": "01/01/1990",
    },
    "pib_variacao_anual": {
        "codigo": 7326,
        "nome": "PIB - Taxa de variação real anual",
        "unidade": "% a.a.",
        "categoria": "PIB",
        "frequencia": "ANUAL",
        "data_inicio": "01/01/1996",
    },
    "divida_liquida_pib": {
        "codigo": 4513,
        "nome": "Dívida Líquida do Setor Público (% PIB)",
        "unidade": "% do PIB",
        "categoria": "DIVIDA_PUBLICA",
        "frequencia": "MENSAL",
        "data_inicio": "01/12/2001",
    },
    "divida_bruta_governo_pib": {
        "codigo": 4536,
        "nome": "Dívida Bruta do Governo Geral (% PIB)",
        "unidade": "% do PIB",
        "categoria": "DIVIDA_PUBLICA",
        "frequencia": "MENSAL",
        "data_inicio": "01/12/2001",
    },
    "salario_minimo_nominal": {
        "codigo": 1619,
        "nome": "Salário Mínimo Nominal",
        "unidade": "R$ / Moeda Vigente",
        "categoria": "SALARIO_MINIMO",
        "frequencia": "MENSAL",
        "data_inicio": "01/01/1980",
    },
    "ibovespa_fechamento": {
        "codigo": 7,
        "nome": "Índice Bovespa (Ibovespa) - Fechamento",
        "unidade": "Pontos",
        "categoria": "MERCADO_FINANCEIRO",
        "frequencia": "DIARIA",
        "data_inicio": "01/01/1990",
    },
    "desemprego_pnad": {
        "codigo": 24369,
        "nome": "Taxa de desocupação - PNAD Contínua",
        "unidade": "%",
        "categoria": "DESEMPREGO",
        "frequencia": "MENSAL",
        "data_inicio": "01/01/2012",
    },
}


# Tetos contra download ou zip gigante numa rotina sem supervisão (o contêiner da atualização diária tem 2 GB de
# memória). O maior arquivo real é o das emendas, com cerca de 32 MB compactados; o CSV anual da CEAP da Câmara tem 7,5 MB
# compactados e 82 MB descomprimidos.
TETO_DO_DOWNLOAD = 200 * 1024 * 1024
TETO_DO_CSV = 300 * 1024 * 1024

# Arquivos processados da CEAP e das emendas: a extração (`sync_ceap_emendas`) grava e a carga (`financas_loader`) lê.
CEAP_ARQUIVO = "despesas_ceap_2019_2026.json"
EMENDAS_ARQUIVO = "emendas_parlamentares_2019_2026.json"
# Processos judiciais: a curadoria (entrada, versionada à mão) e o arquivo que o extrator gera a partir dela e a carga lê.
PROCESSOS_CURADORIA_ARQUIVO = "processos_curados.json"
PROCESSOS_ARQUIVO = "processos_judiciais.json"

# As casas do Congresso (a ordem não significa nada: os mapeamentos por casa são sempre explícitos, por nome). Quem produz
# (`financas_loader.anos_publicados_da_ceap`) e quem consome (`sync_ceap_emendas`) os "anos já publicados por casa" usa
# estas chaves; um teste confere a igualdade.
CASAS_DO_CONGRESSO = ("camara", "senado")

# As cargas de finanças que o timer diário atualiza (extração fresca) e as que só mudam com o commit. Ficam aqui, leves, para a
# política de semeadura (`carga_economica`) não precisar importar o loader inteiro só para saber os nomes.
CHAVES_DO_TIMER = ("ceap", "emendas")
CHAVES_ESTATICAS = ("remuneracao", "patrimonio", "doacoes", "certidoes", "processos")
