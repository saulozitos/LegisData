"""Derivados pré-calculados do legislativo: iguais ao cálculo original e nunca velhos."""

import re
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


def test_pares_de_coautoria_cobrem_so_proposicoes_conjuntas_dentro_do_limite(db):
    maximo = db.execute(text("SELECT coalesce(max(n_autores), 0) FROM leg.mv_coautoria_par")).scalar()
    minimo = db.execute(text("SELECT coalesce(min(n_autores), 2) FROM leg.mv_coautoria_par")).scalar()
    assert minimo >= 2 and maximo <= MAX_AUTORES_POR_PROPOSICAO


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
