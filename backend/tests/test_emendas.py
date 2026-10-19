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
    assert [e["codigo_emenda"] for e in data["emendas"]] == ["1", "5", "2"]  # 2024 (pago 400, por id) e depois 2023
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
    assert client.get(f"{BASE}/localidade/%25%25%25").status_code == 404  # "%%%" é texto, não curinga


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
    assert client.get(f"{BASE}/{rota}/xx").status_code == 400  # 2 caracteres só valem como sigla de estado
    assert client.get(f"{BASE}/{rota}/{'x' * 101}").status_code == 422
    assert client.get(f"{BASE}/{rota}/xxx").status_code == 404


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


def test_termo_de_duas_letras_so_vale_como_sigla_de_estado(client, db):
    _emenda(db, "ANA", "INDIVIDUAL", codigo_emenda="1", localidade_destino="BELO HORIZONTE - MG", uf="MG")
    _emenda(db, "BIA", "INDIVIDUAL", codigo_emenda="2", localidade_destino="BH SHOPPING - MG", uf="MG")
    db.commit()
    assert client.get(f"{BASE}/localidade/bh").status_code == 400  # "BH" não é UF e 2 letras não usam o índice
    assert client.get(f"{BASE}/localidade/mg").json()["total_emendas_encontradas"] == 2  # "MG" é UF: filtra por `uf`
    assert client.get(f"{BASE}/localidade/bh%20sh").json()["total_emendas_encontradas"] == 1


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
        ("localidade", "a", "Informe ao menos 3 caracteres da localidade ou a sigla do estado."),
        ("localidade", "bh", "Informe ao menos 3 caracteres da localidade ou a sigla do estado."),
        ("autor", "a", "Informe ao menos 3 caracteres do autor."),
        ("autor", "mg", "Informe ao menos 3 caracteres do autor."),  # a sigla só vale na busca por localidade
        ("localidade", "%20a%20", "Informe ao menos 3 caracteres da localidade ou a sigla do estado."),  # após o strip
        ("autor", "%20a%20", "Informe ao menos 3 caracteres do autor."),
        ("localidade", "a%00b", "A localidade contém caractere inválido."),
        ("autor", "a%00b", "O autor contém caractere inválido."),
    ],
)
def test_mensagens_da_validacao_do_termo(client, emendas, rota, termo, mensagem):
    resposta = client.get(f"{BASE}/{rota}/{termo}")
    assert resposta.status_code == 400 and resposta.json()["detail"] == mensagem


@pytest.mark.parametrize("termo", ["DF", "df"])
def test_a_sigla_do_estado_filtra_pela_uf(client, db, termo):
    _emenda(
        db, "ANA", "INDIVIDUAL", codigo_emenda="1", localidade_destino="DISTRITO FEDERAL (UF)", uf="DF", valor_pago=1
    )
    _emenda(db, "BIA", "INDIVIDUAL", codigo_emenda="2", localidade_destino="BRASÍLIA - DF", uf="DF", valor_pago=2)
    _emenda(
        db, "CIA", "INDIVIDUAL", codigo_emenda="3", localidade_destino="FEDERAL DE ALGO - GO", uf="GO", valor_pago=4
    )
    db.commit()
    dados = client.get(f"{BASE}/localidade/{termo}").json()
    assert dados["total_emendas_encontradas"] == 2 and dados["total_entregue_pago_brl"] == 3.0


def test_nome_de_estado_por_extenso_e_busca_por_trecho_e_nao_traz_o_estado_inteiro(client, db):
    for codigo, autor, destino, uf in (
        ("1", "ANA", "SÃO PAULO (UF)", "SP"),
        ("2", "BIA", "SÃO PAULO - SP", "SP"),
        ("3", "CIA", "CAMPINAS - SP", "SP"),
        ("4", "DAN", "TOCANTINS - MG", "MG"),  # município mineiro com nome de estado
        ("5", "EVA", "PALMAS - TO", "TO"),
    ):
        _emenda(db, autor, "INDIVIDUAL", codigo_emenda=codigo, localidade_destino=destino, uf=uf, valor_pago=1)
    db.commit()
    # a sigla é o estado inteiro (o estado e os seus municípios)
    assert client.get(f"{BASE}/localidade/SP").json()["total_emendas_encontradas"] == 3
    # o nome por extenso é busca por trecho: a capital e o estado, sem Campinas
    assert client.get(f"{BASE}/localidade/São Paulo").json()["total_emendas_encontradas"] == 2
    assert client.get(f"{BASE}/localidade/sao paulo").json()["total_emendas_encontradas"] == 2
    # um município homônimo de estado continua alcançável pelo nome
    dados = client.get(f"{BASE}/localidade/Tocantins").json()
    assert [e["codigo_emenda"] for e in dados["emendas"]] == ["4"]
    assert client.get(f"{BASE}/localidade/belem").status_code == 404


@pytest.mark.parametrize("rota", ["localidade", "autor"])
@pytest.mark.parametrize("termo", ["%CC%81%CC%81%CC%81", "a%CC%81%CC%81", "%CC%81%CC%81%CC%81%CC%81%CC%81"])
def test_o_minimo_conta_o_termo_normalizado_e_nao_os_caracteres_brutos(client, emendas, rota, termo):
    """Acentos combinantes têm 3 ou mais caracteres brutos e 0 ou 1 normalizados: virariam `LIKE '%%'`."""
    resposta = client.get(f"{BASE}/{rota}/{termo}")
    assert resposta.status_code == 400 and "Informe ao menos 3 caracteres" in resposta.json()["detail"]


def test_espacos_do_meio_nao_contam_a_mais(client, emendas):
    resposta = client.get(f"{BASE}/autor/a%20%20%20b")  # "a b": 3 caracteres normalizados, casa "BANCADA DA BAHIA"
    assert resposta.status_code == 200
    assert [a["nome_amigavel"] for a in resposta.json()["autores_encontrados"]] == ["Bancada Estadual (BA)"]
    assert client.get(f"{BASE}/autor/a%20%20%20%20").status_code == 400  # só "a" depois do strip


def test_buscas_seguidas_na_mesma_sessao_nao_misturam_os_resultados(db):
    from app.services import emendas_service as svc

    _emenda(db, "ANA SILVA", "INDIVIDUAL", codigo_emenda="1", localidade_destino="RECIFE - PE", uf="PE", valor_pago=1)
    _emenda(db, "BIA SOUZA", "INDIVIDUAL", codigo_emenda="2", localidade_destino="NATAL - RN", uf="RN", valor_pago=2)
    db.commit()
    # o mesmo `db`, sem commit entre as chamadas: cada busca é uma consulta única e não deixa nada para a seguinte
    for _ in range(2):
        assert svc.por_autor(db, "silva", 50)["total_emendas_enviadas"] == 1
        assert svc.por_autor(db, "souza", 50)["total_emendas_enviadas"] == 1
        assert svc.por_localidade(db, "recife", 50)["total_emendas_encontradas"] == 1


def test_a_busca_nao_cria_tabela_temporaria_nem_escreve_no_catalogo(db):
    from app.services import emendas_service as svc

    _emenda(db, "ANA SILVA", "INDIVIDUAL", codigo_emenda="1")
    db.commit()
    antes = db.execute(text("SELECT count(*) FROM pg_class")).scalar()
    svc.por_autor(db, "silva", 50)
    assert db.execute(text("SELECT to_regclass('pg_temp.emenda_alvo')")).scalar() is None
    assert db.execute(text("SELECT count(*) FROM pg_class")).scalar() == antes


def test_a_consulta_da_busca_devolve_as_emendas_na_ordem_pedida_e_limita_so_a_lista(db):
    from app.services import emendas_service as svc

    _emenda(db, "ANA SILVA", "INDIVIDUAL", codigo_emenda="1", ano=2022, valor_pago=10)
    _emenda(db, "ANA SILVA", "INDIVIDUAL", codigo_emenda="2", ano=2024, valor_pago=5)
    _emenda(db, "ANA SILVA", "INDIVIDUAL", codigo_emenda="3", ano=2024, valor_pago=90)
    db.commit()
    emendas = svc.por_autor(db, "silva", 50)["emendas"]
    assert [(e["ano"], e["codigo_emenda"]) for e in emendas] == [(2024, "3"), (2024, "2"), (2022, "1")]
    curta = svc.por_autor(db, "silva", 2)
    assert len(curta["emendas"]) == 2 and curta["total_emendas_enviadas"] == 3  # `limit` corta só a lista


def test_busca_cancelada_pelo_banco_por_demora_responde_400_pela_api(client, db, monkeypatch):
    """Cancelamento REAL: o banco cancela a consulta (SQLSTATE 57014) e a API devolve 400."""
    from app.services import emendas_service as svc

    _emenda(db, "ANA SILVA", "INDIVIDUAL", codigo_emenda="1")
    db.commit()
    monkeypatch.setattr(svc, "TEMPO_MAXIMO_DA_BUSCA_MS", 20)
    monkeypatch.setattr(svc, "_BUSCA", text("SELECT pg_sleep(2) AS resultado"))
    resposta = client.get(f"{BASE}/autor/silva")
    assert resposta.status_code == 400 and "mais específico" in resposta.json()["detail"]


def test_depois_do_cancelamento_a_sessao_segue_usavel_sem_o_limite_e_a_vaga_volta(db, monkeypatch):
    """Na MESMA sessão: o `rollback` do 57014 a deixa utilizável, sem o timeout da busca, e a vaga do semáforo volta."""
    import threading

    from app.core.errors import ErroDeDominio
    from app.services import emendas_service as svc

    padrao = db.execute(text("SHOW statement_timeout")).scalar()
    assert padrao != "20ms"
    monkeypatch.setattr(svc, "_BUSCAS_SIMULTANEAS", threading.BoundedSemaphore(1))
    monkeypatch.setattr(svc, "TEMPO_MAXIMO_DA_BUSCA_MS", 20)
    monkeypatch.setattr(svc, "_BUSCA", text("SELECT pg_sleep(2) AS resultado"))
    with pytest.raises(ErroDeDominio) as erro:
        svc._executa_busca(db, "autor", "silva", 50)
    assert erro.value.status_code == 400
    assert db.execute(text("SELECT 1")).scalar() == 1  # o `rollback` tirou a sessão do estado de transação abortada
    assert db.execute(text("SHOW statement_timeout")).scalar() == padrao  # o limite valia só naquela transação
    assert svc._BUSCAS_SIMULTANEAS.acquire(blocking=False)  # a vaga voltou apesar da exceção


def test_outro_erro_de_banco_na_busca_sobe_como_esta_e_devolve_a_vaga(db, monkeypatch):
    import threading

    from app.services import emendas_service as svc
    from sqlalchemy.exc import OperationalError

    class Outro(Exception):
        pgcode = "08006"

    original = db.execute

    def quebra(consulta, *args, **kwargs):
        if consulta is svc._BUSCA:
            raise OperationalError("SELECT 1", {}, Outro())
        return original(consulta, *args, **kwargs)

    monkeypatch.setattr(svc, "_BUSCAS_SIMULTANEAS", threading.BoundedSemaphore(1))
    monkeypatch.setattr(db, "execute", quebra)
    with pytest.raises(OperationalError):  # não vira o 400 de "busca ampla demais"
        svc._executa_busca(db, "autor", "silva", 50)
    assert svc._BUSCAS_SIMULTANEAS.acquire(blocking=False)  # a vaga voltou pelo `finally`


def test_sem_vaga_de_busca_a_api_responde_503_sem_esperar(client, emendas, monkeypatch):
    import threading

    from app.services import emendas_service as svc

    monkeypatch.setattr(svc, "_BUSCAS_SIMULTANEAS", threading.BoundedSemaphore(1))
    assert svc._BUSCAS_SIMULTANEAS.acquire(blocking=False)  # a única vaga está ocupada
    resposta = client.get(f"{BASE}/autor/abel")
    assert resposta.status_code == 503 and "muitas buscas" in resposta.json()["detail"]
    svc._BUSCAS_SIMULTANEAS.release()
    assert client.get(f"{BASE}/autor/abel").status_code == 200  # a vaga é devolvida mesmo depois do 503


def test_a_vaga_da_busca_volta_mesmo_quando_ela_nao_acha_nada(client, emendas, monkeypatch):
    import threading

    from app.services import emendas_service as svc

    monkeypatch.setattr(svc, "_BUSCAS_SIMULTANEAS", threading.BoundedSemaphore(1))
    assert client.get(f"{BASE}/autor/zzznaoexiste").status_code == 404
    assert client.get(f"{BASE}/autor/abel").status_code == 200


def test_o_limite_de_tempo_da_busca_vale_so_na_transacao(db):
    from app.services import emendas_service as svc

    _emenda(db, "ANA SILVA", "INDIVIDUAL", codigo_emenda="1")
    db.commit()
    padrao = db.execute(text("SHOW statement_timeout")).scalar()
    assert padrao != "8s"  # senão o teste passaria mesmo com `set_config(..., false)`
    svc.por_autor(db, "silva", 50)  # o caminho real: liga o limite dentro da transação da busca
    db.commit()  # o fim da transação devolve o valor de antes; `set_config(..., false)` ficaria na sessão
    assert db.execute(text("SHOW statement_timeout")).scalar() == padrao


def test_descricao_do_tipo_de_autor_vem_de_um_lugar_so_no_resumo_e_no_perfil():
    from app.services.emendas_service import meta_do_tipo_de_autor, perfil_do_autor

    for tipo in ("BANCADA_ESTADUAL", "RELATOR_GERAL", "COMISSAO_INSTITUCIONAL", "INDIVIDUAL"):
        perfil = perfil_do_autor("NOME", tipo)
        meta = meta_do_tipo_de_autor(tipo)
        assert perfil["categoria"] == meta["categoria"] and perfil["icone"] == meta["icone"]
    assert meta_do_tipo_de_autor("QUALQUER COISA") == meta_do_tipo_de_autor("INDIVIDUAL")
    assert perfil_do_autor("X", "QUALQUER COISA")["tipo_autor"] == "INDIVIDUAL"


def test_emenda_sem_funcao_usa_a_mesma_area_no_dossie_e_nas_buscas(client, db):
    from app.services.emendas_service import AREA_SEM_FUNCAO

    _emenda(db, "ANA SILVA", "INDIVIDUAL", codigo_emenda="1", funcao=None, valor_pago=3)
    db.commit()
    assert client.get(f"{BASE}/autor/silva").json()["emendas"][0]["area_tematica"] == AREA_SEM_FUNCAO
    assert client.get(f"{BASE}/resumo").json()["por_area_tematica"][0]["area"] == AREA_SEM_FUNCAO
