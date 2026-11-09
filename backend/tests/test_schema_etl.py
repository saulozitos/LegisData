"""Schema do ETL direto: sem staging, com `etl.corte`, `public` sem dado de domínio e a API com papel de leitura."""

import pytest
from sqlalchemy import text

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


def test_tabelas_aposentadas_nao_existem_em_lugar_nenhum(db):
    existentes = set(
        db.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog', 'information_schema')")
        ).scalars()
    )
    assert existentes.isdisjoint(APOSENTADAS)


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
    assert pode("etl.corte", "SELECT") is False  # nem o controle interno da carga
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


def _config_do_alembic(monkeypatch):
    from alembic.config import Config
    from app.core.migrations import BACKEND_DIR

    from .conftest import TEST_DATABASE_URL

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", TEST_DATABASE_URL)
    return config


def test_migracao_0035_nao_desce(pg_engine, monkeypatch):
    """As 17 tabelas aposentadas não voltam com o schema original: o downgrade recusa em vez de fingir."""
    from alembic import command

    config = _config_do_alembic(monkeypatch)
    try:
        with pytest.raises(NotImplementedError, match="irreversível"):
            command.downgrade(config, "0034")
        with pg_engine.connect() as conn:  # a transação única desfez também o que a 0037 e a 0036 já tinham descido
            assert conn.execute(text("SELECT to_regclass('leg.mv_coautoria_par') IS NOT NULL")).scalar()
    finally:
        command.upgrade(config, "head")  # se um dia cada migração tiver a sua transação, o banco volta ao head


def test_nao_existe_staging_nem_funcao_de_fusao(pg_engine):
    """A carga é direta (migração 0039): o schema `stg` e as funções `etl.preparar_*`/`etl.merge_*` não existem."""
    with pg_engine.connect() as conn:
        # o banco de teste recria um `stg` e funções `public.projetar_*` SÓ para semear dado (backend/tests/projecao)
        funcoes = set(
            conn.execute(
                text(
                    "SELECT proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'etl'"
                )
            ).scalars()
        )
    assert funcoes == {"aplicar_linhagens", "resolver_partido_presenca", "verificar_pesos"}


def test_corte_tem_uma_linha_por_fonte_e_recurso(db):
    db.execute(
        text("INSERT INTO etl.corte (fonte, recurso, ultima_data) VALUES ('CAMARA_API', 'votacoes', '2024-01-01')")
    )
    with pytest.raises(Exception, match="duplicate key"):
        db.execute(text("INSERT INTO etl.corte (fonte, recurso) VALUES ('CAMARA_API', 'votacoes')"))
    db.rollback()


def test_ponte_do_legado_saiu_e_a_votacao_aceita_resultado_desconhecido(db):
    assert db.execute(
        text("SELECT to_regclass('core.mandato_legado') IS NULL AND to_regclass('leg.votacao_legado') IS NULL")
    ).scalar()
    assert not db.execute(
        text(
            "SELECT 1 FROM information_schema.columns WHERE table_schema = 'leg' AND table_name = 'autoria' AND column_name = 'legado_id'"
        )
    ).scalar()
    assert (
        db.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns WHERE table_schema = 'leg' AND table_name = 'votacao' AND column_name = 'aprovada'"
            )
        ).scalar()
        == "YES"
    )


def test_partidos_e_seus_nomes_vivem_no_banco(db):
    """Nome, espectro e número dos partidos saíram do código Python para `ref.partido_semente`."""
    total, com_nome = db.execute(text("SELECT count(*), count(nome) FROM ref.partido_semente")).one()
    assert total >= 55 and com_nome >= 40
    assert (
        db.execute(text("SELECT nome FROM ref.partido_semente WHERE sigla_normalizada = 'pt'")).scalar()
        == "Partido dos Trabalhadores"
    )


def test_identificador_curado_e_aceito_e_um_tipo_qualquer_nao(db):
    pessoa = db.execute(text("INSERT INTO core.pessoa (nome_exibicao) VALUES ('Curada') RETURNING id")).scalar_one()
    fonte = db.execute(text("SELECT id FROM etl.fonte WHERE codigo = 'CURADORIA'")).scalar_one()
    db.execute(
        text(
            "INSERT INTO core.pessoa_identificador (pessoa_id, fonte_id, tipo, valor) VALUES (:p, :f, 'CURADORIA_ID', 'x')"
        ),
        {"p": pessoa, "f": fonte},
    )
    with pytest.raises(Exception, match="pessoa_identificador_tipo_check"):
        db.execute(
            text(
                "INSERT INTO core.pessoa_identificador (pessoa_id, fonte_id, tipo, valor) VALUES (:p, :f, 'CPF', '1')"
            ),
            {"p": pessoa, "f": fonte},
        )
    db.rollback()


def test_migracao_0039_nao_desce(pg_engine, monkeypatch):
    """O staging e as pontes do legado não voltam: o downgrade recusa em vez de fingir."""
    from alembic import command

    config = _config_do_alembic(monkeypatch)
    try:
        with pytest.raises(NotImplementedError, match="irreversível"):
            command.downgrade(config, "0038")
        with pg_engine.connect() as conn:
            assert conn.execute(text("SELECT to_regclass('etl.corte') IS NOT NULL")).scalar()
    finally:
        command.upgrade(config, "head")


def test_situacao_chancela_do_despacho_esta_mapeada_em_tramitacao(pg_engine):
    """A situação nova da Câmara (2026) não pode cair em SITUACAO_SEM_MAPEAMENTO: segue em tramitação."""
    with pg_engine.connect() as conn:
        status = (
            conn.execute(
                text(
                    "SELECT status_codigo FROM ref.situacao_camara "
                    "WHERE descricao = 'Aguardando Chancela e Publicação do Despacho' AND tipo_codigo IS NULL"
                )
            )
            .scalars()
            .all()
        )
    assert status == ["EM_TRAMITACAO"]
