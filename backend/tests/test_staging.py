"""Staging no lugar do legado: o `public` fica sem dado de domínio, as funções de fusão leem `stg` e a API tem papel de leitura."""

import pytest
from sqlalchemy import text

TABELAS_CONGELADAS = {  # sem escritor desde a 0040, mas a fusão ainda as lê
    "proposicoes_autores",
    "registros_presenca",
    "votacoes_proposicao",
    "votos_nominais",
    "orientacoes_partidarias",
}
TABELAS_RELACIONAIS_QUE_CAIRAM = {
    "politicos",
    "partidos_politicos",
    "filiacoes_partidarias",
    "mandatos",
    "membros_gabinete",
    "proposicoes",
    "sessoes_votacao",
    "votos_parlamentares",
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
    assert TABELAS_CONGELADAS <= _tabelas(db, "stg")
    assert TABELAS_RELACIONAIS_QUE_CAIRAM.isdisjoint(_tabelas(db, "stg"))
    # nenhum dado de domínio no public (as `w_*` são só do banco de teste: em produção a fusão as cria temporárias)
    assert {t for t in _tabelas(db, "public") if not t.startswith("w_")} <= {"alembic_version"}


def test_tabelas_aposentadas_nao_existem_em_lugar_nenhum(db):
    existentes = set(
        db.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog', 'information_schema')")
        ).scalars()
    )
    assert existentes.isdisjoint(APOSENTADAS)


def test_funcoes_de_fusao_tem_o_nome_novo_e_leem_as_tabelas_de_trabalho(db):
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
    ):
        fonte = db.execute(text("SELECT pg_get_functiondef(CAST(:f AS regproc))"), {"f": funcao}).scalar()
        assert "public." not in fonte.replace("public.alembic", "")  # nenhuma leitura do public


def test_staging_nao_tem_coluna_de_cpf(db):
    """Decisão D3: nenhum CPF em lugar nenhum do staging, nem nas tabelas planas novas nem nas congeladas."""
    colunas = set(
        db.execute(
            text(
                "SELECT table_name || '.' || column_name FROM information_schema.columns "
                "WHERE table_schema IN ('stg', 'core') AND lower(column_name) LIKE '%cpf%'"
            )
        ).scalars()
    )
    assert colunas == set()


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
    assert pode("stg.camara_deputado", "SELECT") is False  # a API nunca lê o staging
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


def test_descer_a_0035_devolve_o_legado_ao_public_e_subir_leva_tudo_de_volta(pg_engine, monkeypatch):
    """Descer a 0035 devolve tabelas, funções e o log do cron ao `public` com os dados; subir leva tudo de volta."""
    from alembic import command

    config = _config_do_alembic(monkeypatch)

    def escalar(sql):
        with pg_engine.connect() as conn:
            return conn.execute(text(sql)).scalar()

    try:
        command.downgrade(config, "0039")  # a 0041 e a 0040 descem: voltam as tabelas relacionais de stg (vazias)
        assert escalar("SELECT to_regclass('stg.politicos') IS NOT NULL")
    except BaseException:
        command.upgrade(config, "head")
        raise
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
        conn.execute(
            text(
                'INSERT INTO etl.log_execucao_cron (id, "statusExecucao", "erroMensagem") VALUES '
                "(gen_random_uuid(), 'FALHA', 'connection to server at \"10.0.0.5\" failed'), "
                "(gen_random_uuid(), 'FALHA', 'votações: OperationalError; economia: TimeoutError')"
            )
        )
    try:
        command.downgrade(config, "0035")
        assert escalar("SELECT count(*) FROM public.politicos") == 1  # a tabela voltou com o dado
        assert escalar("SELECT count(*) FROM public.log_execucao_cron") == 3
        assert escalar("SELECT to_regclass('stg.politicos') IS NULL")
        assert escalar("SELECT to_regclass('etl.log_execucao_cron') IS NULL")
        assert escalar("SELECT to_regprocedure('etl.sincronizar_legado()') IS NOT NULL")
        assert escalar("SELECT to_regprocedure('etl.merge_cadastro()') IS NULL")
        assert escalar("SELECT to_regclass('leg.mv_coautoria_par') IS NULL")
        # o papel de leitura perdeu o que ganhou, inclusive os privilégios padrão sobre tabelas futuras
        assert not escalar("SELECT has_table_privilege('legisdata_leitura', 'core.pessoa', 'SELECT')")
        assert escalar("SELECT count(*) FROM pg_default_acl WHERE defaclacl::text LIKE '%legisdata_leitura%'") == 0
    finally:
        command.upgrade(config, "head")  # mesmo se um assert falhar, o banco de teste volta ao head
        with pg_engine.connect() as conn:
            # subir leva as 3 linhas do log para o `etl`; a 0040 apaga as tabelas relacionais de stg (a pessoa não volta)
            voltaram = conn.execute(text("SELECT count(*) FROM etl.log_execucao_cron")).scalar()
            mensagens = {
                linha[0]
                for linha in conn.execute(
                    text('SELECT "erroMensagem" FROM etl.log_execucao_cron WHERE "erroMensagem" IS NOT NULL')
                )
            }
        # e sem as linhas que este teste gravou fora do TRUNCATE da fixture `db` (senão o teste seguinte as enxerga)
        with pg_engine.begin() as conn:
            conn.execute(text("DELETE FROM etl.log_execucao_cron"))
    assert voltaram == 3
    # a mensagem crua da exceção (host, caminho, SQL) não volta para a tabela que o papel de leitura enxerga
    assert mensagens == {
        "Falha registrada; o detalhe está no log do servidor.",
        "votações: OperationalError; economia: TimeoutError",
    }
    assert escalar("SELECT to_regclass('public.politicos') IS NULL")
    assert not escalar(  # nenhum CPF volta nem na descida: a coluna só existiu antes da 0036
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE column_name = 'cpf' "
        "AND table_schema IN ('public', 'stg', 'core'))"
    )
    assert escalar("SELECT to_regprocedure('etl.merge_cadastro()') IS NOT NULL")
    assert escalar("SELECT to_regclass('leg.mv_coautoria_par') IS NOT NULL")
    assert escalar("SELECT prosecdef FROM pg_proc WHERE oid = 'leg.atualizar_derivados(boolean, text)'::regprocedure")
    assert escalar("SELECT prosecdef FROM pg_proc WHERE oid = 'leg.atualizar_derivados_leitura()'::regprocedure")
    assert escalar("SELECT has_table_privilege('legisdata_leitura', 'core.pessoa', 'SELECT')")  # e voltou ao subir


def test_migracao_0040_passa_os_votos_do_staging_relacional_para_a_plana_cumulativa(pg_engine, monkeypatch):
    """Subir a 0040 copia os votos que o staging relacional guardava para `stg.historico_voto` (senão a 1ª fusão esvazia `leg.voto`)."""
    from alembic import command

    config = _config_do_alembic(monkeypatch)
    try:
        command.downgrade(config, "0039")  # volta o staging relacional (vazio): é nele que o deploy encontra os votos
        with pg_engine.begin() as conn:
            conn.execute(
                text(
                    'INSERT INTO stg.partidos_politicos (id, sigla, "nomeCompleto") '
                    "VALUES ('00000000-0000-0000-0000-0000000000a1', 'PT', 'Partido dos Trabalhadores')"
                )
            )
            conn.execute(
                text(
                    'INSERT INTO stg.politicos (id, "nomeCivil", "nomeEleitoral", "camaraId", "senadoId") VALUES '
                    "('00000000-0000-0000-0000-0000000000b1', 'Ana', 'Ana', 101, NULL), "
                    "('00000000-0000-0000-0000-0000000000b2', 'Beto', 'Beto', NULL, 202), "
                    "('00000000-0000-0000-0000-0000000000b3', 'Sem Id', 'Sem Id', NULL, NULL)"
                )
            )
            conn.execute(
                text(
                    'INSERT INTO stg.proposicoes (id, "idExternoCamara", tipo, numero, ano, titulo, ementa, '
                    '"dataApresentacao", "statusTramitacao", "isReformaEstrutural", "iniciativaPoderExecutivo") '
                    "VALUES ('00000000-0000-0000-0000-0000000000c1', 1, 'PEC', 1, 2020, 'PEC 1/2020', 'Ementa', "
                    "'2020-01-01', 'APROVADA_E_SANCIONADA', false, false)"
                )
            )
            conn.execute(
                text(
                    'INSERT INTO stg.sessoes_votacao (id, "idExterno", "proposicaoId", "casaLegislativa", '
                    '"dataHoraVotacao", "tituloPauta", "isVotacaoSecreta", aprovada, "totalSim", "totalNao", '
                    '"totalAbstencao", "totalObstrucao", created_at) VALUES '
                    "('00000000-0000-0000-0000-0000000000d1', 'SC1', '00000000-0000-0000-0000-0000000000c1', "
                    "'CAMARA_DOS_DEPUTADOS', now(), 'Pauta', false, true, 1, 0, 0, 0, now()), "
                    "('00000000-0000-0000-0000-0000000000d2', 'SS1', '00000000-0000-0000-0000-0000000000c1', "
                    "'SENADO_FEDERAL', now(), 'Pauta', false, true, 1, 0, 0, 0, now())"
                )
            )
            conn.execute(
                text(
                    'INSERT INTO stg.votos_parlamentares (id, "sessaoVotacaoId", "politicoId", "partidoId", voto, '
                    "created_at) VALUES "
                    "(gen_random_uuid(), '00000000-0000-0000-0000-0000000000d1', "
                    "'00000000-0000-0000-0000-0000000000b1', '00000000-0000-0000-0000-0000000000a1', 'SIM', now()), "
                    "(gen_random_uuid(), '00000000-0000-0000-0000-0000000000d2', "
                    "'00000000-0000-0000-0000-0000000000b2', NULL, 'NAO', now()), "
                    "(gen_random_uuid(), '00000000-0000-0000-0000-0000000000d1', "
                    "'00000000-0000-0000-0000-0000000000b3', NULL, 'SIM', now())"
                )
            )
    except BaseException:
        command.upgrade(config, "head")
        raise
    try:
        command.upgrade(config, "head")
        with pg_engine.connect() as conn:
            copiados = [
                tuple(linha)
                for linha in conn.execute(
                    text(
                        "SELECT casa, sessao_ext_id, parlamentar_ext_id, opcao, partido FROM stg.historico_voto "
                        "ORDER BY casa, sessao_ext_id"
                    )
                )
            ]
    finally:
        with pg_engine.begin() as conn:  # a fixture `db` não limpa a plana cumulativa: não deixar rastro
            conn.execute(text("DELETE FROM stg.historico_voto"))
    # o voto do parlamentar sem identificador oficial não tem como ser ligado de novo e fica de fora
    assert copiados == [("CAMARA", "SC1", 101, "SIM", "PT"), ("SENADO", "SS1", 202, "NAO", None)]


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


def test_funcoes_de_fusao_nao_sao_executaveis_pelo_publico(pg_engine):
    """Elas escrevem em `core`/`leg`; o papel de leitura tem USAGE em `etl`, então o EXECUTE do PUBLIC seria uma porta."""
    with pg_engine.connect() as conn:
        for assinatura in (
            "etl.merge_cadastro()",
            "etl.merge_legislativo()",
            "etl.merge_camara_bulk()",
            "etl.merge_camara_historico()",
            "etl.preparar_staging(boolean, boolean)",
            "etl.criar_trabalho()",
        ):
            acl = conn.execute(
                text("SELECT proacl::text FROM pg_proc WHERE oid = CAST(:a AS regprocedure)"), {"a": assinatura}
            ).scalar()
            assert acl is not None and "{=X" not in acl and ",=X" not in acl, assinatura
            assert not conn.execute(
                text("SELECT has_function_privilege('legisdata_leitura', CAST(:a AS regprocedure), 'EXECUTE')"),
                {"a": assinatura},
            ).scalar()


@pytest.mark.parametrize("referencia", ["presenca", "nomeador", "substituto", "presenca_em_nomeado"])
def test_fusao_do_cadastro_preserva_o_mandato_que_algo_referencia(pg_engine, referencia):
    """
    O staging perdeu um mandato da fonte LEGADO que ainda é referenciado (por uma presença, por um mandato que ele nomeou
    ou como substituto numa situação): a fusão não pode apagá-lo (estourava a chave estrangeira e a carga inteira
    falhava). Cada uma das três guardas da 0038 tem o seu caso; o mandato órfão sem referência sai como sempre.
    """
    with pg_engine.connect() as conn:
        transacao = conn.begin()
        try:
            conn.execute(text("SELECT leg.reservar_derivados()"))
            fonte = conn.execute(text("SELECT id FROM etl.fonte WHERE codigo = 'LEGADO'")).scalar_one()
            pessoa = conn.execute(
                text("INSERT INTO core.pessoa (nome_exibicao) VALUES ('Zt Mandato') RETURNING id")
            ).scalar_one()
            casa = conn.execute(
                text("SELECT id FROM ref.casa_legislativa WHERE codigo = 'CAMARA_DOS_DEPUTADOS'")
            ).scalar()

            def mandato(cargo, inicio, fonte_id, nomeado_por=None, numero=1, condicao="TITULAR", orgao=None):
                return conn.execute(
                    text(
                        "INSERT INTO core.mandato (pessoa_id, cargo_id, circunscricao_id, inicio, fonte_id, "
                        "nomeado_por_mandato_id, numero_mandato, condicao, orgao_nome) VALUES (:p, "
                        "(SELECT id FROM ref.cargo WHERE codigo = :cargo), "
                        "(SELECT id FROM ref.circunscricao WHERE tipo = 'BR'), :i, :f, :n, :num, :cond, :org) RETURNING id"
                    ),
                    {
                        "p": pessoa,
                        "i": inicio,
                        "f": fonte_id,
                        "cargo": cargo,
                        "n": nomeado_por,
                        "num": numero,
                        "cond": condicao,
                        "org": orgao,
                    },
                ).scalar_one()

            if referencia == "presenca_em_nomeado":  # o segundo DELETE da fusão, o dos mandatos nomeados
                referenciado = mandato(
                    "MINISTRO_DE_ESTADO", "2003-02-01", fonte, condicao="NOMEADO", orgao="Ministério de Teste"
                )
            else:
                referenciado = mandato("DEPUTADO_FEDERAL", "2003-02-01", fonte)
            orfao = mandato("SENADOR", "2007-02-01", fonte)
            esperados = {referenciado}
            if referencia in ("presenca", "presenca_em_nomeado"):
                conn.execute(
                    text(
                        "INSERT INTO leg.presenca (pessoa_id, casa_id, data_sessao, tipo_codigo, mandato_id) "
                        "VALUES (:p, :c, '2003-03-01', 'PRESENTE', :m)"
                    ),
                    {"p": pessoa, "c": casa, "m": referenciado},
                )
            elif referencia == "nomeador":
                # fonte nula: a fusão não toca no mandato que nomeia, então só a guarda protege o nomeador
                esperados.add(mandato("SENADOR", "2011-02-01", None, nomeado_por=referenciado, numero=2))
            else:
                dono = mandato("SENADOR", "2011-02-01", None, numero=2)
                esperados.add(dono)
                conn.execute(
                    text(
                        "INSERT INTO core.mandato_situacao (mandato_id, situacao, periodo, substituto_mandato_id) "
                        "VALUES (:d, 'SUPLENCIA', daterange('2011-03-01', '2011-04-01'), :s)"
                    ),
                    {"d": dono, "s": referenciado},
                )
            conn.execute(text("SELECT etl.merge_cadastro()"))
            restantes = {
                r[0] for r in conn.execute(text("SELECT id FROM core.mandato WHERE pessoa_id = :p"), {"p": pessoa})
            }
        finally:
            transacao.rollback()
    assert orfao not in restantes  # o órfão sem referência sai
    assert restantes == esperados  # o referenciado fica (e o que o referencia, nos casos em que ele é um mandato)


def test_migracao_0038_desce_e_sobe_com_a_definicao_da_fusao(pg_engine, monkeypatch):
    """Descer a 0037 tira só as três guardas acrescentadas à fusão; subir de novo as devolve."""
    from alembic import command

    config = _config_do_alembic(monkeypatch)

    def corpo_da_fusao():
        with pg_engine.connect() as conn:
            return conn.execute(text("SELECT pg_get_functiondef('etl.merge_cadastro()'::regprocedure)")).scalar_one()

    try:
        command.downgrade(config, "0037")
        sem_guardas = corpo_da_fusao()
        assert "leg.presenca p WHERE p.mandato_id" not in sem_guardas
        assert "nomeado_por_mandato_id = c.id" not in sem_guardas
        assert "substituto_mandato_id = c.id" not in sem_guardas
        assert sem_guardas.count("l.mandato_id = c.id);") == 2  # os dois DELETE de core.mandato, como antes da 0038
    finally:
        command.upgrade(config, "head")
    com_guardas = corpo_da_fusao()
    for trecho in ("leg.presenca p WHERE p.mandato_id = c.id", "n.nomeado_por_mandato_id = c.id"):
        assert com_guardas.count(trecho) == 2
    assert com_guardas.count("s.substituto_mandato_id = c.id") == 2


def _migracao_0038():
    import importlib.util

    from app.core.migrations import BACKEND_DIR

    caminho = BACKEND_DIR / "alembic" / "versions" / "0038_fusao_preserva_mandato_referenciado.py"
    spec = importlib.util.spec_from_file_location("migracao_0038", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.mark.parametrize("ocorrencias", [0, 1, 3])
def test_migracao_0038_recusa_funcao_que_difere_do_texto_esperado(monkeypatch, ocorrencias):
    """Função editada fora das migrações (não há exatamente 2 DELETE a trocar): falha explícita, sem reescrever às cegas."""
    from types import SimpleNamespace

    modulo = _migracao_0038()
    corpo = "CREATE OR REPLACE FUNCTION etl.merge_cadastro() ..." + (modulo.ALVO + " ") * ocorrencias
    executados = []

    class Conexao:
        def exec_driver_sql(self, sql):
            executados.append(sql)
            return SimpleNamespace(scalar_one=lambda: corpo)

    monkeypatch.setattr(modulo, "op", SimpleNamespace(get_bind=lambda: Conexao()))
    with pytest.raises(RuntimeError, match="difere do texto esperado"):
        modulo.upgrade()
    assert len(executados) == 1  # só a leitura do catálogo; nenhum CREATE OR REPLACE foi enviado
