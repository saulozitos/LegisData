"""
Testes automatizados para os endpoints oficiais de Emendas Orçamentárias (/api/v1/emendas).
"""

from app.api.v1.emendas import DICIONARIO_ORCAMENTO, classificar_autor

BASE = "/api/v1/emendas"


def test_classificar_autor_humanizado():
    # Individual
    ind = classificar_autor("ABEL MESQUITA JR.", "Emenda Individual - Transferências com Finalidade Definida")
    assert ind["tipo_autor"] == "INDIVIDUAL"
    assert ind["icone"] == "👤"
    assert "Abel Mesquita Jr." in ind["nome_amigavel"]

    # Bancada
    banc = classificar_autor("BANCADA DE MINAS GERAIS", "Emenda de Bancada")
    assert banc["tipo_autor"] == "BANCADA_ESTADUAL"
    assert banc["icone"] == "🗺️"
    assert banc["uf_referencia"] == "MG"
    assert "Bancada Estadual (MG)" in banc["nome_amigavel"]

    # Relator Geral
    rel = classificar_autor("RELATOR GERAL", "Emenda de Relator")
    assert rel["tipo_autor"] == "RELATOR_GERAL"
    assert rel["icone"] == "⚖️"
    assert rel["nome_amigavel"] == "Relator-Geral do Orçamento"

    # Comissão Temática
    com = classificar_autor("COMISSAO DE SAUDE - CS", "Emenda de Comissão")
    assert com["tipo_autor"] == "COMISSAO_INSTITUCIONAL"
    assert com["icone"] == "🏛️"
    assert "Comissão de Saúde" in com["nome_amigavel"]


def test_dicionario_orcamento_possui_traducoes_claras():
    assert "custeio" in DICIONARIO_ORCAMENTO["termos"]
    assert "investimento" in DICIONARIO_ORCAMENTO["termos"]
    assert "empenhado" in DICIONARIO_ORCAMENTO["termos"]
    assert "pago" in DICIONARIO_ORCAMENTO["termos"]
    assert len(DICIONARIO_ORCAMENTO["linha_do_tempo"]) == 3


def test_get_emendas_resumo_sucesso(client):
    resp = client.get(f"{BASE}/resumo")
    assert resp.status_code == 200
    data = resp.json()
    assert "estatisticas_gerais" in data
    assert data["estatisticas_gerais"]["total_emendas"] > 50000
    assert data["estatisticas_gerais"]["total_reservado_empenhado_brl"] > 1000000000.0
    assert "INDIVIDUAL" in data["por_tipo_autor"]
    assert "BANCADA_ESTADUAL" in data["por_tipo_autor"]
    assert "COMISSAO_INSTITUCIONAL" in data["por_tipo_autor"]
    assert "RELATOR_GERAL" in data["por_tipo_autor"]
    assert len(data["por_area_tematica"]) > 0
    assert len(data["top_ufs"]) > 0
    assert "dicionario" in data


def test_get_emendas_por_localidade_uf(client):
    resp = client.get(f"{BASE}/localidade/MG")
    assert resp.status_code == 200
    data = resp.json()
    assert data["localidade_pesquisada"] == "MG"
    assert data["total_emendas_encontradas"] > 0
    assert data["total_reservado_empenhado_brl"] > 0
    assert len(data["emendas"]) > 0
    assert data["emendas"][0]["estagio"] in ("Dinheiro Entregue", "Dinheiro Reservado")


def test_get_emendas_por_localidade_inexistente_retorna_404(client):
    resp = client.get(f"{BASE}/localidade/NARNIA_CIDADE_INEXISTENTE")
    assert resp.status_code == 404


def test_get_emendas_por_autor_relator(client):
    resp = client.get(f"{BASE}/autor/RELATOR GERAL")
    assert resp.status_code == 200
    data = resp.json()
    assert data["perfil_autor"]["tipo_autor"] == "RELATOR_GERAL"
    assert data["total_emendas_enviadas"] > 0
    assert len(data["emendas"]) > 0


def test_get_emendas_por_autor_bancada(client):
    resp = client.get(f"{BASE}/autor/BANCADA DA BAHIA")
    assert resp.status_code == 200
    data = resp.json()
    assert data["perfil_autor"]["tipo_autor"] == "BANCADA_ESTADUAL"
    assert data["total_emendas_enviadas"] > 0


def test_get_emendas_por_autor_inexistente_retorna_404(client):
    resp = client.get(f"{BASE}/autor/POLITICO_TOTALMENTE_INEXISTENTE_999")
    assert resp.status_code == 404
