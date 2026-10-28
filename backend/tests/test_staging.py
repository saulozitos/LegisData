"""Staging no lugar do legado: o `public` fica sem dado de domínio, as funções de fusão leem `stg` e a API tem papel de leitura."""

import pytest
from sqlalchemy import text

TABELAS_DE_ENTRADA = {
    "politicos",
    "partidos_politicos",
    "filiacoes_partidarias",
    "mandatos",
    "membros_gabinete",
    "proposicoes",
    "proposicoes_autores",
    "sessoes_votacao",
    "votos_parlamentares",
    "registros_presenca",
    "votacoes_proposicao",
    "votos_nominais",
    "orientacoes_partidarias",
}
APOSENTADAS = {
    "remuneracoes_politicos",
    "declaracoes_patrimonio",
    "despesas_cota_parlamentar",
    "emendas_parlamentares",
    "certidoes_judiciais",
    "doacoes_campanha",
    "processos_judiciais",
    "historico_mandatos",
    "series_indicadores",
    "pontos_dados_indicadores",
    "resumos_macroeconomicos_anuais",
    "mandatos_performance_economica",
    "analises_impacto_politica",
    "indicadores_sociais_anuais",
    "indicadores_sociais_uf",
    "resultados_eleicoes_presidenciais_uf",
    "repasses_federais_uf",
}


def _tabelas(db, schema):
    return set(db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = :s"), {"s": schema}).scalars())


def test_tabelas_de_entrada_vivem_em_stg_e_o_public_so_guarda_a_versao_do_alembic(db):
    assert TABELAS_DE_ENTRADA <= _tabelas(db, "stg")
    assert _tabelas(db, "public") <= {"alembic_version", "etl_test_migracoes"}  # nenhum dado de domínio no public


def test_tabelas_aposentadas_nao_existem_em_lugar_nenhum(db):
    existentes = set(
        db.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog', 'information_schema')")
        ).scalars()
    )
    assert existentes.isdisjoint(APOSENTADAS)


def test_funcoes_de_fusao_tem_o_nome_novo_e_leem_stg(db):
    nomes = set(
        db.execute(
            text("SELECT proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'etl'")
        ).scalars()
    )
    assert {"merge_cadastro", "merge_legislativo", "merge_camara_bulk", "merge_camara_historico"} <= nomes
    assert not {"sincronizar_legado", "sincronizar_legado_leg"} & nomes
    for funcao in (
        "etl.merge_cadastro",
        "etl.merge_legislativo",
        "etl.merge_camara_bulk",
        "etl.merge_camara_historico",
        "core.unificar_duplicadas",
    ):
        fonte = db.execute(text("SELECT pg_get_functiondef(CAST(:f AS regproc))"), {"f": funcao}).scalar()
        assert "public." not in fonte.replace("public.alembic", "")  # nenhuma leitura do public


def test_politico_nao_tem_coluna_de_cpf(db):
    colunas = set(
        db.execute(
            text(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = 'stg' AND table_name = 'politicos'"
            )
        ).scalars()
    )
    assert "cpf" not in colunas and "nomeCivil" in colunas


def test_log_do_cron_vive_em_etl(db):
    assert "log_execucao_cron" in _tabelas(db, "etl") and "log_execucao_cron" not in _tabelas(db, "public")


def test_papel_de_leitura_so_le(db):
    assert db.execute(text("SELECT rolcanlogin FROM pg_roles WHERE rolname = 'legisdata_leitura'")).scalar() is False
    pode = lambda tabela, privilegio: db.execute(  # noqa: E731
        text("SELECT has_table_privilege('legisdata_leitura', CAST(:t AS regclass), :p)"),
        {"t": tabela, "p": privilegio},
    ).scalar()
    for tabela in (
        "core.pessoa",
        "leg.proposicao",
        "eco.observacao",
        "fin.despesa_cota",
        "ref.uf",
        "core.partido",
        "param.peso",
        "param.metodologia",
        "etl.fonte",
        "etl.log_execucao_cron",
    ):
        assert pode(tabela, "SELECT") is True
        for escrita in ("INSERT", "UPDATE", "DELETE"):
            assert pode(tabela, escrita) is False
    assert pode("stg.politicos", "SELECT") is False  # a API nunca lê o staging
    assert pode("etl.rejeito", "SELECT") is False  # nem o que o ETL rejeitou (pode trazer dado bruto da fonte)


@pytest.mark.parametrize("schema", ["core", "leg", "eco", "fin", "ref"])
def test_tabelas_novas_nascem_legiveis_pelo_papel_de_leitura(db, schema):
    # ALTER DEFAULT PRIVILEGES: o que as próximas migrações criarem já vale para o papel
    db.execute(text(f"CREATE TABLE {schema}.t_privilegio_teste (id int)"))
    try:
        assert (
            db.execute(
                text("SELECT has_table_privilege('legisdata_leitura', CAST(:t AS regclass), 'SELECT')"),
                {"t": f"{schema}.t_privilegio_teste"},
            ).scalar()
            is True
        )
    finally:
        db.rollback()


def test_migracoes_0036_e_0037_descem_e_sobem_com_dados(pg_engine, monkeypatch):
    """Descer a 0035 devolve tabelas, funções e o log do cron ao `public` com os dados; subir leva tudo de volta."""
    from alembic import command
    from alembic.config import Config
    from app.core.migrations import BACKEND_DIR

    from .conftest import TEST_DATABASE_URL

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", TEST_DATABASE_URL)

    def escalar(sql):
        with pg_engine.connect() as conn:
            return conn.execute(text(sql)).scalar()

    with pg_engine.begin() as conn:
        conn.execute(
            text(
                'INSERT INTO stg.politicos (id, "nomeCivil", "nomeEleitoral") '
                "VALUES (gen_random_uuid(), 'Pessoa de Teste', 'Teste')"
            )
        )
        conn.execute(
            text("INSERT INTO etl.log_execucao_cron (id, \"statusExecucao\") VALUES (gen_random_uuid(), 'SUCESSO')")
        )
    try:
        command.downgrade(config, "0035")
        assert escalar("SELECT count(*) FROM public.politicos") == 1  # a tabela voltou com o dado
        assert escalar("SELECT count(*) FROM public.log_execucao_cron") == 1
        assert escalar("SELECT to_regclass('etl.log_execucao_cron') IS NULL")
        assert escalar("SELECT to_regprocedure('etl.sincronizar_legado()') IS NOT NULL")
        assert escalar("SELECT to_regprocedure('etl.merge_cadastro()') IS NULL")
        assert escalar("SELECT to_regclass('leg.mv_coautoria_par') IS NULL")
    finally:
        command.upgrade(config, "head")  # mesmo se um assert falhar, o banco de teste volta ao head
    assert escalar("SELECT count(*) FROM stg.politicos") == 1
    assert escalar("SELECT count(*) FROM etl.log_execucao_cron") == 1
    assert escalar("SELECT to_regclass('public.politicos') IS NULL")
    assert escalar("SELECT to_regprocedure('etl.merge_cadastro()') IS NOT NULL")
    assert escalar("SELECT to_regclass('leg.mv_coautoria_par') IS NOT NULL")
    assert escalar("SELECT prosecdef FROM pg_proc WHERE oid = 'leg.atualizar_derivados()'::regprocedure")


def test_migracao_0035_nao_desce(pg_engine, monkeypatch):
    """As 17 tabelas aposentadas não voltam com o schema original: o downgrade recusa em vez de fingir."""
    from alembic import command
    from alembic.config import Config
    from app.core.migrations import BACKEND_DIR

    from .conftest import TEST_DATABASE_URL

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", TEST_DATABASE_URL)
    with pytest.raises(NotImplementedError, match="irreversível"):
        command.downgrade(config, "0034")
    with pg_engine.connect() as conn:  # a transação única desfez também o que a 0037 e a 0036 já tinham descido
        assert conn.execute(text("SELECT to_regclass('leg.mv_coautoria_par') IS NOT NULL")).scalar()
