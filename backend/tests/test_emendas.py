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
    # ordem: ano mais recente, depois maior valor pago (o Abel de 2023 tem pago 0 e vem por último)
    assert [e["codigo_emenda"] for e in data["emendas"]][-1] == "2"
    assert data["emendas"][0]["estagio"] == "Dinheiro Entregue"


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


def test_limite_da_lista_nao_altera_os_totais(client, emendas):
    data = client.get(f"{BASE}/localidade/MG?limit=1").json()
    assert data["total_emendas_encontradas"] == 3 and data["total_reservado_empenhado_brl"] == 3000.0
    assert len(data["emendas"]) == 1
    por_autor = client.get(f"{BASE}/autor/abel?limit=1").json()
    assert por_autor["total_emendas_enviadas"] == 2 and len(por_autor["emendas"]) == 1


def test_busca_acha_sem_acento_o_que_esta_acentuado_e_vice_versa(client, db):
    _emenda(db, "JOSÉ ÁVILA", "INDIVIDUAL", codigo_emenda="1", localidade_destino="SÃO PAULO (UF)", uf="SP")
    _emenda(db, "JOSE AVILA FILHO", "INDIVIDUAL", codigo_emenda="2", localidade_destino="SAO PAULO - SP", uf="SP")
    db.commit()
    assert client.get(f"{BASE}/autor/jose avila").json()["total_emendas_enviadas"] == 2
    assert client.get(f"{BASE}/autor/JOSÉ ÁVILA").json()["total_emendas_enviadas"] == 2
    assert client.get(f"{BASE}/localidade/sao paulo").json()["total_emendas_encontradas"] == 2
    assert client.get(f"{BASE}/localidade/são paulo").json()["total_emendas_encontradas"] == 2


@pytest.mark.parametrize("rota", ["localidade", "autor"])
def test_termo_com_caractere_nulo_e_rejeitado_sem_erro_de_servidor(client, emendas, rota):
    assert client.get(f"{BASE}/{rota}/ab%00cd").status_code == 400


def test_a_resposta_nao_traz_classificacao_de_recurso_inventada(client, emendas):
    emenda = client.get(f"{BASE}/localidade/MG").json()["emendas"][0]
    assert "tipo_recurso" not in emenda


def test_sigla_de_estado_busca_pela_uf_e_nao_pelo_trecho_do_nome(client, db):
    _emenda(db, "ANA", "INDIVIDUAL", codigo_emenda="1", localidade_destino="ALAGOAS (UF)", uf="AL", valor_pago=1)
    _emenda(db, "BIA", "INDIVIDUAL", codigo_emenda="2", localidade_destino="MACEIO - AL", uf="AL", valor_pago=2)
    _emenda(db, "CIA", "INDIVIDUAL", codigo_emenda="3", localidade_destino="SALVADOR - BA", uf="BA", valor_pago=4)
    _emenda(db, "DAN", "INDIVIDUAL", codigo_emenda="4", localidade_destino="PORTO ALEGRE - RS", uf="RS", valor_pago=8)
    _emenda(db, "EVA", "INDIVIDUAL", codigo_emenda="5", localidade_destino="Nacional", uf=None, valor_pago=16)
    db.commit()
    for termo in ("AL", "al"):
        dados = client.get(f"{BASE}/localidade/{termo}").json()
        assert dados["total_emendas_encontradas"] == 2 and dados["total_entregue_pago_brl"] == 3.0
    # nome de município continua sendo busca por trecho
    assert client.get(f"{BASE}/localidade/salvador").json()["total_emendas_encontradas"] == 1


def test_busca_por_autor_que_reune_varios_autores_avisa_e_lista_quem_casou(client, db):
    _emenda(db, "ANA SILVA", "INDIVIDUAL", codigo_emenda="1", valor_pago=900)
    _emenda(db, "BIA SILVA", "INDIVIDUAL", codigo_emenda="2", valor_pago=100)
    _emenda(db, "BIA SILVA", "INDIVIDUAL", codigo_emenda="3", valor_pago=50)
    db.commit()
    dados = client.get(f"{BASE}/autor/silva").json()
    assert dados["quantidade_autores"] == 2 and dados["total_emendas_enviadas"] == 3
    assert [a["nome_tecnico"] for a in dados["autores_encontrados"]] == ["ANA SILVA", "BIA SILVA"]
    assert [a["quantidade"] for a in dados["autores_encontrados"]] == [1, 2]
    unico = client.get(f"{BASE}/autor/ana silva").json()
    assert unico["quantidade_autores"] == 1


@pytest.mark.parametrize("rota", ["localidade", "autor"])
def test_404_da_busca_nao_repete_o_termo_digitado(client, emendas, rota):
    resposta = client.get(f"{BASE}/{rota}/zzzNaoExiste")
    assert resposta.status_code == 404 and "zzzNaoExiste" not in resposta.text


def test_termo_de_duas_letras_que_nao_e_uf_busca_por_trecho_do_nome(client, db):
    _emenda(db, "ANA", "INDIVIDUAL", codigo_emenda="1", localidade_destino="BELO HORIZONTE - MG", uf="MG")
    _emenda(db, "BIA", "INDIVIDUAL", codigo_emenda="2", localidade_destino="BH SHOPPING - MG", uf="MG")
    db.commit()
    assert client.get(f"{BASE}/localidade/bh").json()["total_emendas_encontradas"] == 1  # "BH" não é UF
    assert client.get(f"{BASE}/localidade/mg").json()["total_emendas_encontradas"] == 2  # "MG" é UF


def test_lista_de_autores_encontrados_corta_em_dez_e_conta_todos(client, db):
    for i in range(11):
        _emenda(db, f"AUTOR {i:02d} SILVA", "INDIVIDUAL", codigo_emenda=str(i), valor_pago=100 - i)
    db.commit()
    dados = client.get(f"{BASE}/autor/silva").json()
    assert dados["quantidade_autores"] == 11 and len(dados["autores_encontrados"]) == 10
    assert dados["autores_encontrados"][0]["nome_tecnico"] == "AUTOR 00 SILVA"


def test_autor_com_emendas_de_tipos_diferentes_aparece_uma_vez(client, db):
    _emenda(db, "COM. DE SAUDE", "COMISSAO_INSTITUCIONAL", codigo_emenda="1", valor_pago=500)
    _emenda(db, "COM. DE SAUDE", "RELATOR_GERAL", codigo_emenda="2", valor_pago=1)
    db.commit()
    dados = client.get(f"{BASE}/autor/saude").json()
    assert dados["quantidade_autores"] == 1 and len(dados["autores_encontrados"]) == 1
    assert dados["autores_encontrados"][0]["tipo_autor"] == "COMISSAO_INSTITUCIONAL"  # o tipo do maior valor pago


@pytest.mark.parametrize(
    "rota, termo, mensagem",
    [
        ("localidade", "a", "Informe ao menos 2 caracteres da localidade."),
        ("autor", "a", "Informe ao menos 2 caracteres do autor."),
        ("localidade", "%20a%20", "Informe ao menos 2 caracteres da localidade."),  # curto depois do strip
        ("autor", "%20a%20", "Informe ao menos 2 caracteres do autor."),
        ("localidade", "a%00b", "A localidade contém caractere inválido."),
        ("autor", "a%00b", "O autor contém caractere inválido."),
    ],
)
def test_mensagens_da_validacao_do_termo(client, emendas, rota, termo, mensagem):
    resposta = client.get(f"{BASE}/{rota}/{termo}")
    assert resposta.status_code == 400 and resposta.json()["detail"] == mensagem
