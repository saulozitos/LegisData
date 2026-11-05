"""
Dados curados dos partidos políticos: espectro, nomes completos, logos e metadados (ideologia, lema, número eleitoral).

São dados de domínio, sem acesso a banco e sem dependência dos modelos ORM do staging: o espectro é o nome do valor de
`EspectroPoliticoEnum` em texto. Cada metadado curado vale só para a sigla em que está; sigla sem entrada fica sem
ideologia, lema e espectro (nunca recebe texto genérico inventado). Chaves de `PARTY_LOGOS_MAP` e `PARTY_METADATA_MAP`
em maiúsculas para correspondência uniforme.
"""

from etl.pipelines.loader_helpers import SEM_PARTIDO

# Partidos que sempre existem, com o nome completo (a sigla de quem não tem partido vem de `SEM_PARTIDO`)
PARTIDOS_BASE = {
    "PMDB": "Partido do Movimento Democrático Brasileiro",
    "MDB": "Movimento Democrático Brasileiro",
    "PSDB": "Partido da Social Democracia Brasileira",
    "PT": "Partido dos Trabalhadores",
    "PSL": "Partido Social Liberal",
    "PL": "Partido Liberal",
    "PFL": "Partido da Frente Liberal",
    "DEM": "Democratas",
    "UNIÃO": "União Brasil",
    "PP": "Progressistas",
    "PSD": "Partido Social Democrático",
    "REPUBLICANOS": "Republicanos",
    "PSB": "Partido Socialista Brasileiro",
    "PDT": "Partido Democrático Trabalhista",
    "PSOL": "Partido Socialismo e Liberdade",
    "PODE": "Podemos",
    "AVANTE": "Avante",
    "SOLIDARIEDADE": "Solidariedade",
    "NOVO": "Partido Novo",
    "PCdoB": "Partido Comunista do Brasil",
    "PV": "Partido Verde",
    "CIDADANIA": "Cidadania",
    "REDE": "Rede Sustentabilidade",
    "PRD": "Partido Renovação Democrática",
    "PRTB": "Partido Renovador Trabalhista Brasileiro",
    SEM_PARTIDO: "Sem Partido",
}

PARTY_SPECTRUM_MAP = {
    # ESQUERDA
    "PT": "ESQUERDA",
    "PSOL": "ESQUERDA",
    "PCdoB": "ESQUERDA",
    "PC do B": "ESQUERDA",
    "PSTU": "ESQUERDA",
    "PCO": "ESQUERDA",
    "UP": "ESQUERDA",
    "PCB": "ESQUERDA",
    # CENTRO_ESQUERDA
    "PDT": "CENTRO_ESQUERDA",
    "PSB": "CENTRO_ESQUERDA",
    "REDE": "CENTRO_ESQUERDA",
    "PV": "CENTRO_ESQUERDA",
    "CIDADANIA": "CENTRO_ESQUERDA",
    # CENTRO
    "MDB": "CENTRO",
    "PMDB": "CENTRO",
    "PSD": "CENTRO",
    "PSDB": "CENTRO",
    "SOLIDARIEDADE": "CENTRO",
    "AVANTE": "CENTRO",
    "PMN": "CENTRO",
    "AGIR": "CENTRO",
    # CENTRO_DIREITA
    "UNIÃO": "CENTRO_DIREITA",
    "UNIAO": "CENTRO_DIREITA",
    "PP": "CENTRO_DIREITA",
    "PPB": "CENTRO_DIREITA",
    "PPR": "CENTRO_DIREITA",
    "REPUBLICANOS": "CENTRO_DIREITA",
    "PRB": "CENTRO_DIREITA",
    "PODE": "CENTRO_DIREITA",
    "PODEMOS": "CENTRO_DIREITA",
    "PRD": "CENTRO_DIREITA",
    "PSC": "CENTRO_DIREITA",
    "DEM": "CENTRO_DIREITA",
    "PFL": "CENTRO_DIREITA",
    "PTB": "CENTRO_DIREITA",
    # DIREITA
    "PL": "DIREITA",
    "NOVO": "DIREITA",
    "PATRIOTA": "DIREITA",
    "PATRI": "DIREITA",
    "DC": "DIREITA",
    "PMB": "DIREITA",
    "PRTB": "DIREITA",
    "PSL": "DIREITA",
}

# Nomes completos de partidos extintos/renomeados que aparecem em filiações históricas e votos. Sem isto,
# cada um deles virava "Sem Partido" e a trajetória partidária de quem passou por eles era apagada.
PARTY_FULL_NAMES = {
    "PTB": "Partido Trabalhista Brasileiro",
    "PATRIOTA": "Patriota",
    "PATRI": "Patriota",
    "PROS": "Partido Republicano da Ordem Social",
    "PSC": "Partido Social Cristão",
    "PRP": "Partido Republicano Progressista",
    "PHS": "Partido Humanista da Solidariedade",
    "PPS": "Partido Popular Socialista",
    "PRB": "Partido Republicano Brasileiro",
    "PMN": "Partido da Mobilização Nacional",
    "PEN": "Partido Ecológico Nacional",
    "PR": "Partido da República",
    "PDS": "Partido Democrático Social",
    "PPB": "Partido Progressista Brasileiro",
    "PPR": "Partido Progressista Reformador",
    "PC DO B": "Partido Comunista do Brasil",
}


PARTY_LOGOS_MAP = {
    "PT": "https://thumb.wikimedia.org/wikipedia/commons/thumb/c/c3/PT_%28Brazil%29_logo_2021.svg/250px-PT_%28Brazil%29_logo_2021.svg.png",
    "PL": "https://thumb.wikimedia.org/wikipedia/commons/thumb/1/12/Partido_Liberal_%28Brazil%29_logo.svg/250px-Partido_Liberal_%28Brazil%29_logo.svg.png",
    "PSDB": "https://thumb.wikimedia.org/wikipedia/commons/thumb/2/22/Logo_of_the_Brazilian_Social_Democracy_Party_%282023%29.svg/250px-Logo_of_the_Brazilian_Social_Democracy_Party_%282023%29.svg.png",
    "MDB": "https://thumb.wikimedia.org/wikipedia/commons/thumb/e/ef/Movimento_Democr%C3%A1tico_Brasileiro_%282017%29.svg/250px-Movimento_Democr%C3%A1tico_Brasileiro_%282017%29.svg.png",
    "PMDB": "https://thumb.wikimedia.org/wikipedia/commons/thumb/c/cc/PMDB_2000_a_2017.svg/250px-PMDB_2000_a_2017.svg.png",
    "PSOL": "https://thumb.wikimedia.org/wikipedia/commons/thumb/f/f4/Logo_PSOL_roxo.svg/250px-Logo_PSOL_roxo.svg.png",
    "NOVO": "https://thumb.wikimedia.org/wikipedia/commons/thumb/d/d3/Partido_Novo_logo_%282023%29.svg/250px-Partido_Novo_logo_%282023%29.svg.png",
    "UNIÃO": "https://thumb.wikimedia.org/wikipedia/commons/thumb/7/73/Uni%C3%A3o_Brasil_logo.svg/250px-Uni%C3%A3o_Brasil_logo.svg.png",
    "PP": "https://thumb.wikimedia.org/wikipedia/commons/thumb/8/87/Progressistas_%28Brazil%29_logo.svg/250px-Progressistas_%28Brazil%29_logo.svg.png",
    "PDT": "https://thumb.wikimedia.org/wikipedia/commons/thumb/1/1f/Bandeira.PDT.png/250px-Bandeira.PDT.png",
    "PSB": "https://thumb.wikimedia.org/wikipedia/commons/thumb/1/19/Partido_Socialista_Brasileiro_logo.png/250px-Partido_Socialista_Brasileiro_logo.png",
    "REPUBLICANOS": "https://thumb.wikimedia.org/wikipedia/pt/thumb/0/0d/Republicanos_logo.png/250px-Republicanos_logo.png",
    "PCdoB": "https://thumb.wikimedia.org/wikipedia/commons/thumb/b/b2/Logomarca_do_Partido_Comunista_do_Brasil.png/250px-Logomarca_do_Partido_Comunista_do_Brasil.png",
    "PV": "https://thumb.wikimedia.org/wikipedia/commons/thumb/4/46/Logomarca_do_Partido_Verde.svg/250px-Logomarca_do_Partido_Verde.svg.png",
    "REDE": "https://thumb.wikimedia.org/wikipedia/commons/thumb/3/39/Rede_Sustentabilidade_logo.svg/250px-Rede_Sustentabilidade_logo.svg.png",
    "CIDADANIA": "https://thumb.wikimedia.org/wikipedia/commons/thumb/9/9e/Cidadania_%28Brasil%29_logo_%28variant_1%29.svg/250px-Cidadania_%28Brasil%29_logo_%28variant_1%29.svg.png",
    "PODEMOS": "https://thumb.wikimedia.org/wikipedia/commons/thumb/2/2d/Podemos_%28Brasil%29_logo.svg/250px-Podemos_%28Brasil%29_logo.svg.png",
    "PODE": "https://thumb.wikimedia.org/wikipedia/commons/thumb/2/2d/Podemos_%28Brasil%29_logo.svg/250px-Podemos_%28Brasil%29_logo.svg.png",
    "SOLIDARIEDADE": "https://thumb.wikimedia.org/wikipedia/commons/thumb/7/77/Solidariedade_77_%28Brasil%29_logo.svg/250px-Solidariedade_77_%28Brasil%29_logo.svg.png",
    "AVANTE": "https://thumb.wikimedia.org/wikipedia/commons/thumb/f/f9/Avante_70_%28Brasil%29_logo.svg/250px-Avante_70_%28Brasil%29_logo.svg.png",
    "PRD": "https://thumb.wikimedia.org/wikipedia/commons/thumb/d/dc/Partido_Renova%C3%A7%C3%A3o_Democr%C3%A1tica_logo.svg/250px-Partido_Renova%C3%A7%C3%A3o_Democr%C3%A1tica_logo.svg.png",
    "PSD": "https://thumb.wikimedia.org/wikipedia/commons/thumb/0/0c/PSD_Brazil_logo.svg/250px-PSD_Brazil_logo.svg.png",
    "DC": "https://thumb.wikimedia.org/wikipedia/commons/thumb/e/ed/Logomarca_Democracia_Crist%C3%A3.svg/250px-Logomarca_Democracia_Crist%C3%A3.svg.png",
    "DEM": "https://thumb.wikimedia.org/wikipedia/commons/thumb/3/39/Democratas_%28Brazil%29_logo_%282018-2022%29_%28horizontal%29.svg/250px-Democratas_%28Brazil%29_logo_%282018-2022%29_%28horizontal%29.svg.png",
    "PATRIOTA": "https://thumb.wikimedia.org/wikipedia/commons/thumb/f/f9/Logomarca_do_Partido_Patriota.png/250px-Logomarca_do_Partido_Patriota.png",
    "PFL": "https://thumb.wikimedia.org/wikipedia/commons/thumb/e/e7/Partido_da_Frente_Liberal_logo_%281985-2005%29.svg/250px-Partido_da_Frente_Liberal_logo_%281985-2005%29.svg.png",
    "PRTB": "https://thumb.wikimedia.org/wikipedia/commons/thumb/d/d5/Logomarca_do_Partido_Renovador_Trabalhista_Brasileiro_2.png/250px-Logomarca_do_Partido_Renovador_Trabalhista_Brasileiro_2.png",
    "PTB": "https://thumb.wikimedia.org/wikipedia/commons/thumb/6/6a/Logomarca_Partido_Trabalhista_Brasileiro.png/250px-Logomarca_Partido_Trabalhista_Brasileiro.png",
    "MISSÃO": "https://thumb.wikimedia.org/wikipedia/commons/thumb/6/67/Partido_Miss%C3%A3o_logo_%28light%29.svg/250px-Partido_Miss%C3%A3o_logo_%28light%29.svg.png",
    "PROS": "https://thumb.wikimedia.org/wikipedia/commons/thumb/e/ee/Logomarca_do_Partido_Republicano_da_Ordem_Social_%28PROS%29%2C_do_Brasil.png/250px-Logomarca_do_Partido_Republicano_da_Ordem_Social_%28PROS%29%2C_do_Brasil.png",
    "PSC": "https://thumb.wikimedia.org/wikipedia/commons/thumb/a/a9/PSC_logo%28cortado%29.png/250px-PSC_logo%28cortado%29.png",
    "PSL": "https://thumb.wikimedia.org/wikipedia/commons/thumb/c/c2/Partido_Social_Liberal_logo.svg/250px-Partido_Social_Liberal_logo.svg.png",
    "PR": "https://thumb.wikimedia.org/wikipedia/commons/thumb/f/fe/Logomarca_do_Partido_da_Rep%C3%BAblica.png/250px-Logomarca_do_Partido_da_Rep%C3%BAblica.png",
    "PPS": "https://thumb.wikimedia.org/wikipedia/commons/thumb/d/d3/Logomarca_do_Partido_Popular_Socialista.png/250px-Logomarca_do_Partido_Popular_Socialista.png",
    "PRB": "https://thumb.wikimedia.org/wikipedia/commons/thumb/a/a2/Logomarca_do_Partido_Republicano_Brasileiro_%282012%E2%80%932019%29.png/250px-Logomarca_do_Partido_Republicano_Brasileiro_%282012%E2%80%932019%29.png",
    "PHS": "https://thumb.wikimedia.org/wikipedia/commons/thumb/7/75/Logo_-_Partido_Humanista_da_Solidariedade.png/250px-Logo_-_Partido_Humanista_da_Solidariedade.png",
    "PMN": "https://thumb.wikimedia.org/wikipedia/commons/thumb/d/dd/PMN_logo.svg/250px-PMN_logo.svg.png",
    "PSDC": "https://thumb.wikimedia.org/wikipedia/commons/thumb/a/aa/Bandeira_do_Partido_Social_Democrata_Crist%C3%A3o.svg/250px-Bandeira_do_Partido_Social_Democrata_Crist%C3%A3o.svg.png",
    "PDC": "https://thumb.wikimedia.org/wikipedia/commons/thumb/6/65/Bandeirapdc85melhorada.png/250px-Bandeirapdc85melhorada.png",
    "PDS": "https://thumb.wikimedia.org/wikipedia/commons/thumb/a/a9/Partido_Democr%C3%A1tico_Social_logo.svg/250px-Partido_Democr%C3%A1tico_Social_logo.svg.png",
    "PRONA": "https://thumb.wikimedia.org/wikipedia/commons/thumb/c/ca/Partido_de_Reedifica%C3%A7%C3%A3o_da_Ordem_Nacional_logo_%282004%E2%80%932006%29.png/250px-Partido_de_Reedifica%C3%A7%C3%A3o_da_Ordem_Nacional_logo_%282004%E2%80%932006%29.png",
}

PARTY_METADATA_MAP = {
    "PT": {
        "ideologia": "Social-democracia / Trabalhismo democrático",
        "lema": "O Brasil da esperança e da justiça social",
        "espectro": "ESQUERDA",
        "numero": 13,
    },
    "PL": {
        "ideologia": "Conservadorismo social / Liberalismo econômico",
        "lema": "Deus, Pátria, Família e Liberdade",
        "espectro": "DIREITA",
        "numero": 22,
    },
    "UNIÃO": {
        "ideologia": "Liberalismo / Conservadorismo liberal",
        "lema": "Coragem para mudar, união para governar",
        "espectro": "CENTRO_DIREITA",
        "numero": 44,
    },
    "PP": {
        "ideologia": "Centro-direita / Pragmatismo de desenvolvimento",
        "lema": "O futuro se constrói com trabalho e progresso",
        "espectro": "CENTRO_DIREITA",
        "numero": 11,
    },
    "MDB": {
        "ideologia": "Centrismo / Ponto de equilíbrio democrático",
        "lema": "O partido que equilibra o Brasil",
        "espectro": "CENTRO",
        "numero": 15,
    },
    "PSD": {
        "ideologia": "Pragmatismo de centro / Municipalismo",
        "lema": "Nem direita, nem esquerda: a favor do Brasil",
        "espectro": "CENTRO",
        "numero": 55,
    },
    "REPUBLICANOS": {
        "ideologia": "Conservadorismo cristão / Municipalismo",
        "lema": "Defendendo os valores da família e o desenvolvimento",
        "espectro": "CENTRO_DIREITA",
        "numero": 10,
    },
    "PSDB": {
        "ideologia": "Social-democracia clássica / Terceira via",
        "lema": "Por um Brasil moderno, justo e eficiente",
        "espectro": "CENTRO",
        "numero": 45,
    },
    "PSB": {
        "ideologia": "Socialismo democrático / Progressismo",
        "lema": "Igualdade e liberdade construídas com justiça",
        "espectro": "CENTRO_ESQUERDA",
        "numero": 40,
    },
    "PDT": {
        "ideologia": "Trabalhismo brizolista / Nacionalismo desenvolvimentista",
        "lema": "A educação emancipa, o trabalho dignifica",
        "espectro": "CENTRO_ESQUERDA",
        "numero": 12,
    },
    "PSOL": {
        "ideologia": "Socialismo democrático / Ecossocialismo",
        "lema": "Por um Brasil para a maioria trabalhadora",
        "espectro": "ESQUERDA",
        "numero": 50,
    },
    "PODE": {
        "ideologia": "Democracia direta / Centrismo liberal",
        "lema": "Juntos podemos transformar o Brasil",
        "espectro": "CENTRO",
        "numero": 20,
    },
    "PODEMOS": {
        "ideologia": "Democracia direta / Centrismo liberal",
        "lema": "Juntos podemos transformar o Brasil",
        "espectro": "CENTRO",
        "numero": 20,
    },
    "NOVO": {
        "ideologia": "Liberalismo clássico / Estado mínimo",
        "lema": "Menos governo, mais liberdade individual",
        "espectro": "DIREITA",
        "numero": 30,
    },
    "PCdoB": {
        "ideologia": "Comunismo democrático / Antimperialismo",
        "lema": "Pela soberania nacional e o socialismo",
        "espectro": "ESQUERDA",
        "numero": 65,
    },
    "PV": {
        "ideologia": "Ecologismo / Desenvolvimento sustentável",
        "lema": "Paz, ecologia e justiça socioambiental",
        "espectro": "CENTRO_ESQUERDA",
        "numero": 43,
    },
    "CIDADANIA": {
        "ideologia": "Social-liberalismo / Terceira via",
        "lema": "Construindo cidadania plena e oportunidades",
        "espectro": "CENTRO",
        "numero": 23,
    },
    "REDE": {
        "ideologia": "Sustentabilidade ética / Progressismo cívico",
        "lema": "Conectar pessoas pela ética na política",
        "espectro": "CENTRO_ESQUERDA",
        "numero": 18,
    },
    "AVANTE": {
        "ideologia": "Humanismo cívico / Municipalismo",
        "lema": "O Brasil precisa seguir avante",
        "espectro": "CENTRO",
        "numero": 70,
    },
    "SOLIDARIEDADE": {
        "ideologia": "Trabalhismo social / Sindicalismo plural",
        "lema": "Solidariedade com o trabalhador e o desenvolvimento",
        "espectro": "CENTRO",
        "numero": 77,
    },
    "PRD": {
        "ideologia": "Conservadorismo democrático",
        "lema": "Renovação e ordem institucional",
        "espectro": "CENTRO_DIREITA",
        "numero": 25,
    },
    "DC": {
        "ideologia": "Democracia cristã / Conservadorismo social",
        "lema": "Deus, pátria e família",
        "espectro": "DIREITA",
        "numero": 27,
    },
    "DEM": {
        "ideologia": "Liberalismo / Conservadorismo liberal",
        "lema": "A favor do Brasil",
        "espectro": "CENTRO_DIREITA",
        "numero": 25,
    },
    "PATRIOTA": {
        "ideologia": "Conservadorismo / Nacionalismo",
        "lema": "Brasil acima de tudo",
        "espectro": "DIREITA",
        "numero": 51,
    },
    "PFL": {
        "ideologia": "Liberalismo conservador",
        "lema": "Construindo o futuro",
        "espectro": "CENTRO_DIREITA",
        "numero": 25,
    },
    "PMDB": {
        "ideologia": "Centrismo / Democracia partidária",
        "lema": "O partido do Brasil",
        "espectro": "CENTRO",
        "numero": 15,
    },
    "PRTB": {
        "ideologia": "Trabalhismo participativo / Conservadorismo",
        "lema": "Coragem para transformar",
        "espectro": "DIREITA",
        "numero": 28,
    },
    "PTB": {
        "ideologia": "Trabalhismo / Conservadorismo",
        "lema": "A força do trabalhador",
        "espectro": "DIREITA",
        "numero": 14,
    },
    "MISSÃO": {
        "ideologia": "Liberalismo econômico / Renovação política",
        "lema": "Missão pelo futuro do Brasil",
        "espectro": "CENTRO_DIREITA",
        "numero": 99,
    },
    "PROS": {
        "ideologia": "Centrismo / Reformismo social",
        "lema": "Por um Brasil justo e fraterno",
        "espectro": "CENTRO",
        "numero": 90,
    },
    "PSC": {
        "ideologia": "Democracia cristã / Conservadorismo cristão",
        "lema": "O ser humano em primeiro lugar",
        "espectro": "CENTRO_DIREITA",
        "numero": 20,
    },
    "PSL": {
        "ideologia": "Conservadorismo / Liberalismo",
        "lema": "Mais Brasil, menos Brasília",
        "espectro": "DIREITA",
        "numero": 17,
    },
}

# Chaves em maiúsculas para correspondência uniforme
PARTY_SPECTRUM_MAP = {k.upper(): v for k, v in PARTY_SPECTRUM_MAP.items()}
PARTY_FULL_NAMES = {k.upper(): v for k, v in PARTY_FULL_NAMES.items()}
PARTY_LOGOS_MAP = {k.upper(): v for k, v in PARTY_LOGOS_MAP.items()}
PARTY_METADATA_MAP = {k.upper(): v for k, v in PARTY_METADATA_MAP.items()}


def nome_do_partido(sigla: str) -> str:
    """Nome completo curado do partido; sigla sem nome curado vira `Partido <sigla>` (nunca um nome inventado)."""
    return PARTY_FULL_NAMES.get(sigla.upper(), f"Partido {sigla}")
