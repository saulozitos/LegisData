"""Homicídios (Atlas da Violência), desmatamento (PRODES) e Ibovespa: fontes oficiais, sem estimativas."""

import json
from datetime import date, datetime, timezone

import pytest

from etl.extractors import bcb_extractor as bcb_mod
from etl.extractors.bcb_extractor import BCBExtractor
from etl.extractors.ibovespa_extractor import FONTE_YAHOO, fechamentos_anuais
from etl.extractors.inpe_extractor import INPEExtractor, taxas_por_periodo
from etl.extractors.seguranca_extractor import SegurancaExtractor
from etl.utils.http_client import HttpError
from etl.utils.sidra import UF_POR_CODIGO_IBGE

# ----------------------------------------------------------------------------------------------- Atlas / homicídios


def serie_atlas(valores_por_uf, ano):
    return [
        {"valor": v, "periodo": f"{ano}-01-15T00:00:00.000Z", "regiao_id": cod} for cod, v in valores_por_uf.items()
    ]


class HttpAtlas:
    def __init__(self, series=None, erro=None):
        self.series = series or {}
        self.erro = erro

    def get_json(self, url, **_):
        if self.erro:
            raise self.erro
        serie = int(url.split("series-values/")[1].split("/")[0])
        return self.series[serie]


def todas_ufs(valor):
    return {cod: valor for cod in UF_POR_CODIGO_IBGE}


def test_taxa_nacional_e_soma_de_homicidios_sobre_populacao_implicita(tmp_path):
    # 27 UFs com 1.000 homicídios e taxa 10/100 mil => população implícita de 10 milhões cada
    ext = SegurancaExtractor(raw_cache_dir=tmp_path, processed_dir=tmp_path)
    hom = ext._por_uf_ano(serie_atlas(todas_ufs(1000.0), 2022))
    taxas = ext._por_uf_ano(serie_atlas(todas_ufs(10.0), 2022))
    [r] = ext.calcular_taxas_nacionais(hom, taxas)
    assert r["ano"] == 2022 and r["taxa_homicidios"] == 10.0 and r["homicidios_total"] == 27_000
    assert r["taxa_feminicidios"] is None  # sem fonte oficial automatizável


def test_ano_com_uf_faltando_ou_taxa_implausivel_e_descartado(tmp_path):
    ext = SegurancaExtractor(raw_cache_dir=tmp_path, processed_dir=tmp_path)
    ufs = todas_ufs(1000.0)
    ufs.pop(11)
    assert (
        ext.calcular_taxas_nacionais(
            ext._por_uf_ano(serie_atlas(ufs, 2021)), ext._por_uf_ano(serie_atlas(todas_ufs(10.0), 2021))
        )
        == []
    )
    assert (
        ext.calcular_taxas_nacionais(
            ext._por_uf_ano(serie_atlas(todas_ufs(1000.0), 2021)), ext._por_uf_ano(serie_atlas(todas_ufs(0.5), 2021))
        )
        == []
    )  # 1000/200000*100000... taxa implícita fora da faixa plausível


def test_fetch_grava_serie_e_sem_feminicidio(tmp_path):
    http = HttpAtlas({328: serie_atlas(todas_ufs(1000.0), 2022), 20: serie_atlas(todas_ufs(10.0), 2022)})
    ext = SegurancaExtractor(raw_cache_dir=tmp_path, processed_dir=tmp_path, http=http)
    df = ext.fetch_seguranca_history(use_cache=False)
    assert list(df["ano"]) == [2022]
    assert ext.get_annual_homicide_rates() == {2022: 10.0}
    assert ext.get_annual_feminicide_rates() == {}
    gravado = json.loads((tmp_path / "seguranca_publica_historico.json").read_text(encoding="utf-8"))
    assert gravado[0]["is_synthetic"] is False and "Atlas da Violência" in gravado[0]["fonte"]


def test_atlas_indisponivel_preserva_arquivo_anterior(tmp_path):
    (tmp_path / "seguranca_publica_historico.json").write_text(
        json.dumps([{"ano": 2000, "taxa_homicidios": 26.0}]), encoding="utf-8"
    )
    ext = SegurancaExtractor(
        raw_cache_dir=tmp_path, processed_dir=tmp_path, http=HttpAtlas(erro=HttpError("u", 500, "x"))
    )
    ext.fetch_seguranca_history(use_cache=False)
    assert ext.get_annual_homicide_rates() == {2000: 26.0}


# ----------------------------------------------------------------------------------------------- PRODES


def periodo(ano_fim, areas):
    return {
        "startDate": {"year": ano_fim - 1, "month": 8, "day": 1},
        "endDate": {"year": ano_fim, "month": 7, "day": 31},
        "features": [{"loi": 1, "loiname": i, "areas": [{"type": 1, "area": a}]} for i, a in enumerate(areas)],
    }


def test_taxas_por_periodo_soma_estados_e_descarta_implausiveis():
    payload = {"periods": [periodo(2022, [5000, 6594]), periodo(2023, [10]), {"endDate": {}}]}
    assert taxas_por_periodo(payload) == {2022: 11594.0}  # 2023 (10 km²) implausível; período malformado ignorado


def test_taxas_por_periodo_sem_periodos_levanta_erro():
    with pytest.raises(HttpError):
        taxas_por_periodo({})


class HttpPRODES:
    def __init__(self, existentes):
        self.existentes = existentes  # {ano: payload}
        self.urls = []

    def get_json(self, url, **_):
        self.urls.append(url)
        ano = int(url.rsplit("rates", 1)[1].split(".")[0])
        if ano in self.existentes:
            return self.existentes[ano]
        raise HttpError(url, 404, "nf")


def test_prodes_procura_o_arquivo_do_ano_mais_recente_para_tras(tmp_path):
    http = HttpPRODES({2025: {"periods": [periodo(2024, [6518])]}})
    ext = INPEExtractor(raw_cache_dir=tmp_path, processed_dir=tmp_path, http=http, hoje=date(2026, 10, 1))
    df = ext.fetch_deforestation_history(use_cache=False)
    assert http.urls[0].endswith("rates2027.json") and http.urls[-1].endswith("rates2025.json")
    assert (
        list(df["desmatamento_km2"]) == [6518.0]
        and df["is_synthetic"].iloc[0] is False
        or not df["is_synthetic"].iloc[0]
    )
    assert ext.get_deforestation_for_years([2024, 2025]) == {
        "desmatamento_acumulado_km2": 6518.0,
        "desmatamento_medio_anual_km2": 6518.0,
        "anos_com_dados": 1,
    }


def test_prodes_media_1993_94_e_sinalizada(tmp_path):
    http = HttpPRODES({2025: {"periods": [periodo(1993, [14896]), periodo(1994, [14896])]}})
    ext = INPEExtractor(raw_cache_dir=tmp_path, processed_dir=tmp_path, http=http, hoje=date(2026, 1, 1))
    df = ext.fetch_deforestation_history(use_cache=False).set_index("ano")
    assert "Média 1993-94" in df.loc[1993, "nota"]


def test_prodes_falha_de_rede_usa_cache_anterior_e_sem_cache_levanta(tmp_path):
    ext = INPEExtractor(raw_cache_dir=tmp_path, processed_dir=tmp_path, http=HttpPRODES({}), hoje=date(2026, 1, 1))
    with pytest.raises(HttpError):
        ext.fetch_series(use_cache=False)
    ext.cache_file.parent.mkdir(parents=True, exist_ok=True)
    ext.cache_file.write_text('{"2020": 10851.0}', encoding="utf-8")
    assert ext.fetch_series(use_cache=False) == {2020: 10851.0}


# ----------------------------------------------------------------------------------------------- Ibovespa


def ts(ano, mes):
    return int(datetime(ano, mes, 1, 12, tzinfo=timezone.utc).timestamp())


def payload_yahoo(pontos):
    return {
        "chart": {
            "result": [
                {
                    "timestamp": [ts(a, m) for a, m, _ in pontos],
                    "indicators": {"quote": [{"close": [c for _, _, c in pontos]}]},
                }
            ]
        }
    }


def test_fechamento_anual_usa_dezembro_e_marca_ano_corrente_como_parcial():
    payload = payload_yahoo([(2024, 11, 125000.0), (2024, 12, 120283.0), (2026, 1, 190000.0), (2026, 9, 206220.0)])
    resultado = fechamentos_anuais(payload, hoje=date(2026, 10, 8))
    assert resultado[2024] == {"valor": 120283.0, "parcial": False}  # novembro de 2024 é ignorado
    assert resultado[2026] == {"valor": 206220.0, "parcial": True}  # último valor disponível, NÃO fechamento anual


def test_fechamento_ignora_barras_sem_preco():
    payload = payload_yahoo([(2023, 12, None), (2024, 12, 120283.0)])
    assert set(fechamentos_anuais(payload, hoje=date(2026, 1, 1))) == {2024}


def test_payload_inesperado_levanta_erro():
    with pytest.raises(HttpError):
        fechamentos_anuais({"chart": {}})


class IbovespaFalso:
    def __init__(self, dados):
        self.dados = dados

    def fetch(self, **_):
        return self.dados


class HttpSGSFalho:
    """O SGS (série 7) fica fora do ar: anos sem Yahoo nem tabela da B3 não podem ser preenchidos."""

    def get_json(self, url, **_):
        raise HttpError(url, 500, "fora do ar")


def ibov(tmp_path, dados, ano_fim=2026):
    ext = BCBExtractor(tmp_path, http=HttpSGSFalho())
    df = ext.fetch_ibovespa_annual_closing(2022, ano_fim, ibovespa=IbovespaFalso(dados))
    return {r["ano"]: r for r in df.to_dict("records")}


def test_ibovespa_prefere_b3_corroborada_e_usa_yahoo_onde_nao_ha_tabela(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb_mod, "IBOVESPA_FECHAMENTOS_B3", {2022: 109735.0, 2023: 134185.0})
    dados = {
        2022: {"valor": 110031.0, "parcial": False, "fonte": FONTE_YAHOO},  # 0,27% de diferença: corrobora a B3
        2025: {"valor": 161125.0, "parcial": False, "fonte": FONTE_YAHOO},
        2026: {"valor": 206220.0, "parcial": True, "fonte": FONTE_YAHOO},
    }
    r = ibov(tmp_path, dados)
    assert r[2022]["ibovespa_fechamento"] == 109735.0 and "conferida com Yahoo" in r[2022]["fonte"]
    assert r[2025]["ibovespa_fechamento"] == 161125.0 and r[2025]["fonte"] == FONTE_YAHOO
    assert r[2026]["ibovespa_fechamento"] is None or r[2026]["ibovespa_fechamento"] != r[2026]["ibovespa_fechamento"]
    assert r[2026]["ibovespa_ultimo_pregao"] == 206220.0 and r[2026]["parcial"] is True


def test_ibovespa_divergencia_acima_de_1pc_descarta_o_ano(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb_mod, "IBOVESPA_FECHAMENTOS_B3", {2023: 134185.0})
    r = ibov(tmp_path, {2023: {"valor": 13418.5, "parcial": False, "fonte": FONTE_YAHOO}}, ano_fim=2023)
    v = r[2023]["ibovespa_fechamento"]
    assert v is None or v != v  # nem o Yahoo nem a tabela: ano sem valor, nunca escolhido ao acaso


def test_ibovespa_sem_yahoo_cai_na_tabela_b3_e_nao_inventa_o_resto(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb_mod, "IBOVESPA_FECHAMENTOS_B3", {2023: 134185.0})
    ext = BCBExtractor(tmp_path, http=HttpSGSFalho())
    df = ext.fetch_ibovespa_annual_closing(2023, 2025, ibovespa=IbovespaFalso({}))
    r = {x["ano"]: x for x in df.to_dict("records")}
    assert r[2023]["ibovespa_fechamento"] == 134185.0 and "sem conferência" in r[2023]["fonte"]
    assert r[2025]["ibovespa_fechamento"] is None or r[2025]["ibovespa_fechamento"] != r[2025]["ibovespa_fechamento"]
