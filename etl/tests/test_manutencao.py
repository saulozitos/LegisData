"""Pós-processamento da carga: ANALYZE e derivados rodam no Postgres, nunca derrubam a carga e a esteira os chama."""

from sqlalchemy import text

from etl import run_etl
from etl.utils import manutencao
from etl.utils.manutencao import analisar_banco, posprocessar_carga, refazer_derivados_apos_carga


def _constante_da_migracao_0037(nome):
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from app.core.migrations import BACKEND_DIR

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return getattr(ScriptDirectory.from_config(config).get_revision("0037").module, nome)


class EngineQuebrado:
    def connect(self):
        raise RuntimeError("banco fora do ar")

    def begin(self):
        raise RuntimeError("banco fora do ar")


def test_analisar_banco_atualiza_as_estatisticas(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS public.etl_test_analyze"))  # sobra de uma execução abortada
        conn.execute(text("CREATE TABLE public.etl_test_analyze (id int)"))
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


def _contagem_de_analyze(pg_engine):
    with pg_engine.connect() as conn:
        return dict(
            conn.execute(
                text(
                    "SELECT relname, analyze_count FROM pg_stat_user_tables "
                    "WHERE relname IN ('mv_autoria_pontuada_unica', 'mv_coautoria_par', 'autoria')"
                )
            ).all()
        )


def test_analisar_so_os_derivados(pg_engine):
    """O `ANALYZE` tem de alcançar as duas visões materializadas (um `return True` sem executar nada não passa)."""
    import time

    antes = _contagem_de_analyze(pg_engine)
    visoes = ("mv_autoria_pontuada_unica", "mv_coautoria_par")
    assert set(antes) >= set(visoes) and "autoria" in antes
    assert analisar_banco(pg_engine, apenas_derivados=True) is True
    for _ in range(100):  # as estatísticas são gravadas de forma assíncrona: espera com limite, sem dormir às cegas
        depois = _contagem_de_analyze(pg_engine)
        if all(depois[nome] > antes[nome] for nome in visoes):
            break
        time.sleep(0.1)
    assert all(depois[nome] > antes[nome] for nome in visoes), f"ANALYZE não alcançou as visões: {antes} -> {depois}"
    assert depois["autoria"] == antes["autoria"]  # só os derivados: o ANALYZE do banco inteiro é o outro modo


def test_atualizar_derivados_distingue_refeito_em_dia_e_ocupado(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("UPDATE leg.proposicao SET titulo = titulo"))  # liga o sinalizador
    assert refazer_derivados_apos_carga(pg_engine) == "refeito"
    assert refazer_derivados_apos_carga(pg_engine) == "em_dia"  # nada mudou depois


def test_etl_chama_a_porta_bloqueante_com_a_espera_longa():
    """O ETL espera a vez em vez de desistir em meio segundo como a leitura: modo bloqueante e `ESPERA_DO_ETL`."""
    from contextlib import nullcontext
    from unittest.mock import MagicMock

    conexao = MagicMock()
    conexao.execute.return_value.scalar.return_value = "em_dia"
    motor = MagicMock()
    motor.begin.return_value = nullcontext(conexao)
    refazer_derivados_apos_carga(motor)
    comando, parametros = conexao.execute.call_args.args
    assert "leg.atualizar_derivados(true," in str(comando) and parametros == {"espera": manutencao.ESPERA_DO_ETL}
    assert manutencao.ESPERA_DO_ETL not in ("0", "500ms")  # espera de verdade, bem mais que a da leitura


def test_etl_espera_a_vez_de_outra_atualizacao_em_curso(pg_engine):
    """Com o bloqueio na mão de outra transação por um instante, o ETL aguarda e refaz (a leitura teria desistido)."""
    import threading
    import time

    with pg_engine.begin() as conn:
        conn.execute(text("UPDATE leg.proposicao SET titulo = titulo"))  # liga o sinalizador
    chave = _constante_da_migracao_0037("BLOQUEIO_DA_ATUALIZACAO")
    outra = pg_engine.connect()
    transacao = outra.begin()
    resultado = []
    espera = threading.Thread(target=lambda: resultado.append(refazer_derivados_apos_carga(pg_engine)))
    iniciada = False
    try:
        outra.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": chave})
        espera.start()
        iniciada = True
        with pg_engine.connect() as conn:
            for _ in range(100):  # sem dormir às cegas: espera a chamada do ETL aparecer na fila do bloqueio
                na_fila = conn.execute(
                    text(
                        "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted AND objid = :k "
                        "AND database = (SELECT oid FROM pg_database WHERE datname = current_database())"
                    ),
                    {"k": chave},
                ).scalar()
                if na_fila:
                    break
                time.sleep(0.1)
            assert na_fila, "o ETL não ficou esperando o bloqueio"
        assert not resultado
    finally:
        transacao.rollback()
        outra.close()
        if iniciada:
            espera.join(timeout=60)
    assert resultado == ["refeito"]


def test_atualizar_derivados_avisa_quando_nao_conseguiu_a_vez(caplog):
    class Ocupado:
        def begin(self):
            from contextlib import nullcontext
            from unittest.mock import MagicMock

            conexao = MagicMock()
            conexao.execute.return_value.scalar.return_value = "ocupado"
            return nullcontext(conexao)

    with caplog.at_level("WARNING", logger="Manutencao"):
        assert refazer_derivados_apos_carga(Ocupado()) == "ocupado"
    assert any("NÃO atualizados" in r.getMessage() for r in caplog.records)  # nível AVISO, não "sem mudança"


def test_falha_do_banco_vira_aviso_e_nao_excecao(caplog):
    with caplog.at_level("WARNING", logger="Manutencao"):
        assert analisar_banco(EngineQuebrado()) is False
        assert refazer_derivados_apos_carga(EngineQuebrado()) == "falhou"
    mensagens = " ".join(r.getMessage() for r in caplog.records)
    assert "ANALYZE não executado" in mensagens and "Derivados do legislativo não atualizados" in mensagens


def test_posprocessar_analisa_antes_e_depois_do_refresh(monkeypatch):
    chamadas = []
    motor = object()
    monkeypatch.setattr(
        "etl.utils.manutencao.refazer_derivados_apos_carga",
        lambda engine: chamadas.append(("derivados", engine)) or "refeito",
    )
    monkeypatch.setattr(
        "etl.utils.manutencao.analisar_banco",
        lambda engine, apenas_derivados=False: chamadas.append(
            ("analyze_derivados" if apenas_derivados else "analyze", engine)
        ),
    )
    assert posprocessar_carga(motor) == "refeito"  # o estado dos derivados volta para quem chamou registrar
    assert chamadas == [("analyze", motor), ("derivados", motor), ("analyze_derivados", motor)]  # sempre o mesmo engine


def test_posprocessar_nao_analisa_os_derivados_se_nao_refez(monkeypatch):
    chamadas = []
    monkeypatch.setattr("etl.utils.manutencao.refazer_derivados_apos_carga", lambda engine: "em_dia")
    monkeypatch.setattr(
        "etl.utils.manutencao.analisar_banco", lambda engine, apenas_derivados=False: chamadas.append(apenas_derivados)
    )
    assert posprocessar_carga(object()) == "em_dia"
    assert chamadas == [False]


def _executar_com(monkeypatch, etapas):
    chamadas = []
    monkeypatch.setattr(run_etl, "_posprocessar", lambda: chamadas.append("pos"))
    run_etl.executar(etapas, modo_completo=False)
    return chamadas


def _quebra():
    raise RuntimeError("falhou")


def test_esteira_posprocessa_uma_vez_quando_alguma_etapa_grava(monkeypatch):
    etapas = [
        run_etl.Etapa("a", "A", lambda: None, grava_banco=True),
        run_etl.Etapa("b", "B", lambda: None, grava_banco=True),
        run_etl.Etapa("c", "C", lambda: None),
    ]
    assert _executar_com(monkeypatch, etapas) == ["pos"]


def test_esteira_sem_etapa_que_grava_nao_posprocessa(monkeypatch):
    assert _executar_com(monkeypatch, [run_etl.Etapa("c", "C", lambda: None)]) == []


def test_etapa_que_grava_e_falha_depois_de_confirmar_ainda_posprocessa(monkeypatch):
    """Ela pode ter confirmado lotes antes de falhar: os gatilhos ligaram o sinalizador e o ANALYZE faz falta."""
    assert _executar_com(monkeypatch, [run_etl.Etapa("a", "A", _quebra, grava_banco=True)]) == ["pos"]


def test_uma_gravadora_que_falha_e_outra_que_passa_posprocessam_uma_vez(monkeypatch):
    etapas = [
        run_etl.Etapa("a", "A", _quebra, grava_banco=True),
        run_etl.Etapa("b", "B", lambda: None, grava_banco=True),
    ]
    assert _executar_com(monkeypatch, etapas) == ["pos"]


def test_etapa_pulada_por_falha_de_extracao_nao_posprocessa(monkeypatch):
    etapas = [
        run_etl.Etapa("extrai", "Extrai", _quebra),
        run_etl.Etapa("carga", "Carga", lambda: None, depende_de_extracao=True, grava_banco=True),
    ]
    chamadas = []
    monkeypatch.setattr(run_etl, "_posprocessar", lambda: chamadas.append("pos"))
    resultados = run_etl.executar(etapas, modo_completo=True)
    assert resultados["carga"].startswith("PULADA") and chamadas == []  # nada foi gravado


def test_falha_do_posprocessamento_nao_derruba_a_esteira(monkeypatch):
    """A esteira chama `posprocessar_carga(engine)` e, se ele levantar, a etapa continua OK (nenhum teste do tipo passa com `pass`)."""
    from app.core import database

    chamadas = []

    def quebra(motor):
        chamadas.append(motor)
        raise RuntimeError("sem banco")

    monkeypatch.setattr("etl.utils.manutencao.posprocessar_carga", quebra)
    resultados = run_etl.executar([run_etl.Etapa("a", "A", lambda: None, grava_banco=True)], modo_completo=False)
    assert resultados["a"].startswith("OK")
    assert chamadas == [database.engine]  # a chamada aconteceu, com o motor do app


def test_posprocessamento_da_esteira_devolve_o_estado_dos_derivados(monkeypatch):
    monkeypatch.setattr("etl.utils.manutencao.posprocessar_carga", lambda motor: "ocupado")
    assert run_etl._posprocessar() == "ocupado"

    def quebra(motor):
        raise RuntimeError("sem banco")

    monkeypatch.setattr("etl.utils.manutencao.posprocessar_carga", quebra)
    assert run_etl._posprocessar() == "falhou"


def test_toda_carga_que_escreve_nas_dependencias_reserva_a_trava_antes_de_qualquer_escrita():
    """
    A trava de controle dos derivados tem de ser a primeira coisa da transação (ver a docstring da migração 0037): senão a
    carga pode segurar uma linha de `core.pessoa` e só depois pedir o controle, e formar um ciclo de espera com a fusão.
    """
    import ast
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[2]
    pontos = (
        ("backend/app/services/staging_merge.py", "merge_staging"),
        ("etl/pipelines/camara_bulk_loader.py", "mesclar"),
        ("etl/pipelines/camara_historico_loader.py", "carregar"),
        ("etl/pipelines/presidencia_loader.py", "carregar"),
    )
    for arquivo, nome in pontos:
        arvore = ast.parse((raiz / arquivo).read_text(encoding="utf-8"))
        funcao = next(n for n in ast.walk(arvore) if isinstance(n, ast.FunctionDef) and n.name == nome)
        chamadas = sorted(
            (no.lineno, getattr(no.func, "id", None) or getattr(no.func, "attr", None))
            for no in ast.walk(funcao)
            if isinstance(no, ast.Call)
        )
        reservas = [linha for linha, chamada in chamadas if chamada == "reservar_derivados"]
        execucoes = [linha for linha, chamada in chamadas if chamada == "execute"]
        assert reservas, f"{arquivo}::{nome} não reserva a trava de controle dos derivados"
        assert min(reservas) < min(execucoes), f"{arquivo}::{nome} escreve antes de reservar"


def test_todas_as_etapas_que_gravam_no_banco_estao_marcadas():
    """
    Esquecer a marca numa etapa nova deixaria a primeira leitura pagar o refresh e o planejador sem estatísticas. O
    catálogo real é montado com todas as etapas ligadas e a regra é exaustiva: carga no Postgres = marcada, o resto não.
    """
    parser = run_etl.montar_parser()
    args = parser.parse_args(
        []
    )  # sem flag de etapa = modo completo, com todo o catálogo (menos o DataJud, só sob pedido)
    etapas = {e.chave: e for e in run_etl.construir_etapas(args)}
    grava = {chave for chave, e in etapas.items() if e.grava_banco}
    cargas = {chave for chave in etapas if chave.startswith("load_") or chave in ("camara_bulk", "camara_historico")}
    # o piso impede o teste de passar vazio, que foi o defeito de montar o catálogo com uma flag só
    assert {"load_db", "load_presenca", "load_economia", "camara_bulk", "camara_historico"} <= cargas
    assert grava == cargas, f"marcadas {sorted(grava)} != cargas no banco {sorted(cargas)}"
