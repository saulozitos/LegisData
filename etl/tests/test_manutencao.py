"""Pós-processamento da carga: derivados e `ANALYZE` rodam no Postgres, nunca derrubam a carga e a esteira os chama."""

from sqlalchemy import text

from etl import run_etl
from etl.utils.manutencao import analisar_banco, atualizar_derivados, posprocessar_carga


class EngineQuebrado:
    def connect(self):
        raise RuntimeError("banco fora do ar")

    def begin(self):
        raise RuntimeError("banco fora do ar")


def test_analisar_banco_atualiza_as_estatisticas(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS public.etl_test_analyze (id int)"))
        conn.execute(text("INSERT INTO public.etl_test_analyze SELECT generate_series(1, 50)"))
    try:
        assert analisar_banco(pg_engine) is True
        with pg_engine.connect() as conn:
            ultima = conn.execute(
                text("SELECT last_analyze FROM pg_stat_user_tables WHERE relname = 'etl_test_analyze'")
            ).scalar()
        assert ultima is not None  # o ANALYZE enxergou a tabela recém-carregada
    finally:
        with pg_engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS public.etl_test_analyze"))


def test_atualizar_derivados_refaz_so_quando_mudou(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("UPDATE leg.proposicao SET titulo = titulo"))  # liga o sinalizador
    assert atualizar_derivados(pg_engine) is True
    assert atualizar_derivados(pg_engine) is False  # nada mudou depois
    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT sujo FROM leg.pontuacao_controle")).scalar() is False


def test_falha_do_banco_vira_aviso_e_nao_excecao(caplog):
    with caplog.at_level("WARNING", logger="Manutencao"):
        assert analisar_banco(EngineQuebrado()) is False
        assert atualizar_derivados(EngineQuebrado()) is False
    mensagens = " ".join(r.getMessage() for r in caplog.records)
    assert "ANALYZE não executado" in mensagens and "Derivados do legislativo não atualizados" in mensagens


def test_posprocessar_faz_os_derivados_antes_do_analyze(monkeypatch):
    ordem = []
    monkeypatch.setattr("etl.utils.manutencao.atualizar_derivados", lambda engine: ordem.append("derivados"))
    monkeypatch.setattr("etl.utils.manutencao.analisar_banco", lambda engine: ordem.append("analyze"))
    posprocessar_carga(object())
    assert ordem == ["derivados", "analyze"]


def _executar_com(monkeypatch, etapas):
    chamadas = []
    monkeypatch.setattr(run_etl, "_posprocessar", lambda: chamadas.append("pos"))
    run_etl.executar(etapas, modo_completo=False)
    return chamadas


def test_esteira_posprocessa_uma_vez_quando_alguma_etapa_grava(monkeypatch):
    etapas = [
        run_etl.Etapa("a", "A", lambda: None, grava_banco=True),
        run_etl.Etapa("b", "B", lambda: None, grava_banco=True),
        run_etl.Etapa("c", "C", lambda: None),
    ]
    assert _executar_com(monkeypatch, etapas) == ["pos"]


def test_esteira_sem_etapa_que_grava_nao_posprocessa(monkeypatch):
    assert _executar_com(monkeypatch, [run_etl.Etapa("c", "C", lambda: None)]) == []


def test_etapa_que_grava_e_falha_nao_aciona_o_posprocessamento(monkeypatch):
    def quebra():
        raise RuntimeError("falhou")

    assert _executar_com(monkeypatch, [run_etl.Etapa("a", "A", quebra, grava_banco=True)]) == []


def test_etapas_de_carga_no_banco_estao_marcadas_como_gravadoras():
    """Esquecer a marca numa etapa nova deixaria a primeira leitura pagar o refresh e o planejador sem estatísticas."""
    import inspect
    import re

    fonte = inspect.getsource(run_etl)
    for chave in ("camara_bulk", "camara_historico", "load_db", "load_presenca", "load_economia"):
        bloco = re.search(r'Etapa\(\s*"%s",.*?\n        \),' % chave, fonte, re.S)
        assert bloco and "grava_banco=True" in bloco.group(0), chave
