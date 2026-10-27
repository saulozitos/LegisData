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
    for funcao in ("etl.merge_cadastro", "etl.merge_legislativo", "etl.merge_camara_bulk", "core.unificar_duplicadas"):
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
        "param.peso_ialp" if False else "core.partido",
    ):
        assert pode(tabela, "SELECT") is True
        for escrita in ("INSERT", "UPDATE", "DELETE"):
            assert pode(tabela, escrita) is False
    assert pode("stg.politicos", "SELECT") is False  # a API nunca lê o staging


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
