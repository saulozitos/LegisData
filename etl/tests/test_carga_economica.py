"""Carga econômica única: ordem, filtro por chaves, isolamento de falhas e dependência da composição."""

import pytest

from etl.pipelines import carga_economica


@pytest.fixture()
def chamadas(monkeypatch):
    registro = []
    for chave, _nome, modulo, _dep in carga_economica.CARGAS:
        monkeypatch.setattr(f"{modulo}.carregar", lambda engine, c=chave: registro.append(c) or {"ok": c})
    return registro


def test_executa_todas_na_ordem_e_devolve_o_resultado_de_cada_uma(chamadas):
    resultados = carga_economica.carregar_tudo(object())
    assert chamadas == ["series", "presidencia", "composicao", "pnad", "financas"]
    assert resultados["composicao"] == {"ok": "composicao"}


def test_chaves_limitam_as_cargas(chamadas):
    carga_economica.carregar_tudo(object(), chaves=("series", "presidencia"))
    assert chamadas == ["series", "presidencia"]


def test_a_composicao_depende_dos_mandatos_e_as_demais_seguem(chamadas, monkeypatch):
    def quebra(engine):
        raise RuntimeError("sem presidentes")

    monkeypatch.setattr("etl.pipelines.presidencia_loader.carregar", quebra)
    with pytest.raises(RuntimeError) as erro:
        carga_economica.carregar_tudo(object())
    assert "sem presidentes" in str(erro.value) and "Composição do Congresso" in str(erro.value)
    assert chamadas == ["series", "pnad", "financas"]


def test_carga_tolerada_que_falha_nao_levanta_e_devolve_o_erro(chamadas, monkeypatch):
    def quebra(engine):
        raise RuntimeError("tabela encolheria")

    monkeypatch.setattr("etl.pipelines.financas_loader.carregar", quebra)
    resultados = carga_economica.carregar_tudo(object(), toleradas=("financas",))
    assert resultados["financas"] == {"erro": "tabela encolheria"} and chamadas[-1] == "pnad"
    with pytest.raises(RuntimeError, match="tabela encolheria"):  # sem tolerância, o erro sobe como sempre
        carga_economica.carregar_tudo(object())


def test_carga_nao_tolerada_continua_levantando_mesmo_com_financas_tolerada(chamadas, monkeypatch):
    def quebra(engine):
        raise RuntimeError("sem séries")

    monkeypatch.setattr("etl.pipelines.economia_loader.carregar", quebra)
    with pytest.raises(RuntimeError, match="sem séries"):
        carga_economica.carregar_tudo(object(), toleradas=("financas",))


def test_erro_do_banco_numa_carga_tolerada_sai_sem_os_valores_da_linha(chamadas, monkeypatch, caplog):
    import logging

    from sqlalchemy.exc import IntegrityError

    class Diag:
        message_primary = "new row violates check constraint"
        constraint_name = "doacao_campanha_doador_documento_check"

    class Original(Exception):
        diag = Diag()

    def quebra(engine):
        raise IntegrityError("INSERT ...", {}, Original("DETAIL: Failing row contains (Fulano-De-Tal)"))

    monkeypatch.setattr("etl.pipelines.financas_loader.carregar", quebra)
    with caplog.at_level(logging.ERROR, logger="CargaEconomica"):
        resultados = carga_economica.carregar_tudo(object(), toleradas=("financas",))
    assert "Fulano-De-Tal" not in resultados["financas"]["erro"]
    # o log leva a descrição saneada e NENHUMA pilha: a pilha repetiria a mensagem do Postgres, com a linha inteira
    registros = [r for r in caplog.records if r.name == "CargaEconomica" and r.levelno == logging.ERROR]
    assert len(registros) == 1 and not registros[0].exc_info
    assert "Fulano-De-Tal" not in caplog.text and "Failing row" not in caplog.text
    assert "doacao_campanha_doador_documento_check" in caplog.text
    assert resultados["financas"]["erro"] == (
        "IntegrityError: new row violates check constraint (restrição doacao_campanha_doador_documento_check)"
    )
    caplog.clear()
    with pytest.raises(RuntimeError) as erro:  # sem tolerância o erro sobe, também sem os valores
        carga_economica.carregar_tudo(object())
    assert "Fulano-De-Tal" not in str(erro.value) and "Fulano-De-Tal" not in caplog.text


def test_outro_tipo_de_erro_mantem_a_pilha_no_log_para_o_diagnostico(chamadas, monkeypatch, caplog):
    import logging

    def quebra(engine):
        raise RuntimeError("tabela encolheria")

    monkeypatch.setattr("etl.pipelines.financas_loader.carregar", quebra)
    with caplog.at_level(logging.ERROR, logger="CargaEconomica"):
        carga_economica.carregar_tudo(object(), toleradas=("financas",))
    registros = [r for r in caplog.records if r.name == "CargaEconomica" and r.levelno == logging.ERROR]
    assert len(registros) == 1 and registros[0].exc_info is not None  # só o erro do banco perde a pilha


def test_erro_de_dado_do_banco_nao_leva_o_valor_ofendido_nem_a_mensagem_principal():
    from sqlalchemy.exc import DataError

    class Diag:
        message_primary = 'invalid input syntax for type integer: "Fulano-De-Tal"'
        constraint_name = None
        column_name = "quantidade_doadores"

    class Original(Exception):
        pgcode = "22P02"
        diag = Diag()

    texto = carga_economica.descricao_do_erro(DataError("INSERT ...", {}, Original("x")))
    assert "Fulano-De-Tal" not in texto
    assert texto == "DataError: erro de dado (SQLSTATE 22P02) na coluna quantidade_doadores"

    class SemDiag(Exception):
        pgcode = "22003"

    assert carga_economica.descricao_do_erro(DataError("INSERT ...", {}, SemDiag("x"))) == (
        "DataError: erro de dado (SQLSTATE 22003)"
    )
