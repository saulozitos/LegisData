"""Cliente SIDRA: valores ausentes viram None, gzip inesperado é tratado e o cache evita nova consulta."""

import gzip
import json

import pytest

from etl.utils.http_client import HttpError
from etl.utils.sidra import SidraClient, parse_valor, serie_por_ano, serie_por_uf_ano


class HttpFalso:
    def __init__(self, resposta=None, erro=None):
        self.resposta = resposta
        self.erro = erro
        self.urls = []

    def get_bytes(self, url, **_):
        self.urls.append(url)
        if self.erro:
            raise self.erro
        return self.resposta


CABECALHO = {"NC": "Nível", "V": "Valor", "D3C": "Ano (Código)"}


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("0.517", 0.517),
        ("12", 12.0),
        ("-", None),
        ("..", None),
        ("...", None),
        ("X", None),
        ("", None),
        (None, None),
        ("abc", None),
    ],
)
def test_parse_valor_nunca_transforma_ausente_em_zero(texto, esperado):
    assert parse_valor(texto) == esperado


def test_build_url_com_classificacoes():
    url = SidraClient.build_url(7113, 3, "all", "10267", "all", {2: "6794", 58: "2795"})
    assert url == "https://apisidra.ibge.gov.br/values/t/7113/n3/all/v/10267/p/all/c2/6794/c58/2795?formato=json"


def test_values_descarta_cabecalho_e_cacheia(tmp_path):
    corpo = json.dumps([CABECALHO, {"V": "8.8", "D3C": "2012"}, {"V": "-", "D3C": "2013"}]).encode()
    http = HttpFalso(corpo)
    cliente = SidraClient(http=http, cache_dir=tmp_path)
    linhas = cliente.values(5817, 1, "all", "9617")
    assert [r["D3C"] for r in linhas] == ["2012", "2013"]
    assert serie_por_ano(linhas) == {2012: 8.8, 2013: None}
    cliente.values(5817, 1, "all", "9617")
    assert len(http.urls) == 1  # segunda chamada veio do cache


def test_values_descomprime_gzip_inesperado(tmp_path):
    corpo = gzip.compress(json.dumps([CABECALHO, {"V": "1", "D3C": "2020"}]).encode())
    linhas = SidraClient(http=HttpFalso(corpo), cache_dir=tmp_path).values(1, 1)
    assert linhas == [{"V": "1", "D3C": "2020"}]


def test_values_resposta_invalida_levanta_httperror(tmp_path):
    with pytest.raises(HttpError):
        SidraClient(http=HttpFalso(b"<html>erro</html>"), cache_dir=tmp_path).values(1, 1)


def test_try_values_devolve_lista_vazia_em_falha(tmp_path):
    cliente = SidraClient(http=HttpFalso(erro=HttpError("u", 500, "x")), cache_dir=tmp_path)
    assert cliente.try_values(1, 1) == []


def test_serie_por_uf_ano_traduz_codigo_ibge():
    linhas = [
        {"V": "0.5", "D1C": "11", "D3C": "2012"},
        {"V": "0.6", "D1C": "35", "D3C": "2012"},
        {"V": "0.7", "D1C": "99", "D3C": "2012"},  # código desconhecido é ignorado
    ]
    assert serie_por_uf_ano(linhas, "D1C", "D3C") == {"RO": {2012: 0.5}, "SP": {2012: 0.6}}
