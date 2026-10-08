from fastapi.testclient import TestClient
from unittest.mock import patch
import pandas as pd
from app.main import app

client = TestClient(app)

@patch("app.api.v1.economic.Path.exists")
@patch("app.api.v1.economic.pd.read_csv")
def test_get_annual_macro_summary_no_filter(mock_read_csv, mock_exists):
    mock_exists.return_value = True
    df_mock = pd.DataFrame({"ano": [2020, 2021], "ipca": [4.5, 10.0]})
    mock_read_csv.return_value = df_mock

    response = client.get("/api/v1/economic/annual-summary")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["ano"] == 2020

@patch("app.api.v1.economic.Path.exists")
@patch("app.api.v1.economic.pd.read_csv")
def test_get_annual_macro_summary_with_filter(mock_read_csv, mock_exists):
    mock_exists.return_value = True
    df_mock = pd.DataFrame({"ano": [2020, 2021, 2022], "ipca": [4.5, 10.0, 5.0]})
    mock_read_csv.return_value = df_mock
    
    # Mocking open for json.load
    import builtins
    import json
    from unittest.mock import mock_open
    
    mocked_json = json.dumps([{"id_mandato": "teste-2021", "data_inicio": "2021-01-01", "data_fim": "2024-12-31"}])
    with patch.object(builtins, "open", mock_open(read_data=mocked_json)):
        response = client.get("/api/v1/economic/annual-summary?mandate_id=teste-2021")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["ano"] == 2021

@patch("app.api.v1.economic.Path.exists")
@patch("app.api.v1.economic.pd.read_csv")
def test_get_monthly_ipca(mock_read_csv, mock_exists):
    mock_exists.return_value = True
    df_mock = pd.DataFrame({"ano": [2020, 2021, 2022], "valor": [0.5, 0.6, 0.7]})
    mock_read_csv.return_value = df_mock

    response = client.get("/api/v1/economic/ipca-monthly?ano_inicio=2021&ano_fim=2021")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["ano"] == 2021
