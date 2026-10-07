"""
Extrator e Catálogo Histórico dos Presidentes da República do Brasil (1992 - Presente)
Abrange desde a posse de Itamar Franco (outubro/1992) até a atual administração.
"""

from typing import List, Dict, Any
from datetime import datetime


PRESIDENTES_HISTORICO: List[Dict[str, Any]] = [
    {
        "id_referencia": "itamar-franco-1992",
        "nome_civil": "Itamar Augusto Cautiero Franco",
        "nome_eleitoral": "Itamar Franco",
        "cpf": None,
        "data_nascimento": "1930-06-28",
        "data_falecimento": "2011-07-02",
        "genero": "MASCULINO",
        "naturalidade_municipio": "Salvador",
        "naturalidade_uf": "BA",
        "partido_eleicao": "PMDB",
        "partido_sigla": "PMDB",
        "partido_nome": "Partido do Movimento Democrático Brasileiro",
        "mandato_numero": 1,
        "ano_eleicao": 1989,  # Eleito vice-presidente na chapa de Fernando Collor
        "data_inicio": "1992-10-02",  # Posse interina (afastamento de Collor) / Efetivação em 29/12/1992
        "data_fim": "1995-01-01",
        "status_mandato": "CONCLUIDO",
        "motivo_inicio": "Assumiu interinamente após abertura do processo de impeachment de Collor; efetivado com a renúncia deste.",
        "vice_presidente": "Vago (Itamar era o vice-presidente)",
        "ministros_fazenda_chave": [
            {"nome": "Gustavo Krause", "inicio": "1992-10-02", "fim": "1992-12-16"},
            {"nome": "Paulo Roberto Haddad", "inicio": "1992-12-16", "fim": "1993-03-01"},
            {"nome": "Eliseu Resende", "inicio": "1993-03-01", "fim": "1993-05-19"},
            {"nome": "Fernando Henrique Cardoso", "inicio": "1993-05-19", "fim": "1994-03-30", "papel": "Arquiteto do Plano Real"},
            {"nome": "Rubens Ricupero", "inicio": "1994-03-30", "fim": "1994-09-06"},
            {"nome": "Ciro Gomes", "inicio": "1994-09-06", "fim": "1995-01-01"}
        ],
        "marcos_economicos": [
            "Lançamento do Plano Real (Medida Provisória nº 434 de 27/02/1994)",
            "Criação da Unidade Real de Valor (URV) em março de 1994",
            "Entrada em circulação da nova moeda Real (R$) em 01/07/1994",
            "Fim da hiperinflação crônica de décadas (queda de ~40% ao mês para ~2% ao mês)"
        ],
        "foto_url": "/presidents/itamar-franco.jpg"
    },
    {
        "id_referencia": "fhc-1995",
        "nome_civil": "Fernando Henrique Cardoso",
        "nome_eleitoral": "Fernando Henrique Cardoso (FHC 1)",
        "cpf": None,
        "data_nascimento": "1931-06-18",
        "data_falecimento": None,
        "genero": "MASCULINO",
        "naturalidade_municipio": "Rio de Janeiro",
        "naturalidade_uf": "RJ",
        "partido_eleicao": "PSDB",
        "partido_sigla": "PSDB",
        "partido_nome": "Partido da Social Democracia Brasileira",
        "mandato_numero": 1,
        "ano_eleicao": 1994,
        "data_inicio": "1995-01-01",
        "data_fim": "1999-01-01",
        "status_mandato": "CONCLUIDO",
        "motivo_inicio": "Eleito em 1º turno com 54,28% dos votos válidos.",
        "vice_presidente": "Marco Maciel (PFL)",
        "ministros_fazenda_chave": [
            {"nome": "Pedro Malan", "inicio": "1995-01-01", "fim": "1999-01-01", "papel": "Consolidação da estabilização monetária"}
        ],
        "marcos_economicos": [
            "Regime de bandas cambiais (âncora cambial para conter preços)",
            "Programa de Estímulo à Reestruturação e ao Sistema Financeiro Nacional (PROER)",
            "Grandes privatizações (Sistema Telebrás, Companhia Vale do Rio Doce - CVRD)",
            "Emenda Constitucional da Reeleição (EC nº 16/1997)",
            "Impacto da Crise Asiática (1997) e Crise Russa (1998) com elevação recorde da Selic a 45% a.a."
        ],
        "foto_url": "/presidents/fhc.jpg"
    },
    {
        "id_referencia": "fhc-1999",
        "nome_civil": "Fernando Henrique Cardoso",
        "nome_eleitoral": "Fernando Henrique Cardoso (FHC 2)",
        "cpf": None,
        "data_nascimento": "1931-06-18",
        "data_falecimento": None,
        "genero": "MASCULINO",
        "naturalidade_municipio": "Rio de Janeiro",
        "naturalidade_uf": "RJ",
        "partido_eleicao": "PSDB",
        "partido_sigla": "PSDB",
        "partido_nome": "Partido da Social Democracia Brasileira",
        "mandato_numero": 2,
        "ano_eleicao": 1998,
        "data_inicio": "1999-01-01",
        "data_fim": "2003-01-01",
        "status_mandato": "CONCLUIDO",
        "motivo_inicio": "Reeleito em 1º turno com 53,06% dos votos válidos.",
        "vice_presidente": "Marco Maciel (PFL)",
        "ministros_fazenda_chave": [
            {"nome": "Pedro Malan", "inicio": "1999-01-01", "fim": "2003-01-01"}
        ],
        "marcos_economicos": [
            "Transição para Câmbio Flutuante em janeiro de 1999 após maxidesvalorização do Real",
            "Criação do Regime de Metas para a Inflação (Decreto nº 3.088/1999) sob Arminio Fraga no BCB",
            "Implementação do 'Tripé Macroeconômico' (Câmbio Flutuante, Metas de Inflação e Metas de Superávit Primário)",
            "Aprovação da Lei de Responsabilidade Fiscal - LRF (Lei Complementar nº 101/2000)",
            "Crise energética brasileira ('Crise do Apagão' em 2001) e recessão pontual"
        ],
        "foto_url": "/presidents/fhc.jpg"
    },
    {
        "id_referencia": "lula-2003",
        "nome_civil": "Luiz Inácio Lula da Silva",
        "nome_eleitoral": "Lula (Lula 1)",
        "cpf": None,
        "data_nascimento": "1945-10-27",
        "data_falecimento": None,
        "genero": "MASCULINO",
        "naturalidade_municipio": "Caetés",
        "naturalidade_uf": "PE",
        "partido_eleicao": "PT",
        "partido_sigla": "PT",
        "partido_nome": "Partido dos Trabalhadores",
        "mandato_numero": 1,
        "ano_eleicao": 2002,
        "data_inicio": "2003-01-01",
        "data_fim": "2007-01-01",
        "status_mandato": "CONCLUIDO",
        "motivo_inicio": "Eleito em 2º turno com 61,27% dos votos válidos.",
        "vice_presidente": "José Alencar (PL)",
        "ministros_fazenda_chave": [
            {"nome": "Antonio Palocci", "inicio": "2003-01-01", "fim": "2006-03-27"},
            {"nome": "Guido Mantega", "inicio": "2006-03-27", "fim": "2007-01-01"}
        ],
        "marcos_economicos": [
            "Manutenção do Tripé Macroeconômico e credibilidade da 'Carta ao Povo Brasileiro'",
            "Henrique Meirelles na presidência do Banco Central",
            "Início do grande ciclo global de alta das commodities (Boom das Commodities)",
            "Criação e unificação do Programa Bolsa Família (Lei nº 10.836/2004)",
            "Quitação antecipada da dívida brasileira com o Fundo Monetário Internacional (FMI) em 2005",
            "Início da expressiva acumulação de reservas internacionais em moeda estrangeira"
        ],
        "foto_url": "/presidents/lula.jpg"
    },
    {
        "id_referencia": "lula-2007",
        "nome_civil": "Luiz Inácio Lula da Silva",
        "nome_eleitoral": "Lula (Lula 2)",
        "cpf": None,
        "data_nascimento": "1945-10-27",
        "data_falecimento": None,
        "genero": "MASCULINO",
        "naturalidade_municipio": "Caetés",
        "naturalidade_uf": "PE",
        "partido_eleicao": "PT",
        "partido_sigla": "PT",
        "partido_nome": "Partido dos Trabalhadores",
        "mandato_numero": 2,
        "ano_eleicao": 2006,
        "data_inicio": "2007-01-01",
        "data_fim": "2011-01-01",
        "status_mandato": "CONCLUIDO",
        "motivo_inicio": "Reeleito em 2º turno com 60,83% dos votos válidos.",
        "vice_presidente": "José Alencar (PRB)",
        "ministros_fazenda_chave": [
            {"nome": "Guido Mantega", "inicio": "2007-01-01", "fim": "2011-01-01"}
        ],
        "marcos_economicos": [
            "Lançamento do Programa de Aceleração do Crescimento (PAC)",
            "Descoberta e anúncio comercial da camada Pré-Sal na Bacia de Santos",
            "Conquista do Grau de Investimento (Investment Grade) pelas agências S&P e Fitch em 2008",
            "Enfrentamento da Crise Financeira Global (Subprime 2008) via bancos públicos e desonerações (IPI)",
            "Crescimento recorde do PIB em 2010 (+7,5%), maior taxa em mais de 24 anos"
        ],
        "foto_url": "/presidents/lula.jpg"
    },
    {
        "id_referencia": "dilma-2011",
        "nome_civil": "Dilma Vana Rousseff",
        "nome_eleitoral": "Dilma Rousseff (Dilma 1)",
        "cpf": None,
        "data_nascimento": "1947-12-14",
        "data_falecimento": None,
        "genero": "FEMININO",
        "naturalidade_municipio": "Belo Horizonte",
        "naturalidade_uf": "MG",
        "partido_eleicao": "PT",
        "partido_sigla": "PT",
        "partido_nome": "Partido dos Trabalhadores",
        "mandato_numero": 1,
        "ano_eleicao": 2010,
        "data_inicio": "2011-01-01",
        "data_fim": "2015-01-01",
        "status_mandato": "CONCLUIDO",
        "motivo_inicio": "Eleita em 2º turno com 56,05% dos votos válidos.",
        "vice_presidente": "Michel Temer (PMDB)",
        "ministros_fazenda_chave": [
            {"nome": "Guido Mantega", "inicio": "2011-01-01", "fim": "2015-01-01"}
        ],
        "marcos_economicos": [
            "Adoção da chamada 'Nova Matriz Econômica' (estímulo fiscal, controle tarifário e subsídios via BNDES)",
            "Queda da Taxa Selic para mínimas históricas temporárias (7,25% a.a. em 2012) e subsequente pressão inflacionária",
            "Desonerações da folha de pagamento e contenção artificial de tarifas de energia e combustíveis",
            "Mínima taxa histórica de desemprego (em torno de 4,8% em 2014) em contraste com perda de dinamismo industrial",
            "Jornadas de Junho de 2013 (grandes manifestações populares)"
        ],
        "foto_url": "/presidents/dilma.jpg"
    },
    {
        "id_referencia": "dilma-2015",
        "nome_civil": "Dilma Vana Rousseff",
        "nome_eleitoral": "Dilma Rousseff (Dilma 2)",
        "cpf": None,
        "data_nascimento": "1947-12-14",
        "data_falecimento": None,
        "genero": "FEMININO",
        "naturalidade_municipio": "Belo Horizonte",
        "naturalidade_uf": "MG",
        "partido_eleicao": "PT",
        "partido_sigla": "PT",
        "partido_nome": "Partido dos Trabalhadores",
        "mandato_numero": 2,
        "ano_eleicao": 2014,
        "data_inicio": "2015-01-01",
        "data_fim": "2016-08-31",
        "status_mandato": "IMPEACHMENT",
        "motivo_inicio": "Reeleita em 2º turno com 51,64% dos votos válidos.",
        "vice_presidente": "Michel Temer (PMDB)",
        "ministros_fazenda_chave": [
            {"nome": "Joaquim Levy", "inicio": "2015-01-01", "fim": "2015-12-18", "papel": "Tentativa de ajuste fiscal"},
            {"nome": "Nelson Barbosa", "inicio": "2015-12-18", "fim": "2016-05-12"}
        ],
        "marcos_economicos": [
            "Grave recessão econômica de 2015-2016 (queda acumulada de ~7% do PIB)",
            "Aceleração inflacionária (IPCA superior a 10% em 2015) com tarifaço e correção de preços represados",
            "Perda do Grau de Investimento soberano pelas agências de risco",
            "Deterioração das contas públicas, déficits primários sucessivos e pedaladas fiscais",
            "Processo de impeachment votado pelo Congresso Nacional, concluído em 31/08/2016"
        ],
        "foto_url": "/presidents/dilma.jpg"
    },
    {
        "id_referencia": "temer-2016",
        "nome_civil": "Michel Miguel Elias Temer Lulia",
        "nome_eleitoral": "Michel Temer",
        "cpf": None,
        "data_nascimento": "1940-09-23",
        "data_falecimento": None,
        "genero": "MASCULINO",
        "naturalidade_municipio": "Tietê",
        "naturalidade_uf": "SP",
        "partido_eleicao": "PMDB",
        "partido_sigla": "MDB",
        "partido_nome": "Movimento Democrático Brasileiro",
        "mandato_numero": 1,
        "ano_eleicao": 2014,
        "data_inicio": "2016-08-31",  # Interino desde 12/05/2016, efetivado em 31/08/2016
        "data_fim": "2019-01-01",
        "status_mandato": "CONCLUIDO",
        "motivo_inicio": "Assumiu como presidente em exercício em maio/2016 e definitivamente após a cassação do mandato de Dilma Rousseff.",
        "vice_presidente": "Vago (Temer era o vice-presidente)",
        "ministros_fazenda_chave": [
            {"nome": "Henrique Meirelles", "inicio": "2016-05-12", "fim": "2018-04-10"},
            {"nome": "Eduardo Guardia", "inicio": "2018-04-10", "fim": "2019-01-01"}
        ],
        "marcos_economicos": [
            "Implementação do documento 'Uma Ponte para o Futuro'",
            "Aprovação da Emenda Constitucional do Teto de Gastos Públicos (EC nº 95/2016)",
            "Aprovação da Reforma Trabalhista (Lei nº 13.467/2017)",
            "Queda acelerada da inflação e redução da Selic de 14,25% para 6,5% a.a.",
            "Ilan Goldfajn na presidência do Banco Central",
            "Crise da Greve dos Caminhoneiros em maio de 2018 com desabastecimento temporário"
        ],
        "foto_url": "/presidents/temer.jpg"
    },
    {
        "id_referencia": "bolsonaro-2019",
        "nome_civil": "Jair Messias Bolsonaro",
        "nome_eleitoral": "Jair Bolsonaro",
        "cpf": None,
        "data_nascimento": "1955-03-21",
        "data_falecimento": None,
        "genero": "MASCULINO",
        "naturalidade_municipio": "Glicério",
        "naturalidade_uf": "SP",
        "partido_eleicao": "PSL",
        "partido_sigla": "PL",  # Filiou-se ao PL posteriormente
        "partido_nome": "Partido Liberal",
        "mandato_numero": 1,
        "ano_eleicao": 2018,
        "data_inicio": "2019-01-01",
        "data_fim": "2023-01-01",
        "status_mandato": "CONCLUIDO",
        "motivo_inicio": "Eleito em 2º turno com 55,13% dos votos válidos.",
        "vice_presidente": "Hamilton Mourão (PRTB)",
        "ministros_fazenda_chave": [
            {"nome": "Paulo Guedes", "inicio": "2019-01-01", "fim": "2023-01-01", "papel": "Superministro da Economia"}
        ],
        "marcos_economicos": [
            "Aprovação da Nova Reforma da Previdência (EC nº 103/2019)",
            "Aprovação da Lei de Liberdade Econômica (Lei nº 13.874/2019)",
            "Aprovação da Autonomia Formal do Banco Central do Brasil (LC nº 179/2021)",
            "Lançamento do sistema de pagamentos instantâneos PIX pelo Banco Central (nov/2020)",
            "Pandemia de Covid-19 (2020-2021) com aprovação do Orçamento de Guerra e Auxílio Emergencial",
            "Forte desvalorização cambial (dólar acima de R$ 5,00) e choque inflacionário global de combustíveis e alimentos"
        ],
        "foto_url": "/presidents/bolsonaro.jpg"
    },
    {
        "id_referencia": "lula-2023",
        "nome_civil": "Luiz Inácio Lula da Silva",
        "nome_eleitoral": "Lula (Lula 3)",
        "cpf": None,
        "data_nascimento": "1945-10-27",
        "data_falecimento": None,
        "genero": "MASCULINO",
        "naturalidade_municipio": "Caetés",
        "naturalidade_uf": "PE",
        "partido_eleicao": "PT",
        "partido_sigla": "PT",
        "partido_nome": "Partido dos Trabalhadores",
        "mandato_numero": 3,
        "ano_eleicao": 2022,
        "data_inicio": "2023-01-01",
        "data_fim": "2027-01-01",
        "status_mandato": "TITULAR_ATIVO",
        "motivo_inicio": "Eleito em 2º turno com 50,90% dos votos válidos.",
        "vice_presidente": "Geraldo Alckmin (PSB)",
        "ministros_fazenda_chave": [
            {"nome": "Fernando Haddad", "inicio": "2023-01-01", "fim": None, "papel": "Ministro da Fazenda"},
            {"nome": "Simone Tebet", "inicio": "2023-01-01", "fim": None, "papel": "Ministra do Planejamento"}
        ],
        "marcos_economicos": [
            "Aprovação do Novo Arcabouço Fiscal (Lei Complementar nº 200/2023) substituindo o Teto de Gastos",
            "Aprovação histórica da Reforma Tributária sobre o Consumo (EC nº 132/2023 - IVA Dual: CBS e IBS)",
            "Reelevação da nota soberana de crédito do Brasil por agências globais (S&P, Fitch, Moody's)",
            "Queda da inflação e ciclo de alívio monetário seguido de vigilância fiscal",
            "Adoção do Plano de Transformação Ecológica e retomada dos investimentos do Novo PAC"
        ],
        "foto_url": "/presidents/lula.jpg"
    }
]


class PresidentsExtractor:
    """Extrai e manipula a linha do tempo dos presidentes brasileiros."""

    @staticmethod
    def get_presidents() -> List[Dict[str, Any]]:
        """Retorna a lista completa e estruturada dos presidentes desde 1992."""
        return PRESIDENTES_HISTORICO

    @staticmethod
    def get_mandate_by_date(date_str: str) -> Dict[str, Any]:
        """
        Retorna o presidente que governava na data especificada (formato YYYY-MM-DD).
        """
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        for pres in PRESIDENTES_HISTORICO:
            dt_inicio = datetime.strptime(pres["data_inicio"], "%Y-%m-%d")
            dt_fim = datetime.strptime(pres["data_fim"], "%Y-%m-%d") if pres["data_fim"] else datetime.now()
            if dt_inicio <= dt <= dt_fim:
                return pres
        return None
