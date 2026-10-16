"""Resumo anual e IPCA mensal lidos de `eco` (séries oficiais, janela de 1995 em diante)."""

from datetime import date

import pytest
from sqlalchemy import text

from .conftest import criar_mandato_presidencial

BASE = "/api/v1/economic"


def _observar(db, codigo, referencia, valor):
    db.execute(
        text(
            "INSERT INTO eco.observacao (serie_id, referencia, valor) "
            "VALUES ((SELECT id FROM eco.serie WHERE codigo = :c), :r, :v)"
        ),
        {"c": codigo, "r": referencia, "v": valor},
    )


@pytest.fixture()
def macro(db):
    criar_mandato_presidencial(db, "Presidente Um", date(2019, 1, 1), date(2023, 1, 1), "teste-2019")
    criar_mandato_presidencial(db, "Presidente Dois", date(2023, 1, 1), None, "aberto-2023", "Dois 1")
    for ano, ipca, pib in ((2019, 4.3, 1.2), (2020, 4.5, None), (2021, 10.1, 4.8), (2022, 5.8, 3.0), (2023, 4.6, 2.9)):
        _observar(db, "IPCA_ACUM_ANO", date(ano, 1, 1), ipca)
        if pib is not None:
            _observar(db, "PIB_CRESC_REAL", date(ano, 1, 1), pib)
    db.commit()


def test_annual_summary_without_filter_returns_all_years(client, macro):
    response = client.get(f"{BASE}/annual-summary")
    assert response.status_code == 200
    assert [row["ano"] for row in response.json()] == [2019, 2020, 2021, 2022, 2023]


def test_annual_summary_missing_value_is_null_never_zero(client, macro):
    rows = client.get(f"{BASE}/annual-summary").json()
    assert rows[1]["ano"] == 2020 and rows[1]["pib_crescimento_real_pct"] is None
    assert rows[0]["pib_crescimento_real_pct"] == 1.2
    # séries sem fonte carregada vêm null: nunca 0
    assert rows[0]["taxa_feminicidios"] is None and "ibovespa_fechamento" not in rows[0]
    assert rows[0]["salario_minimo"] is None


def test_annual_summary_names_the_dominant_president(client, macro):
    rows = {r["ano"]: r["presidente_dominante"] for r in client.get(f"{BASE}/annual-summary").json()}
    assert rows[2019] == "Presidente Um" and rows[2023] == "Presidente Dois (Dois 1)"


def test_annual_summary_mandate_end_date_is_exclusive(client, macro):
    """Mandato 2019-01-01 -> 2023-01-01 cobre 2019..2022 (2023 pertence ao mandato seguinte)."""
    rows = client.get(f"{BASE}/annual-summary", params={"mandate_id": "teste-2019"}).json()
    assert [row["ano"] for row in rows] == [2019, 2020, 2021, 2022]


def test_annual_summary_open_mandate_runs_to_last_year_of_series(client, macro):
    rows = client.get(f"{BASE}/annual-summary", params={"mandate_id": "aberto-2023"}).json()
    assert [row["ano"] for row in rows] == [2023]


def test_annual_summary_accumulated_inflation_restarts_in_each_mandate(client, db, macro):
    for ano in range(2019, 2024):
        for mes in range(1, 13):
            _observar(db, "IPCA_MENSAL", date(ano, mes, 1), 1.0)
    db.commit()
    rows = {r["ano"]: r["inflacao_acumulada_mandato"] for r in client.get(f"{BASE}/annual-summary").json()}
    assert rows[2019] == pytest.approx((1.01**12 - 1) * 100, rel=1e-6)
    assert rows[2022] == pytest.approx((1.01**48 - 1) * 100, rel=1e-6)
    assert rows[2023] == pytest.approx((1.01**12 - 1) * 100, rel=1e-6)


def test_annual_summary_unknown_mandate_is_404_not_the_whole_series(client, macro):
    response = client.get(f"{BASE}/annual-summary", params={"mandate_id": "nao-existe"})
    assert response.status_code == 404
    assert "nao-existe" in response.json()["detail"]


def test_annual_summary_does_not_treat_mandate_id_as_a_path(client, macro):
    response = client.get(f"{BASE}/annual-summary", params={"mandate_id": "../../etc/passwd"})
    assert response.status_code == 404


def test_annual_summary_without_data_is_404(client):
    assert client.get(f"{BASE}/annual-summary").status_code == 404


def test_ipca_monthly_filters_by_year_range(client, db):
    for referencia, valor in (
        (date(2020, 1, 1), 0.2),
        (date(2021, 1, 1), 0.5),
        (date(2021, 2, 1), 0.6),
        (date(2022, 1, 1), 0.7),
    ):
        _observar(db, "IPCA_MENSAL", referencia, valor)
    db.commit()
    rows = client.get(f"{BASE}/ipca-monthly", params={"ano_inicio": 2021, "ano_fim": 2021}).json()
    assert [(r["ano"], r["mes"], r["valor"]) for r in rows] == [(2021, 1, 0.5), (2021, 2, 0.6)]
    only_start = client.get(f"{BASE}/ipca-monthly", params={"ano_inicio": 2021}).json()
    assert {r["ano"] for r in only_start} == {2021, 2022}


def test_ipca_monthly_inverted_range_is_422(client):
    response = client.get(f"{BASE}/ipca-monthly", params={"ano_inicio": 2022, "ano_fim": 2020})
    assert response.status_code == 422


@pytest.mark.parametrize("params", [{"ano_inicio": 1800}, {"ano_fim": 3000}, {"ano_inicio": "abc"}])
def test_ipca_monthly_rejects_out_of_range_years(client, params):
    assert client.get(f"{BASE}/ipca-monthly", params=params).status_code == 422


def test_ipca_monthly_without_data_is_404(client):
    assert client.get(f"{BASE}/ipca-monthly").status_code == 404


def test_observation_before_1995_is_rejected_by_the_table(db):
    with pytest.raises(Exception, match="observacao_referencia_check"):
        _observar(db, "IPCA_MENSAL", date(1994, 12, 1), 1.0)
        db.flush()
