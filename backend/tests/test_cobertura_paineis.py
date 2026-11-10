"""Cada painel diz de onde vêm os dados, que período cobre, quando foi atualizado e se a base é completa ou parcial."""

from datetime import date

import pytest
from app.services import cobertura_service as cs

BASE = "/api/v1"


@pytest.mark.parametrize(
    "inicio, alvo, esperado",
    [(date(1995, 2, 1), 1995, cs.COMPLETA), (date(2019, 2, 12), 1995, cs.PARCIAL), (None, 1995, cs.SEM_DADOS)],
)
def test_situacao_e_parcial_quando_a_base_comeca_depois_do_ano_alvo(inicio, alvo, esperado):
    assert cs._situacao(inicio, alvo) == esperado


def test_nota_parcial_diz_a_partir_de_quando_a_base_tem_dados_e_que_ausencia_nao_e_inatividade():
    nota = cs._nota(cs.PARCIAL, "Votações nominais", date(2019, 2, 12), 1995)
    assert "a partir de 2019" in nota and "não significa que não houve atividade" in nota


def test_endpoint_lista_os_cinco_paineis_com_fonte_e_situacao(client, seed):
    corpo = client.get(f"{BASE}/cobertura").json()
    paineis = {c["painel"]: c for c in corpo}
    assert set(paineis) == {"votacoes", "proposicoes", "parlamentares", "presenca", "gastos"}
    votacoes = paineis["votacoes"]
    assert "Câmara dos Deputados" in votacoes["fonte"] and votacoes["unidade"] == "votações"
    assert votacoes["periodo_inicio"] == "2023-05-02" and votacoes["registros"] >= 2
    assert votacoes["situacao"] == "PARCIAL"  # a semente só tem votações de 2023, e a meta da base é 1995


def test_painel_sem_dado_fica_sem_dados_e_nunca_inventa_periodo(client):
    gastos = next(c for c in client.get(f"{BASE}/cobertura").json() if c["painel"] == "gastos")
    assert gastos["situacao"] == "SEM_DADOS" and gastos["periodo_inicio"] is None and gastos["registros"] == 0


def test_calendario_descreve_a_cobertura_da_base_e_nao_a_atividade_do_congresso(client, seed):
    texto = client.get(f"{BASE}/legislative/calendar", params={"year": 2023}).json()["estatisticas_anuais"][
        "texto_estatistica"
    ]
    assert "a base tem 2 dias com votação nominal cadastrado" in texto
    assert "cobertura da base, não toda a atividade do Congresso" in texto
    assert "realizou" not in texto
