import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
from app.main import app
from app.core.database import get_db

client = TestClient(app)

def mock_get_db():
    mock_session = MagicMock()
    
    # Mock for mandates
    mock_mandate = MagicMock()
    mock_mandate.id = "55ba9d16-7fac-440a-87f1-63632fa729a1"
    mock_mandate.nome = "Teste"
    mock_mandate.inicio = "2023-01-01"
    mock_mandate.fim = "2026-12-31"
    mock_mandate.partido = "PT"
    mock_mandate.foto_url = ""
    
    mock_session.query().order_by().all.return_value = [mock_mandate]
    mock_session.query().filter().first.return_value = None
    
    yield mock_session

app.dependency_overrides[get_db] = mock_get_db

def test_list_presidential_mandates():
    response = client.get("/api/v1/executivo/mandates")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["nome"] == "Teste"

def test_get_mandate_indicators_not_found():
    import uuid
    random_id = str(uuid.uuid4())
    response = client.get(f"/api/v1/executivo/mandates/{random_id}/indicators")
    assert response.status_code == 404
