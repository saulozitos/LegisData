from fastapi.testclient import TestClient
from unittest.mock import MagicMock
import uuid

from app.main import app
from app.core.database import get_db
from app.models import PoliticalParty, EspectroPoliticoEnum

client = TestClient(app)

def test_list_parties():
    mock_db = MagicMock()
    
    # Mock para parties
    party_mock = MagicMock()
    party_mock.id = uuid.uuid4()
    party_mock.acronym = "PT"
    party_mock.full_name = "Partido dos Trabalhadores"
    party_mock.electoral_number = 13
    party_mock.political_spectrum = EspectroPoliticoEnum.ESQUERDA
    party_mock.ideology = "Social-democracia"
    party_mock.motto = "A estrela brilha"
    party_mock.logo_url = None
    
    # query(PoliticalParty).filter(...).all()
    mock_db.query.return_value.filter.return_value.all.return_value = [party_mock]
    
    # query(Mandate).filter(...).group_by(...).all() - deputados, senadores e filiados
    mock_db.query.return_value.filter.return_value.group_by.return_value.all.side_effect = [
        [(party_mock.id, 50)], # deputados
        [(party_mock.id, 10)], # senadores
        [(party_mock.id, 1000)] # filiados
    ]

    app.dependency_overrides[get_db] = lambda: mock_db
    
    try:
        response = client.get("/api/v1/parties")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["sigla"] == "PT"
        assert data[0]["total_deputados"] == 50
        assert data[0]["total_senadores"] == 10
        assert data[0]["total_filiados_ativos"] == 1000
        assert data[0]["cor_hex"] == "#ef4444"
    finally:
        app.dependency_overrides.clear()
