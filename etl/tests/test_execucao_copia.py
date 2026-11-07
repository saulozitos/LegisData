"""Registro de execuções e arquivos de origem (`etl.execucao`, `etl.arquivo_bruto`) e o COPY para o staging."""

import hashlib
import logging
import os

import pytest
from sqlalchemy import text

from etl.pipelines.semeadura_das_financas import fontes_do_timer
from etl.utils import copia, execucao

MARCA = {"teste": "execucao"}  # permite apagar o que estes testes gravam
FILTRO_MARCA = 'parametros @> \'{"teste": "execucao"}\''


@pytest.fixture(autouse=True)
def limpa(pg_engine):
    yield
    with pg_engine.begin() as conn:
        conn.execute(
            text(
                f"DELETE FROM etl.arquivo_bruto WHERE execucao_id IN (SELECT id FROM etl.execucao WHERE {FILTRO_MARCA})"
            )
        )
        conn.execute(text("DELETE FROM etl.arquivo_bruto WHERE caminho LIKE '/teste/%'"))
        ids = f"SELECT id FROM etl.execucao WHERE {FILTRO_MARCA}"
        conn.execute(
            text(f"DELETE FROM etl.verificacao WHERE execucao_id IN ({ids})")
        )  # toda execução tem a de contagens
        conn.execute(text(f"DELETE FROM etl.rejeito WHERE execucao_id IN ({ids})"))
        conn.execute(text(f"DELETE FROM etl.execucao WHERE {FILTRO_MARCA}"))


def _linha(pg_engine, identificador):
    with pg_engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT status, estagio, finalizado_em IS NOT NULL AS fechada, linhas_lidas, linhas_gravadas, "
                "linhas_rejeitadas, erro, parametros FROM etl.execucao WHERE id = :i"
            ),
            {"i": identificador},
        ).one()


def _executar(pg_engine, lidas=None, gravadas=None, rejeitadas=None):
    with execucao.registrar_execucao(pg_engine, "CAMARA_CSV", "CARREGAR", MARCA) as e:
        e.lidas, e.gravadas, e.rejeitadas = lidas, gravadas, rejeitadas
    return _linha(pg_engine, e.id)


def test_execucao_ok_fecha_com_as_contagens(pg_engine):
    with execucao.registrar_execucao(pg_engine, "CAMARA_CSV", "CARREGAR", MARCA) as e:
        assert _linha(pg_engine, e.id).status == "EXECUTANDO" and not _linha(pg_engine, e.id).fechada
        e.lidas, e.gravadas, e.rejeitadas = 10, 10, 0
    linha = _linha(pg_engine, e.id)
    assert (linha.status, linha.estagio, linha.fechada) == ("OK", "CARREGAR", True)
    assert (linha.linhas_lidas, linha.linhas_gravadas, linha.linhas_rejeitadas, linha.erro) == (10, 10, 0, None)


def test_execucao_com_rejeitadas_fecha_com_alerta(pg_engine):
    assert _executar(pg_engine, 10, 8, 2).status == "COM_ALERTA"


def test_carregador_pode_marcar_alerta_mesmo_com_as_contagens_fechando(pg_engine):
    """Um arquivo pulado inteiro não aparece nas contagens: o carregador marca `com_alerta` e a execução não sai OK."""
    with execucao.registrar_execucao(pg_engine, "CAMARA_CSV", "CARREGAR", MARCA) as e:
        e.lidas, e.gravadas, e.rejeitadas = 10, 10, 0
        e.com_alerta = True
    assert _linha(pg_engine, e.id).status == "COM_ALERTA"
    assert _executar(pg_engine, 10, 10, 0).status == "OK"  # sem a marca, as mesmas contagens fecham OK


def test_contagem_ausente_ou_que_nao_fecha_nao_vira_ok(pg_engine, caplog):
    """Desconhecido não é zero: o deploy lê CARREGAR+OK, então uma carga sem contagens não pode aparecer como OK."""
    with caplog.at_level(logging.WARNING, logger="Execucao"):
        sem_contagem = _executar(pg_engine)
        so_lidas = _executar(pg_engine, lidas=5)
        nao_fecha = _executar(pg_engine, 10, 8, 0)  # duas linhas sumiram no caminho
    assert [sem_contagem.status, so_lidas.status, nao_fecha.status] == ["COM_ALERTA"] * 3
    assert sem_contagem.linhas_lidas is None  # fica NULL, nunca zero
    assert "contagens ausentes ou que não fecham" in caplog.text


def test_execucao_que_falha_fica_registrada_como_erro_sem_o_texto_da_excecao(pg_engine):
    class Falha(RuntimeError):
        pass

    anterior = {}
    with pytest.raises(Falha):
        with execucao.registrar_execucao(pg_engine, "CAMARA_CSV", "CARREGAR", MARCA) as e:
            anterior["id"] = e.id
            raise Falha("host 10.0.0.5 recusou a conexão")
    linha = _linha(pg_engine, anterior["id"])
    assert (linha.status, linha.fechada, linha.erro) == ("ERRO", True, "Falha")  # só a classe


def test_carga_desfeita_deixa_o_staging_vazio_e_a_execucao_como_erro(pg_engine, tabela_de_copia):
    """A carga grava e desfaz; a execução, em transação própria, sobrevive como ERRO e o staging não guarda nada."""
    with pytest.raises(ZeroDivisionError):
        with execucao.registrar_execucao(pg_engine, "CAMARA_CSV", "CARREGAR", MARCA) as e:
            with copia.transacao_de_carga(pg_engine) as cursor:
                copia.copiar_linhas(cursor, tabela_de_copia, ["a", "bC"], [["1", "x"], ["2", "y"]])
                assert copia.contar(cursor, tabela_de_copia) == 2  # dentro da transação, as linhas existem
                raise ZeroDivisionError
    assert _linha(pg_engine, e.id).status == "ERRO"
    with pg_engine.connect() as conn:
        assert conn.execute(text(f"SELECT count(*) FROM {tabela_de_copia}")).scalar() == 0


def test_falha_ao_fechar_nao_troca_a_excecao_da_carga(pg_engine, monkeypatch, caplog):
    def quebra(*args, **kwargs):
        raise RuntimeError("banco caiu ao fechar")

    class Falha(Exception):
        pass

    monkeypatch.setattr(execucao, "fechar_execucao", quebra)
    with caplog.at_level(logging.WARNING, logger="Execucao"):
        with pytest.raises(Falha):  # a exceção da carga é a que sobe
            with execucao.registrar_execucao(pg_engine, "CAMARA_CSV", "CARREGAR", MARCA):
                raise Falha
    assert "não pôde ser fechada como ERRO" in caplog.text


def test_falha_ao_fechar_depois_de_uma_carga_boa_vira_aviso_e_a_carga_segue(pg_engine, monkeypatch, caplog):
    """A carga já foi confirmada: perder o registro não pode impedir o merge que vem depois."""

    def quebra(*args, **kwargs):
        raise RuntimeError("banco caiu ao fechar")

    monkeypatch.setattr(execucao, "fechar_execucao", quebra)
    with caplog.at_level(logging.WARNING, logger="Execucao"):
        with execucao.registrar_execucao(pg_engine, "CAMARA_CSV", "CARREGAR", MARCA) as e:
            e.lidas = e.gravadas = e.rejeitadas = 0
    assert "não pôde ser fechada como OK" in caplog.text
    assert _linha(pg_engine, e.id).status == "EXECUTANDO"  # órfã: a próxima abertura da fonte a fecha


def test_execucao_orfa_e_fechada_na_proxima_abertura_da_mesma_fonte(pg_engine):
    with pg_engine.begin() as conn:
        ids = {}
        for chave, fonte, idade in [
            ("velha", "CAMARA_CSV", "7 hours"),
            ("recente", "CAMARA_CSV", "1 hour"),
            ("outra_fonte", "CAMARA_API", "7 hours"),
        ]:
            ids[chave] = conn.execute(
                text(
                    "INSERT INTO etl.execucao (fonte_id, estagio, iniciado_em, parametros) "
                    "SELECT id, 'CARREGAR', now() - CAST(:idade AS interval), CAST(:p AS jsonb) FROM etl.fonte "
                    "WHERE codigo = :fonte RETURNING id"
                ),
                {"idade": idade, "fonte": fonte, "p": '{"teste": "execucao"}'},
            ).scalar()
    execucao.abrir_execucao(pg_engine, "CAMARA_CSV", "CARREGAR", MARCA)
    velha, recente, outra = (_linha(pg_engine, ids[c]) for c in ("velha", "recente", "outra_fonte"))
    assert (velha.status, velha.fechada, velha.erro) == ("ERRO", True, "INTERROMPIDA")
    assert recente.status == "EXECUTANDO" and outra.status == "EXECUTANDO"  # uma carga viva e outra fonte não se tocam


def test_orfa_apos_pode_ser_ajustado_para_cargas_mais_longas(pg_engine):
    with pg_engine.begin() as conn:
        identificador = conn.execute(
            text(
                "INSERT INTO etl.execucao (fonte_id, estagio, iniciado_em, parametros) "
                "SELECT id, 'CARREGAR', now() - interval '7 hours', CAST(:p AS jsonb) FROM etl.fonte "
                "WHERE codigo = 'CAMARA_CSV' RETURNING id"
            ),
            {"p": '{"teste": "execucao"}'},
        ).scalar()
    execucao.abrir_execucao(pg_engine, "CAMARA_CSV", "CARREGAR", MARCA, orfa_apos="12 hours")
    assert _linha(pg_engine, identificador).status == "EXECUTANDO"  # uma carga de até 12 h ainda conta como viva
    execucao.abrir_execucao(pg_engine, "CAMARA_CSV", "CARREGAR", MARCA, orfa_apos="1 hour")
    assert _linha(pg_engine, identificador).status == "ERRO"


def test_entradas_invalidas_sao_recusadas(pg_engine):
    with pytest.raises(ValueError, match="estágio"):
        execucao.abrir_execucao(pg_engine, "CAMARA_CSV", "CARREGUE", MARCA)
    with pytest.raises(ValueError, match="fonte desconhecida"):
        execucao.abrir_execucao(pg_engine, "NAO_EXISTE", "CARREGAR", MARCA)
    for chave in ("carga", "fonte"):  # chaves que o deploy lê para decidir quem é dono das finanças
        with pytest.raises(ValueError, match="deploy"):
            execucao.abrir_execucao(pg_engine, "CAMARA_CSV", "CARREGAR", {**MARCA, chave: "ceap"})


def test_execucao_de_carga_nao_interfere_no_sinal_de_posse_das_financas(pg_engine):
    antes = fontes_do_timer(pg_engine)
    _executar(pg_engine, 0, 0, 0)
    assert fontes_do_timer(pg_engine) == antes


def test_arquivo_bruto_e_registrado_uma_vez_por_conteudo_e_a_primeira_linha_permanece(pg_engine):
    sha = hashlib.sha256(b"conteudo-de-teste").hexdigest()
    primeira = execucao.abrir_execucao(pg_engine, "CAMARA_CSV", "CARREGAR", MARCA)
    segunda = execucao.abrir_execucao(pg_engine, "CAMARA_CSV", "CARREGAR", MARCA)
    with copia.transacao_de_carga(pg_engine) as cursor:
        execucao.registrar_arquivo_bruto(cursor, "CAMARA_CSV", "http://x/a.csv", sha, 17, "/teste/a.csv", primeira.id)
        # o mesmo conteúdo outra vez, por outra execução e com outro tamanho: nada muda (DO NOTHING, não DO UPDATE)
        execucao.registrar_arquivo_bruto(cursor, "CAMARA_CSV", "http://x/b.csv", sha, 99, "/teste/b.csv", segunda.id)
    with pg_engine.connect() as conn:
        linhas = conn.execute(
            text("SELECT execucao_id, bytes, url FROM etl.arquivo_bruto WHERE sha256 = :s"), {"s": sha}
        ).all()
    assert linhas == [(primeira.id, 17, "http://x/a.csv")]


def test_arquivo_bruto_sem_execucao_continua_aceito(pg_engine):
    sha = hashlib.sha256(b"sem-execucao").hexdigest()
    with copia.transacao_de_carga(pg_engine) as cursor:
        execucao.registrar_arquivo_bruto(cursor, "CAMARA_CSV", "http://x/c.csv", sha, 3, "/teste/c.csv")
    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT execucao_id FROM etl.arquivo_bruto WHERE sha256 = :s"), {"s": sha}).all() == [
            (None,)
        ]


@pytest.fixture
def tabela_de_copia(pg_engine):
    nome = f"public.copia_teste_{os.getpid()}"  # um nome por processo: a suíte pode rodar em paralelo
    with pg_engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS {nome}; CREATE TABLE {nome} (a text, "bC" text, execucao_id bigint)'))
    yield nome
    with pg_engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {nome}"))


def _copiar(pg_engine, acao):
    with copia.transacao_de_carga(pg_engine) as cursor:
        return acao(cursor)


def test_contar_linhas_do_csv_ignora_cabecalho_e_conta_registro_com_quebra_de_linha_uma_vez(tmp_path):
    arquivo = tmp_path / "x.csv"
    arquivo.write_text('a;b\n1;"duas\nlinhas"\n2;y\n', encoding="utf-8")
    assert copia.contar_linhas_csv(arquivo) == 2
    so_cabecalho = tmp_path / "so.csv"
    so_cabecalho.write_text("a;b\n", encoding="utf-8")
    vazio = tmp_path / "vazio.csv"
    vazio.write_bytes(b"")
    assert copia.contar_linhas_csv(so_cabecalho) == 0 == copia.contar_linhas_csv(vazio)


def test_copiar_linhas_de_uma_coluna_grava_none_como_nulo_em_texto_e_em_data(pg_engine):
    """O csv.writer escreve `""` entre aspas numa linha de uma coluna só; sem FORCE_NULL isso seria texto vazio (ou erro em date)."""
    with copia.transacao_de_carga(pg_engine) as cursor:
        cursor.execute("CREATE TEMP TABLE _uma_texto (x text) ON COMMIT DROP")
        cursor.execute("CREATE TEMP TABLE _uma_data (d date) ON COMMIT DROP")
        copia.copiar_linhas(cursor, "_uma_texto", ["x"], [[None], ["a"], [""]])
        copia.copiar_linhas(cursor, "_uma_data", ["d"], [[None], ["2024-01-02"]])
        cursor.execute("SELECT count(*) FILTER (WHERE x IS NULL), count(*) FILTER (WHERE x = '') FROM _uma_texto")
        assert cursor.fetchone() == (2, 0)  # None e '' viram NULL; nada vira texto vazio
        cursor.execute("SELECT count(*) FILTER (WHERE d IS NULL), count(d) FROM _uma_data")
        assert cursor.fetchone() == (1, 1)


def test_esvaziar_valida_os_nomes_e_limpa_varias_tabelas_de_uma_vez(pg_engine, tabela_de_copia):
    with copia.transacao_de_carga(pg_engine) as cursor:
        cursor.execute("CREATE TEMP TABLE _outra (x int) ON COMMIT DROP")
        copia.copiar_linhas(cursor, tabela_de_copia, ["a", "bC"], [["1", "x"]])
        copia.copiar_linhas(cursor, "_outra", ["x"], [[1], [2]])
        copia.esvaziar(cursor, [tabela_de_copia, "_outra"])
        assert copia.contar(cursor, tabela_de_copia) == 0 == copia.contar(cursor, "_outra")
        with pytest.raises(ValueError, match="nome de tabela inválido"):
            copia.esvaziar(cursor, ["stg.x; DROP TABLE y"])
        with pytest.raises(ValueError, match="ao menos uma"):
            copia.esvaziar(cursor, [])


def test_copiar_linhas_normalizadas(pg_engine, tabela_de_copia):
    linhas = [["1", 'com,vírgula e "aspas"'], [None, "só b"]]
    assert _copiar(pg_engine, lambda c: copia.copiar_linhas(c, tabela_de_copia, ["a", "bC"], linhas)) == 2
    with pg_engine.connect() as conn:
        lido = conn.execute(text(f'SELECT a, "bC" FROM {tabela_de_copia} ORDER BY a NULLS LAST')).all()
    assert _copiar(pg_engine, lambda c: copia.contar(c, tabela_de_copia)) == 2
    assert lido == [("1", 'com,vírgula e "aspas"'), (None, "só b")]


def test_nomes_e_delimitador_que_nao_sao_simples_sao_recusados(tmp_path):
    class CursorQueNaoDeveSerUsado:
        def __getattr__(self, nome):
            def chamada(*args, **kwargs):
                raise AssertionError("o comando não pode chegar ao banco")

            return chamada

    cursor = CursorQueNaoDeveSerUsado()
    for tabela in ["stg.x; DROP TABLE y", "stg.X", 'stg."x"', "a.b.c", "", "stg.x y"]:
        with pytest.raises(ValueError, match="nome de tabela inválido"):
            copia.copiar_linhas(cursor, tabela, ["a"], [["1"]])
        with pytest.raises(ValueError, match="nome de tabela inválido"):
            copia.contar(cursor, tabela)
    arquivo = tmp_path / "a.csv"
    arquivo.write_text("a\n1\n", encoding="utf-8")
    for delimitador in ["'", '"', "\\", "\n", "", ";;"]:
        with pytest.raises(ValueError, match="delimitador inválido"):
            copia.contar_linhas_csv(arquivo, delimitador)
    assert copia.contar_linhas_csv(arquivo, "|") == 1


def test_tabelas_temporarias_sem_schema_continuam_aceitas(pg_engine):
    with copia.transacao_de_carga(pg_engine) as cursor:
        cursor.execute("CREATE TEMP TABLE _tmp_copia (codigo int, data date) ON COMMIT DROP")
        assert copia.copiar_linhas(cursor, "_tmp_copia", ["codigo", "data"], [[1, "2024-01-02"], [None, None]]) == 2
        assert copia.contar(cursor, "_tmp_copia") == 2


def test_transacao_de_carga_confirma_desfaz_e_devolve_a_conexao(pg_engine, tabela_de_copia):
    with copia.transacao_de_carga(pg_engine) as cursor:
        cursor.execute(f"INSERT INTO {tabela_de_copia} (a) VALUES ('ok')")
    with pytest.raises(RuntimeError):
        with copia.transacao_de_carga(pg_engine) as cursor:
            cursor.execute(f"INSERT INTO {tabela_de_copia} (a) VALUES ('desfeito')")
            raise RuntimeError
    with pg_engine.connect() as conn:
        assert [r[0] for r in conn.execute(text(f"SELECT a FROM {tabela_de_copia}"))] == ["ok"]


# ---------------------------------------------------------------------------------------------- verificações e rejeitos
def _verificacoes(pg_engine, execucao_id):
    with pg_engine.connect() as conn:
        return {
            r.nome: (r.passou, r.detalhe)
            for r in conn.execute(
                text("SELECT nome, passou, detalhe FROM etl.verificacao WHERE execucao_id = :id"), {"id": execucao_id}
            )
        }


def test_verificacoes_medidas_e_a_de_contagens_vao_para_etl_verificacao(pg_engine):
    from etl.utils.verificacoes import cobertura_minima, sem_duplicatas

    with execucao.registrar_execucao(pg_engine, "CAMARA_CSV", "CARREGAR", MARCA) as e:
        e.lidas, e.gravadas, e.rejeitadas = 10, 10, 0
        e.verificar(sem_duplicatas("ids_unicos", [1, 2, 3]))
        e.verificar(cobertura_minima("cobertura", 10, 10))
    registradas = _verificacoes(pg_engine, e.id)
    assert set(registradas) == {"ids_unicos", "cobertura", "contagens"}
    assert all(passou for passou, _ in registradas.values())
    assert _linha(pg_engine, e.id).status == "OK"


def test_verificacao_reprovada_deixa_a_execucao_em_alerta_e_o_detalhe_explica(pg_engine):
    from etl.utils.verificacoes import sem_duplicatas

    with execucao.registrar_execucao(pg_engine, "CAMARA_CSV", "CARREGAR", MARCA) as e:
        e.lidas, e.gravadas, e.rejeitadas = 3, 3, 0  # as contagens fecham e nada foi rejeitado
        e.verificar(sem_duplicatas("ids_unicos", [1, 1, 2]))
    passou, detalhe = _verificacoes(pg_engine, e.id)["ids_unicos"]
    assert passou is False and detalhe["repetidas"] == 1
    assert _linha(pg_engine, e.id).status == "COM_ALERTA"


def test_contagem_desconhecida_registra_a_verificacao_reprovada_sem_virar_zero(pg_engine):
    with execucao.registrar_execucao(pg_engine, "CAMARA_CSV", "CARREGAR", MARCA) as e:
        pass  # nenhuma contagem informada
    assert _verificacoes(pg_engine, e.id)["contagens"][0] is False
    linha = _linha(pg_engine, e.id)
    assert (linha.linhas_lidas, linha.linhas_gravadas, linha.linhas_rejeitadas) == (None, None, None)


def test_rejeitadas_por_motivo_viram_um_registro_agregado_em_etl_rejeito(pg_engine):
    contagem = execucao.Contagem()
    for _ in range(5):
        contagem.ler()
    contagem.gravar(3)
    contagem.rejeitar("NAO_CADASTRADO", 2)
    with execucao.registrar_execucao(pg_engine, "CAMARA_CSV", "CARREGAR", {**MARCA, "recurso": "demo"}) as e:
        e.aplicar(contagem)
    with pg_engine.connect() as conn:
        rejeitos = conn.execute(
            text("SELECT recurso, motivo, (payload->>'total')::int FROM etl.rejeito WHERE execucao_id = :id"),
            {"id": e.id},
        ).all()
    assert [tuple(r) for r in rejeitos] == [("demo", "NAO_CADASTRADO", 2)]
    linha = _linha(pg_engine, e.id)
    assert (linha.status, linha.linhas_lidas, linha.linhas_gravadas, linha.linhas_rejeitadas) == ("COM_ALERTA", 5, 3, 2)


def test_contagem_soma_motivos_e_fecha():
    a, b = execucao.Contagem(lidas=3, gravadas=2), execucao.Contagem(lidas=2, gravadas=1)
    a.rejeitar("X")
    b.rejeitar("X")
    b.rejeitar("Y")
    soma = a + b
    assert (soma.lidas, soma.gravadas, soma.rejeitadas, soma.motivos) == (5, 3, 3, {"X": 2, "Y": 1})
    assert soma.lidas != soma.gravadas + soma.rejeitadas  # o exemplo não fecha de propósito: quem confere é a execução


def test_fonte_da_esteira_existe_depois_da_migracao_0039(pg_engine):
    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM etl.fonte WHERE codigo = 'PIPELINE'")).scalar() == 1
