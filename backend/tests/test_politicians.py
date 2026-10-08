from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
import json
import uuid

from app.main import app
from app.api.v1.politicians import _normalize_name, _get_processed_ceap, _get_processed_emendas
from app.core.database import get_db

client = TestClient(app)

def test_normalize_name():
    assert _normalize_name("Joãoção DA SÍLVA") == "JOAOCAO DA SILVA"
    assert _normalize_name(None) == ""

@patch("app.api.v1.politicians.Path.exists")
def test_get_processed_ceap(mock_exists):
    mock_exists.return_value = True
    
    mocked_json = json.dumps({"JOAO DA SILVA": {"total": 1000}})
    import builtins
    from unittest.mock import mock_open
    
    with patch.object(builtins, "open", mock_open(read_data=mocked_json)):
        # Must reset cache since it's global
        import app.api.v1.politicians as pol
        pol._ceap_cache = None
        
        res = _get_processed_ceap("João da Silva")
        assert res is not None
        assert res["total"] == 1000

@patch("app.api.v1.politicians.Path.exists")
def test_get_processed_emendas(mock_exists):
    mock_exists.return_value = True
    
    mocked_json = json.dumps([{"politician_name": "JOAO DA SILVA", "valor": 5000}])
    import builtins
    from unittest.mock import mock_open
    
    with patch.object(builtins, "open", mock_open(read_data=mocked_json)):
        import app.api.v1.politicians as pol
        pol._emendas_cache = None
        
        res = _get_processed_emendas("João da Silva")
        assert len(res) == 1
        assert res[0]["valor"] == 5000

def test_get_presidents():
    import builtins
    from unittest.mock import mock_open
    mock_exists = patch("app.api.v1.politicians.Path.exists").start()
    mock_exists.return_value = True
    
    mocked_json = json.dumps([{"id_mandato": "lula-2003", "nome": "Lula"}])
    with patch.object(builtins, "open", mock_open(read_data=mocked_json)):
        response = client.get("/api/v1/politicians/presidents")
        assert response.status_code == 200
        assert len(response.json()) == 1
    patch.stopall()
