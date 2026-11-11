from unittest.mock import ANY, MagicMock, patch

import pytest
from app.core.config import settings
from app.services import cidadania_service as svc

URL = "/api/v1/cidadania/consultas"

CONSULTAS = [
    {
        "id_externo": "123",
        "casa": "Senado",
        "sigla_projeto": "PL 123/2020",
        "ementa": "Teste ementa",
        "link_oficial_votacao": "http://teste.com",
        "em_votacao_aberta": True,
    },
    {
        "id_externo": "456",
        "casa": "Câmara",
        "sigla_projeto": "PEC 45/2019",
        "ementa": "Teste ementa 2",
        "link_oficial_votacao": "http://teste2.com",
        "em_votacao_aberta": False,
    },
]


@pytest.fixture()
def fake_service():
    with patch("app.api.v1.cidadania.consultas_publicas", return_value=CONSULTAS) as mock:
        yield mock


def test_list_all_consultas(client, fake_service):
    response = client.get(URL)
    assert response.status_code == 200
    assert [c["id_externo"] for c in response.json()] == ["123", "456"]


@pytest.mark.parametrize("casa,expected", [("Senado", "Senado"), ("senado", "Senado"), ("  câmara ", "Câmara")])
def test_filter_by_house_ignores_case_and_whitespace(client, fake_service, casa, expected):
    data = client.get(URL, params={"casa": casa}).json()
    assert [c["casa"] for c in data] == [expected]


def test_filter_by_unknown_house_returns_empty_list(client, fake_service):
    assert client.get(URL, params={"casa": "Assembleia"}).json() == []


def test_item_without_house_key_does_not_break_the_filter(client):
    with patch("app.api.v1.cidadania.consultas_publicas", return_value=[{**CONSULTAS[0], "casa": None}]):
        assert client.get(URL, params={"casa": "Senado"}).json() == []


def test_house_filter_length_is_bounded(client, fake_service):
    assert client.get(URL, params={"casa": "x" * 21}).status_code == 422


def test_force_refresh_is_ignored_for_anonymous_users(client, fake_service, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_REFRESH_TOKEN", "segredo-admin")
    assert client.get(URL, params={"force_refresh": "true"}).status_code == 200
    fake_service.assert_called_with(ANY, force_refresh=False)


def test_force_refresh_rejects_wrong_token(client, fake_service, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_REFRESH_TOKEN", "segredo-admin")
    client.get(URL, params={"force_refresh": "true"}, headers={"X-Admin-Token": "errado"})
    fake_service.assert_called_with(ANY, force_refresh=False)


def test_force_refresh_accepts_valid_token(client, fake_service, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_REFRESH_TOKEN", "segredo-admin")
    client.get(URL, params={"force_refresh": "true"}, headers={"X-Admin-Token": "segredo-admin"})
    fake_service.assert_called_with(ANY, force_refresh=True)


def test_force_refresh_disabled_when_no_admin_token_is_configured(client, fake_service, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_REFRESH_TOKEN", "")
    client.get(URL, params={"force_refresh": "true"}, headers={"X-Admin-Token": ""})
    fake_service.assert_called_with(ANY, force_refresh=False)


# ---------------------------------------------------------------------------
# Serviço (coleta nas fontes oficiais), sempre com a rede simulada
# ---------------------------------------------------------------------------
def _response(payload=None, text="", status=200):
    resp = MagicMock(status_code=status, text=text)
    resp.json.return_value = payload
    return resp


def test_totals_and_percentages():
    item = svc._calcular_totais_e_percentuais({"votos_sim": 30, "votos_nao": 10})
    assert (item["total_votos"], item["percentual_sim"], item["percentual_nao"]) == (40, 75.0, 25.0)
    no_votes = svc._calcular_totais_e_percentuais({"votos_sim": 0, "votos_nao": 0})
    assert no_votes["percentual_sim"] is None
    missing = svc._calcular_totais_e_percentuais({"votos_sim": None, "votos_nao": 5})
    assert missing["total_votos"] is None


def test_camara_null_ementa_does_not_discard_other_proposals():
    payload = {
        "dados": [
            {"id": 1, "siglaTipo": "PL", "numero": 1, "ano": 2025, "ementa": None},
            {
                "id": 2,
                "siglaTipo": "PL",
                "numero": 2,
                "ano": 2025,
                "ementa": "  Valida  ",
                "dataApresentacao": "2025-03-01T10:00",
            },
        ]
    }
    with patch.object(svc.requests, "get", return_value=_response(payload)):
        items = svc.fetch_camara_consultas()
    assert [i["id_externo"] for i in items] == ["2"]
    assert items[0]["ementa"] == "Valida"
    assert items[0]["data_apresentacao"] == "2025-03-01"
    assert items[0]["em_votacao_aberta"] is False


def test_senado_fallback_uses_current_year_and_tolerates_null_ementa():
    payload = {
        "PesquisaBasicaMateria": {
            "Materias": {
                "Materia": [
                    {"Codigo": 1, "Sigla": "PL", "Numero": 1, "Ano": 2025, "Ementa": None},
                    {"Codigo": 2, "DescricaoIdentificacao": "PL 2/2025", "Ementa": "Ok"},
                ]
            }
        }
    }
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        if "principalmateria" in url:
            return _response(status=500)
        return _response(payload)

    with patch.object(svc.requests, "get", side_effect=fake_get):
        items = svc.fetch_senado_consultas(limit=6)
    assert [i["id_externo"] for i in items] == ["2"]
    assert f"ano={svc.date.today().year}" in calls[-1]


def test_network_errors_return_empty_lists_without_raising():
    with patch.object(svc.requests, "get", side_effect=ConnectionError("rede fora")):
        assert svc.fetch_camara_consultas() == []
        assert svc.fetch_senado_consultas() == []


def test_curated_open_consultation_is_not_claimed_open_without_live_confirmation():
    with (
        patch.object(svc, "fetch_senado_consultas", return_value=[]),
        patch.object(svc, "fetch_camara_consultas", return_value=[]),
    ):
        items, live_ok = svc._build_consultas()
    assert live_ok is False
    assert all(i["fonte_dados"] == "curadoria" for i in items)
    assert not any(i["em_votacao_aberta"] for i in items)
    assert any("sem confirmação" in i["status"] for i in items)


def test_live_confirmation_reopens_curated_item_and_refreshes_tally():
    curated = svc.DESTAQUES_CONSULTAS[0]
    live = {
        "id_externo": curated["id_externo"],
        "casa": "Senado",
        "sigla_projeto": curated["sigla_projeto"],
        "ementa": "x",
        "em_votacao_aberta": True,
        "votos_sim": 10,
        "votos_nao": 30,
    }
    with (
        patch.object(svc, "fetch_senado_consultas", return_value=[live]),
        patch.object(svc, "fetch_camara_consultas", return_value=[]),
    ):
        items, live_ok = svc._build_consultas()
    item = next(i for i in items if i["id_externo"] == curated["id_externo"])
    assert live_ok is True
    assert item["em_votacao_aberta"] is True and item["fonte_dados"] == "tempo_real"
    assert (item["votos_sim"], item["votos_nao"], item["percentual_sim"]) == (10, 30, 25.0)
    assert sum(1 for i in items if i["sigla_projeto"] == curated["sigla_projeto"]) == 1  # sem duplicar


def test_module_level_curated_data_is_not_mutated_by_a_build():
    before = [dict(d) for d in svc.DESTAQUES_CONSULTAS]
    with (
        patch.object(svc, "fetch_senado_consultas", return_value=[]),
        patch.object(svc, "fetch_camara_consultas", return_value=[]),
    ):
        svc._build_consultas()
    assert svc.DESTAQUES_CONSULTAS == before


def test_failed_refresh_keeps_last_good_cache(monkeypatch):
    good = [{"sigla_projeto": "PL 1/2025", "marca": "bom"}]
    clock = {"now": 10_000.0}
    monkeypatch.setattr(svc.time, "time", lambda: clock["now"])
    monkeypatch.setattr(svc, "_cache_data", good)
    monkeypatch.setattr(svc, "_cache_timestamp", clock["now"] - svc.CACHE_TTL_SECONDS - 1)  # vencido

    with patch.object(svc, "_build_consultas", return_value=([{"sigla_projeto": "vazio"}], False)) as build:
        result = svc.get_consultas_publicas()
    build.assert_called_once()
    assert result is good  # fontes fora do ar: nada de sobrescrever com lista nova/vazia
    assert svc._cache_timestamp > clock["now"] - svc.CACHE_TTL_SECONDS  # só tenta de novo após o cooldown


def test_first_load_without_live_data_still_serves_curated_items(monkeypatch):
    curated = [{"sigla_projeto": "PL 1/2025"}]
    with patch.object(svc, "_build_consultas", return_value=(curated, False)):
        assert svc.get_consultas_publicas() == curated


def test_fresh_cache_is_served_without_hitting_the_network(monkeypatch):
    monkeypatch.setattr(svc.time, "time", lambda: 5_000.0)
    monkeypatch.setattr(svc, "_cache_data", [{"k": 1}])
    monkeypatch.setattr(svc, "_cache_timestamp", 4_999.0)
    with patch.object(svc, "_build_consultas") as build:
        assert svc.get_consultas_publicas() == [{"k": 1}]
        assert svc.get_consultas_publicas(force_refresh=True) == [{"k": 1}]  # dentro do cooldown
    build.assert_not_called()


def test_forced_refresh_after_cooldown_rebuilds_cache(monkeypatch):
    monkeypatch.setattr(svc.time, "time", lambda: 5_000.0)
    monkeypatch.setattr(svc, "_cache_data", [{"k": "velho"}])
    monkeypatch.setattr(svc, "_cache_timestamp", 5_000.0 - svc.MIN_COOLDOWN_SECONDS - 1)
    with patch.object(svc, "_build_consultas", return_value=([{"k": "novo"}], True)):
        assert svc.get_consultas_publicas(force_refresh=True) == [{"k": "novo"}]


def test_senado_portal_scraping_extracts_matters_and_live_tally():
    html = (
        "<div class='col-sm-12 resumo-materia'><header><a href='visualizacaomateria?id=555'>PL 55/2026</a></header>"
        "<section><a href='#'>Ementa do projeto</a></section></div>"
        "<div class='col-sm-12 resumo-materia'><header><a href='visualizacaomateria?id=556'>PL 56/2026</a></header>"
        "<section><a href='#'>  </a></section></div>"
    )
    page = "<span class='contabilizacao-favor'>1.200<span><span class='contabilizacao-contra'>300<span>"

    def fake_get(url, **kwargs):
        if "principalmateria" in url:
            return _response(text=html)
        if "visualizacaomateria" in url:
            return _response(text=page)
        return _response(status=500)

    with patch.object(svc.requests, "get", side_effect=fake_get):
        items = svc.fetch_senado_consultas(limit=1)
    assert len(items) == 1  # a matéria sem ementa é descartada
    item = items[0]
    assert item["id_externo"] == "555" and item["ementa"] == "Ementa do projeto"
    assert (item["votos_sim"], item["votos_nao"], item["total_votos"]) == (1200, 300, 1500)
    assert item["percentual_sim"] == 80.0 and item["em_votacao_aberta"] is True


def test_senado_portal_vote_page_failure_keeps_matter_without_tally():
    html = (
        "<div class='col-sm-12 resumo-materia'><header><a href='visualizacaomateria?id=7'>PL 7/2026</a></header>"
        "<section><a href='#'>Ementa</a></section></div>"
    )

    def fake_get(url, **kwargs):
        if "principalmateria" in url:
            return _response(text=html)
        raise TimeoutError("lento")

    with patch.object(svc.requests, "get", side_effect=fake_get):
        items = svc.fetch_senado_consultas(limit=1)
    assert items[0]["votos_sim"] is None and items[0]["percentual_sim"] is None


# ---------------------------------------------------------------------------
# Foto diária no banco: o job coleta e grava, a API só lê
# ---------------------------------------------------------------------------
@pytest.fixture()
def tabela_limpa(db):
    from sqlalchemy import text

    db.execute(text("DELETE FROM leg.consulta_publica"))
    db.commit()
    yield db
    db.execute(text("DELETE FROM leg.consulta_publica"))
    db.commit()


def _item(sigla, aberta, sim=None, nao=None, casa="Senado", id_externo=None, fonte="tempo_real"):
    return {
        "id_externo": id_externo or sigla,
        "casa": casa,
        "sigla_projeto": sigla,
        "ementa": f"Ementa de {sigla}",
        "link_oficial_votacao": f"http://x/{sigla}",
        "link_tramitacao_oficial": None,
        "em_votacao_aberta": aberta,
        "votos_sim": sim,
        "votos_nao": nao,
        "tema": "Tema",
        "status": "Votação Popular Aberta Agora" if aberta else "Encerrada",
        "autor": None,
        "data_apresentacao": "2026-03-10",
        "destaque": aberta,
        "fonte_dados": fonte,
    }


def _coleta(itens, live=True):
    return patch.object(svc, "_build_consultas", return_value=(itens, live))


def test_coleta_diaria_grava_a_foto_e_a_api_serve_o_banco_com_as_abertas_primeiro(client, tabela_limpa):
    with _coleta([_item("PL 1/2026", False), _item("PL 2/2026", True, 70, 30)]):
        resultado = svc.atualizar_consultas(tabela_limpa)
    assert resultado == {"atualizado": True, "itens": 2, "abertas": 1}
    corpo = client.get(URL).json()
    assert [c["sigla_projeto"] for c in corpo] == ["PL 2/2026", "PL 1/2026"]  # a aberta vem primeiro
    aberta = corpo[0]
    assert aberta["percentual_sim"] == 70.0 and aberta["data_apresentacao"] == "2026-03-10"
    assert aberta["atualizado_em"]  # a tela mostra quando foi a última coleta


def test_rodar_de_novo_nao_duplica_e_atualiza_o_placar(client, tabela_limpa):
    with _coleta([_item("PL 2/2026", True, 70, 30)]):
        svc.atualizar_consultas(tabela_limpa)
    with _coleta([_item("PL 2/2026", True, 80, 20)]):
        svc.atualizar_consultas(tabela_limpa)
    corpo = client.get(URL).json()
    assert len(corpo) == 1 and corpo[0]["votos_sim"] == 80 and corpo[0]["percentual_sim"] == 80.0


def test_materia_aberta_que_sumiu_do_portal_vira_encerrada_sem_ser_apagada(client, tabela_limpa):
    with _coleta([_item("PL 2/2026", True, 70, 30), _item("PL 3/2026", True, 5, 5)]):
        svc.atualizar_consultas(tabela_limpa)
    with _coleta([_item("PL 3/2026", True, 6, 6)]):  # a PL 2 saiu do portal
        svc.atualizar_consultas(tabela_limpa)
    por_sigla = {c["sigla_projeto"]: c for c in client.get(URL).json()}
    assert por_sigla["PL 2/2026"]["em_votacao_aberta"] is False
    assert por_sigla["PL 2/2026"]["status"] == svc.STATUS_FORA_DO_PORTAL
    assert por_sigla["PL 3/2026"]["em_votacao_aberta"] is True


def test_fontes_fora_do_ar_nao_gravam_nada_e_mantem_a_foto_anterior(client, tabela_limpa):
    with _coleta([_item("PL 2/2026", True, 70, 30)]):
        svc.atualizar_consultas(tabela_limpa)
    with _coleta([], live=False):
        assert svc.atualizar_consultas(tabela_limpa) == {"atualizado": False, "itens": 0, "abertas": 0}
    corpo = client.get(URL).json()
    assert [c["sigla_projeto"] for c in corpo] == ["PL 2/2026"] and corpo[0]["em_votacao_aberta"] is True


def test_banco_vazio_cai_na_coleta_direta_em_memoria(client, tabela_limpa):
    with patch.object(svc, "get_consultas_publicas", return_value=CONSULTAS) as direta:
        corpo = client.get(URL).json()
    assert [c["id_externo"] for c in corpo] == ["123", "456"]
    direta.assert_called_once_with(force_refresh=False)


def test_banco_com_dados_nunca_chama_as_fontes_externas(client, tabela_limpa):
    with _coleta([_item("PL 2/2026", True, 70, 30)]):
        svc.atualizar_consultas(tabela_limpa)
    with patch.object(svc, "get_consultas_publicas", side_effect=AssertionError("não deve ir à rede")):
        assert client.get(URL).status_code == 200


def test_filtro_por_casa_vale_para_a_foto_do_banco(client, tabela_limpa):
    with _coleta([_item("PL 2/2026", True), _item("PEC 1/2026", True, casa="Câmara")]):
        svc.atualizar_consultas(tabela_limpa)
    assert [c["sigla_projeto"] for c in client.get(URL, params={"casa": " câmara "}).json()] == ["PEC 1/2026"]


def test_primeira_coleta_fica_fixa_e_o_encerramento_e_registrado_quando_a_consulta_fecha(client, tabela_limpa):
    with _coleta([_item("PL 2/2026", True, 70, 30)]):
        svc.atualizar_consultas(tabela_limpa)
    primeira = client.get(URL).json()[0]
    assert primeira["primeira_coleta_em"] and primeira["encerrada_em"] is None

    with _coleta([_item("PL 2/2026", True, 75, 25)]):  # continua aberta: a primeira coleta não muda
        svc.atualizar_consultas(tabela_limpa)
    de_novo = client.get(URL).json()[0]
    assert de_novo["primeira_coleta_em"] == primeira["primeira_coleta_em"] and de_novo["encerrada_em"] is None

    with _coleta([_item("PL 2/2026", False, 75, 25)]):  # o portal passou a informar como encerrada
        svc.atualizar_consultas(tabela_limpa)
    fechada = client.get(URL).json()[0]
    assert fechada["encerrada_em"] is not None
    assert fechada["primeira_coleta_em"] == primeira["primeira_coleta_em"]

    with _coleta([_item("PL 2/2026", True, 80, 20)]):  # reabriu: o fim registrado deixa de valer
        svc.atualizar_consultas(tabela_limpa)
    assert client.get(URL).json()[0]["encerrada_em"] is None


def test_materia_que_sumiu_do_portal_ganha_o_fim_observado(client, tabela_limpa):
    with _coleta([_item("PL 2/2026", True), _item("PL 3/2026", True)]):
        svc.atualizar_consultas(tabela_limpa)
    with _coleta([_item("PL 3/2026", True)]):
        svc.atualizar_consultas(tabela_limpa)
    por_sigla = {c["sigla_projeto"]: c for c in client.get(URL).json()}
    assert por_sigla["PL 2/2026"]["encerrada_em"] is not None and por_sigla["PL 3/2026"]["encerrada_em"] is None


def test_materia_encerrada_ja_na_primeira_coleta_nao_inventa_data_de_encerramento(client, tabela_limpa):
    with _coleta([_item("PL 1/2026", False)]):
        svc.atualizar_consultas(tabela_limpa)
    assert client.get(URL).json()[0]["encerrada_em"] is None  # nunca foi vista aberta


def test_data_de_apresentacao_oficial_vem_dos_dados_abertos_do_senado():
    payload = {"DetalheMateria": {"Materia": {"DadosBasicosMateria": {"DataApresentacao": "2020-11-05"}}}}
    with patch.object(svc.requests, "get", return_value=_response(payload=payload)):
        assert svc._data_apresentacao_senado("146046") == "2020-11-05"


@pytest.mark.parametrize("resposta", [_response(status=500), _response(payload={"DetalheMateria": {}})])
def test_sem_data_oficial_devolve_none_em_vez_de_inventar(resposta):
    with patch.object(svc.requests, "get", return_value=resposta):
        assert svc._data_apresentacao_senado("1") is None


def test_falha_de_rede_na_data_de_apresentacao_devolve_none():
    with patch.object(svc.requests, "get", side_effect=TimeoutError("lento")):
        assert svc._data_apresentacao_senado("1") is None
