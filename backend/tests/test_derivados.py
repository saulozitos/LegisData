"""Derivados pré-calculados do legislativo: iguais ao cálculo original e nunca velhos."""

import threading
import time
from pathlib import Path

import pytest
from app.services import derivados_service
from app.services.derivados_service import descartar_motores, garantir_atualizados
from app.services.legislative_scoring import MAX_AUTORES_POR_PROPOSICAO
from sqlalchemy import text

BASE = "/api/v1"
APP = Path(__file__).resolve().parents[1] / "app"
DEPENDENCIAS = [
    "leg.autoria",
    "leg.proposicao",
    "param.peso",
    "param.metodologia",
    "ref.tipo_proposicao",
    "core.filiacao",
    "core.mandato",
]


@pytest.fixture(autouse=True)
def _sem_estado_entre_testes(pg_engine):
    """Cada teste começa com os derivados em dia e sem pool dedicado herdado do anterior."""
    descartar_motores()
    yield
    descartar_motores()
    with pg_engine.begin() as conn:
        conn.execute(text("SET LOCAL statement_timeout = '20s'"))
        conn.execute(text("SELECT leg.atualizar_derivados(true, '20s')"))


def _sujo(db):
    return db.execute(text("SELECT sujo FROM leg.pontuacao_controle")).scalar()


def _diferencas_entre_visao_e_derivado(db):
    return db.execute(
        text(
            """
            SELECT count(*) FROM (
                (SELECT * FROM leg.vw_autoria_pontuada_unica EXCEPT SELECT * FROM leg.mv_autoria_pontuada_unica)
                UNION ALL
                (SELECT * FROM leg.mv_autoria_pontuada_unica EXCEPT SELECT * FROM leg.vw_autoria_pontuada_unica)
            ) d
            """
        )
    ).scalar()


def test_derivado_de_pontuacao_e_igual_ao_calculo_original(client, db, seed):
    client.get(f"{BASE}/politicians")  # a ponte do legado projeta o seed
    garantir_atualizados(db)
    assert db.execute(text("SELECT count(*) FROM leg.mv_autoria_pontuada_unica")).scalar() > 0
    assert _diferencas_entre_visao_e_derivado(db) == 0


def test_garantir_so_refaz_quando_algo_mudou(client, db, seed):
    client.get(f"{BASE}/politicians")
    garantir_atualizados(db)
    assert _sujo(db) is False
    assert garantir_atualizados(db) is False  # nada mudou: não refaz
    db.execute(text("UPDATE leg.proposicao SET titulo = titulo"))
    db.commit()
    assert _sujo(db) is True
    assert garantir_atualizados(db) is True and _sujo(db) is False


@pytest.mark.parametrize("tabela", DEPENDENCIAS)
def test_toda_tabela_de_que_o_calculo_depende_liga_o_sinalizador(client, db, seed, tabela):
    client.get(f"{BASE}/politicians")
    garantir_atualizados(db)
    assert _sujo(db) is False
    db.execute(text(f"DELETE FROM {tabela} WHERE false"))  # o gatilho é por comando: dispara mesmo sem linhas
    db.commit()
    assert _sujo(db) is True


@pytest.mark.parametrize("tabela", DEPENDENCIAS)
def test_esvaziar_a_tabela_tambem_liga_o_sinalizador(client, db, seed, tabela):
    client.get(f"{BASE}/politicians")
    garantir_atualizados(db)
    assert _sujo(db) is False
    try:
        db.execute(text(f"TRUNCATE {tabela} CASCADE"))
        assert _sujo(db) is True
    finally:
        db.rollback()  # nada de TRUNCATE de verdade neste teste, nem se o assert falhar


def test_controle_esvaziado_conta_como_sujo_e_volta_a_existir(client, db, seed):
    client.get(f"{BASE}/politicians")
    garantir_atualizados(db)
    db.execute(text("DELETE FROM leg.pontuacao_controle"))
    db.commit()
    assert garantir_atualizados(db) is True  # sem a linha de controle, refaz por precaução
    assert _sujo(db) is False


def test_ranking_de_autores_acompanha_uma_mudanca_na_mesma_hora(client, db, seed):
    def score_do_fulano():
        ranking = client.get(f"{BASE}/legislative/ranking/authors", params={"limit": 50}).json()
        return next(r for r in ranking if r["nome_eleitoral"] == "Fulano")["score_ialp"]

    antes = score_do_fulano()
    pessoa = db.execute(text("SELECT id FROM core.pessoa WHERE uid = :u"), {"u": seed.fulano.id}).scalar()
    atual = db.execute(
        text("SELECT tipo_codigo FROM leg.autoria WHERE pessoa_id = :a ORDER BY id LIMIT 1"), {"a": pessoa}
    ).scalar()
    novo = "COAUTOR" if atual == "AUTOR_PRINCIPAL" else "AUTOR_PRINCIPAL"
    db.execute(text("UPDATE leg.autoria SET tipo_codigo = :t WHERE pessoa_id = :a"), {"t": novo, "a": pessoa})
    db.commit()
    depois = score_do_fulano()
    esperado = db.execute(
        text("SELECT round(sum(pontos_ialp)::numeric, 1) FROM leg.vw_autoria_pontuada_unica WHERE pessoa_id = :a"),
        {"a": pessoa},
    ).scalar()
    assert depois == float(esperado) and depois != antes  # o papel mudou e o ranking já mostra o novo total


def test_pares_de_coautoria_respeitam_o_limite_de_autores_do_codigo(db):
    """Mudar `MAX_AUTORES_POR_PROPOSICAO` sem refazer `leg.mv_coautoria_par` deixaria a rede inconsistente."""
    comentario = db.execute(text("SELECT obj_description('leg.mv_coautoria_par'::regclass, 'pg_class')")).scalar()
    assert comentario == f"max_autores={MAX_AUTORES_POR_PROPOSICAO}"


def _proposicao_com_autores(db, numero, n_pessoas, institucionais=0):
    """Cria uma proposição com `n_pessoas` autores (pessoas novas) e `institucionais` autorias de órgão."""
    tipo = db.execute(text("SELECT codigo FROM ref.tipo_proposicao ORDER BY codigo LIMIT 1")).scalar()
    status = db.execute(text("SELECT codigo FROM ref.status_tramitacao ORDER BY codigo LIMIT 1")).scalar()
    proposicao = db.execute(
        text(
            "INSERT INTO leg.proposicao (tipo_codigo, numero, ano, titulo, data_apresentacao, status_codigo)"
            " VALUES (:t, :n, 2023, :ti, '2023-03-01', :s) RETURNING id"
        ),
        {"t": tipo, "n": numero, "ti": f"Proposição {numero}", "s": status},
    ).scalar()
    pessoas = []
    for i in range(n_pessoas):
        pessoa = db.execute(
            text("INSERT INTO core.pessoa (nome_exibicao) VALUES (:n) RETURNING id"), {"n": f"Autor {numero}-{i}"}
        ).scalar()
        pessoas.append(pessoa)
        db.execute(
            text(
                "INSERT INTO leg.autoria (proposicao_id, pessoa_id, nome_autor, tipo_codigo, ordem)"
                " VALUES (:p, :a, :n, :t, :o)"
            ),
            {
                "p": proposicao,
                "a": pessoa,
                "n": f"Autor {numero}-{i}",
                "t": "AUTOR_PRINCIPAL" if i == 0 else "COAUTOR",
                "o": i + 1,
            },
        )
    for j in range(institucionais):
        db.execute(
            text(
                "INSERT INTO leg.autoria (proposicao_id, nome_autor, tipo_codigo, ordem)"
                " VALUES (:p, 'Comissão', 'INSTITUCIONAL', :o)"
            ),
            {"p": proposicao, "o": 100 + j},
        )
    return proposicao, pessoas


def test_pares_de_coautoria_cobrem_so_proposicoes_conjuntas_dentro_do_limite(db):
    sozinha, _ = _proposicao_com_autores(db, 1, 1)
    dupla, pessoas_da_dupla = _proposicao_com_autores(db, 2, 2)
    so_uma_pessoa_com_orgao, _ = _proposicao_com_autores(db, 3, 1, institucionais=1)  # órgão não faz par
    no_limite, _ = _proposicao_com_autores(db, 4, MAX_AUTORES_POR_PROPOSICAO)
    acima, _ = _proposicao_com_autores(db, 5, MAX_AUTORES_POR_PROPOSICAO + 1)  # assinatura em massa
    db.commit()
    assert garantir_atualizados(db) is True

    contagem = dict(
        db.execute(text("SELECT proposicao_id, count(*) FROM leg.mv_coautoria_par GROUP BY proposicao_id")).all()
    )
    n = MAX_AUTORES_POR_PROPOSICAO
    assert contagem == {dupla: 1, no_limite: n * (n - 1) // 2}  # nem a sozinha, nem a do órgão, nem a acima do limite
    assert not {sozinha, so_uma_pessoa_com_orgao, acima} & set(contagem)
    par = db.execute(
        text("SELECT pessoa_a, pessoa_b, n_autores FROM leg.mv_coautoria_par WHERE proposicao_id = :p"), {"p": dupla}
    ).one()
    assert (par[0], par[1], par[2]) == (min(pessoas_da_dupla), max(pessoas_da_dupla), 2)


def test_derivado_de_coautoria_equivale_ao_calculo_direto(db):
    """A rede lê o derivado: com proposições de vários tamanhos, os pares têm de bater com o SELECT direto."""
    for numero, n_pessoas, orgaos in ((1, 2, 0), (2, 3, 1), (3, 1, 1), (4, MAX_AUTORES_POR_PROPOSICAO + 1, 0)):
        _proposicao_com_autores(db, numero, n_pessoas, orgaos)
    db.commit()
    garantir_atualizados(db)
    direto = """
        SELECT a.proposicao_id, a.pessoa_id AS pessoa_a, b.pessoa_id AS pessoa_b
        FROM (SELECT DISTINCT proposicao_id, pessoa_id FROM leg.autoria
              WHERE pessoa_id IS NOT NULL AND tipo_codigo <> 'INSTITUCIONAL') a
        JOIN (SELECT DISTINCT proposicao_id, pessoa_id FROM leg.autoria
              WHERE pessoa_id IS NOT NULL AND tipo_codigo <> 'INSTITUCIONAL') b
          ON b.proposicao_id = a.proposicao_id AND a.pessoa_id < b.pessoa_id
        WHERE a.proposicao_id IN (SELECT proposicao_id FROM leg.autoria WHERE pessoa_id IS NOT NULL
                                  AND tipo_codigo <> 'INSTITUCIONAL' GROUP BY 1
                                  HAVING count(DISTINCT pessoa_id) BETWEEN 2 AND :maximo)
    """
    derivado = "SELECT proposicao_id, pessoa_a, pessoa_b FROM leg.mv_coautoria_par"
    diferencas = db.execute(
        text(f"SELECT count(*) FROM (({direto} EXCEPT {derivado}) UNION ALL ({derivado} EXCEPT {direto})) d"),
        {"maximo": MAX_AUTORES_POR_PROPOSICAO},
    ).scalar()
    assert diferencas == 0 and db.execute(text("SELECT count(*) FROM leg.mv_coautoria_par")).scalar() > 0


def test_papel_de_leitura_enxerga_os_derivados(db):
    for visao in ("leg.mv_autoria_pontuada_unica", "leg.mv_coautoria_par"):
        assert db.execute(
            text("SELECT has_table_privilege('legisdata_leitura', CAST(:v AS regclass), 'SELECT')"), {"v": visao}
        ).scalar()


def _marcar_sujo(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("UPDATE leg.proposicao SET titulo = titulo"))  # o gatilho é por comando


def _sujo_no_banco(pg_engine):
    with pg_engine.connect() as conn:
        return conn.execute(text("SELECT sujo FROM leg.pontuacao_controle")).scalar()


def _atualizar(pg_engine, bloquear=False, espera="500ms", teto="20s"):
    """Chama a função do banco; o `statement_timeout` faz um defeito de trava virar falha em segundos, não suíte parada."""
    with pg_engine.begin() as conn:
        conn.execute(text(f"SET LOCAL statement_timeout = '{teto}'"))
        return conn.execute(text("SELECT leg.atualizar_derivados(:b, :e)"), {"b": bloquear, "e": espera}).scalar()


def _na_fila_do_bloqueio(conn, chave):
    """Quantas chamadas esperam o bloqueio consultivo `chave` neste banco (o `pg_locks` vale para o cluster inteiro)."""
    return conn.execute(
        text(
            "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted AND objid = :k "
            "AND database = (SELECT oid FROM pg_database WHERE datname = current_database())"
        ),
        {"k": chave},
    ).scalar()


def _esperando_trava_de_linha(conn, trecho):
    """Quantas sessões deste banco esperam uma trava (de linha ou transação) com uma consulta que contém `trecho`."""
    # `pg_stat_activity` fica em cache até o fim da transação: sem limpar, a segunda leitura repete a primeira
    conn.execute(text("SELECT pg_stat_clear_snapshot()"))
    return conn.execute(
        text(
            "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND wait_event_type = 'Lock' "
            "AND query LIKE :q AND pid <> pg_backend_pid()"
        ),
        {"q": f"%{trecho}%"},
    ).scalar()


def _constante_da_migracao_0037(nome):
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from app.core.migrations import BACKEND_DIR

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return getattr(ScriptDirectory.from_config(config).get_revision("0037").module, nome)


def test_estado_devolvido_distingue_refeito_em_dia_e_ocupado(pg_engine):
    _marcar_sujo(pg_engine)
    assert _atualizar(pg_engine) == "refeito"
    assert _atualizar(pg_engine) == "em_dia"
    _marcar_sujo(pg_engine)
    outra = pg_engine.connect()
    transacao = outra.begin()
    try:
        outra.execute(
            text("SELECT pg_advisory_xact_lock(:k)"), {"k": _constante_da_migracao_0037("BLOQUEIO_DA_ATUALIZACAO")}
        )
        assert _atualizar(pg_engine) == "ocupado"  # a vez é de outra atualização
    finally:
        transacao.rollback()
        outra.close()


def test_leitura_nao_fica_presa_atras_de_uma_carga_em_andamento(pg_engine):
    """Uma carga que já escreveu numa tabela dependente segura a linha de controle: o leitor desiste e não bloqueia."""
    _marcar_sujo(pg_engine)
    carga = pg_engine.connect()
    transacao = carga.begin()
    try:
        carga.execute(text("UPDATE leg.proposicao SET titulo = titulo"))  # trava a linha de controle até o commit
        inicio = time.monotonic()
        assert _atualizar(pg_engine) == "ocupado"
        assert time.monotonic() - inicio < 5  # esperou no máximo o lock_timeout, não a carga inteira
        assert _sujo_no_banco(pg_engine) is True  # a tentativa desfeita não perde o aviso
    finally:
        transacao.rollback()
        carga.close()
    assert _atualizar(pg_engine) == "refeito" and _sujo_no_banco(pg_engine) is False  # sem a carga, refaz


def test_etl_espera_a_vez_em_vez_de_desistir(pg_engine):
    """O ETL chama em modo bloqueante: se outra atualização segura a vez por um instante, ele espera e refaz."""
    _marcar_sujo(pg_engine)
    chave = _constante_da_migracao_0037("BLOQUEIO_DA_ATUALIZACAO")
    outra = pg_engine.connect()
    transacao = outra.begin()
    resultado = []
    espera = threading.Thread(target=lambda: resultado.append(_atualizar(pg_engine, bloquear=True, espera="20s")))
    iniciada = False
    try:
        outra.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": chave})
        espera.start()
        iniciada = True
        with pg_engine.connect() as conn:
            for _ in range(100):  # espera, sem dormir às cegas, a chamada do ETL aparecer na fila do bloqueio
                na_fila = _na_fila_do_bloqueio(conn, chave)
                if na_fila:
                    break
                time.sleep(0.1)
            assert na_fila, "a chamada do ETL não ficou esperando o bloqueio"
        assert not resultado  # esperando de verdade: quem desiste já teria devolvido 'ocupado'
    finally:
        transacao.rollback()
        outra.close()
        if iniciada:
            espera.join(timeout=30)
    assert resultado == ["refeito"]


def test_etl_desiste_com_aviso_se_a_vez_nao_chega(pg_engine):
    _marcar_sujo(pg_engine)
    chave = _constante_da_migracao_0037("BLOQUEIO_DA_ATUALIZACAO")
    outra = pg_engine.connect()
    transacao = outra.begin()
    try:
        outra.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": chave})
        assert _atualizar(pg_engine, bloquear=True, espera="1s") == "ocupado"
        assert _sujo_no_banco(pg_engine) is True
    finally:
        transacao.rollback()
        outra.close()


def test_gravacao_durante_a_atualizacao_nao_se_perde(pg_engine):
    """
    O sinalizador é desligado ANTES do refresh: quem escreve enquanto o refresh roda espera a linha de controle, que a
    atualização já travou, e religa o sinalizador depois dela. Com a ordem inversa (refresh e só então desligar) o
    escritor confirmaria no meio e a atualização apagaria o aviso dele: o teste solta a atualização, deixa as duas
    terminarem e exige o sinalizador ligado SEM nenhuma gravação posterior.
    """
    _marcar_sujo(pg_engine)
    segurando = pg_engine.connect()
    transacao = segurando.begin()
    erros = []
    resultado = []

    def atualizar():
        try:
            resultado.append(_atualizar(pg_engine, bloquear=True, espera="30s", teto="60s"))
        except Exception as exc:  # noqa: BLE001 - registrado e afirmado abaixo
            erros.append(exc)

    def escrever():
        try:
            with pg_engine.begin() as conn:
                conn.execute(text("SET LOCAL lock_timeout = '40s'"))
                conn.execute(text("UPDATE leg.proposicao SET titulo = titulo  /* escritor do teste */"))
        except Exception as exc:  # noqa: BLE001 - registrado e afirmado abaixo
            erros.append(exc)

    atualizacao = threading.Thread(target=atualizar)
    escritor = threading.Thread(target=escrever)
    iniciadas = []
    try:
        # o `REFRESH` lê `leg.autoria`: com ela travada, a atualização desliga o sinalizador e para no REFRESH
        segurando.execute(text("LOCK TABLE leg.autoria IN ACCESS EXCLUSIVE MODE"))
        atualizacao.start()
        iniciadas.append(atualizacao)
        with pg_engine.connect() as conn:
            for _ in range(
                100
            ):  # espera, sem dormir às cegas, a atualização chegar ao REFRESH e parar na trava da tabela
                esperando = conn.execute(
                    text(
                        "SELECT count(*) FROM pg_locks WHERE NOT granted AND locktype = 'relation' "
                        "AND relation = 'leg.autoria'::regclass"
                    )
                ).scalar()
                if esperando:
                    break
                time.sleep(0.1)
            assert esperando, "a atualização não chegou ao REFRESH"
            escritor.start()
            iniciadas.append(escritor)
            for _ in range(100):  # o escritor tem de ficar esperando a linha de controle que a atualização segura
                preso = _esperando_trava_de_linha(conn, "escritor do teste")
                if preso:
                    break
                time.sleep(0.1)
            if not preso:
                atividade = conn.execute(
                    text(
                        "SELECT state, wait_event_type, wait_event, left(query, 70) FROM pg_stat_activity "
                        "WHERE datname = current_database() AND pid <> pg_backend_pid()"
                    )
                ).all()
            assert (
                preso
            ), f"o escritor não esperou a atualização: a gravação poderia ser apagada por ela: {atividade} {erros}"
    finally:
        transacao.rollback()  # solta a tabela: a atualização termina o REFRESH e só então o escritor segue
        segurando.close()
        for fio in iniciadas:
            fio.join(timeout=90)
    assert not erros and resultado == ["refeito"]
    assert _sujo_no_banco(pg_engine) is True  # a gravação que terminou depois do refresh deixou o aviso ligado


def test_cargas_concorrentes_nao_entram_em_deadlock(pg_engine, db):
    """
    Duas transações que escrevem nas dependências pegam a trava de controle ANTES de qualquer linha de dado (gatilho
    `BEFORE`), então a segunda espera sem segurar a linha que a primeira vai tocar. Com o gatilho `AFTER` a segunda
    atualizava a linha, esperava o controle, e a primeira, ao tocar a mesma linha, fechava o ciclo: deadlock.
    """
    proposicao, _ = _proposicao_com_autores(db, 900, 1)
    db.commit()
    primeira = pg_engine.connect()
    transacao = primeira.begin()
    erros = []

    def segunda():
        try:
            with pg_engine.begin() as conn:
                conn.execute(text("SET LOCAL lock_timeout = '30s'"))
                conn.execute(
                    text("UPDATE leg.proposicao SET titulo = 'segunda /* segunda carga */' WHERE id = :p"),
                    {"p": proposicao},
                )
        except Exception as exc:  # noqa: BLE001 - registrado e afirmado abaixo
            erros.append(exc)

    fio = threading.Thread(target=segunda)
    iniciado = False
    try:
        primeira.execute(text("SET LOCAL lock_timeout = '30s'"))
        primeira.execute(text("DELETE FROM param.peso WHERE false"))  # só o gatilho: a primeira segura o controle
        fio.start()
        iniciado = True
        with pg_engine.connect() as conn:
            for _ in range(100):
                preso = _esperando_trava_de_linha(conn, "segunda carga")
                if preso:
                    break
                time.sleep(0.1)
            assert preso, "a segunda carga não esperou a trava de controle"
        primeira.execute(
            text("UPDATE leg.proposicao SET titulo = 'primeira' WHERE id = :p"), {"p": proposicao}
        )  # a mesma linha: com o AFTER isto fechava o ciclo
        transacao.commit()
    finally:
        if transacao.is_active:
            transacao.rollback()
        primeira.close()
        if iniciado:
            fio.join(timeout=60)
    assert not erros, erros


def test_dono_dos_derivados_nao_e_superusuario_e_o_publico_nao_executa(pg_engine):
    with pg_engine.connect() as conn:
        definidor, dono_super, acl = conn.execute(
            text(
                "SELECT p.prosecdef, r.rolsuper, p.proacl::text FROM pg_proc p JOIN pg_roles r ON r.oid = p.proowner "
                "WHERE p.oid = 'leg.atualizar_derivados(boolean, text)'::regprocedure"
            )
        ).one()
        donos = {
            linha[0]
            for linha in conn.execute(
                text(
                    "SELECT r.rolname FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner "
                    "WHERE c.oid IN ('leg.mv_autoria_pontuada_unica'::regclass, 'leg.mv_coautoria_par'::regclass, "
                    "'leg.pontuacao_controle'::regclass)"
                )
            )
        }
    assert definidor is True and dono_super is False and donos == {"legisdata_derivados"}
    assert "legisdata_leitura" not in acl and "{=X" not in acl and ",=X" not in acl  # nem leitura nem PUBLIC executam
    with pg_engine.connect() as conn:
        acl_leitura = conn.execute(
            text("SELECT proacl::text FROM pg_proc WHERE oid = 'leg.atualizar_derivados_leitura()'::regprocedure")
        ).scalar()
    assert "legisdata_leitura=X" in acl_leitura and "{=X" not in acl_leitura and ",=X" not in acl_leitura
    with pg_engine.connect() as conn:
        # o gatilho que acende o sinalizador também não é do público (senão o papel de leitura o ligaria a um gatilho seu)
        acl_gatilho = conn.execute(
            text("SELECT proacl::text FROM pg_proc WHERE oid = 'leg.marcar_derivados_sujos()'::regprocedure")
        ).scalar()
    assert (
        acl_gatilho and "{=X" not in acl_gatilho and ",=X" not in acl_gatilho and "legisdata_leitura" not in acl_gatilho
    )


def test_papel_de_leitura_atualiza_os_derivados_mas_nao_escreve_direto(pg_engine):
    _marcar_sujo(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("SET LOCAL ROLE legisdata_leitura"))
        assert conn.execute(text("SELECT sujo FROM leg.pontuacao_controle")).scalar() is True  # a API lê o sinalizador
        assert conn.execute(text("SELECT leg.atualizar_derivados_leitura()")).scalar() == "refeito"
    with pg_engine.connect() as conn:
        conn.execute(text("SET ROLE legisdata_leitura"))
        with pytest.raises(Exception, match="permission denied"):
            conn.execute(text("UPDATE leg.pontuacao_controle SET sujo = false"))
    with pg_engine.connect() as conn:  # a porta com espera livre é do ETL: o papel de leitura não a executa
        conn.execute(text("SET ROLE legisdata_leitura"))
        with pytest.raises(Exception, match="permission denied"):
            conn.execute(text("SELECT leg.atualizar_derivados(true, '0')"))


def test_garantir_atualizados_nao_toca_na_transacao_de_quem_chama(db, pg_engine):
    """A atualização roda em conexão própria: nada pendente na sessão do chamador é confirmado."""
    _marcar_sujo(pg_engine)
    db.execute(text("INSERT INTO core.pessoa (nome_exibicao) VALUES ('Pendente')"))  # sem commit
    assert garantir_atualizados(db) is True
    db.rollback()
    assert db.execute(text("SELECT count(*) FROM core.pessoa WHERE nome_exibicao = 'Pendente'")).scalar() == 0


def test_derivado_em_dia_nao_usa_conexao_extra_do_pool(pg_engine, caplog):
    """
    O sinalizador é lido na sessão do chamador: com tudo em dia, um pool de uma conexão basta. Uma segunda conexão do
    pool do chamador estouraria o `pool_timeout`, que `garantir_atualizados` engole como aviso e devolve False: por isso
    o teste exige também que não haja aviso e que o pool dedicado dos derivados nem tenha sido criado.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    _atualizar(pg_engine)  # garante em dia
    pequeno = create_engine(pg_engine.url, pool_size=1, max_overflow=0, pool_timeout=1)
    try:
        with Session(pequeno) as sessao:
            sessao.execute(text("SELECT 1"))  # a sessão segura a única conexão
            with caplog.at_level("WARNING"):
                assert garantir_atualizados(sessao) is False
            assert pequeno.pool.checkedout() == 1
        assert not caplog.records
        assert derivados_service._motores == {}
    finally:
        pequeno.dispose()


def test_derivado_velho_atualiza_em_pool_proprio_sem_esgotar_o_da_requisicao(pg_engine):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    _marcar_sujo(pg_engine)
    pequeno = create_engine(pg_engine.url, pool_size=1, max_overflow=0, pool_timeout=1)
    try:
        with Session(pequeno) as sessao:
            sessao.execute(text("SELECT 1"))
            assert garantir_atualizados(sessao) is True  # com o pool da requisição todo ocupado, não trava nem falha
            assert pequeno.pool.checkedout() == 1
    finally:
        pequeno.dispose()


def test_falha_na_atualizacao_vira_aviso_e_a_leitura_segue(db, pg_engine, monkeypatch, caplog):
    from app.services import derivados_service
    from sqlalchemy.exc import OperationalError

    _marcar_sujo(pg_engine)

    class Quebrado:
        def begin(self):
            raise OperationalError("SELECT", {}, Exception("sem conexão"))

    monkeypatch.setattr(derivados_service, "_motor_da_atualizacao", lambda motor: Quebrado())
    with caplog.at_level("WARNING"):
        assert garantir_atualizados(db) is False
    assert any("não atualizados" in r.getMessage() for r in caplog.records)


def test_garantir_atualizados_com_a_vez_ocupada_segue_sem_refazer(db, pg_engine, caplog):
    """A função do banco devolve 'ocupado': o serviço não refaz, não avisa e deixa o sinalizador ligado."""
    _marcar_sujo(pg_engine)
    outra = pg_engine.connect()
    transacao = outra.begin()
    try:
        outra.execute(
            text("SELECT pg_advisory_xact_lock(:k)"), {"k": _constante_da_migracao_0037("BLOQUEIO_DA_ATUALIZACAO")}
        )
        with caplog.at_level("WARNING"):
            assert garantir_atualizados(db) is False
    finally:
        transacao.rollback()
        outra.close()
    assert _sujo_no_banco(pg_engine) is True
    assert not caplog.records


def test_sinalizador_ilegivel_nao_deixa_a_sessao_de_quem_chama_quebrada(db, monkeypatch, caplog):
    """Se o SELECT do sinalizador falhar na sessão do chamador, ela é desfeita: a consulta seguinte dele funciona."""

    def quebrado(sessao):
        sessao.execute(text("SELECT * FROM leg.tabela_que_nao_existe"))

    monkeypatch.setattr(derivados_service, "derivados_velhos", quebrado)
    with caplog.at_level("WARNING"):
        assert garantir_atualizados(db) is False
    assert db.execute(text("SELECT 1")).scalar() == 1  # sem o rollback: InFailedSqlTransaction
    assert any("ilegível" in r.getMessage() for r in caplog.records)


def test_pool_dedicado_usa_a_fabrica_do_app(pg_engine):
    """O pool dos derivados herda as opções da fábrica única (`hide_parameters`, `pool_recycle`), só com tamanho próprio."""
    from app.core.database import POOL_RECYCLE_SEGUNDOS

    motor = derivados_service._motor_da_atualizacao(pg_engine)
    assert motor.pool.size() == 1 and motor.pool._max_overflow == 0
    assert motor.pool._recycle == POOL_RECYCLE_SEGUNDOS and motor.hide_parameters is True


def test_quem_le_um_derivado_chama_garantir_atualizados():
    """Esquecer a chamada serviria dado velho: toda FUNÇÃO de `app` que lê um derivado tem de atualizá-lo antes."""
    import ast

    leitores = []
    for arquivo in APP.rglob("*.py"):
        if arquivo.name == "derivados_service.py":
            continue
        fonte = arquivo.read_text(encoding="utf-8")
        if "leg.mv_" not in fonte:
            continue
        arvore = ast.parse(fonte)
        constantes = {  # SQL guardado em constante de módulo conta para a função que a usa
            no.targets[0].id
            for no in arvore.body
            if isinstance(no, ast.Assign)
            and isinstance(no.targets[0], ast.Name)
            and "leg.mv_" in (ast.get_source_segment(fonte, no) or "")
        }
        for funcao in (n for n in ast.walk(arvore) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
            primeira = funcao.body[0] if funcao.body else None
            docstring = (
                primeira.value if isinstance(primeira, ast.Expr) else None
            )  # citar o nome na docstring não é ler
            usos = [  # onde a função nomeia o derivado: no texto do SQL ou na constante que o guarda
                no.lineno
                for no in ast.walk(funcao)
                if no is not docstring
                and (
                    (isinstance(no, ast.Constant) and isinstance(no.value, str) and "leg.mv_" in no.value)
                    or (isinstance(no, ast.Name) and no.id in constantes)
                )
            ]
            if usos:
                # uma CHAMADA de verdade (comentário ou docstring citando o nome não conta) e ANTES do primeiro uso do derivado
                chamadas = [
                    no.lineno
                    for no in ast.walk(funcao)
                    if isinstance(no, ast.Call)
                    and (getattr(no.func, "id", None) or getattr(no.func, "attr", None)) == "garantir_atualizados"
                ]
                leitores.append((arquivo.name, funcao.name, bool(chamadas) and min(chamadas) < min(usos)))
    assert leitores, "nenhum leitor encontrado: o teste deixou de proteger"
    assert [(a, f) for a, f, chama in leitores if not chama] == []


def _sujo_depois(client, pg_engine, caminho, **params):
    _marcar_sujo(pg_engine)
    assert _sujo_no_banco(pg_engine) is True
    assert client.get(caminho, params=params).status_code == 200
    return _sujo_no_banco(pg_engine)


@pytest.mark.parametrize(
    "caminho",
    [
        f"{BASE}/legislative/ranking/authors",
        f"{BASE}/attendance/ranking/politicians",
        f"{BASE}/legislative/network",
    ],
)
def test_cada_tela_que_le_derivado_o_atualiza_antes(client, seed, pg_engine, caminho):
    client.get(f"{BASE}/politicians")
    assert _sujo_depois(client, pg_engine, caminho) is False


def test_dossie_do_politico_atualiza_os_derivados_antes_de_ler(client, seed, pg_engine):
    client.get(f"{BASE}/politicians")
    _marcar_sujo(pg_engine)
    assert client.get(f"{BASE}/politicians/{seed.fulano.id}").status_code == 200
    assert _sujo_no_banco(pg_engine) is False


def _dupla_de_autores_em(db, numero, tipo, pessoas=None):
    """Uma proposição do `tipo` assinada por duas pessoas (as dadas, ou duas novas); devolve as pessoas."""
    status = db.execute(text("SELECT codigo FROM ref.status_tramitacao ORDER BY codigo LIMIT 1")).scalar()
    proposicao = db.execute(
        text(
            "INSERT INTO leg.proposicao (tipo_codigo, numero, ano, titulo, data_apresentacao, status_codigo)"
            " VALUES (:t, :n, 2023, :ti, '2023-03-01', :s) RETURNING id"
        ),
        {"t": tipo, "n": numero, "ti": f"Proposição {numero}", "s": status},
    ).scalar()
    if pessoas is None:
        pessoas = [
            db.execute(
                text("INSERT INTO core.pessoa (nome_exibicao) VALUES (:n) RETURNING id"), {"n": f"Dupla {numero}-{i}"}
            ).scalar()
            for i in range(2)
        ]
    for ordem, pessoa in enumerate(pessoas, start=1):
        db.execute(
            text(
                "INSERT INTO leg.autoria (proposicao_id, pessoa_id, nome_autor, tipo_codigo, ordem)"
                " VALUES (:p, :a, 'Autor', :t, :o)"
            ),
            {"p": proposicao, "a": pessoa, "t": "AUTOR_PRINCIPAL" if ordem == 1 else "COAUTOR", "o": ordem},
        )
    return pessoas


def test_rede_filtra_por_tipo_de_pedido_e_soma_o_peso_dos_pares_repetidos(db):
    """`REQ_INC` só enxerga requerimentos e indicações; o peso de uma aresta é o número de proposições do par."""
    from app.services.legislative_scoring import build_coauthorship_network

    pessoas = _dupla_de_autores_em(db, 1, "REQ")
    _dupla_de_autores_em(db, 2, "INC", pessoas)  # o mesmo par assina uma segunda proposição
    _dupla_de_autores_em(db, 3, "PEC")
    db.commit()
    garantir_atualizados(db)

    def arestas(**filtros):
        return build_coauthorship_network(db=db, limit_nodes=50, **filtros)["edges"]

    pedidos = arestas(tipo_proposta="REQ_INC")
    assert len(pedidos) == 1 and pedidos[0]["weight"] == 2  # a PEC de outro par fica de fora
    assert arestas(tipo_proposta="REQ_INC", min_weight=2)[0]["weight"] == 2  # o peso mínimo mantém o par repetido
    assert arestas(tipo_proposta="REQ_INC", min_weight=3) == []
    assert len(arestas(tipo_proposta="PEC")) == 1
