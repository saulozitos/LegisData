"""Linhas do staging relacional em memória e a gravação por COPY (`etl.pipelines.stg_tabela`); exige Postgres."""

import enum
from datetime import date

import pytest
from sqlalchemy import text

from etl.pipelines import stg_tabela
from etl.utils.copia import transacao_de_carga

LIMPAR = "TRUNCATE stg.votos_parlamentares, stg.sessoes_votacao, stg.proposicoes, stg.mandatos, stg.filiacoes_partidarias, stg.membros_gabinete, stg.politicos, stg.partidos_politicos CASCADE"


@pytest.fixture
def banco(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text(LIMPAR))
    yield pg_engine
    with pg_engine.begin() as conn:
        conn.execute(text(LIMPAR))


def _gravar(engine, *tabelas):
    with transacao_de_carga(engine) as cursor:
        return [t.gravar(cursor) for t in tabelas]


def _carregar(engine, fabrica):
    with transacao_de_carga(engine) as cursor:
        return fabrica().carregar(cursor)


def test_linha_nova_ganha_id_e_padroes_e_vazio_vira_nulo(banco):
    tabela = stg_tabela.politicos()
    linha = tabela.nova(civil_name="Ana Teste", electoral_name="Ana", email="", camara_id=9001)
    assert linha.id is not None and linha.possui_processos_declarados is False
    assert _gravar(banco, tabela) == [{"inseridas": 1, "atualizadas": 0}]

    lida = _carregar(banco, stg_tabela.politicos).linhas[0]
    assert (lida.id, lida.civil_name, lida.camara_id) == (linha.id, "Ana Teste", 9001)
    assert lida.email is None  # desconhecido é nulo, nunca texto vazio
    assert lida.possui_processos_declarados is False


def test_so_a_linha_alterada_e_atualizada_e_o_id_nao_muda(banco):
    tabela = stg_tabela.politicos()
    a = tabela.nova(civil_name="A", electoral_name="A", camara_id=9001)
    b = tabela.nova(civil_name="B", electoral_name="B", camara_id=9002)
    _gravar(banco, tabela)

    recarregada = _carregar(banco, stg_tabela.politicos)
    assert recarregada.alteradas() == []
    por_id = {linha.id: linha for linha in recarregada}
    por_id[a.id].email = "a@camara.leg.br"
    assert [linha.id for linha in recarregada.alteradas()] == [a.id]
    assert _gravar(banco, recarregada) == [{"inseridas": 0, "atualizadas": 1}]

    final = {linha.id: linha for linha in _carregar(banco, stg_tabela.politicos)}
    assert final[a.id].email == "a@camara.leg.br" and final[b.id].email is None
    assert set(final) == {a.id, b.id}  # nenhum id novo: o `uid` público de quem já existe não muda


def test_json_booleano_enum_e_data_vao_no_formato_do_banco(banco):
    class Cargo(str, enum.Enum):
        SENADOR = "Senador"

    politicos = stg_tabela.politicos()
    pol = politicos.nova(
        civil_name="C", electoral_name="C", social_links={"x": ["a", "b"]}, possui_processos_declarados=True
    )
    partidos = stg_tabela.partidos()
    partido = partidos.nova(acronym="ZTT", full_name="Partido ZTT")
    mandatos = stg_tabela.mandatos()
    mandatos.nova(
        politician_id=pol.id,
        party_id=partido.id,
        office=Cargo.SENADOR,  # o banco guarda o NOME do membro, não o valor
        election_year=2018,
        start_date=date(2019, 2, 1),
    )
    _gravar(banco, partidos, politicos, mandatos)

    lido = _carregar(banco, stg_tabela.politicos).linhas[0]
    assert lido.social_links == {"x": ["a", "b"]} and lido.possui_processos_declarados is True
    mandato = _carregar(banco, stg_tabela.mandatos).linhas[0]
    assert (mandato.office, mandato.sphere, mandato.status, mandato.term_number) == (
        "SENADOR",
        "FEDERAL",
        "TITULAR_ATIVO",
        1,
    )
    assert mandato.start_date == date(2019, 2, 1) and mandato.jurisdiction_state == "BR"


def test_atributo_desconhecido_e_recusado():
    with pytest.raises(AttributeError, match="desconhecidos"):
        stg_tabela.politicos().nova(civil_name="A", electoral_name="A", cpf="x")


def test_staging_grava_na_ordem_das_chaves_estrangeiras(banco):
    with transacao_de_carga(banco) as cursor:
        staging = stg_tabela.Staging.carregar(cursor)
    partidos = stg_tabela.partidos()
    partido = partidos.nova(acronym="ZTU", full_name="Partido ZTU")
    pol = staging.politicos.nova(civil_name="D", electoral_name="D")
    staging.mandatos.nova(
        politician_id=pol.id,
        party_id=partido.id,
        office="DEPUTADO_FEDERAL",
        election_year=2022,
        start_date=date(2023, 2, 1),
    )
    prop = staging.proposicoes.nova(
        proposition_type="PL",
        number=1,
        year=2023,
        title="PL 1/2023",
        summary="x",
        presentation_date=date(2023, 1, 1),
        author_politician_id=pol.id,
    )
    staging.sessoes.nova(
        external_id="zt-sessao",
        proposition_id=prop.id,
        legislative_house="CAMARA_DOS_DEPUTADOS",
        session_datetime=date(2023, 5, 1).isoformat(),
        agenda_title="t",
        is_approved=True,
    )
    with transacao_de_carga(banco) as cursor:
        partidos.gravar(cursor)
        resultado = staging.gravar(cursor)  # político antes de mandato e de proposição, proposição antes de sessão
    assert {nome: r["inseridas"] for nome, r in resultado.items()} == {
        "politicos": 1,
        "filiacoes_partidarias": 0,
        "mandatos": 1,
        "membros_gabinete": 0,
        "proposicoes": 1,
        "sessoes_votacao": 1,
    }


def test_gravar_duas_vezes_na_mesma_transacao_reaproveita_a_tabela_temporaria(banco):
    tabela = stg_tabela.politicos()
    tabela.nova(civil_name="E", electoral_name="E")
    with transacao_de_carga(banco) as cursor:
        tabela.gravar(cursor)
        tabela.nova(civil_name="F", electoral_name="F")
        assert tabela.gravar(cursor) == {"inseridas": 1, "atualizadas": 0}  # só a nova, não a repete
    assert len(_carregar(banco, stg_tabela.politicos)) == 2
