"""Disparidade salarial e classes sociais da PNAD, lidas das séries e tabelas oficiais de `eco`."""

from datetime import date

import pytest
from sqlalchemy import text

from .conftest import criar_mandato_presidencial, observar_serie

BASE = "/api/v1/analytics"


def _subsidio(db, ano, valor, norma="Decreto Legislativo 1/2000"):
    db.execute(
        text(
            "INSERT INTO eco.observacao (serie_id, referencia, valor, nota) "
            "VALUES ((SELECT id FROM eco.serie WHERE codigo = 'SUBSIDIO_PARLAMENTAR'), :r, :v, :n)"
        ),
        {"r": date(ano, 1, 1), "v": valor, "n": norma},
    )


@pytest.fixture()
def salarios(db):
    criar_mandato_presidencial(db, "Um", date(2000, 1, 1), date(2002, 1, 1), "um-2000", "U 1")
    criar_mandato_presidencial(db, "Dois", date(2002, 1, 1), None, "dois-2002")
    for ano, minimo, subsidio, ipca in (
        (2000, 100.0, 8000.0, 6.0),
        (2001, 120.0, 8000.0, 10.0),
        (2002, 200.0, 12000.0, 5.0),
    ):
        observar_serie(db, "SALARIO_MINIMO", date(ano, 1, 1), minimo)
        _subsidio(db, ano, subsidio)
        observar_serie(db, "IPCA_ACUM_ANO", date(ano, 1, 1), ipca)
    db.commit()


def test_serie_historica_indexa_pelo_primeiro_ano(client, salarios):
    corpo = client.get(f"{BASE}/wage-disparity").json()
    pontos = corpo["serie_historica"]
    assert [p["ano"] for p in pontos] == [2000, 2001, 2002]
    assert pontos[0]["indice_salario_minimo_base100"] == 100.0 and pontos[0]["indice_ipca_base100"] == 100.0
    assert pontos[2]["indice_salario_minimo_base100"] == 200.0
    assert pontos[2]["indice_salario_parlamentar_base100"] == 150.0
    # o IPCA acumula a partir do ano seguinte ao primeiro: 1,10 * 1,05 = 115,5
    assert pontos[2]["indice_ipca_base100"] == 115.5
    assert pontos[0]["multiplo_salarios_minimos"] == 80.0 and pontos[2]["multiplo_salarios_minimos"] == 60.0
    assert pontos[0]["presidente_dominante"] == "Um (U 1)" and pontos[2]["presidente_dominante"] == "Dois"


def test_estatisticas_sao_calculadas_da_propria_serie(client, salarios):
    est = client.get(f"{BASE}/wage-disparity").json()["estatisticas_disparidade"]
    assert (est["ano_referencia_inicial"], est["ano_referencia_atual"]) == (2000, 2002)
    assert (est["salario_minimo_inicial"], est["salario_minimo_atual"]) == (100.0, 200.0)
    assert (est["salario_parlamentar_inicial"], est["salario_parlamentar_atual"]) == (8000.0, 12000.0)
    assert (est["pico_multiplo_ano"], est["pico_multiplo_valor"], est["multiplo_atual"]) == (2000, 80.0, 60.0)
    assert est["multiplo_medio_historico"] == 68.9  # (80 + 66,7 + 60) / 3
    assert est["crescimento_acumulado_salario_minimo_pct"] == 100.0
    assert est["crescimento_acumulado_salario_parlamentar_pct"] == 50.0


def test_ano_sem_norma_do_subsidio_fica_fora_da_serie(client, db, salarios):
    observar_serie(db, "SALARIO_MINIMO", date(2003, 1, 1), 240.0)  # sem subsídio com decreto citado
    db.commit()
    anos = [p["ano"] for p in client.get(f"{BASE}/wage-disparity").json()["serie_historica"]]
    assert 2003 not in anos


def test_ipca_ausente_no_ano_vem_nulo_e_nao_zera_o_indice(client, db):
    observar_serie(db, "SALARIO_MINIMO", date(2000, 1, 1), 100.0)
    observar_serie(db, "SALARIO_MINIMO", date(2001, 1, 1), 110.0)
    _subsidio(db, 2000, 8000.0)
    _subsidio(db, 2001, 8000.0)
    db.commit()
    pontos = client.get(f"{BASE}/wage-disparity").json()["serie_historica"]
    assert pontos[1]["ipca_acumulado_ano_pct"] is None and pontos[1]["indice_ipca_base100"] == 100.0


def test_sem_series_carregadas_e_404(client):
    resposta = client.get(f"{BASE}/wage-disparity")
    assert resposta.status_code == 404 and "ETL" in resposta.json()["detail"]


def _votacao_mpv(db, sim, nao, abst, ausente=0):
    casa = db.execute(text("SELECT id FROM ref.casa_legislativa WHERE codigo = 'CAMARA_DOS_DEPUTADOS'")).scalar()
    prop = db.execute(
        text(
            "INSERT INTO leg.proposicao (tipo_codigo, numero, ano, titulo, ementa, data_apresentacao, status_codigo) "
            "VALUES ('MPV', 1172, 2023, 'MPV 1172/2023', 'Salário mínimo', DATE '2023-05-01', 'APROVADA_E_SANCIONADA') "
            "RETURNING id"
        )
    ).scalar()
    votacao = db.execute(
        text(
            "INSERT INTO leg.votacao (proposicao_id, casa_id, data_hora, tipo_deliberacao, aprovada) VALUES "
            "(:p, :c, TIMESTAMPTZ '2023-08-23 15:00+00', 'NOMINAL', true) RETURNING id"
        ),
        {"p": prop, "c": casa},
    ).scalar()
    opcoes = ["SIM"] * sim + ["NAO"] * nao + ["ABSTENCAO"] * abst + ["AUSENTE"] * ausente
    for i, opcao in enumerate(opcoes):
        pessoa = db.execute(
            text("INSERT INTO core.pessoa (nome_exibicao) VALUES (:n) RETURNING id"), {"n": f"D{i}"}
        ).scalar()
        db.execute(
            text("INSERT INTO leg.voto (votacao_id, pessoa_id, opcao_codigo) VALUES (:v, :p, :o)"),
            {"v": votacao, "p": pessoa, "o": opcao},
        )
    return votacao


def test_placar_da_votacao_do_salario_minimo_vem_dos_votos_nominais(client, db, salarios):
    _votacao_mpv(db, sim=5, nao=2, abst=1, ausente=3)
    db.commit()
    votacao = client.get(f"{BASE}/wage-disparity").json()["votacao_salario_minimo"]
    assert votacao["data_votacao"] == "2023-08-23" and votacao["dados_indisponiveis"] is False
    assert (votacao["placar"]["SIM"], votacao["placar"]["NAO"], votacao["placar"]["ABSTENCAO"]) == (5, 2, 1)
    assert votacao["placar"]["TOTAL"] == 8 and votacao["placar"]["AUSENTE"] == 3


def test_sem_a_votacao_o_placar_fica_indisponivel_e_nao_zerado(client, salarios):
    votacao = client.get(f"{BASE}/wage-disparity").json()["votacao_salario_minimo"]
    assert votacao["placar"] is None and votacao["data_votacao"] is None and votacao["dados_indisponiveis"] is True


# ---------------------------------------------------------------------------
# classes sociais (PNAD)
# ---------------------------------------------------------------------------
def _pnad_ano(db, ano, salario, dom, pessoas):
    db.execute(
        text("INSERT INTO eco.pnad_ano (ano, visita, salario_minimo_brl) VALUES (:a, 5, :s)"), {"a": ano, "s": salario}
    )
    for nome, pct, total in (
        ("domicilios_renda_total", dom, 78_000_000),
        ("pessoas_renda_domiciliar", pessoas, 210_000_000),
    ):
        db.execute(
            text(
                "INSERT INTO eco.pnad_distribuicao (ano, escopo, distribuicao, total_estimado, media_nominal_brl, percentual) "
                "VALUES (:a, 'BR', :d, :t, 5000, CAST(:p AS numeric[]))"
            ),
            {"a": ano, "d": nome, "t": total, "p": "{" + ",".join(str(x) for x in pct) + "}"},
        )


DOM = [2.0, 4.0, 7.0, 27.0, 33.0, 20.5, 4.5, 2.0]
PESSOAS = [3.0, 5.0, 8.0, 28.0, 31.0, 18.0, 5.0, 2.0]


@pytest.fixture()
def pnad(db):
    _pnad_ano(db, 2023, 1320.0, DOM, PESSOAS)
    _pnad_ano(db, 2024, 1412.0, DOM, PESSOAS)
    db.execute(text("INSERT INTO eco.pnad_metodologia (chave, texto) VALUES ('ponderacao', 'Peso calibrado')"))
    db.commit()


def test_classes_usam_o_ano_mais_recente_e_o_salario_do_proprio_ano(client, pnad):
    corpo = client.get(f"{BASE}/social-classes").json()
    assert corpo["origem"] == "pnad" and corpo["ano_referencia"] == 2024 and corpo["anos_disponiveis"] == [2023, 2024]
    assert corpo["salario_minimo_referencia_brl"] == 1412.0
    classes = {c["classe"]: c for c in corpo["classes"]}
    assert [c["classe"] for c in corpo["classes"]] == ["Classe A", "Classe B", "Classe C", "Classe D", "Classe E"]
    assert classes["Classe A"]["percentual_domicilios"] == 2.0 and classes["Classe A"]["percentual_populacao"] == 2.0
    assert classes["Classe E"]["percentual_domicilios"] == 40.0  # faixas 0 a 3: 2 + 4 + 7 + 27
    assert classes["Classe E"]["percentual_populacao"] == 44.0
    assert classes["Classe A"]["renda_familiar_min_brl"] == pytest.approx(20 * 1412.0)
    assert classes["Classe A"]["renda_familiar_max_brl"] is None
    assert classes["Classe A"]["faixa_renda_formatada"].startswith("Acima de R$ 28.240,00")
    assert corpo["metodologia"] == {"ponderacao": "Peso calibrado"}
    assert len(corpo["faixas"]) == 8 and corpo["faixas"][0]["rotulo"] == "Sem rendimento"
    assert corpo["resumo_populacional"]["maioria_populacao_acumulada_d_e_pct"] == 73.0  # D 33 + E 40 (domicílios)


def test_ano_pedido_usa_o_salario_daquele_ano(client, pnad):
    corpo = client.get(f"{BASE}/social-classes", params={"ano": 2023}).json()
    assert corpo["ano_referencia"] == 2023 and corpo["salario_minimo_referencia_brl"] == 1320.0


def test_ano_sem_microdados_e_404_com_os_anos_disponiveis(client, pnad):
    resposta = client.get(f"{BASE}/social-classes", params={"ano": 1999})
    assert resposta.status_code == 404 and "2023" in resposta.json()["detail"]


def test_sem_microdados_nao_ha_estimativa_de_reserva(client):
    resposta = client.get(f"{BASE}/social-classes")
    assert resposta.status_code == 404 and "PNAD" in resposta.json()["detail"]
    assert "referencia_fixa" not in resposta.text
