"""Parsing das despesas da cota parlamentar (CEAP Câmara e CEAPS Senado).

Câmara: https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip
    CSV UTF-8 com BOM, ';', decimal com ponto. ideCadastro = id do deputado na API
    de Dados Abertos (= Politician.camara_id). Linhas de liderança/bloco
    (ex.: "LID.GOV-CD") vêm com ideCadastro vazio e não são de um deputado.
    ideDocumento identifica o documento; o mesmo documento pode aparecer em mais de
    uma linha (parcelas, bilhetes), por isso a chave de deduplicação é
    (ideDocumento, numParcela, txtPassageiro, txtTrecho, vlrLiquido) quando existe ideDocumento.
Senado: https://adm.senado.gov.br/adm-dadosabertos/api/v1/senadores/despesas_ceaps/{ano}
    JSON; "id" é único por lançamento; codSenador = Politician.senado_id.
"""

from datetime import date, datetime
from typing import Dict, Optional, Tuple

from etl.parsers.valores import parse_int, parse_valor_ponto, texto_ou_none

URL_CAMARA_CEAP_ANO = "https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip"
URL_SENADO_CEAPS_ANO = "https://adm.senado.gov.br/adm-dadosabertos/api/v1/senadores/despesas_ceaps/{ano}"


def parse_data(valor) -> Optional[date]:
    s = texto_ou_none(valor)
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            d = datetime.strptime(s[:19] if "T" in s else s[:10], fmt).date()
        except ValueError:
            continue
        # A API do Senado tem datas digitadas erradas (ex.: ano 0204). Fora de uma
        # janela plausível, a data é descartada (o ano/mês de competência permanecem).
        if 2000 <= d.year <= 2100:
            return d
        return None
    return None


def chave_camara(linha: Dict[str, str]) -> Optional[Tuple]:
    doc = texto_ou_none(linha.get("ideDocumento"))
    if not doc:
        return None
    return (
        "camara", doc,
        texto_ou_none(linha.get("numParcela")) or "0",
        texto_ou_none(linha.get("txtPassageiro")) or "",
        texto_ou_none(linha.get("txtTrecho")) or "",
        texto_ou_none(linha.get("vlrLiquido")) or "",
    )


def normalizar_linha_camara(linha: Dict[str, str], fonte_url: str) -> Optional[dict]:
    """Linha do CSV anual da Câmara -> registro de despesa, ou None se não for de deputado."""
    camara_id = parse_int(linha.get("ideCadastro"))
    if camara_id is None:
        return None
    ano = parse_int(linha.get("numAno"))
    valor = parse_valor_ponto(linha.get("vlrLiquido"))
    if ano is None or valor is None:
        return None
    return {
        "casa": "camara",
        "parlamentar_id": camara_id,
        "id_documento": texto_ou_none(linha.get("ideDocumento")),
        "ano": ano,
        "mes": parse_int(linha.get("numMes")),
        "tipo_despesa": texto_ou_none(linha.get("txtDescricao")) or "Não informado na fonte",
        "valor_liquido": valor,
        "fornecedor": texto_ou_none(linha.get("txtFornecedor")) or "Não informado na fonte",
        "cnpj_cpf": texto_ou_none(linha.get("txtCNPJCPF")),
        "data_emissao": parse_data(linha.get("datEmissao")),
        "url_documento": texto_ou_none(linha.get("urlDocumento")),
        "fonte_url": fonte_url,
        "chave": chave_camara(linha),
    }


def normalizar_item_senado(item: dict, fonte_url: str) -> Optional[dict]:
    senado_id = parse_int(item.get("codSenador"))
    ano = parse_int(item.get("ano"))
    valor = parse_valor_ponto(item.get("valorReembolsado"))
    if senado_id is None or ano is None or valor is None:
        return None
    lanc_id = texto_ou_none(item.get("id"))
    return {
        "casa": "senado",
        "parlamentar_id": senado_id,
        "id_documento": lanc_id,
        "ano": ano,
        "mes": parse_int(item.get("mes")),
        "tipo_despesa": texto_ou_none(item.get("tipoDespesa")) or "Não informado na fonte",
        "valor_liquido": valor,
        "fornecedor": texto_ou_none(item.get("fornecedor")) or "Não informado na fonte",
        "cnpj_cpf": texto_ou_none(item.get("cpfCnpj")),
        "data_emissao": parse_data(item.get("data")),
        # O Senado não publica link do comprovante por lançamento.
        "url_documento": None,
        "fonte_url": fonte_url,
        "chave": ("senado", lanc_id) if lanc_id else None,
    }
