"""Atualização diária das finanças: extrai com cache, só carrega o `fin` se tudo foi gravado e relata a falha."""

from datetime import date

import pytest

import etl.pipelines.financas_atualizacao as atualizacao


class Chamadas:
    def __init__(self):
        self.run = []
        self.carga = []


@pytest.fixture()
def simulado(monkeypatch):
    chamadas = Chamadas()
    resultado = {"ceap_gravado": True, "emendas_gravado": True}

    def run(**kwargs):
        chamadas.run.append(kwargs)
        return dict(resultado)

    def carregar_tudo(engine, chaves=None, toleradas=()):
        chamadas.carga.append((engine, chaves))
        return {"financas": {"emendas": {"emendas": 3}}}

    monkeypatch.setattr(atualizacao.sync_ceap_emendas, "run", run)
    monkeypatch.setattr(atualizacao, "carregar_tudo", carregar_tudo)
    chamadas.resultado = resultado
    return chamadas


def test_extrai_com_cache_do_ano_inicial_ate_o_ano_corrente_e_so_carrega_as_financas(simulado, tmp_path):
    engine = object()
    resultado = atualizacao.atualizar(engine, hoje=date(2026, 10, 19), cache_dir=tmp_path)
    assert simulado.run == [{"ano_inicio": 2019, "ano_fim": 2026, "cache_dir": tmp_path, "hoje": date(2026, 10, 19)}]
    assert simulado.carga == [(engine, ("financas",))]  # nada além das finanças é recarregado
    assert resultado["carga"] == {"emendas": {"emendas": 3}} and resultado["extracao"]["ceap_gravado"] is True


def test_cache_padrao_fica_em_raw_fora_do_git():
    assert atualizacao.CACHE_DIR.parts[-3:] == ("data", "raw", "ceap_por_ano")


@pytest.mark.parametrize("campo", ["ceap_gravado", "emendas_gravado"])
def test_extracao_que_nao_gravou_nao_carrega_o_fin_e_falha(simulado, campo):
    simulado.resultado[campo] = False
    with pytest.raises(RuntimeError, match="não gravadas"):
        atualizacao.atualizar(object(), hoje=date(2026, 10, 19))
    assert simulado.carga == []  # o fin fica como estava


def test_falha_da_carga_sobe_para_quem_chamou(monkeypatch, simulado):
    def quebra(engine, chaves=None, toleradas=()):
        raise RuntimeError("Finanças (fin): tabela encolheria")

    monkeypatch.setattr(atualizacao, "carregar_tudo", quebra)
    with pytest.raises(RuntimeError, match="encolheria"):
        atualizacao.atualizar(object(), hoje=date(2026, 10, 19))


def test_main_devolve_1_quando_falha_e_0_quando_funciona(monkeypatch):
    monkeypatch.setattr(atualizacao, "atualizar", lambda engine: {"ok": True})
    assert atualizacao.main() == 0

    def quebra(engine):
        raise RuntimeError("Portal fora do ar")

    monkeypatch.setattr(atualizacao, "atualizar", quebra)
    assert atualizacao.main() == 1
