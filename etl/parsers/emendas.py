"""Parsing do CSV oficial de Emendas Parlamentares (Portal da Transparência / CGU).

Arquivo: EmendasParlamentares.csv dentro de EmendasParlamentares.zip
(https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares/UNICO).
Formato verificado em out/2026: separador ';', aspas '"', encoding latin-1
(cp1252-compatível; o cabeçalho tem bytes 0xF3 'ó', não é UTF-8), decimal com vírgula.

Valores observados na coluna "Tipo de Emenda" (arquivo de 07/10/2026, 94.638 linhas):
    Emenda Individual - Transferências com Finalidade Definida   79.860
    Emenda Individual - Transferências Especiais                  5.108  ("emendas PIX")
    Emenda de Relator                                             3.892
    Emenda de Bancada                                             3.588
    Emenda de Comissão                                            2.190
Somente os dois tipos "Emenda Individual - ..." têm autor parlamentar individual.
Bancada/Comissão/Relator vêm com autor coletivo ("BANCADA DE ...", "RELATOR GERAL")
ou "Sem informação" e NÃO podem ser atribuídas a um parlamentar.
Mesmo entre as individuais há ~11 mil linhas (2014-2015) com autor "S/I"/"Sem informação":
essas também são descartadas.
"""

from typing import Dict, Iterable, Iterator, List, Optional

from etl.parsers.valores import parse_int, parse_valor_br, texto_ou_none

FONTE_EMENDAS_URL = "https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares/UNICO"
ENCODING_EMENDAS_CSV = "latin-1"
PREFIXO_TIPO_INDIVIDUAL = "Emenda Individual"

# Cabeçalho oficial -> nome interno
COLUNAS = {
    "Código da Emenda": "codigo_emenda",
    "Ano da Emenda": "ano",
    "Tipo de Emenda": "tipo_emenda",
    "Código do Autor da Emenda": "codigo_autor_siafi",
    "Nome do Autor da Emenda": "nome_autor",
    "Localidade de aplicação do recurso": "localidade_destino",
    "Código Município IBGE": "municipio_ibge",
    "UF": "uf",
    "Nome Função": "funcao",
    "Valor Empenhado": "valor_empenhado",
    "Valor Liquidado": "valor_liquidado",
    "Valor Pago": "valor_pago",
}

# Códigos de autor que significam "sem autor individual"
CODIGOS_AUTOR_INVALIDOS = {"-99", "0"}


def eh_emenda_individual(tipo: Optional[str]) -> bool:
    return bool(tipo) and tipo.strip().startswith(PREFIXO_TIPO_INDIVIDUAL)


def autor_identificado(codigo: Optional[str], nome: Optional[str]) -> bool:
    codigo = texto_ou_none(codigo)
    nome = texto_ou_none(nome)
    if not codigo or not nome or codigo in CODIGOS_AUTOR_INVALIDOS:
        return False
    return codigo.lstrip("-").isdigit()


def normalizar_linha(linha: Dict[str, str], fonte_url: str = FONTE_EMENDAS_URL) -> Optional[dict]:
    """Converte uma linha do CSV (chaves = cabeçalho oficial) no registro processado.

    Retorna None se a linha não for emenda individual com autor identificado.
    """
    tipo = texto_ou_none(linha.get("Tipo de Emenda"))
    if not eh_emenda_individual(tipo):
        return None
    codigo_autor = texto_ou_none(linha.get("Código do Autor da Emenda"))
    nome_autor = texto_ou_none(linha.get("Nome do Autor da Emenda"))
    if not autor_identificado(codigo_autor, nome_autor):
        return None
    ano = parse_int(linha.get("Ano da Emenda"))
    if ano is None:
        return None

    def _valor(col):
        v = parse_valor_br(linha.get(col))
        return None if v is None else str(v)

    return {
        "codigo_emenda": texto_ou_none(linha.get("Código da Emenda")),
        "ano": ano,
        "tipo_emenda": tipo,
        "codigo_autor_siafi": codigo_autor,
        "nome_autor": nome_autor,
        "localidade_destino": texto_ou_none(linha.get("Localidade de aplicação do recurso")),
        "municipio_ibge": texto_ou_none(linha.get("Código Município IBGE")),
        "uf": texto_ou_none(linha.get("UF")),
        "funcao": texto_ou_none(linha.get("Nome Função")),
        "valor_empenhado": _valor("Valor Empenhado"),
        "valor_liquidado": _valor("Valor Liquidado"),
        "valor_pago": _valor("Valor Pago"),
        "fonte_url": fonte_url,
    }


def filtrar_linhas(linhas: Iterable[Dict[str, str]], fonte_url: str = FONTE_EMENDAS_URL) -> Iterator[dict]:
    for ln in linhas:
        reg = normalizar_linha(ln, fonte_url)
        if reg is not None:
            yield reg


def validar_cabecalho(cabecalho: List[str]) -> List[str]:
    """Retorna as colunas esperadas que faltam (lista vazia = ok)."""
    presentes = {c.strip().strip('"').lstrip("\ufeff") for c in cabecalho}
    return [c for c in COLUNAS if c not in presentes]
