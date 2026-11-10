"""Mudança de nome do partido (PMDB→MDB), fusão e incorporação não são troca de partido."""

from datetime import date

from app.services import filiacao_service as fs
from sqlalchemy import text
from tests.stg_models import PartyAffiliation, PoliticalParty

BASE = "/api/v1/analytics"


def test_primeira_filiacao_e_inicial_e_sigla_nova_do_mesmo_partido_e_renomeacao():
    assert fs.classificar([7, 7], {}) == [fs.INICIAL, fs.RENOMEACAO]


def test_partido_sem_relacao_com_o_anterior_e_troca_e_conta():
    tipos = fs.classificar([1, 2, 3], {})
    assert tipos == [fs.INICIAL, fs.TROCA, fs.TROCA] and fs.contar_trocas(tipos) == 2


def test_fusao_e_incorporacao_vem_da_tabela_de_sucessao_e_nao_contam_como_troca():
    relacoes = {(1, 2): "FUSAO", (3, 4): "INCORPORACAO"}
    tipos = fs.classificar([1, 2, 3, 4, 5], relacoes)
    assert tipos == [fs.INICIAL, fs.FUSAO, fs.TROCA, fs.INCORPORACAO, fs.TROCA]
    assert fs.contar_trocas(tipos) == 2


def test_a_relacao_vale_so_no_sentido_do_tempo():
    assert fs.classificar([2, 1], {(1, 2): "FUSAO"}) == [fs.INICIAL, fs.TROCA]


def test_sem_filiacao_nao_ha_tipo_nem_troca():
    assert fs.classificar([], {}) == [] and fs.contar_trocas([]) == 0


def _filiar(db, pessoa, partidos, ano_inicial=2010):
    """Cria os partidos (sigla, nome) e filia a pessoa neles em sequência, cada um a partir de um ano."""
    criados = [PoliticalParty(acronym=sigla, full_name=nome) for sigla, nome in partidos]
    db.add_all(criados)
    db.commit()
    for i, partido in enumerate(criados):
        ultimo = i == len(criados) - 1
        db.add(
            PartyAffiliation(
                politician_id=pessoa.id,
                party_id=partido.id,
                start_date=date(ano_inicial + 4 * i, 1, 1),
                end_date=None if ultimo else date(ano_inicial + 3 + 4 * i, 12, 31),
                is_current=ultimo,
            )
        )
    db.commit()


def _nomade_maria(client):
    nomades = client.get(f"{BASE}/party-fidelity").json()["top_nomads"]
    return next((n for n in nomades if n["nome_eleitoral"] == "Maria Silva"), None)


def test_renomeacao_do_partido_nao_entra_na_contagem_de_trocas_da_analise_de_fidelidade(client, db, seed):
    db.execute(text("INSERT INTO ref.partido_renomeacao VALUES ('PXA', 'PXB', 'teste')"))
    try:
        _filiar(db, seed.maria_a, [("PXA", "Partido Exemplo Antigo"), ("PXB", "Partido Exemplo Novo")])
        assert _nomade_maria(client) is None  # PXA→PXB é o mesmo partido com outro nome
    finally:
        db.rollback()
        db.execute(text("DELETE FROM ref.partido_renomeacao WHERE sigla_antiga = 'PXA'"))
        db.commit()


def test_fusao_nao_conta_como_troca_mas_troca_de_verdade_conta(client, db, seed):
    db.execute(text("INSERT INTO ref.partido_sucessao_semente VALUES ('PXC', 'PXD', 'FUSAO', NULL, 'teste')"))
    try:
        _filiar(db, seed.maria_a, [("PXC", "Partido Exemplo C"), ("PXD", "Partido Exemplo D")])
        assert _nomade_maria(client) is None  # fusão não é escolha do parlamentar
        _filiar(db, seed.maria_a, [("PXE", "Partido Exemplo E")], ano_inicial=2020)
        nomade = _nomade_maria(client)
        assert nomade["total_trocas"] == 1  # só a ida para o PXE, que não tem relação com o PXD
        assert [h["tipo_mudanca"] for h in nomade["historico"]] == ["INICIAL", "FUSAO", "TROCA"]
    finally:
        db.rollback()
        db.execute(text("DELETE FROM ref.partido_sucessao_semente WHERE sigla_origem = 'PXC'"))
        db.commit()
