from fastapi.testclient import TestClient
from app.main import app, startup_db_migrations
from app.core.schema_patches import EMENDAS_CEAP_DDL
from app.core.enum_migrations import NOVOS_VALORES_TIPO_PRESENCA
from unittest.mock import patch, MagicMock

client = TestClient(app)

def test_read_main():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "service" in data
    assert "docs_url" in data

def test_startup_db_migrations():
    with patch("app.core.database.SessionLocal") as mock_session:
        # Success case
        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db
        startup_db_migrations()
        assert mock_db.execute.call_count == 5 + len(EMENDAS_CEAP_DDL) + len(NOVOS_VALORES_TIPO_PRESENCA)
        # um commit para os valores de ENUM (precisam de transação própria) e outro para o DDL
        assert mock_db.commit.call_count == 2
        
    with patch("app.core.database.SessionLocal") as mock_session:
        # Error case
        mock_session.return_value.__enter__.side_effect = Exception("Test Exception")
        with patch("logging.getLogger") as mock_logger:
            startup_db_migrations()
            mock_logger.return_value.warning.assert_called_once()
