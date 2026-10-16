"""BCB: validação de resposta, janelas de 5 anos, cache reaproveitável e nenhum cache de erro."""

import json
import os
import time
from datetime import date

from etl.extractors.bcb_extractor import BCBExtractor, janelas, resposta_valida
from etl.utils.http_client import HttpError


class HttpFalso:
    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.urls = []

    def get_json(self, url, **_):
        self.urls.append(url)
        item = self.respostas.pop(0) if len(self.respostas) > 1 else self.respostas[0]
        if isinstance(item, Exception):
            raise item
        return item


def pontos(*valores):
    return [{"data": f"01/{m:02d}/2020", "valor": str(v)} for m, v in enumerate(valores, start=1)]


def test_resposta_valida():
    assert resposta_valida(pontos(1, 2))
    assert (
        not resposta_valida({"error": "x"})
        and not resposta_valida([])
        and not resposta_valida([{"a": 1}])
        and not resposta_valida(None)
    )


def test_janelas_cobrem_intervalo_sem_sobreposicao_nem_lacuna():
    ini, fim = date(1992, 10, 2), date(2026, 10, 8)
    js = janelas(ini, fim)
    assert js[0][0] == ini and js[-1][1] == fim
    for (a1, b1), (a2, b2) in zip(js, js[1:]):
        assert (a2 - b1).days == 1
    assert all((b.year - a.year) <= 10 for a, b in js)


def test_dict_de_erro_nao_e_cacheado(tmp_path):
    ext = BCBExtractor(tmp_path, http=HttpFalso({"error": "Valor inválido"}))
    assert ext.fetch_serie(433, "01/01/2020", "31/12/2020") == []
    assert list(tmp_path.iterdir()) == []


def test_sucesso_grava_cache_com_nome_estavel_e_reaproveita(tmp_path):
    http = HttpFalso(pontos(1, 2, 3))
    ext = BCBExtractor(tmp_path, http=http)
    assert len(ext.fetch_serie(433, "01/01/2020", "31/12/2020")) == 3
    assert len(ext.fetch_serie(433, "01/01/2020", "30/12/2021")) == 3  # outra data final: mesmo cache
    assert len(http.urls) == 1
    assert [p.name for p in tmp_path.iterdir()] == ["bcb_serie_433_01012020.json"]


def test_cache_expirado_e_ignorado(tmp_path):
    http = HttpFalso(pontos(9))
    ext = BCBExtractor(tmp_path, http=http, cache_max_idade_horas=1)
    arquivo = tmp_path / "bcb_serie_433_01012020.json"
    arquivo.write_text(json.dumps(pontos(1)), encoding="utf-8")
    velho = time.time() - 3 * 3600
    os.utime(arquivo, (velho, velho))
    assert ext.fetch_serie(433, "01/01/2020", "31/12/2020")[0]["valor"] == "9"


def test_recusa_de_janela_longa_repete_em_janelas_menores(tmp_path):
    http = HttpFalso(HttpError("u", 400, "janela"), pontos(1))
    ext = BCBExtractor(tmp_path, http=http)
    dados = ext.fetch_serie(11, "01/01/1990", "31/12/2025")
    assert len(http.urls) >= 4  # 1 tentativa completa + janelas de até 5 anos
    assert len(dados) == len(http.urls) - 1


def test_janela_faltando_nao_devolve_serie_parcial(tmp_path):
    http = HttpFalso(HttpError("u", 400, "janela"), pontos(1), HttpError("u", 500, "falha"))
    ext = BCBExtractor(tmp_path, http=http)
    assert ext.fetch_serie(11, "01/01/1990", "31/12/2025") == []
    assert list(tmp_path.iterdir()) == []


def test_falha_definitiva_devolve_vazio(tmp_path):
    ext = BCBExtractor(tmp_path, http=HttpFalso(HttpError("u", 500, "x")))
    assert ext.fetch_serie(433) == []


def test_ibovespa_anos_sem_valor_ficam_none_sem_palpite(tmp_path):
    ext = BCBExtractor(tmp_path, http=HttpFalso(HttpError("u", 500, "x")))
    df = ext.fetch_ibovespa_annual_closing(2023, 2026)
    valores = dict(zip(df["ano"], df["ibovespa_fechamento"]))
    assert valores[2023] == 134185.0
    assert valores[2025] is None or valores[2025] != valores[2025]  # None/NaN: não foi inventado
