"""
Testes dos endpoints de Emendas Orçamentárias (/api/v1/emendas), sobre as linhas de `fin.emenda`.
"""

import pytest
from app.services.emendas_service import DICIONARIO_ORCAMENTO, perfil_do_autor
from sqlalchemy import text

from .conftest import fonte_id, inserir_fin

BASE = "/api/v1/emendas"


def test_perfil_do_autor_humanizado():
    ind = perfil_do_autor("ABEL MESQUITA JR.", "INDIVIDUAL")
    assert ind["tipo_autor"] == "INDIVIDUAL"
    assert ind["icone"] == "👤"
    assert "Abel Mesquita Jr." in ind["nome_amigavel"]

    banc = perfil_do_autor("BANCADA DE MINAS GERAIS", "BANCADA_ESTADUAL")
    assert banc["tipo_autor"] == "BANCADA_ESTADUAL"
    assert banc["icone"] == "🗺️"
    assert banc["uf_referencia"] == "MG"
    assert "Bancada Estadual (MG)" in banc["nome_amigavel"]

    rel = perfil_do_autor("RELATOR GERAL", "RELATOR_GERAL")
    assert rel["tipo_autor"] == "RELATOR_GERAL"
    assert rel["icone"] == "⚖️"
    assert rel["nome_amigavel"] == "Relator-Geral do Orçamento"

    com = perfil_do_autor("COMISSAO DE SAUDE - CS", "COMISSAO_INSTITUCIONAL")
    assert com["tipo_autor"] == "COMISSAO_INSTITUCIONAL"
    assert com["icone"] == "🏛️"
    assert "Comissão de Saúde" in com["nome_amigavel"]


def test_dicionario_orcamento_possui_traducoes_claras():
    assert "custeio" in DICIONARIO_ORCAMENTO["termos"]
    assert "investimento" in DICIONARIO_ORCAMENTO["termos"]
    assert "empenhado" in DICIONARIO_ORCAMENTO["termos"]
    assert "pago" in DICIONARIO_ORCAMENTO["termos"]
    assert len(DICIONARIO_ORCAMENTO["linha_do_tempo"]) == 3


def _emenda(db, autor, tipo_autor, **colunas):
    base = dict(
        autor_texto=autor,
        autor_codigo="1",
        tipo_autor=tipo_autor,
        autor_situacao="IDENTIFICADO" if tipo_autor == "INDIVIDUAL" else "INSTITUCIONAL",
        ano=2024,
        codigo_emenda=f"{autor}-{len(colunas)}",
        tipo_emenda="Emenda Individual - Transferências Especiais",
        valor_empenhado=1000,
        valor_pago=400,
        localidade_destino="BELO HORIZONTE - MG",
        uf="MG",
        funcao="Saúde",
        fonte_id=fonte_id(db, "PORTAL_TRANSPARENCIA"),
    )
    base.update(colunas)
    if base["tipo_autor"] == "INDIVIDUAL":
        pessoa = db.execute(
            text("INSERT INTO core.pessoa (nome_exibicao) VALUES (:n) RETURNING id"), {"n": autor}
        ).scalar_one()
        base["pessoa_id"] = pessoa
    inserir_fin(db, "emenda", **base)


@pytest.fixture()
def emendas(db):
    _emenda(db, "ABEL MESQUITA JR.", "INDIVIDUAL", codigo_emenda="1", autor_codigo="3030")
    _emenda(db, "ABEL MESQUITA JR.", "INDIVIDUAL", codigo_emenda="2", ano=2023, valor_pago=0, funcao=None)
    _emenda(
        db,
        "BANCADA DA BAHIA",
        "BANCADA_ESTADUAL",
        codigo_emenda="3",
        tipo_emenda="Emenda de Bancada",
        localidade_destino="BAHIA (UF)",
        uf="BA",
        funcao="Educação",
    )
    _emenda(
        db,
        "RELATOR GERAL",
        "RELATOR_GERAL",
        codigo_emenda=None,
        tipo_emenda="Emenda de Relator",
        localidade_destino="Nacional",
        uf=None,
    )
    _emenda(db, "COM. DE SAUDE", "COMISSAO_INSTITUCIONAL", codigo_emenda="5", tipo_emenda="Emenda de Comissão")
    db.commit()


def test_get_emendas_resumo_sem_dados_retorna_404(client):
    assert client.get(f"{BASE}/resumo").status_code == 404


def test_get_emendas_resumo_sucesso(client, emendas):
    resp = client.get(f"{BASE}/resumo")
    assert resp.status_code == 200
    data = resp.json()
    geral = data["estatisticas_gerais"]
    assert geral["total_emendas"] == 5
    assert geral["total_reservado_empenhado_brl"] == 5000.0 and geral["total_entregue_pago_brl"] == 1600.0
    assert geral["taxa_execucao_pago_pct"] == 32.0
    assert set(data["por_tipo_autor"]) == {"INDIVIDUAL", "BANCADA_ESTADUAL", "COMISSAO_INSTITUCIONAL", "RELATOR_GERAL"}
    assert data["por_tipo_autor"]["INDIVIDUAL"]["quantidade"] == 2
    assert data["por_ano"]["2023"]["quantidade"] == 1
    assert {a["area"] for a in data["por_area_tematica"]} == {"Saúde", "Educação", "Outros"}
    assert [u["uf"] for u in data["top_ufs"]] == ["MG", "BA"]  # o destino sem UF não entra no ranking
    assert "dicionario" in data


def test_get_emendas_por_localidade_uf(client, emendas):
    resp = client.get(f"{BASE}/localidade/MG")
    assert resp.status_code == 200
    data = resp.json()
    assert data["localidade_pesquisada"] == "MG"
    assert data["total_emendas_encontradas"] == 3  # as duas do Abel e a da comissão; "BAHIA (UF)" não casa
    assert data["total_reservado_empenhado_brl"] == 3000.0
    assert len(data["emendas"]) == 3
    assert data["emendas"][0]["estagio"] == "Dinheiro Entregue"  # ordem: ano mais recente, depois maior valor pago


def test_get_emendas_por_localidade_inexistente_retorna_404(client, emendas):
    resp = client.get(f"{BASE}/localidade/NARNIA_CIDADE_INEXISTENTE")
    assert resp.status_code == 404


def test_get_emendas_por_autor_relator(client, emendas):
    resp = client.get(f"{BASE}/autor/RELATOR GERAL")
    assert resp.status_code == 200
    data = resp.json()
    assert data["perfil_autor"]["tipo_autor"] == "RELATOR_GERAL"
    assert data["total_emendas_enviadas"] == 1
    assert data["emendas"][0]["codigo_emenda"] is None  # emenda de relator sem código na fonte


def test_get_emendas_por_autor_bancada(client, emendas):
    resp = client.get(f"{BASE}/autor/BANCADA DA BAHIA")
    assert resp.status_code == 200
    data = resp.json()
    assert data["perfil_autor"]["tipo_autor"] == "BANCADA_ESTADUAL"
    assert data["perfil_autor"]["uf_referencia"] == "BA"
    assert data["total_emendas_enviadas"] == 1


def test_get_emendas_por_autor_inexistente_retorna_404(client, emendas):
    resp = client.get(f"{BASE}/autor/POLITICO_TOTALMENTE_INEXISTENTE_999")
    assert resp.status_code == 404


def test_get_emendas_por_autor_aceita_o_codigo_do_autor_e_ignora_acento_e_caixa(client, emendas):
    por_codigo = client.get(f"{BASE}/autor/3030").json()
    assert por_codigo["total_emendas_enviadas"] == 1  # só a emenda cujo autor_codigo é 3030
    por_nome = client.get(f"{BASE}/autor/abel mesquita").json()
    assert por_nome["total_emendas_enviadas"] == 2 and por_nome["perfil_autor"]["tipo_autor"] == "INDIVIDUAL"
    assert por_nome["top_destinos"][0]["localidade"] == "BELO HORIZONTE - MG"


@pytest.mark.parametrize("rota", ["localidade", "autor"])
def test_busca_vazia_retorna_400(client, emendas, rota):
    assert client.get(f"{BASE}/{rota}/%20").status_code == 400


def test_localidade_trata_curinga_de_like_como_texto(client, emendas):
    assert client.get(f"{BASE}/localidade/%25%25").status_code == 404


@pytest.mark.parametrize(
    "autor,uf",
    [
        ("BANCADA DO PARANA", "PR"),  # não é PA, que está contido em PARANA
        ("BANCADA DA PARAIBA", "PB"),
        ("BANCADA MATO GROSSO DO SUL", "MS"),  # não é MT
        ("BANCADA DE MATO GROSSO", "MT"),
        ("BANCADA DO PARA", "PA"),
        ("BANCADA SEM ESTADO", "NACIONAL"),
    ],
)
def test_uf_da_bancada_prefere_o_nome_de_estado_mais_longo(autor, uf):
    assert perfil_do_autor(autor, "BANCADA_ESTADUAL")["uf_referencia"] == uf


def test_busca_ampla_por_autor_monta_o_perfil_de_uma_unica_emenda(client, db):
    # a bancada entra primeiro (menor id): o perfil tem de vir da maior em valor pago, não da primeira por id
    _emenda(
        db,
        "BANCADA DE SAO PAULO SILVA",
        "BANCADA_ESTADUAL",
        codigo_emenda="2",
        tipo_emenda="Emenda de Bancada",
        valor_pago=10,
    )
    _emenda(db, "ANA SILVA", "INDIVIDUAL", codigo_emenda="1", valor_pago=900)
    db.commit()
    data = client.get(f"{BASE}/autor/silva").json()
    assert data["total_emendas_enviadas"] == 2
    # o perfil é o da emenda de maior valor pago (Ana, individual), não o nome de uma e o tipo de outra
    assert data["perfil_autor"]["tipo_autor"] == "INDIVIDUAL"
    assert data["perfil_autor"]["nome_tecnico"] == "ANA SILVA"


@pytest.mark.parametrize("rota", ["localidade", "autor"])
def test_busca_publica_rejeita_termo_curto_ou_longo_demais(client, emendas, rota):
    assert client.get(f"{BASE}/{rota}/a").status_code == 400
    assert client.get(f"{BASE}/{rota}/{'x' * 101}").status_code == 422
    assert client.get(f"{BASE}/{rota}/xx").status_code == 404


def test_busca_ignora_acento_e_caixa(client, emendas):
    assert client.get(f"{BASE}/autor/abel mesquita").json()["total_emendas_enviadas"] == 2
    assert client.get(f"{BASE}/localidade/belo horizonte").json()["total_emendas_encontradas"] == 3
