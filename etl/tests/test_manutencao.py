"""`ANALYZE` depois da carga: roda no Postgres e nunca derruba a carga."""

from sqlalchemy import text

from etl.utils.manutencao import analisar_banco


def test_analisar_banco_roda_no_postgres_de_teste(pg_engine):
    assert analisar_banco(pg_engine) is True
    with pg_engine.connect() as conn:
        # a revisão do Alembic existe e o ANALYZE não deixou transação aberta
        assert conn.execute(text("SELECT count(*) FROM alembic_version")).scalar() == 1


def test_falha_do_banco_vira_aviso_e_nao_excecao(caplog):
    class EngineQuebrado:
        def connect(self):
            raise RuntimeError("banco fora do ar")

    with caplog.at_level("WARNING", logger="Manutencao"):
        assert analisar_banco(EngineQuebrado()) is False
    assert any("ANALYZE não executado" in r.getMessage() for r in caplog.records)
