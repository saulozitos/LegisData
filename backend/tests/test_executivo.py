import uuid
from datetime import date

import pytest
from app.services.executivo_service import acumulado_12_meses
from sqlalchemy import text

from .conftest import criar_mandato_presidencial, observar_serie

BASE = "/api/v1/executivo"


def _uid(db, mandato_id):
    return str(db.execute(text("SELECT uid FROM core.mandato WHERE id = :m"), {"m": mandato_id}).scalar())


@pytest.fixture()
def mandates(db):
    antigo = criar_mandato_presidencial(db, "Antigo", date(2011, 1, 1), date(2015, 1, 1), "antigo-2011", "A 1", "PT")
    atual = criar_mandato_presidencial(db, "Atual", date(2023, 1, 1), None, "atual-2023", None, "PT")
    vazio = criar_mandato_presidencial(db, "Sem indicadores", date(2030, 1, 1), None, "vazio-2030")
    # IPCA mensal de 2022-01 a 2023-04; a taxa do mês sobe em 2023, então o acumulado em 12 meses também sobe
    for i in range(16):
        ano, mes = 2022 + i // 12, i % 12 + 1
        observar_serie(db, "IPCA_MENSAL", date(ano, mes, 1), 0.5 if i < 12 else 1.0)
    observar_serie(db, "DESEMPREGO_PNADC_MENSAL", date(2023, 1, 1), 8.0)
    observar_serie(db, "DESEMPREGO_PNADC_MENSAL", date(2023, 2, 1), 9.0)
    observar_serie(db, "CAMBIO_MENSAL", date(2023, 1, 1), 5.0)
    observar_serie(db, "SELIC_META", date(2023, 1, 1), 13.75)
    db.commit()
    return {"antigo": _uid(db, antigo), "atual": _uid(db, atual), "vazio": _uid(db, vazio)}


def test_acumulado_12_meses_exige_os_onze_meses_anteriores():
    serie = [(date(2022, m, 1), 1.0) for m in range(1, 13)] + [(date(2023, 1, 1), 2.0)]
    resultado = dict(acumulado_12_meses(serie))
    assert date(2022, 11, 1) not in resultado  # só 11 meses de histórico
    assert resultado[date(2022, 12, 1)] == pytest.approx((1.01**12 - 1) * 100, abs=1e-3)
    assert resultado[date(2023, 1, 1)] == pytest.approx((1.01**11 * 1.02 - 1) * 100, abs=1e-3)


def test_acumulado_12_meses_nao_atravessa_buraco_na_serie():
    serie = [(date(2022, m, 1), 1.0) for m in range(1, 13) if m != 6] + [(date(2023, 1, 1), 1.0)]
    assert acumulado_12_meses(serie) == []


def test_list_mandates_is_ordered_by_start_date(client, mandates):
    response = client.get(f"{BASE}/mandates")
    assert response.status_code == 200
    assert [m["nome"] for m in response.json()] == ["Antigo (A 1)", "Atual", "Sem indicadores"]
    assert [m["id"] for m in response.json()] == [mandates["antigo"], mandates["atual"], mandates["vazio"]]


def test_list_mandates_does_not_ship_the_monthly_series(client, mandates):
    for item in client.get(f"{BASE}/mandates").json():
        assert "indicadores" not in item


def test_list_mandates_empty_database(client):
    assert client.get(f"{BASE}/mandates").json() == []


def test_summary_computes_stats_from_official_series(client, mandates):
    body = client.get(f"{BASE}/mandates/{mandates['atual']}/summary").json()
    assert body["nome"] == "Atual" and body["fim"] is None and body["partido"] == "PT"
    ipca = body["kpis"]["inflacao_ipca"]
    # jan/2023: fev-dez/2022 a 0,5% (11 meses) e jan/2023 a 1,0%; abr/2023: mai-dez/2022 (8 meses) a 0,5% e 4 a 1,0%
    assert ipca["primeiro"] == pytest.approx((1.005**11 * 1.01 - 1) * 100, abs=0.01)
    assert ipca["ultimo"] == pytest.approx((1.005**8 * 1.01**4 - 1) * 100, abs=0.01)
    assert ipca["variacao_pp"] == pytest.approx(round(ipca["ultimo"] - ipca["primeiro"], 2), abs=0.01)
    assert ipca["minimo"] == ipca["primeiro"] and ipca["maximo"] == ipca["ultimo"]
    assert body["kpis"]["desemprego_pnad"] == {
        "primeiro": 8.0,
        "ultimo": 9.0,
        "minimo": 8.0,
        "maximo": 9.0,
        "media": 8.5,
    }
    assert body["kpis"]["selic_meta"]["primeiro"] == 13.75 and body["kpis"]["cambio_usd_brl"]["media"] == 5.0
    assert body["total_meses"] == 4  # IPCA 12 meses só existe de 2022-12 em diante; 4 meses caem em 2023


def test_summary_does_not_invent_indicators_without_source(client, mandates):
    kpis = client.get(f"{BASE}/mandates/{mandates['atual']}/summary").json()["kpis"]
    assert "aprovacao_popular" not in kpis and "emendas_bilhoes" not in kpis


def test_summary_of_mandate_without_indicators_is_empty_not_an_error(client, mandates):
    body = client.get(f"{BASE}/mandates/{mandates['vazio']}/summary").json()
    assert body["kpis"] == {} and body["total_meses"] == 0


def test_summary_unknown_mandate_is_404(client, mandates):
    assert client.get(f"{BASE}/mandates/{uuid.uuid4()}/summary").status_code == 404


@pytest.mark.parametrize("suffix", ["summary", "indicators"])
def test_invalid_uuid_is_422(client, suffix):
    assert client.get(f"{BASE}/mandates/nao-e-uuid/{suffix}").status_code == 422


def test_indicators_group_values_by_date(client, mandates):
    rows = client.get(f"{BASE}/mandates/{mandates['atual']}/indicators").json()
    assert [row["data"] for row in rows] == sorted(row["data"] for row in rows)
    january = next(row for row in rows if row["data"] == "2023-01-01")
    assert set(january) == {"data", "inflacao_ipca", "desemprego_pnad", "cambio_usd_brl", "selic_meta"}
    february = next(row for row in rows if row["data"] == "2023-02-01")
    assert "cambio_usd_brl" not in february  # mês sem observação não traz a chave


def test_indicators_empty_series_and_unknown_mandate(client, mandates):
    assert client.get(f"{BASE}/mandates/{mandates['vazio']}/indicators").json() == []
    assert client.get(f"{BASE}/mandates/{uuid.uuid4()}/indicators").status_code == 404


def test_iple_service_mathematical_formulas():
    from app.services.iple_service import (
        calculate_iple,
        calculate_ipp,
        calculate_nep,
        calculate_opposition_share,
        calculate_tmv,
        calculate_ts,
        calibrate_crisp_set,
    )

    # 1. TS
    assert calculate_ts(100, 87) == 0.87
    assert calculate_ts(0, 0) == 0.0

    # 2. TMV
    assert calculate_tmv(70, 100) == 0.70
    assert calculate_tmv(0, 0, fallback_ts=0.85) == 0.85
    assert calculate_tmv(0, 0) == 1.0

    # 3. IPLE
    assert calculate_iple(0.87, 0.70) == 0.785
    assert 0.0 <= calculate_iple(1.0, 1.0) <= 1.0

    # 4. NEP
    bancadas = [{"partido": "A", "cadeiras": 50}, {"partido": "B", "cadeiras": 50}]
    assert calculate_nep(bancadas) == 2.0

    # 5. IPP
    assert calculate_ipp(bancadas, {"A": 2.0, "B": 8.0}) == 9.0

    # 6. Oposição
    assert calculate_opposition_share(150, 500) == 0.30

    # 7. Calibragem Crisp-set
    crisp = calibrate_crisp_set(0.88, 0.75, 0.815, 0.35, 9.0, 2.5)
    assert crisp["ts"]["crisp_val"] == 1
    assert crisp["tmv"]["crisp_val"] == 1
    assert crisp["iple"]["crisp_val"] == 1
    assert crisp["oposicao_x1"]["crisp_val"] == 1
    assert crisp["fragmentacao_x2"]["crisp_val"] == 1
    assert crisp["polarizacao_x3"]["crisp_val"] == 1
