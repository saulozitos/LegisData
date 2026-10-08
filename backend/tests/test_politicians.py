from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
import json
import uuid

from app.main import app
from app.core.database import get_db

client = TestClient(app)

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
