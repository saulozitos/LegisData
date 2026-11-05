"""O relatório da rodada (`etl.utils.relatorio`) e o registro da esteira inteira (`run_etl.executar_registrando`)."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from etl import run_etl
from etl.utils import execucao, relatorio

MARCA = {"teste": "relatorio"}
FILTRO_MARCA = 'parametros @> \'{"teste": "relatorio"}\''


@pytest.fixture(autouse=True)
def limpa(pg_engine):
    yield
    with pg_engine.begin() as conn:
        ids = f"SELECT id FROM etl.execucao WHERE {FILTRO_MARCA}"
        conn.execute(text(f"DELETE FROM etl.rejeito WHERE execucao_id IN ({ids})"))
        conn.execute(text(f"DELETE FROM etl.verificacao WHERE execucao_id IN ({ids})"))
        conn.execute(text(f"DELETE FROM etl.execucao WHERE {FILTRO_MARCA}"))


def test_relatorio_lista_fonte_contagens_rejeitos_e_verificacoes_reprovadas(pg_engine):
    from etl.utils.verificacoes import sem_duplicatas

    inicio = datetime.now(timezone.utc) - timedelta(seconds=5)
    contagem = execucao.Contagem(lidas=10, gravadas=7)
    contagem.rejeitar("NAO_CADASTRADO", 3)
    with execucao.registrar_execucao(pg_engine, "TSE", "CARREGAR", {**MARCA, "recurso": "filiacoes"}) as e:
        e.aplicar(contagem)
        e.verificar(sem_duplicatas("ids_unicos", [1, 1]))
    with execucao.registrar_execucao(pg_engine, "CAMARA_API", "CARREGAR", {**MARCA, "recurso": "politicos"}) as ok:
        ok.lidas, ok.gravadas, ok.rejeitadas = 4, 4, 0

    texto = relatorio.montar_relatorio(pg_engine, inicio)
    assert "TSE/CARREGAR [filiacoes]" in texto and "COM_ALERTA" in texto
    assert "lidas 10 · gravadas 7 · rejeitadas 3" in texto
    assert "rejeitos: filiacoes / NAO_CADASTRADO: 3" in texto
    assert "verificação que não passou: ids_unicos" in texto
    assert "CAMARA_API/CARREGAR [politicos]" in texto and "lidas 4 · gravadas 4 · rejeitadas 0" in texto


def test_relatorio_mostra_desconhecido_como_nd_e_nao_como_zero(pg_engine):
    inicio = datetime.now(timezone.utc) - timedelta(seconds=5)
    with execucao.registrar_execucao(pg_engine, "TSE", "CARREGAR", {**MARCA, "recurso": "sem_contagem"}):
        pass
    assert "lidas n/d · gravadas n/d · rejeitadas n/d" in relatorio.montar_relatorio(pg_engine, inicio)


def test_relatorio_sem_execucoes_diz_isso(pg_engine):
    futuro = datetime.now(timezone.utc) + timedelta(days=1)
    assert "nenhuma execução" in relatorio.montar_relatorio(pg_engine, futuro)


def test_esteira_registra_a_rodada_inteira_com_as_etapas_que_falharam(pg_engine, monkeypatch):
    monkeypatch.setattr(run_etl, "_engine_ou_none", lambda: pg_engine)

    def falha():
        raise RuntimeError("falhou")

    etapas = [
        run_etl.Etapa("a", "Etapa A", lambda: None, grava_banco=True),
        run_etl.Etapa("b", "Etapa B", falha, grava_banco=True),
    ]
    monkeypatch.setattr(run_etl, "_posprocessar", lambda: "em_dia")
    # a rodada leva a marca do teste nos parâmetros para a limpeza achar a linha
    original = execucao.registrar_execucao
    monkeypatch.setattr(
        execucao,
        "registrar_execucao",
        lambda engine, fonte, estagio, parametros=None, **k: original(
            engine, fonte, estagio, {**MARCA, **(parametros or {})}, **k
        ),
    )
    resultados = run_etl.executar_registrando(etapas, modo_completo=False)
    assert resultados["a"].startswith("OK") and resultados["b"].startswith("FALHOU")
    with pg_engine.connect() as conn:
        linha = conn.execute(
            text(
                "SELECT status, linhas_lidas, linhas_gravadas, linhas_rejeitadas FROM etl.execucao "
                f"WHERE estagio = 'TUDO' AND {FILTRO_MARCA} ORDER BY id DESC LIMIT 1"
            )
        ).one()
    assert tuple(linha) == ("COM_ALERTA", 2, 1, 1)


def test_esteira_so_de_extracao_nao_registra_nada_no_banco(monkeypatch):
    chamadas = []
    monkeypatch.setattr(run_etl, "_engine_ou_none", lambda: chamadas.append("engine"))
    resultados = run_etl.executar_registrando([run_etl.Etapa("x", "X", lambda: None)], modo_completo=False)
    assert resultados["x"].startswith("OK") and chamadas == []  # sem etapa que grava, nem se abre o banco
