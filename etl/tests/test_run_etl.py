"""CLI: etapas isoladas, resumo honesto, carga bloqueada após falha na extração, código de saída."""

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
