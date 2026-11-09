"""Salário vs inflação, filiações, composição do Congresso, segurança/INPE e extractors que não podem apagar dados."""

import pandas as pd

from etl.extractors.composicao_extractor import COMPOSICAO_CONGRESSO_HISTORICO as COMPOSICOES
from etl.extractors.presidents_extractor import PresidentsExtractor
from etl.extractors.senado_extractor import SenadoExtractor


def test_get_mandate_by_date_fim_exclusivo():
    assert PresidentsExtractor.get_mandate_by_date("1998-12-31")["id_referencia"] == "fhc-1995"
    assert (
        PresidentsExtractor.get_mandate_by_date("1999-01-01")["id_referencia"] == "fhc-1999"
    )  # antes: devolvia o anterior
    assert PresidentsExtractor.get_mandate_by_date("1000-01-01") is None


def resumo_csv(tmp_path, anos):
    linhas = [
        {
            "ano": a,
            "presidente_dominante": "X",
            "salario_minimo_nominal_brl": 100.0 + a - 1994,
            "ipca_acumulado_ano_pct": 5.0,
        }
        for a in anos
    ]
    pd.DataFrame(linhas).to_csv(tmp_path / "resumo_macroeconomico_anual.csv", index=False)


def test_composicao_nao_copia_bancadas_de_outro_mandato():
    for mandato in ("fhc-1999", "lula-2007", "dilma-2011", "temer-2016"):
        c = COMPOSICOES[mandato]
        assert c["dados_incompletos"] is True
        assert c["camara"]["bancadas"] == [] and c["senado"]["bancadas"] == []
        assert all(v is None for v in c["camara"]["governabilidade"].values())
    # mandatos curados permanecem completos
    assert COMPOSICOES["lula-2023"]["camara"]["bancadas"] and "dados_incompletos" not in COMPOSICOES["lula-2023"]


def test_presidente_do_senado_atualizado():
    presidentes = COMPOSICOES["lula-2023"]["senado"]["presidentes"]
    assert [p["nome"] for p in presidentes] == ["Rodrigo Pacheco", "Davi Alcolumbre"]
    assert presidentes[-1]["periodo"] == "2025 - Presente"


class HttpFalso:
    def __init__(self, resposta):
        self.resposta = resposta

    def get_json(self, url, **_):
        if isinstance(self.resposta, Exception):
            raise self.resposta
        return self.resposta


def test_senado_falha_na_api_nao_apaga_arquivos_existentes(tmp_path, monkeypatch):
    import etl.extractors.senado_extractor as mod
    from etl.utils.http_client import HttpError

    monkeypatch.setattr(mod, "PROCESSED_DATA_DIR", tmp_path)
    for nome in (
        "senadores_senado.json",
        "sessoes_votacao_senado.json",
        "votos_nominais_senado.json",
        "proposicoes_senado.json",
    ):
        (tmp_path / nome).write_text('["bom"]', encoding="utf-8")

    ext = SenadoExtractor(raw_cache_dir=tmp_path, http=HttpFalso(HttpError("u", 500, "fora do ar")))
    monkeypatch.setattr(ext, "fetch_proposicoes_senado", lambda: [])
    resultado = ext.run_full_extraction()
    assert resultado["total_senadores"] == 0
    for nome in (
        "senadores_senado.json",
        "sessoes_votacao_senado.json",
        "votos_nominais_senado.json",
        "proposicoes_senado.json",
    ):
        assert (tmp_path / nome).read_text(encoding="utf-8") == '["bom"]'


def test_senado_proposicoes_devolve_lista(tmp_path):
    ext = SenadoExtractor(raw_cache_dir=tmp_path, http=HttpFalso(None))
    assert ext.fetch_proposicoes_senado() == []  # lista (antes devolvia dict e quebrava o loader na extração seguinte)


def test_senadores_duplicados_na_resposta_viram_um(tmp_path):
    parlamentar = {
        "IdentificacaoParlamentar": {"CodigoParlamentar": "5", "NomeParlamentar": "S", "UfParlamentar": "AC"}
    }
    resposta = {"ListaParlamentarEmExercicio": {"Parlamentares": {"Parlamentar": [parlamentar, parlamentar]}}}
    senadores = SenadoExtractor(raw_cache_dir=tmp_path, http=HttpFalso(resposta)).fetch_senadores_em_exercicio()
    assert [s["senado_id"] for s in senadores] == [5]
