"""Carga econômica única: ordem, filtro por chaves, isolamento de falhas e dependência da composição."""

import pytest

from etl.pipelines import carga_economica


@pytest.fixture()
def chamadas(monkeypatch):
    registro = []
    for chave, _nome, modulo, _dep in carga_economica.CARGAS:
        alvo = modulo.replace(":", ".") if ":" in modulo else f"{modulo}.carregar"
        monkeypatch.setattr(
            alvo, lambda engine, c=chave, **kw: registro.append(c) or ({"ok": c, "kw": kw} if kw else {"ok": c})
        )
    # fin vazio e nenhuma fonte do timer: semeia tudo
    monkeypatch.setattr(carga_economica, "estado_do_fin", lambda engine: (False, False))
    monkeypatch.setattr(carga_economica, "fontes_do_timer", lambda engine: set())
    return registro


def test_executa_todas_na_ordem_e_devolve_o_resultado_de_cada_uma(chamadas):
    resultados = carga_economica.carregar_tudo(object())
    assert chamadas == ["series", "presidencia", "composicao", "pnad", "financas"]
    assert resultados["composicao"] == {"ok": "composicao"}


def test_chaves_limitam_as_cargas(chamadas):
    carga_economica.carregar_tudo(object(), chaves=("series", "presidencia"))
    assert chamadas == ["series", "presidencia"]


def test_a_composicao_depende_dos_mandatos_e_as_demais_seguem(chamadas, monkeypatch):
    def quebra(engine, **kw):
        raise RuntimeError("sem presidentes")

    monkeypatch.setattr("etl.pipelines.presidencia_loader.carregar", quebra)
    with pytest.raises(RuntimeError) as erro:
        carga_economica.carregar_tudo(object())
    assert "sem presidentes" in str(erro.value) and "Composição do Congresso" in str(erro.value)
    assert chamadas == ["series", "pnad", "financas"]


def test_carga_tolerada_que_falha_nao_levanta_e_devolve_o_erro(chamadas, monkeypatch):
    def quebra(engine, **kw):
        raise RuntimeError("tabela encolheria")

    monkeypatch.setattr("etl.pipelines.financas_loader.carregar", quebra)
    resultados = carga_economica.carregar_tudo(object(), toleradas=("financas",))
    assert resultados["financas"] == {"erro": "tabela encolheria"} and chamadas[-1] == "pnad"
    with pytest.raises(RuntimeError, match="tabela encolheria"):  # sem tolerância, o erro sobe como sempre
        carga_economica.carregar_tudo(object())


def test_carga_nao_tolerada_continua_levantando_mesmo_com_financas_tolerada(chamadas, monkeypatch):
    def quebra(engine, **kw):
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

    def quebra(engine, **kw):
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

    def quebra(engine, **kw):
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


def _financas_recebeu(resultados):
    return resultados["financas"]["kw"]


@pytest.mark.parametrize(
    "tem_ceap, tem_emendas, ceap_timer, emendas_timer, modo",
    [
        (False, False, False, False, "completa"),
        (True, True, False, False, "completa"),  # fin carregado do git, nenhuma fonte assumida pelo timer
        (True, True, True, False, "sem_ceap"),  # só a CEAP é do timer: o git semeia as emendas
        (True, True, False, True, "sem_emendas"),
        (True, True, True, True, "estaticas"),  # tudo assumido: só as estáticas
        (False, True, True, True, "sem_emendas"),  # CEAP vazia (esvaziada) mesmo que o timer a tenha assumido: semeia
        (True, False, True, True, "sem_ceap"),  # emendas vazias: semeia só as emendas, a CEAP do timer fica
    ],
)
def test_sem_chaves_o_modo_das_financas_vem_do_banco_fonte_por_fonte(
    chamadas, monkeypatch, tem_ceap, tem_emendas, ceap_timer, emendas_timer, modo
):
    monkeypatch.setattr(carga_economica, "estado_do_fin", lambda engine: (tem_ceap, tem_emendas))
    assert carga_economica.modo_de_semeadura(tem_ceap, tem_emendas, ceap_timer, emendas_timer) in (
        None if modo == "estaticas" else modo,
    )
    monkeypatch.setattr(
        carga_economica,
        "fontes_do_timer",
        lambda engine: {f for f, v in (("ceap", ceap_timer), ("emendas", emendas_timer)) if v},
    )
    resultados = carga_economica.carregar_tudo(object())
    assert "financas" in chamadas
    assert _financas_recebeu(resultados)["chaves"] == carga_economica.FINANCAS_POR_MODO[modo]


def test_recarregar_ceap_e_emendas_forca_o_modo_completo_mesmo_com_tudo_do_timer(chamadas, monkeypatch):
    monkeypatch.setattr(carga_economica, "estado_do_fin", lambda engine: (True, True))
    monkeypatch.setattr(carga_economica, "fontes_do_timer", lambda engine: {"ceap", "emendas"})
    resultados = carga_economica.carregar_tudo(object(), recarregar_ceap_e_emendas=True)
    assert _financas_recebeu(resultados)["chaves"] is None  # None = todas as fontes


def test_o_gancho_ao_confirmar_chega_a_carga_de_financas(chamadas):
    def gancho(conn, chave, resultado):
        pass

    resultados = carga_economica.carregar_tudo(object(), ao_confirmar=gancho)
    assert _financas_recebeu(resultados)["ao_confirmar"] is gancho


def test_chaves_explicitas_nao_consultam_o_banco(chamadas, monkeypatch):
    def nao_deve_ser_chamada(engine):
        raise AssertionError("consultou o banco")

    monkeypatch.setattr(carga_economica, "estado_do_fin", nao_deve_ser_chamada)
    monkeypatch.setattr(carga_economica, "fontes_do_timer", nao_deve_ser_chamada)
    carga_economica.carregar_tudo(object(), chaves=("financas",), chaves_financas=("remuneracao",))
    assert chamadas == ["financas"]


def test_o_mapa_de_modos_e_as_toleradas_derivam_das_fontes_reais_das_financas():
    from etl.pipelines import financas_loader

    todas = {chave for chave, _ in financas_loader.CARGAS}
    for modo, selecionadas in carga_economica.FINANCAS_POR_MODO.items():
        assert selecionadas is None or set(selecionadas) <= todas, modo
    assert set(carga_economica.FINANCAS_POR_MODO["estaticas"]) == set(financas_loader.CHAVES_ESTATICAS)
    assert set(carga_economica.FINANCAS_POR_MODO["sem_emendas"]) == {"ceap", *financas_loader.CHAVES_ESTATICAS}
    assert set(carga_economica.FINANCAS_POR_MODO["sem_ceap"]) == {"emendas", *financas_loader.CHAVES_ESTATICAS}
    assert set(financas_loader.CHAVES_DO_TIMER) | set(financas_loader.CHAVES_ESTATICAS) == todas
    assert carga_economica.TOLERADAS_NO_DEPLOY == ("financas",)
    assert carga_economica.MODOS_DO_DEPLOY == tuple(carga_economica.FINANCAS_POR_MODO)


@pytest.mark.parametrize("modo", sorted(carga_economica.FINANCAS_POR_MODO))
def test_chaves_do_modo_e_plano(modo):
    esperado = ["series", "presidencia", "composicao", "pnad"] + ([] if modo == "nenhuma" else ["financas"])
    assert carga_economica.chaves_do_modo(modo) == esperado
    assert carga_economica.plano_do_modo(modo) == {
        "chaves": esperado,
        "chaves_financas": carga_economica.FINANCAS_POR_MODO[modo],
    }


def test_chaves_do_modo_com_modo_desconhecido_falha_em_vez_de_assumir_um(chamadas):
    for invalido in ("", "COMPLETA", "tudo", None):
        with pytest.raises(ValueError, match="modo de finanças desconhecido"):
            carga_economica.chaves_do_modo(invalido)


@pytest.mark.parametrize("a", [True, False])
@pytest.mark.parametrize("b", [True, False])
@pytest.mark.parametrize("c", [True, False])
@pytest.mark.parametrize("d", [True, False])
def test_modo_de_semeadura_cobre_as_16_combinacoes_sem_nunca_semear_fonte_assumida(a, b, c, d):
    modo = carga_economica.modo_de_semeadura(a, b, c, d)
    semeia_ceap = not (a and c)
    semeia_emendas = not (b and d)
    esperado = {(True, True): "completa", (True, False): "sem_emendas", (False, True): "sem_ceap", (False, False): None}
    assert modo == esperado[(semeia_ceap, semeia_emendas)]


def test_carregar_tudo_chama_a_carga_de_financas_so_com_as_fontes_do_plano_e_a_falha_tolerada_vira_erro(
    chamadas, monkeypatch
):
    def quebra(engine, **kw):
        raise RuntimeError("tabela encolheria")

    monkeypatch.setattr("etl.pipelines.financas_loader.carregar", quebra)
    plano = carga_economica.plano_do_modo("estaticas")
    resultados = carga_economica.carregar_tudo(object(), toleradas=("financas",), **plano)
    assert resultados["financas"] == {"erro": "tabela encolheria"}
    assert carga_economica.falhas_toleradas(resultados) == ["financas"]


@pytest.mark.parametrize("faltando", carga_economica.TABELAS_DA_CEAP + carga_economica.TABELAS_DAS_EMENDAS)
def test_estado_do_fin_olha_cada_fonte_com_todas_as_tabelas_dela(pg_engine, faltando):
    """Popula tudo numa transação revertida e esvazia uma tabela por vez: a fonte dela deixa de "ter dado"."""
    from sqlalchemy import text

    with pg_engine.connect() as conexao:
        transacao = conexao.begin()
        try:
            for tabela in carga_economica.TABELAS_DA_CEAP + carga_economica.TABELAS_DAS_EMENDAS:
                conexao.execute(text(f"TRUNCATE fin.{tabela} CASCADE"))
            conexao.execute(text("TRUNCATE core.pessoa CASCADE"))
            assert _estado(conexao) == (False, False)
            _popular(conexao)
            assert _estado(conexao) == (True, True)
            conexao.execute(text(f"DELETE FROM fin.{faltando}"))
            esperado = (
                faltando not in carga_economica.TABELAS_DA_CEAP,
                faltando not in carga_economica.TABELAS_DAS_EMENDAS,
            )
            assert _estado(conexao) == esperado
            assert conexao.execute(text(f"select {carga_economica.SQL_FIN_TEM_ALGUM_DADO}")).scalar() is True
        finally:
            transacao.rollback()


def _estado(conexao):
    class Motor:
        def connect(self):
            class Ctx:
                def __enter__(s):
                    return conexao

                def __exit__(s, *a):
                    return False

            return Ctx()

    return carga_economica.estado_do_fin(Motor())


def test_estado_do_fin_sem_o_schema_fin_e_falso_sem_consultar_as_tabelas():
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

    assert carga_economica.estado_do_fin(Motor()) == (False, False)
    assert len(consultas) == 1 and "to_regclass" in consultas[0]


def test_carga_de_modulo_e_funcao_resolve_a_funcao_nomeada_e_o_padrao_carregar():
    assert carga_economica._carga_de("etl.pipelines.financas_loader:registrar_carga_do_git").__name__ == (
        "registrar_carga_do_git"
    )
    assert carga_economica._carga_de("etl.pipelines.pnad_loader").__name__ == "carregar"
    with pytest.raises(AttributeError):
        carga_economica._carga_de("etl.pipelines.financas_loader:nao_existe")


def test_falhas_toleradas_so_olha_as_cargas_toleradas_e_o_formato_de_erro():
    f = carga_economica.falhas_toleradas
    assert f({"financas": {"erro": "x"}, "series": {"erro": "y"}, "pnad": 3}) == ["financas"]
    assert f({"financas": "texto"}) == [] and f({}) == []


def _popular(conexao):
    from sqlalchemy import text

    fonte = conexao.execute(text("select id from etl.fonte order by id limit 1")).scalar()
    assert fonte is not None, "o banco de teste precisa do catálogo etl.fonte (migrações)"
    pessoa = conexao.execute(text("insert into core.pessoa (nome_exibicao) values ('TESTE') returning id")).scalar()
    conexao.execute(
        text(
            "insert into fin.despesa_cota (pessoa_id, ano, tipo_despesa, valor_liquido, fonte_id) "
            "values (:p, 2023, 'X', 1, :f)"
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
