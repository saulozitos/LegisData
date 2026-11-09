"""O comando por fonte e por estágio (`etl.fontes` e as flags `--fonte`/`--estagio` do `run_etl`)."""

import pytest

from etl import run_etl
from etl.carga.orquestra import RECURSOS
from etl.fontes import FONTES, resolver


def test_todo_recurso_da_carga_relacional_pertence_a_uma_fonte():
    cobertos = {r for fonte in FONTES.values() for r in fonte.recursos}
    # o histórico por deputado e o CSV em lote baixam e carregam na mesma etapa da esteira (`carregar=`), não por recurso
    assert cobertos == set(RECURSOS) - {"camara_historico", "camara_lote"}


def test_carregar_so_pede_a_carga_e_extrair_so_pede_a_extracao():
    assert resolver(["votacoes"], "carregar") == (
        ["load_db"],
        ["partidos", "pessoas", "votacoes"],
    )
    assert resolver(["votacoes"], "extrair") == (
        ["camara", "senado", "votacoes", "senadores_basicos", "senadores_filiacoes", "cpf"],
        [],
    )
    chaves, recursos = resolver(["filiacoes"], "tudo")
    assert chaves == ["load_db"] and recursos == ["filiacoes"]


def test_fontes_repetidas_nao_repetem_etapas_e_a_carga_vem_uma_vez():
    chaves, recursos = resolver(["politicos", "mandatos"], "tudo")
    assert chaves.count("camara") == 1 and chaves.count("load_db") == 1
    assert recursos == ["partidos", "pessoas"]  # os mandatos saem dos arquivos das pessoas: um recurso só


def test_etapas_proprias_entram_pela_chave_da_esteira():
    assert resolver(["presenca"], "carregar") == (["load_presenca"], [])
    assert resolver(["camara-bulk"], "tudo")[0] == ["camara_bulk"]


def test_fonte_ou_estagio_desconhecido_e_recusado():
    with pytest.raises(ValueError, match="fonte desconhecida"):
        resolver(["nao-existe"])
    with pytest.raises(ValueError, match="estágio desconhecido"):
        resolver(["politicos"], "limpar")


def test_run_etl_monta_so_as_etapas_da_fonte_pedida():
    args = run_etl.montar_parser().parse_args(["--fonte", "votacoes", "--estagio", "carregar"])
    etapas = run_etl.construir_etapas(args)
    assert [e.chave for e in etapas] == ["load_db"]
    assert etapas[0].grava_banco


def test_run_etl_sem_estagio_extrai_e_carrega_a_fonte():
    args = run_etl.montar_parser().parse_args(["--fonte", "filiacoes"])
    assert [e.chave for e in run_etl.construir_etapas(args)] == ["load_db"]


def test_run_etl_lista_as_fontes_e_sai(capsys):
    assert run_etl.main(["--listar-fontes"]) == 0
    saida = capsys.readouterr().out
    assert all(slug in saida for slug in FONTES)
