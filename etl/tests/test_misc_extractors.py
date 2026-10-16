"""Salário vs inflação, filiações, composição do Congresso, segurança/INPE e extractors que não podem apagar dados."""

import json

import pandas as pd
import pytest

from etl.extractors.composicao_extractor import COMPOSICAO_CONGRESSO_HISTORICO as COMPOSICOES
from etl.extractors.presidents_extractor import PresidentsExtractor
from etl.extractors.senado_extractor import SenadoExtractor
from etl.extractors.tse_extractor import NOMADES_HISTORICO, TSEExtractor


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


def test_filiacoes_sem_origem_inventada(tmp_path):
    (tmp_path / "deputados_camara.json").write_text(
        json.dumps(
            [
                {"camara_id": 1, "nome_eleitoral": "Fulano", "partido_sigla": "UNIÃO", "uf": "SP"},
                {"camara_id": 1, "nome_eleitoral": "Fulano", "partido_sigla": "UNIÃO", "uf": "SP"},  # duplicado
                {"camara_id": 2, "nome_eleitoral": "Kim Kataguiri", "partido_sigla": "UNIÃO", "uf": "SP"},
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "senadores_senado.json").write_text(
        json.dumps(
            [
                {"senado_id": 9, "nome_eleitoral": "Sicrano", "partido_sigla": "PODE", "uf": "AC"},
            ]
        ),
        encoding="utf-8",
    )
    df = TSEExtractor(tmp_path).extract_affiliations()

    fulano = df[df["politico_nome"] == "Fulano"]
    assert len(fulano) == 1  # só a filiação atual: sem "DEM"/"PSL" sorteados por idx % 2
    assert (fulano.iloc[0]["data_filiacao"] is None or pd.isna(fulano.iloc[0]["data_filiacao"])) and bool(
        fulano.iloc[0]["data_filiacao_desconhecida"]
    )
    assert fulano.iloc[0]["partido_sigla"] == "UNIÃO"

    kim = df[df["politico_nome"] == "Kim Kataguiri"]
    assert len(kim) == len(NOMADES_HISTORICO["Kim Kataguiri"])
    assert set(kim["fonte"]) == {kim.iloc[0]["fonte"]} and "Curadoria" in kim.iloc[0]["fonte"]
    assert (df["is_synthetic"] == False).all()  # noqa: E712


def test_filiacoes_vazia_nao_sobrescreve_arquivo_existente(tmp_path):
    (tmp_path / "filiacoes_partidarias.json").write_text("[1]", encoding="utf-8")
    ext = TSEExtractor(tmp_path)
    with pytest.raises(RuntimeError):
        ext.save_data(ext.extract_affiliations())
    assert (tmp_path / "filiacoes_partidarias.json").read_text(encoding="utf-8") == "[1]"


def test_save_data_grava_ids_como_inteiros(tmp_path):
    (tmp_path / "deputados_camara.json").write_text(
        json.dumps([{"camara_id": 7, "nome_eleitoral": "A", "partido_sigla": "PT", "uf": "BA"}]), encoding="utf-8"
    )
    (tmp_path / "senadores_senado.json").write_text(
        json.dumps([{"senado_id": 8, "nome_eleitoral": "B", "partido_sigla": "PT", "uf": "BA"}]), encoding="utf-8"
    )
    ext = TSEExtractor(tmp_path)
    ext.save_data(ext.extract_affiliations())
    registros = json.loads((tmp_path / "filiacoes_partidarias.json").read_text(encoding="utf-8"))
    por_nome = {r["politico_nome"]: r for r in registros}
    assert (
        por_nome["A"]["camara_id"] == 7
        and isinstance(por_nome["A"]["camara_id"], int)
        and por_nome["A"]["senado_id"] is None
    )
    assert por_nome["B"]["senado_id"] == 8 and isinstance(por_nome["B"]["senado_id"], int)


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
