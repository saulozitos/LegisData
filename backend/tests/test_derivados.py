"""Derivados pré-calculados do legislativo: iguais ao cálculo original e nunca velhos."""

import re
import threading
import time
from pathlib import Path

import pytest
from app.services.derivados_service import garantir_atualizados
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
    db.execute(text(f"TRUNCATE {tabela} CASCADE"))
    assert _sujo(db) is True
    db.rollback()  # nada de TRUNCATE de verdade neste teste


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


def test_quem_le_um_derivado_chama_garantir_atualizados():
    """Esquecer a chamada serviria dado velho: todo arquivo de `app` que lê um derivado tem de atualizá-lo antes."""
    leitores = []
    for arquivo in APP.rglob("*.py"):
        texto = arquivo.read_text(encoding="utf-8")
        if re.search(r"FROM\s+leg\.mv_|JOIN\s+leg\.mv_", texto) and arquivo.name != "derivados_service.py":
            leitores.append(arquivo)
    assert leitores, "nenhum leitor encontrado: o teste deixou de proteger"
    for arquivo in leitores:
        assert "garantir_atualizados(" in arquivo.read_text(
            encoding="utf-8"
        ), f"{arquivo.name} lê um derivado sem atualizá-lo"


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


def _atualizar(pg_engine):
    with pg_engine.begin() as conn:
        return conn.execute(text("SELECT leg.atualizar_derivados()")).scalar()


def test_leitura_nao_fica_presa_atras_de_uma_carga_em_andamento(pg_engine):
    """Uma carga que já escreveu numa tabela dependente segura a linha de controle: o leitor desiste e não bloqueia."""
    _marcar_sujo(pg_engine)
    carga = pg_engine.connect()
    transacao = carga.begin()
    try:
        carga.execute(text("UPDATE leg.proposicao SET titulo = titulo"))  # trava a linha de controle até o commit
        inicio = time.monotonic()
        assert _atualizar(pg_engine) is False
        assert time.monotonic() - inicio < 5  # esperou no máximo o lock_timeout, não a carga inteira
        assert _sujo_no_banco(pg_engine) is True  # a tentativa desfeita não perde o aviso
    finally:
        transacao.rollback()
        carga.close()
    assert _atualizar(pg_engine) is True and _sujo_no_banco(pg_engine) is False  # sem a carga, refaz


def test_outra_atualizacao_em_curso_faz_o_leitor_servir_a_visao_como_esta(pg_engine):
    _marcar_sujo(pg_engine)
    outra = pg_engine.connect()
    transacao = outra.begin()
    try:
        outra.execute(text("SELECT pg_advisory_xact_lock(727420002)"))
        assert _atualizar(pg_engine) is False
        assert _sujo_no_banco(pg_engine) is True
    finally:
        transacao.rollback()
        outra.close()
    assert _atualizar(pg_engine) is True


def test_gravacao_durante_a_atualizacao_nao_se_perde(pg_engine):
    """O sinalizador é desligado antes de refazer: quem escrever enquanto a atualização não confirmou o religa."""
    _marcar_sujo(pg_engine)
    atualizacao = pg_engine.connect()
    transacao = atualizacao.begin()
    escritor_terminou = threading.Event()

    def escrever():
        with pg_engine.begin() as conn:
            conn.execute(text("SET LOCAL lock_timeout = '10s'"))
            conn.execute(text("UPDATE leg.proposicao SET titulo = titulo"))
        escritor_terminou.set()

    try:
        assert atualizacao.execute(text("SELECT leg.atualizar_derivados()")).scalar() is True
        escritor = threading.Thread(target=escrever)
        escritor.start()
        time.sleep(0.5)
        assert not escritor_terminou.is_set()  # o escritor espera a linha de controle da atualização
    finally:
        transacao.commit()
        atualizacao.close()
    escritor.join(timeout=15)
    assert escritor_terminou.is_set()
    assert _sujo_no_banco(pg_engine) is True  # a gravação posterior religou o sinalizador
    assert _atualizar(pg_engine) is True


def test_papel_de_leitura_atualiza_os_derivados_mas_o_publico_nao_executa(pg_engine):
    _marcar_sujo(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("SET LOCAL ROLE legisdata_leitura"))
        assert conn.execute(text("SELECT leg.atualizar_derivados()")).scalar() is True
    with pg_engine.connect() as conn:
        definidor, acl = conn.execute(
            text("SELECT prosecdef, proacl::text FROM pg_proc WHERE oid = 'leg.atualizar_derivados()'::regprocedure")
        ).one()
    assert definidor is True
    assert "legisdata_leitura=X" in acl and "{=X" not in acl and ",=X" not in acl  # nada de EXECUTE para PUBLIC
    # o papel de leitura continua sem poder escrever direto nas tabelas
    with pg_engine.connect() as conn:
        conn.execute(text("SET ROLE legisdata_leitura"))
        with pytest.raises(Exception, match="permission denied"):
            conn.execute(text("UPDATE leg.pontuacao_controle SET sujo = false"))
