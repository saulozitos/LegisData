"""Serviço de finanças sobre `fin`: limites, ordenação e a regra de que dado desconhecido nunca vira zero."""

from app.services import financas_service as fs
from sqlalchemy import text

from .conftest import fonte_id, inserir_fin


def test_formatar_cnpj_so_aceita_14_digitos():
    assert fs.formatar_cnpj("02558157000162") == "02.558.157/0001-62"
    assert (
        fs.formatar_cnpj("123") is None and fs.formatar_cnpj(None) is None and fs.formatar_cnpj("12345678901") is None
    )


def test_pessoas_do_parlamentar_junta_o_cadastro_do_uid_e_o_do_identificador(db):
    legado = db.execute(
        text("INSERT INTO core.pessoa (nome_exibicao, uid) VALUES ('Ana', gen_random_uuid()) RETURNING id, uid")
    ).one()
    novo = db.execute(text("INSERT INTO core.pessoa (nome_exibicao) VALUES ('Ana') RETURNING id")).scalar_one()
    outro = db.execute(text("INSERT INTO core.pessoa (nome_exibicao) VALUES ('Beto') RETURNING id")).scalar_one()
    for pessoa, tipo, valor in ((novo, "CAMARA_ID", "10"), (outro, "SENADO_ID", "20")):
        db.execute(
            text("INSERT INTO core.pessoa_identificador (pessoa_id, fonte_id, tipo, valor) VALUES (:p, :f, :t, :v)"),
            {"p": pessoa, "f": fonte_id(db, "CAMARA_API"), "t": tipo, "v": valor},
        )
    db.commit()
    assert sorted(fs.pessoas_do_parlamentar(db, legado.uid, 10, None)) == sorted([legado.id, novo])
    assert sorted(fs.pessoas_do_parlamentar(db, legado.uid, None, 20)) == sorted([legado.id, outro])
    assert fs.pessoas_do_parlamentar(db, legado.uid, None, None) == [legado.id]


def test_ceap_limita_a_dez_fornecedores_e_ordena_pelo_maior_total(db, pessoa):
    inserir_fin(db, "despesa_cota", pessoa_id=pessoa, ano=2024, tipo_despesa="T", valor_liquido=1000)
    for i in range(12):
        inserir_fin(
            db, "despesa_cota_fornecedor", pessoa_id=pessoa, nome=f"F{i:02d}", cnpj=None, valor_total=i + 1, notas=1
        )
    db.commit()
    forn = fs.custos_ceap(db, [pessoa])["maiores_fornecedores"]
    assert len(forn) == 10 and forn[0]["nome_fornecedor"] == "F11" and forn[-1]["nome_fornecedor"] == "F02"
    assert forn[0]["cnpj_cpf"] is None


def test_ceap_sem_resumo_de_notas_devolve_notas_desconhecidas_e_nao_zero(db, pessoa):
    inserir_fin(db, "despesa_cota", pessoa_id=pessoa, ano=2023, tipo_despesa="A", valor_liquido=10)
    inserir_fin(db, "despesa_cota", pessoa_id=pessoa, ano=2024, tipo_despesa="A", valor_liquido=30)
    inserir_fin(db, "despesa_cota", pessoa_id=pessoa, ano=2024, tipo_despesa="B", valor_liquido=5)
    db.commit()
    resumo = fs.custos_ceap(db, [pessoa])
    assert resumo["total_notas"] is None and resumo["gasto_total_recente"] == 45.0
    assert [a["ano"] for a in resumo["gastos_por_ano"]] == [2024, 2023]
    por_ano = fs.ceap_por_ano_e_tipo(db, [pessoa])
    assert por_ano["total_gasto"] == 45.0 and por_ano["total_notas"] is None
    assert [(d["ano"], d["tipo"]) for d in por_ano["despesas"]] == [(2024, "A"), (2024, "B"), (2023, "A")]
    inserir_fin(db, "despesa_cota_resumo", pessoa_id=pessoa, total_notas=7)
    db.commit()
    assert fs.ceap_por_ano_e_tipo(db, [pessoa])["total_notas"] == 7


def test_ceap_sem_pessoa_ou_sem_linhas(db, pessoa):
    assert fs.custos_ceap(db, []) is None and fs.custos_ceap(db, [pessoa]) is None
    assert fs.ceap_por_ano_e_tipo(db, []) == {"total_gasto": 0.0, "total_notas": None, "despesas": []}


def test_remuneracao_sem_registro_nao_inventa_total_zero(db, pessoa):
    vazio = fs.remuneracao(db, [pessoa])
    assert vazio["ano"] is None and vazio["total_bruto_ano"] is None and vazio["bruto_atual"] is None
    assert fs.remuneracao(db, [])["historico"] == []
    inserir_fin(
        db, "remuneracao", pessoa_id=pessoa, ano=2024, mes=1, salario_bruto=100, fonte_id=fonte_id(db, "CAMARA_PORTAL")
    )
    db.commit()
    com = fs.remuneracao(db, [pessoa])
    assert com["total_bruto_ano"] == 100 and com["total_ceap_ano"] is None and com["media_ceap"] is None


def test_emendas_sem_funcao_agrupam_em_outras_funcoes_e_a_lista_respeita_o_limite(db, pessoa, monkeypatch):
    for i in range(3):
        inserir_fin(
            db,
            "emenda",
            pessoa_id=pessoa,
            autor_texto="ANA",
            tipo_autor="INDIVIDUAL",
            autor_situacao="IDENTIFICADO",
            ano=2024,
            codigo_emenda=str(i),
            tipo_emenda="Individual",
            valor_empenhado=100,
            valor_pago=10 * (i + 1),
            localidade_destino="SÃO PAULO (UF)",
            funcao=None,
            fonte_id=fonte_id(db, "PORTAL_TRANSPARENCIA"),
        )
    db.commit()
    monkeypatch.setattr(fs, "MAX_EMENDAS_LISTADAS", 2)
    monkeypatch.setattr(fs, "MAX_EMENDAS_DETALHADAS", 1)
    resumo = fs.emendas_do_parlamentar(db, [pessoa])
    assert resumo["total_emendas"] == 3 and len(resumo["lista_emendas"]) == 2
    assert resumo["lista_emendas"][0]["valor_pago"] == 30.0  # maior pago primeiro
    assert resumo["distribuicao_por_area"][0]["area"] == "Outros"
    assert len(fs.emendas_detalhadas(db, [pessoa])["emendas"]) == 1
    assert fs.emendas_do_parlamentar(db, []) is None


def test_doacoes_e_certidoes_vem_ordenadas(db, pessoa):
    for nome, valor in (("Pequena", 1), ("Grande", 900), ("Media", 50)):
        inserir_fin(
            db,
            "doacao_campanha",
            pessoa_id=pessoa,
            ano_eleicao=2022,
            doador_nome=nome,
            doador_documento=None,
            valor=valor,
            fonte_id=fonte_id(db, "TSE"),
        )
    for orgao, tipo in (("TSE", "B"), ("STF", "Z"), ("TSE", "A")):
        inserir_fin(
            db, "certidao", pessoa_id=pessoa, orgao=orgao, tipo=tipo, situacao="ok", fonte_id=fonte_id(db, "TSE")
        )
    db.commit()
    assert [d["nome_doador"] for d in fs.doacoes_de_campanha(db, [pessoa])] == ["Grande", "Media", "Pequena"]
    assert [(c.court_agency, c.certificate_type) for c in fs.certidoes(db, [pessoa])] == [
        ("STF", "Z"),
        ("TSE", "A"),
        ("TSE", "B"),
    ]
    assert fs.doacoes_de_campanha(db, []) == [] and fs.certidoes(db, []) == []


def test_vazio_ceap_nao_inventa_zero_de_notas():
    assert fs.VAZIO_CEAP["total_notas"] is None and fs.VAZIO_CEAP["possui_dados"] is False


def test_total_de_notas_parcial_e_desconhecido(db, pessoa):
    outra = db.execute(text("INSERT INTO core.pessoa (nome_exibicao) VALUES ('Beto') RETURNING id")).scalar_one()
    for p in (pessoa, outra):
        inserir_fin(db, "despesa_cota", pessoa_id=p, ano=2024, tipo_despesa="T", valor_liquido=10)
    inserir_fin(db, "despesa_cota_resumo", pessoa_id=pessoa, total_notas=3)
    db.commit()
    # só uma das duas pessoas tem resumo: somar 3 ao lado de um gasto de 20 enganaria
    assert fs.custos_ceap(db, [pessoa, outra])["total_notas"] is None
    assert fs.custos_ceap(db, [pessoa])["total_notas"] == 3
    inserir_fin(db, "despesa_cota_resumo", pessoa_id=outra, total_notas=0)
    db.commit()
    assert fs.custos_ceap(db, [pessoa, outra])["total_notas"] == 3  # zero é dado válido


def test_ceap_ordena_o_detalhe_por_ano_depois_por_valor(db, pessoa):
    inserir_fin(db, "despesa_cota", pessoa_id=pessoa, ano=2024, tipo_despesa="Z", valor_liquido=900)
    inserir_fin(db, "despesa_cota", pessoa_id=pessoa, ano=2024, tipo_despesa="A", valor_liquido=5)
    db.commit()
    # Z antes de A só se a ordem for por valor (a ordem alfabética colocaria A primeiro)
    assert [d["tipo"] for d in fs.ceap_por_ano_e_tipo(db, [pessoa])["despesas"]] == ["Z", "A"]


def test_ceap_junta_o_mesmo_cnpj_com_grafias_diferentes_num_fornecedor_so(db, pessoa):
    inserir_fin(db, "despesa_cota", pessoa_id=pessoa, ano=2024, tipo_despesa="T", valor_liquido=1000)
    for nome, valor in (("POSTO SOL LTDA", 300), ("POSTO SOL", 200)):
        inserir_fin(
            db,
            "despesa_cota_fornecedor",
            pessoa_id=pessoa,
            nome=nome,
            cnpj="02558157000162",
            valor_total=valor,
            notas=2,
        )
    inserir_fin(db, "despesa_cota_fornecedor", pessoa_id=pessoa, nome="SEM CNPJ", cnpj=None, valor_total=400, notas=1)
    db.commit()
    forn = fs.custos_ceap(db, [pessoa])["maiores_fornecedores"]
    assert [(f["nome_fornecedor"], f["total_recebido"], f["num_notas"]) for f in forn] == [
        ("POSTO SOL LTDA", 500.0, 4),  # nome de maior valor, soma e notas das duas grafias
        ("SEM CNPJ", 400.0, 1),
    ]
    assert forn[0]["cnpj_cpf"] == "02.558.157/0001-62"


def test_remuneracao_devolve_so_os_ultimos_12_meses_do_mais_recente_para_o_mais_antigo(db, pessoa):
    for mes in range(1, 13):
        for ano in (2023, 2024):
            inserir_fin(db, "remuneracao", pessoa_id=pessoa, ano=ano, mes=mes, salario_bruto=1000 + mes)
    db.commit()
    historico = fs.remuneracao(db, [pessoa])["historico"]
    assert len(historico) == 12
    assert (historico[0]["ano"], historico[0]["mes"]) == (2024, 12) and (
        historico[-1]["ano"],
        historico[-1]["mes"],
    ) == (
        2024,
        1,
    )


def test_resumo_das_doacoes_soma_tudo_mas_lista_so_os_cinco_maiores_com_a_participacao_de_cada_um():
    doacoes = [
        {"nome_doador": f"D{i}", "cpf_cnpj_doador": None, "valor_doado": float(valor), "tipo_receita": None}
        for i, valor in enumerate((50, 20, 10, 10, 5, 3, 2))
    ]
    resumo = fs.resumo_das_doacoes(doacoes)
    assert resumo["total"] == 100.0 and resumo["quantidade"] == 7
    assert [d["nome_doador"] for d in resumo["top_5"]] == ["D0", "D1", "D2", "D3", "D4"]
    assert resumo["top_5"][0]["percentual"] == 50.0
    assert fs.resumo_das_doacoes([]) == {"total": 0.0, "quantidade": 0, "top_5": []}
