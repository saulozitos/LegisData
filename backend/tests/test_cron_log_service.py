"""Mensagens de falha do cron: o que se registra e o que a rota pública repete."""

import pytest
from app.services.cron_log_service import ETAPAS_CONHECIDAS, MENSAGEM_GENERICA, descrever_falha, mensagem_publica


class ErroDeTeste(Exception):
    pass


def test_descrever_falha_registra_etapa_e_classe_sem_o_texto_da_excecao():
    erro = ErroDeTeste('connection to server at "10.0.0.5" failed')
    assert descrever_falha("finanças", erro) == "finanças: ErroDeTeste"
    assert descrever_falha(None, erro) == "ErroDeTeste"
    assert "10.0.0.5" not in descrever_falha("finanças", erro)


@pytest.mark.parametrize(
    "registrada",
    [
        "OperationalError",
        "votações: OperationalError",
        "votações: HTTPError; presença: TimeoutError",
    ],
)
def test_formato_do_registro_passa_inalterado(registrada):
    assert mensagem_publica(registrada) == registrada


@pytest.mark.parametrize(
    "crua",
    [
        'connection to server at "10.0.0.5", port 5432 failed',
        "/caminho/qualquer/arquivo.json não encontrado",
        '(psycopg2.errors.UndefinedTable) relation "leg.segredo" does not exist\n[SQL: SELECT 1]',
        "votações: senado fora do ar",
        "etapa desconhecida: OperationalError",
        "OperationalError\n[SQL: SELECT 1]",
        "x" * 1000,
    ],
)
def test_qualquer_outro_texto_vira_a_mensagem_generica(crua):
    assert mensagem_publica(crua) == MENSAGEM_GENERICA


def test_vazio_e_nulo_nao_viram_mensagem():
    assert mensagem_publica(None) is None and mensagem_publica("") is None and mensagem_publica("  \n ") is None


def test_etapa_fora_do_catalogo_nao_pode_ser_registrada():
    with pytest.raises(ValueError):
        descrever_falha("processos", ErroDeTeste("x"))


def test_toda_etapa_do_catalogo_passa_na_rota_publica():
    for etapa in ETAPAS_CONHECIDAS:
        registrada = descrever_falha(etapa, ErroDeTeste("x"))
        assert mensagem_publica(registrada) == registrada
