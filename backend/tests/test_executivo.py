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
