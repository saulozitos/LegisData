"""CLI: etapas isoladas, resumo honesto, carga bloqueada após falha na extração, código de saída."""

import pytest

import etl.run_etl as cli
from etl.run_etl import Etapa, construir_etapas, executar, imprimir_resumo, montar_parser


def args(*argv):
    return montar_parser().parse_args(list(argv))


def test_modo_completo_inclui_ceap_e_carga_mas_nao_itens_com_autorizacao_explicita():
    chaves = [e.chave for e in construir_etapas(args())]
    assert "ceap" in chaves and "load_db" in chaves and "tse" in chaves and "patrimonio" in chaves
    assert "processos" not in chaves and "sinteticos" not in chaves
    # presença/remuneração oficiais: extração antes da carga e carga depois do load_db
    assert chaves.index("presenca") < chaves.index("load_db") < chaves.index("load_presenca")
    assert "remuneracao" in chaves


def test_modo_completo_tem_a_carga_economica_depois_do_load_db_e_nao_tem_mais_renda():
    chaves = [e.chave for e in construir_etapas(args())]
    assert "load_economia" in chaves and chaves.index("load_db") < chaves.index("load_economia")
    assert "renda" not in chaves
    with pytest.raises(SystemExit):
        montar_parser().parse_args(["--renda"])  # a etapa foi removida do CLI


def test_processos_so_com_autorizacao():
    assert "processos" in [e.chave for e in construir_etapas(args("--allow-unverified-legal"))]
    # a presença/remuneração SINTÉTICAS deixaram de existir: --allow-synthetic não cria etapa de dados sorteados
    assert "sinteticos" not in [e.chave for e in construir_etapas(args("--allow-synthetic"))]


def test_selecao_de_etapas():
    assert [e.chave for e in construir_etapas(args("--camara", "--senado"))] == ["camara", "senado"]


def etapa(chave, falha=False, carga=False, chamadas=None):
    def executar_():
        if chamadas is not None:
            chamadas.append(chave)
        if falha:
            raise RuntimeError("quebrou")

    return Etapa(chave, chave.upper(), executar_, depende_de_extracao=carga)


def test_falha_isolada_nao_interrompe_demais_etapas_e_bloqueia_a_carga_no_modo_completo(capsys):
    chamadas = []
    res = executar(
        [
            etapa("a", falha=True, chamadas=chamadas),
            etapa("b", chamadas=chamadas),
            etapa("load", carga=True, chamadas=chamadas),
        ],
        modo_completo=True,
    )
    assert chamadas == ["a", "b"]  # a carga não rodou
    assert res["a"].startswith("FALHOU") and res["b"].startswith("OK") and res["load"].startswith("PULADA")
    assert imprimir_resumo(res) is False
    assert "COM FALHAS" in capsys.readouterr().out


def test_carga_explicita_roda_mesmo_com_falha_anterior():
    chamadas = []
    res = executar(
        [etapa("a", falha=True, chamadas=chamadas), etapa("load", carga=True, chamadas=chamadas)], modo_completo=False
    )
    assert chamadas == ["a", "load"] and res["load"].startswith("OK")


def test_resumo_de_sucesso(capsys):
    assert imprimir_resumo({"a": "OK (0.1s)"}) is True
    assert "concluída com sucesso" in capsys.readouterr().out


def test_main_retorna_codigo_1_quando_alguma_etapa_falha(monkeypatch):
    monkeypatch.setattr(cli, "ensure_data_dirs", lambda: None)
    monkeypatch.setattr(cli, "construir_etapas", lambda _args: [etapa("x", falha=True)])
    assert cli.main(["--camara"]) == 1


def test_main_retorna_0_quando_tudo_ok(monkeypatch):
    monkeypatch.setattr(cli, "ensure_data_dirs", lambda: None)
    monkeypatch.setattr(cli, "construir_etapas", lambda _args: [etapa("x")])
    assert cli.main(["--camara"]) == 0


def test_carga_economica_isola_cada_loader_e_relata_as_falhas_no_fim(monkeypatch):
    monkeypatch.setattr("etl.pipelines.carga_economica.estado_do_fin", lambda engine: (False, False))
    chamadas = []

    def ok(nome):
        return lambda engine, **kw: chamadas.append(nome) or {"ok": nome}

    def quebra(engine):
        chamadas.append("composicao")
        raise RuntimeError("Mandatos sem identificador no banco: y-1999")

    monkeypatch.setattr("etl.pipelines.economia_loader.carregar", ok("series"))
    monkeypatch.setattr("etl.pipelines.presidencia_loader.carregar", ok("presidencia"))
    monkeypatch.setattr("etl.pipelines.composicao_loader.carregar", quebra)
    monkeypatch.setattr("etl.pipelines.pnad_loader.carregar", ok("pnad"))
    monkeypatch.setattr("etl.pipelines.financas_loader.carregar", ok("financas"))
    with pytest.raises(RuntimeError, match="Composição do Congresso.*y-1999"):
        cli._load_economia()
    # a PNAD e as finanças rodaram apesar da falha da composição
    assert chamadas == ["series", "presidencia", "composicao", "pnad", "financas"]


def test_carga_economica_sem_falha_nao_levanta_e_com_duas_falhas_relata_as_duas(monkeypatch):
    monkeypatch.setattr("etl.pipelines.carga_economica.estado_do_fin", lambda engine: (False, False))

    def quebra(mensagem):
        def _(engine, **kw):
            raise RuntimeError(mensagem)

        return _

    for modulo in ("economia_loader", "presidencia_loader", "composicao_loader", "pnad_loader", "financas_loader"):
        monkeypatch.setattr(f"etl.pipelines.{modulo}.carregar", lambda engine, **kw: {})
    cli._load_economia()  # nenhuma falha: sem exceção

    monkeypatch.setattr("etl.pipelines.economia_loader.carregar", quebra("BCB sem arquivo"))
    monkeypatch.setattr("etl.pipelines.pnad_loader.carregar", quebra("PNAD ausente"))
    with pytest.raises(RuntimeError) as erro:
        cli._load_economia()
    assert "BCB sem arquivo" in str(erro.value) and "PNAD ausente" in str(erro.value)


def test_composicao_nao_roda_se_os_mandatos_presidenciais_falharam(monkeypatch):
    monkeypatch.setattr("etl.pipelines.carga_economica.estado_do_fin", lambda engine: (False, False))
    chamadas = []

    def quebra(engine):
        raise RuntimeError("sem arquivo de presidentes")

    monkeypatch.setattr("etl.pipelines.economia_loader.carregar", lambda engine: chamadas.append("series") or {})
    monkeypatch.setattr("etl.pipelines.presidencia_loader.carregar", quebra)
    monkeypatch.setattr("etl.pipelines.composicao_loader.carregar", lambda engine: chamadas.append("composicao") or {})
    monkeypatch.setattr("etl.pipelines.pnad_loader.carregar", lambda engine: chamadas.append("pnad") or {})
    monkeypatch.setattr("etl.pipelines.financas_loader.carregar", lambda engine, **kw: {})
    with pytest.raises(RuntimeError) as erro:
        cli._load_economia()
    assert "sem arquivo de presidentes" in str(erro.value) and "não executada" in str(erro.value)
    assert chamadas == ["series", "pnad"]  # a composição foi pulada, sem erro em cascata mascarando a causa


def test_o_ano_inicial_do_ceap_no_cli_e_o_mesmo_da_atualizacao_diaria():
    from etl.pipelines.sync_ceap_emendas import ANO_INICIAL_ARQUIVO

    assert args().ceap_ano_inicio == ANO_INICIAL_ARQUIVO == 2019


def test_etapa_ceap_falha_quando_alguma_fonte_nao_foi_gravada_e_passa_quando_foram_as_duas(monkeypatch):
    import etl.pipelines.sync_ceap_emendas as sync

    monkeypatch.setattr(cli, "_anos_ja_carregados_ou_none", lambda: None)
    monkeypatch.setattr(sync, "run", lambda ano_inicio, **kw: {"ceap_gravado": True, "emendas_gravado": True})
    assert cli._ceap_emendas(2019) == {"ceap_gravado": True, "emendas_gravado": True}
    for falha in ("ceap_gravado", "emendas_gravado"):
        monkeypatch.setattr(
            sync,
            "run",
            lambda ano_inicio, falha=falha, **kw: {"ceap_gravado": True, "emendas_gravado": True, falha: False},
        )
        with pytest.raises(RuntimeError, match="não gravadas"):
            cli._ceap_emendas(2019)


def test_recarregar_ceap_emendas_chega_ate_a_carga(monkeypatch):
    recebido = {}
    monkeypatch.setattr("etl.pipelines.carga_economica.carregar_tudo", lambda engine, **kw: recebido.update(kw) or {})
    cli._load_economia(recarregar_ceap_e_emendas=True)
    assert recebido["recarregar_ceap_e_emendas"] is True and callable(recebido["ao_confirmar"])
    assert (
        cli.montar_parser().parse_args(["--load-economia", "--recarregar-ceap-emendas"]).recarregar_ceap_emendas is True
    )


@pytest.mark.parametrize(
    "argumentos, extracao_ok, esperado",
    [
        ([], True, True),  # ETL completo: a CEAP extraída agora entra na carga
        (["--ceap", "--load-economia"], True, True),
        (["--ceap", "--load-economia"], False, False),  # extração falhou: o arquivo é o retrato antigo, não recarrega
        (["--load-economia"], True, False),  # só a carga: o fin pode estar à frente dos arquivos do git
        (["--load-economia", "--recarregar-ceap-emendas"], True, True),
        (["--ceap", "--load-economia", "--recarregar-ceap-emendas"], False, True),  # o operador pediu explicitamente
    ],
)
def test_a_carga_recarrega_ceap_e_emendas_so_quando_a_extracao_desta_execucao_deu_certo_ou_quando_pedido(
    monkeypatch, argumentos, extracao_ok, esperado
):
    recebido = []

    def extracao(ano_inicio, usar_cache=True):
        if not extracao_ok:
            raise RuntimeError("CEAP/emendas não gravadas")
        return {}

    monkeypatch.setattr(cli, "_ceap_emendas", extracao)
    monkeypatch.setattr(
        cli,
        "_load_economia",
        lambda recarregar=False, extracao_fresca=False: recebido.append((recarregar, extracao_fresca)),
    )
    etapas = {e.chave: e for e in cli.construir_etapas(cli.montar_parser().parse_args(argumentos))}
    if "ceap" in etapas:
        try:
            etapas["ceap"].executar()
        except RuntimeError:
            pass
    etapas["load_economia"].executar()
    fresca = "ceap" in etapas and extracao_ok  # só a extração desta execução, e só se deu certo, vale como fresca
    assert recebido == [(esperado, fresca)]


def test_a_extracao_manual_usa_o_cache_por_ano_e_os_anos_ja_carregados(monkeypatch):
    chamadas = {}
    monkeypatch.setattr(
        "etl.pipelines.sync_ceap_emendas.run",
        lambda **kw: chamadas.update(kw) or {"ceap_gravado": True, "emendas_gravado": True},
    )
    monkeypatch.setattr(cli, "_anos_ja_carregados_ou_none", lambda: {"camara": {2026}, "senado": set()})
    cli._ceap_emendas(2019)
    assert chamadas["cache_dir"].name == "ceap_por_ano" and chamadas["anos_publicados"] == {
        "camara": {2026},
        "senado": set(),
    }


def test_sem_banco_a_extracao_manual_segue_so_com_o_arquivo(monkeypatch):
    monkeypatch.setattr("app.core.database.engine", object())  # um motor que não responde a nada

    def quebra(engine):
        raise RuntimeError("sem banco")

    monkeypatch.setattr("etl.pipelines.financas_atualizacao.anos_ja_carregados", quebra)
    assert cli._anos_ja_carregados_ou_none() is None


def test_o_gancho_da_carga_diz_de_onde_veio_o_dado(monkeypatch):
    """Extração fresca desta execução => `fresca=true` (origem run_etl); recarga a pedido do git => revoga a posse."""
    recebido = {}
    monkeypatch.setattr("etl.pipelines.carga_economica.carregar_tudo", lambda engine, **kw: recebido.update(kw) or {})
    cli._load_economia(recarregar_ceap_e_emendas=True, extracao_fresca=True)
    fresca = recebido["ao_confirmar"]
    assert fresca.func.__name__ == "registrar_carga_fresca" and fresca.keywords == {"origem": "run_etl"}
    cli._load_economia(recarregar_ceap_e_emendas=True)
    assert recebido["ao_confirmar"].__name__ == "registrar_carga_do_git"


def test_no_cache_na_extracao_manual_baixa_de_novo_sem_perder_o_cache(monkeypatch):
    chamadas = {}
    monkeypatch.setattr(
        "etl.pipelines.sync_ceap_emendas.run",
        lambda **kw: chamadas.update(kw) or {"ceap_gravado": True, "emendas_gravado": True},
    )
    monkeypatch.setattr(cli, "_anos_ja_carregados_ou_none", lambda: None)
    cli._ceap_emendas(2019, usar_cache=False)
    # baixa tudo de novo, mas mantém a escrita do cache e a reserva do cache vencido
    assert chamadas["ignorar_cache"] is True and chamadas["cache_dir"] is not None
    cli._ceap_emendas(2019)
    assert chamadas["ignorar_cache"] is False
