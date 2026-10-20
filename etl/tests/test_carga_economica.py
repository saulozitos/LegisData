"""Carga econômica única: ordem, filtro por chaves, isolamento de falhas e dependência da composição."""

import pytest

from etl.pipelines import carga_economica


@pytest.fixture()
def chamadas(monkeypatch):
    registro = []
    for chave, _nome, modulo, _dep in carga_economica.CARGAS:
        alvo = modulo.replace(":", ".") if ":" in modulo else f"{modulo}.carregar"
        monkeypatch.setattr(alvo, lambda engine, c=chave: registro.append(c) or {"ok": c})
    monkeypatch.setattr(carga_economica, "fin_tem_ceap_e_emendas", lambda engine: False)  # fin vazio: semeia tudo
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


def test_sem_chaves_e_com_o_fin_carregado_so_rodam_as_cargas_estaticas(chamadas, monkeypatch):
    monkeypatch.setattr(carga_economica, "fin_tem_ceap_e_emendas", lambda engine: True)
    carga_economica.carregar_tudo(object())
    assert "financas" not in chamadas and chamadas[-1] == "financas_estaticas"  # o arquivo do git não desfaz o timer


def test_recarregar_ceap_e_emendas_forca_a_carga_completa_mesmo_com_o_fin_carregado(chamadas, monkeypatch):
    monkeypatch.setattr(carga_economica, "fin_tem_ceap_e_emendas", lambda engine: True)
    carga_economica.carregar_tudo(object(), recarregar_ceap_e_emendas=True)
    assert chamadas[-1] == "financas" and "financas_estaticas" not in chamadas


def test_chaves_explicitas_nao_consultam_o_banco(chamadas, monkeypatch):
    def nao_deve_ser_chamada(engine):
        raise AssertionError("consultou o banco")

    monkeypatch.setattr(carga_economica, "fin_tem_ceap_e_emendas", nao_deve_ser_chamada)
    carga_economica.carregar_tudo(object(), chaves=("financas_estaticas",))
    assert chamadas == ["financas_estaticas"]


def test_o_mapa_de_modos_cobre_as_cargas_de_financas_e_as_toleradas():
    chaves = {chave for chave, *_ in carga_economica.CARGAS}
    assert {c for c in carga_economica.FINANCAS_POR_MODO.values() if c} <= chaves
    assert set(carga_economica.TOLERADAS_NO_DEPLOY) == {
        "financas",
        "financas_estaticas",
        "financas_sem_emendas",
        "financas_sem_ceap",
    }
    assert carga_economica.MODOS_DO_DEPLOY == tuple(carga_economica.FINANCAS_POR_MODO)


@pytest.mark.parametrize(
    "modo, esperado",
    [
        ("completa", ["series", "presidencia", "composicao", "pnad", "financas"]),
        ("estaticas", ["series", "presidencia", "composicao", "pnad", "financas_estaticas"]),
        ("sem_emendas", ["series", "presidencia", "composicao", "pnad", "financas_sem_emendas"]),
        ("sem_ceap", ["series", "presidencia", "composicao", "pnad", "financas_sem_ceap"]),
        ("nenhuma", ["series", "presidencia", "composicao", "pnad"]),
    ],
)
def test_chaves_do_modo_por_modo_de_financas(modo, esperado):
    assert carga_economica.chaves_do_modo(modo) == esperado


def test_chaves_do_modo_com_modo_desconhecido_falha_em_vez_de_assumir_um(chamadas):
    for invalido in ("", "COMPLETA", "tudo", None):
        with pytest.raises(ValueError, match="modo de finanças desconhecido"):
            carga_economica.chaves_do_modo(invalido)


def test_o_modo_de_deploy_executa_exatamente_essas_cargas(chamadas):
    carga_economica.carregar_tudo(object(), chaves=carga_economica.chaves_do_modo("estaticas"))
    assert chamadas == ["series", "presidencia", "composicao", "pnad", "financas_estaticas"]
    chamadas.clear()
    carga_economica.carregar_tudo(object(), chaves=carga_economica.chaves_do_modo("nenhuma"))
    assert "financas" not in chamadas and "financas_estaticas" not in chamadas


def test_carga_estatica_tolerada_que_falha_nao_derruba_o_deploy(chamadas, monkeypatch):
    def quebra(engine):
        raise RuntimeError("remuneracao: arquivo corrompido")

    monkeypatch.setattr("etl.pipelines.financas_loader.carregar_estaticas", quebra)
    resultados = carga_economica.carregar_tudo(
        object(), chaves=carga_economica.chaves_do_modo("estaticas"), toleradas=("financas", "financas_estaticas")
    )
    assert "corrompido" in resultados["financas_estaticas"]["erro"]


@pytest.mark.parametrize("faltando", carga_economica.TABELAS_DA_CEAP_E_EMENDAS)
def test_fin_tem_ceap_e_emendas_exige_as_quatro_tabelas_com_dados(pg_engine, faltando):
    """Popula tudo numa transação revertida e esvazia uma tabela por vez: cada uma é exigida (`and`, não `or`)."""
    from sqlalchemy import text

    with pg_engine.connect() as conexao:
        transacao = conexao.begin()
        try:
            for tabela in carga_economica.TABELAS_DA_CEAP_E_EMENDAS:
                conexao.execute(text(f"TRUNCATE fin.{tabela} CASCADE"))
            conexao.execute(text("TRUNCATE core.pessoa CASCADE"))
            assert _consultar(conexao) is False  # tudo vazio
            _popular(conexao)
            assert _consultar(conexao) is True
            conexao.execute(text(f"DELETE FROM fin.{faltando}"))
            assert _consultar(conexao) is False
            assert conexao.execute(text(f"select {carga_economica.sql_fin_tem_dados('or')}")).scalar() is True
        finally:
            transacao.rollback()


def test_fin_tem_ceap_e_emendas_sem_o_schema_fin_e_falso_sem_consultar_as_tabelas():
    consultas = []

    class Conexao:
        def execute(self, consulta):
            consultas.append(str(consulta))

            class Resultado:
                def scalar(self):
                    return False  # to_regclass('fin.emenda') is not null => false

            return Resultado()

    class Motor:
        def connect(self):
            class Ctx:
                def __enter__(s):
                    return Conexao()

                def __exit__(s, *a):
                    return False

            return Ctx()

    assert carga_economica.fin_tem_ceap_e_emendas(Motor()) is False
    assert len(consultas) == 1 and "to_regclass" in consultas[0]


def test_carga_de_modulo_e_funcao_resolve_a_funcao_nomeada_e_o_padrao_carregar():
    assert (
        carga_economica._carga_de("etl.pipelines.financas_loader:carregar_estaticas").__name__ == "carregar_estaticas"
    )
    assert carga_economica._carga_de("etl.pipelines.pnad_loader").__name__ == "carregar"
    with pytest.raises(AttributeError):
        carga_economica._carga_de("etl.pipelines.financas_loader:nao_existe")


def test_falhas_toleradas_so_olha_as_cargas_toleradas_e_o_formato_de_erro():
    f = carga_economica.falhas_toleradas
    assert f({"financas_sem_ceap": {"erro": "x"}, "series": {"erro": "y"}, "financas": {"ceap": {}}, "pnad": 3}) == [
        "financas_sem_ceap"
    ]
    assert f({"financas": "texto"}) == [] and f({}) == []


def _consultar(conexao):
    class Motor:
        def connect(self):
            class Ctx:
                def __enter__(s):
                    return conexao

                def __exit__(s, *a):
                    return False

            return Ctx()

    return carga_economica.fin_tem_ceap_e_emendas(Motor())


def _popular(conexao):
    from sqlalchemy import text

    fonte = conexao.execute(text("select id from etl.fonte order by id limit 1")).scalar()
    assert fonte is not None, "o banco de teste precisa do catálogo etl.fonte (migrações)"
    pessoa = conexao.execute(text("insert into core.pessoa (nome_exibicao) values ('TESTE') returning id")).scalar()
    conexao.execute(
        text(
            "insert into fin.despesa_cota (pessoa_id, ano, tipo_despesa, valor_liquido, fonte_id) values (:p, 2023, 'X', 1, :f)"
        ),
        {"p": pessoa, "f": fonte},
    )
    conexao.execute(
        text(
            "insert into fin.despesa_cota_fornecedor (pessoa_id, nome, valor_total, fonte_id) values (:p, 'F', 1, :f)"
        ),
        {"p": pessoa, "f": fonte},
    )
    conexao.execute(
        text("insert into fin.despesa_cota_resumo (pessoa_id, total_notas, fonte_id) values (:p, 1, :f)"),
        {"p": pessoa, "f": fonte},
    )
    conexao.execute(text(_EMENDA_SQL), {"p": pessoa, "f": fonte})


_EMENDA_SQL = (
    "insert into fin.emenda (pessoa_id, autor_texto, tipo_autor, autor_situacao, ano, tipo_emenda, valor_empenhado, "
    "valor_pago, localidade_destino, fonte_id) "
    "values (:p, 'TESTE', 'INDIVIDUAL', 'IDENTIFICADO', 2023, 'Individual', 1, 1, 'X', :f)"
)
