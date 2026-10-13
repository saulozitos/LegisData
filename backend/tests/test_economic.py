import pytest

from .conftest import write_json, write_text

BASE = "/api/v1/economic"

MACRO_CSV = "ano,ipca,pib\n2019,4.3,1.2\n2020,4.5,\n2021,10.1,4.8\n2022,5.8,3.0\n2023,4.6,2.9\n"
MANDATES = [
    {"id_mandato": "teste-2019", "data_inicio": "2019-01-01", "data_fim": "2023-01-01"},
    {"id_mandato": "aberto-2023", "data_inicio": "2023-01-01", "data_fim": None},
]


@pytest.fixture()
def macro(data_dir):
    write_text(data_dir, "resumo_macroeconomico_anual.csv", MACRO_CSV)
    write_json(data_dir, "indicadores_por_mandato.json", MANDATES)
    return data_dir


def test_annual_summary_without_filter_returns_all_years(client, macro):
    response = client.get(f"{BASE}/annual-summary")
    assert response.status_code == 200
    assert [row["ano"] for row in response.json()] == [2019, 2020, 2021, 2022, 2023]


def test_annual_summary_nan_becomes_json_null(client, macro):
    """NaN não é JSON válido: antes virava HTTP 500 na serialização."""
    rows = client.get(f"{BASE}/annual-summary").json()
    assert rows[1]["ano"] == 2020 and rows[1]["pib"] is None
    assert rows[0]["pib"] == 1.2


def test_annual_summary_mandate_end_date_is_exclusive(client, macro):
    """Mandato 2019-01-01 -> 2023-01-01 cobre 2019..2022 (2023 pertence ao mandato seguinte)."""
    rows = client.get(f"{BASE}/annual-summary", params={"mandate_id": "teste-2019"}).json()
    assert [row["ano"] for row in rows] == [2019, 2020, 2021, 2022]


def test_annual_summary_open_mandate_runs_to_last_year_of_series(client, macro):
    rows = client.get(f"{BASE}/annual-summary", params={"mandate_id": "aberto-2023"}).json()
    assert [row["ano"] for row in rows] == [2023]


def test_annual_summary_unknown_mandate_is_404_not_the_whole_series(client, macro):
    response = client.get(f"{BASE}/annual-summary", params={"mandate_id": "nao-existe"})
    assert response.status_code == 404
    assert "nao-existe" in response.json()["detail"]


def test_annual_summary_does_not_treat_mandate_id_as_a_path(client, macro):
    response = client.get(f"{BASE}/annual-summary", params={"mandate_id": "../../etc/passwd"})
    assert response.status_code == 404


def test_annual_summary_missing_csv_is_404(client, data_dir):
    assert client.get(f"{BASE}/annual-summary").status_code == 404


def test_annual_summary_missing_mandate_catalog_is_404(client, data_dir):
    write_text(data_dir, "resumo_macroeconomico_anual.csv", MACRO_CSV)
    response = client.get(f"{BASE}/annual-summary", params={"mandate_id": "teste-2019"})
    assert response.status_code == 404
    assert "Catálogo" in response.json()["detail"]


def test_annual_summary_csv_without_year_column_is_a_clear_500(client, data_dir):
    write_text(data_dir, "resumo_macroeconomico_anual.csv", "x,y\n1,2\n")
    response = client.get(f"{BASE}/annual-summary")
    assert response.status_code == 500
    assert "ano" in response.json()["detail"]


def test_annual_summary_infinite_values_become_null(client, data_dir):
    write_text(data_dir, "resumo_macroeconomico_anual.csv", "ano,divida\n2020,inf\n2021,-inf\n2022,3.5\n")
    rows = client.get(f"{BASE}/annual-summary").json()
    assert [row["divida"] for row in rows] == [None, None, 3.5]


def test_ipca_monthly_filters_by_year_range(client, data_dir):
    write_text(data_dir, "ipca_mensal_historico.csv", "ano,mes,valor\n2020,1,0.2\n2021,1,0.5\n2021,2,0.6\n2022,1,0.7\n")
    rows = client.get(f"{BASE}/ipca-monthly", params={"ano_inicio": 2021, "ano_fim": 2021}).json()
    assert [(r["ano"], r["mes"]) for r in rows] == [(2021, 1), (2021, 2)]
    only_start = client.get(f"{BASE}/ipca-monthly", params={"ano_inicio": 2021}).json()
    assert {r["ano"] for r in only_start} == {2021, 2022}


def test_ipca_monthly_inverted_range_is_422(client, data_dir):
    write_text(data_dir, "ipca_mensal_historico.csv", "ano,mes,valor\n2020,1,0.2\n")
    response = client.get(f"{BASE}/ipca-monthly", params={"ano_inicio": 2022, "ano_fim": 2020})
    assert response.status_code == 422


@pytest.mark.parametrize("params", [{"ano_inicio": 1800}, {"ano_fim": 3000}, {"ano_inicio": "abc"}])
def test_ipca_monthly_rejects_out_of_range_years(client, data_dir, params):
    assert client.get(f"{BASE}/ipca-monthly", params=params).status_code == 422


def test_ipca_monthly_missing_file_is_404(client, data_dir):
    assert client.get(f"{BASE}/ipca-monthly").status_code == 404


def test_ipca_monthly_nan_becomes_null(client, data_dir):
    write_text(data_dir, "ipca_mensal_historico.csv", "ano,mes,valor\n2020,1,\n")
    assert client.get(f"{BASE}/ipca-monthly").json() == [{"ano": 2020, "mes": 1, "valor": None}]
