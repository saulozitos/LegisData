from fastapi.testclient import TestClient
from unittest.mock import MagicMock
from app.main import app
from app.api.v1.analytics import _clean_val, _get_mandate_years, _calculate_mandate_prosperity_score
from app.core.database import get_db

client = TestClient(app)

def test_clean_val():
    assert _clean_val(None) is None
    assert _clean_val("invalid") is None
    assert _clean_val(10.555) == 10.55
    assert _clean_val("20.123") == 20.12

def test_get_mandate_years():
    assert _get_mandate_years({"id_mandato": "itamar-franco-1992"}) == [1993, 1994]
    assert _get_mandate_years({"id_mandato": "lula-2023"}) == [2023, 2024, 2025, 2026]
    assert _get_mandate_years({"data_inicio": "2010-01-01", "data_fim": "2014-12-31"}) == [2010, 2011, 2012, 2013]

def test_calculate_mandate_prosperity_score():
    m = {
        "pib_medio_anual_pct": 2.5,
        "ipca_acumulado_pct": 15.0,
        "valores_anuais": [1, 2, 3, 4],
        "salario_minimo_inicial_usd": 100,
        "salario_minimo_final_usd": 150,
        "fome_media_pct": 5.0,
        "desemprego_medio_pct": 8.0,
        "desmatamento_medio_anual_km2": 5000.0
    }
    score = _calculate_mandate_prosperity_score(m)
    assert "score_geral" in score
    assert "classificacao" in score

def test_wage_disparity():
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    
    try:
        response = client.get("/api/v1/analytics/wage-disparity")
        # Just checking if the route doesn't crash since it queries DB and calculates
        assert response.status_code in [200, 404] 
    finally:
        app.dependency_overrides.clear()
