from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app

client = TestClient(app)

@patch("app.api.v1.cidadania.get_consultas_publicas")
def test_listar_consultas(mock_get_consultas, monkeypatch):
    mock_get_consultas.return_value = [
        {
            "id_externo": "123",
            "casa": "Senado",
            "sigla_projeto": "PL 123/2020",
            "ementa": "Teste ementa",
            "link_oficial_votacao": "http://teste.com",
            "em_votacao_aberta": True
        },
        {
            "id_externo": "456",
            "casa": "Câmara",
            "sigla_projeto": "PEC 45/2019",
            "ementa": "Teste ementa 2",
            "link_oficial_votacao": "http://teste2.com",
            "em_votacao_aberta": True
        }
    ]

    # Test without filter
    response = client.get("/api/v1/cidadania/consultas")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["casa"] == "Senado"

    # Test with filter Senado
    response = client.get("/api/v1/cidadania/consultas?casa=Senado")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["casa"] == "Senado"

    # Test with filter Câmara
    response = client.get("/api/v1/cidadania/consultas?casa=câmara")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["casa"] == "Câmara"

    # force_refresh público foi removido: o parâmetro na URL é ignorado
    response = client.get("/api/v1/cidadania/consultas?force_refresh=true")
    assert response.status_code == 200
    mock_get_consultas.assert_called_with(force_refresh=False)

    # Sem ADMIN_TOKEN configurado, nem o header força a renovação
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    client.get("/api/v1/cidadania/consultas", headers={"X-Admin-Token": "qualquer"})
    mock_get_consultas.assert_called_with(force_refresh=False)

    # Com ADMIN_TOKEN, só o token correto força a renovação
    monkeypatch.setenv("ADMIN_TOKEN", "token-de-teste")
    client.get("/api/v1/cidadania/consultas", headers={"X-Admin-Token": "errado"})
    mock_get_consultas.assert_called_with(force_refresh=False)
    client.get("/api/v1/cidadania/consultas", headers={"X-Admin-Token": "token-de-teste"})
    mock_get_consultas.assert_called_with(force_refresh=True)
