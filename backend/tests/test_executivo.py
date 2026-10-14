import uuid
from datetime import date

import pytest
from app.models import MandateIndicator, PresidentialMandate

BASE = "/api/v1/executivo"


@pytest.fixture()
def mandates(db):
    antigo = PresidentialMandate(nome="Antigo", inicio=date(2011, 1, 1), fim=date(2015, 1, 1), partido="XX")
    atual = PresidentialMandate(
        nome="Atual", inicio=date(2023, 1, 1), fim=None, partido="PT", foto_url="/presidents/x.jpg"
    )
    vazio = PresidentialMandate(nome="Sem indicadores", inicio=date(2030, 1, 1), fim=None, partido="YY")
    db.add_all([antigo, atual, vazio])
    db.flush()

    def add(mandate, key, when, value):
        db.add(MandateIndicator(mandate_id=mandate.id, chave_indicador=key, valor=value, data_medicao=when))

    # IPCA: 4.0 -> 6.0 (variação +2.0 pp), min 3.0, max 6.0
    add(atual, "inflacao_ipca", date(2023, 1, 1), 4.0)
    add(atual, "inflacao_ipca", date(2023, 2, 1), 3.0)
    add(atual, "inflacao_ipca", date(2023, 3, 1), 6.0)
    # Emendas acumuladas no ano: vale o MAIOR valor de cada ano (dezembro), somados entre anos
    add(atual, "emendas_bilhoes", date(2023, 6, 1), 10.0)
    add(atual, "emendas_bilhoes", date(2023, 12, 1), 20.0)
    add(atual, "emendas_bilhoes", date(2024, 12, 1), 30.0)
    db.commit()
    return {"antigo": antigo, "atual": atual, "vazio": vazio}


def test_list_mandates_is_ordered_by_start_date(client, mandates):
    response = client.get(f"{BASE}/mandates")
    assert response.status_code == 200
    assert [m["nome"] for m in response.json()] == ["Antigo", "Atual", "Sem indicadores"]


def test_list_mandates_does_not_ship_the_monthly_series(client, mandates):
    for item in client.get(f"{BASE}/mandates").json():
        assert "indicadores" not in item


def test_list_mandates_empty_database(client):
    assert client.get(f"{BASE}/mandates").json() == []


def test_summary_computes_stats_and_variation(client, mandates):
    response = client.get(f"{BASE}/mandates/{mandates['atual'].id}/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["nome"] == "Atual" and body["fim"] is None and body["foto_url"] == "/presidents/x.jpg"
    ipca = body["kpis"]["inflacao_ipca"]
    assert ipca["primeiro"] == 4.0 and ipca["ultimo"] == 6.0
    assert ipca["minimo"] == 3.0 and ipca["maximo"] == 6.0
    assert ipca["media"] == pytest.approx(4.33)
    assert ipca["variacao_pp"] == 2.0
    assert body["total_meses"] == 3


def test_summary_emendas_total_uses_max_of_each_year(client, mandates):
    body = client.get(f"{BASE}/mandates/{mandates['atual'].id}/summary").json()
    assert body["kpis"]["emendas_bilhoes"]["total_acumulado"] == 50.0  # 20 (2023) + 30 (2024)


def test_summary_of_mandate_without_indicators_is_empty_not_an_error(client, mandates):
    body = client.get(f"{BASE}/mandates/{mandates['vazio'].id}/summary").json()
    assert body["kpis"] == {}
    assert body["total_meses"] == 0


def test_summary_with_only_ipca_has_no_emendas_total(client, db, mandates):
    mandate = mandates["antigo"]
    db.add(
        MandateIndicator(
            mandate_id=mandate.id, chave_indicador="inflacao_ipca", valor=5.0, data_medicao=date(2012, 1, 1)
        )
    )
    db.commit()
    body = client.get(f"{BASE}/mandates/{mandate.id}/summary").json()
    assert body["kpis"]["inflacao_ipca"]["variacao_pp"] == 0.0
    assert "emendas_bilhoes" not in body["kpis"]


def test_summary_unknown_mandate_is_404(client, mandates):
    assert client.get(f"{BASE}/mandates/{uuid.uuid4()}/summary").status_code == 404


@pytest.mark.parametrize("suffix", ["summary", "indicators"])
def test_invalid_uuid_is_422(client, suffix):
    assert client.get(f"{BASE}/mandates/nao-e-uuid/{suffix}").status_code == 422


def test_indicators_group_values_by_date(client, mandates):
    rows = client.get(f"{BASE}/mandates/{mandates['atual'].id}/indicators").json()
    first = rows[0]
    assert first == {"data": "2023-01-01", "inflacao_ipca": 4.0}
    assert [row["data"] for row in rows] == sorted(row["data"] for row in rows)
    june = next(row for row in rows if row["data"] == "2023-06-01")
    assert june["emendas_bilhoes"] == 10.0


def test_indicators_empty_series_and_unknown_mandate(client, mandates):
    assert client.get(f"{BASE}/mandates/{mandates['vazio'].id}/indicators").json() == []
    assert client.get(f"{BASE}/mandates/{uuid.uuid4()}/indicators").status_code == 404


def test_get_all_mandates_iple(client):
    res = client.get(f"{BASE}/iple")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 10
    first = data[0]
    assert "mandato_id" in first
    assert "indicadores_base" in first
    assert "variaveis_contextuais" in first
    assert "calibragem_crisp_set" in first
    assert 0.0 <= first["indicadores_base"]["iple_score"] <= 1.0


def test_get_single_mandate_iple(client):
    res = client.get(f"{BASE}/iple?mandate_id=lula-2023")
    assert res.status_code == 200
    data = res.json()
    assert data["mandato_id"] == "lula-2023"
    base = data["indicadores_base"]
    assert 0.0 <= base["taxa_sucesso_ts"] <= 1.0
    assert 0.0 <= base["taxa_manutencao_vetos_tmv"] <= 1.0
    assert 0.0 <= base["iple_score"] <= 1.0
    ctx = data["variaveis_contextuais"]
    assert ctx["fragmentacao_nep_x2"] > 0
    assert ctx["polarizacao_ipp_x3"] > 0
    assert "calibragem_crisp_set" in data


def test_unknown_mandate_iple_is_404(client):
    assert client.get(f"{BASE}/iple?mandate_id=desconhecido-9999").status_code == 404


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
