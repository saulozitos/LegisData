"""Gravação dos votos nominais por COPY (`staging_votos.gravar_votos`); exige Postgres."""

from datetime import date, datetime, timezone

import psycopg2.errors
import pytest
from app.models import (
    CasaLegislativaEnum,
    PoliticalParty,
    Politician,
    Proposition,
    StatusTramitacaoEnum,
    TipoProposicaoEnum,
    VotingSession,
)
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from etl.pipelines.staging_votos import ContagemDeVotos, gravar_votos
from etl.utils import copia

LIMPAR = (
    "TRUNCATE stg.votos_parlamentares, stg.sessoes_votacao, stg.proposicoes, stg.politicos, "
    "stg.partidos_politicos CASCADE"
)


@pytest.fixture
def base(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text(LIMPAR))
    sessao = sessionmaker(bind=pg_engine, expire_on_commit=False)()
    partido = PoliticalParty(acronym="ZTV", full_name="Partido ZTV")
    politicos = [
        Politician(civil_name=f"Pessoa {i}", electoral_name=f"Pessoa {i}", camara_id=900 + i) for i in range(3)
    ]
    prop = Proposition(
        external_camara_id=777,
        proposition_type=TipoProposicaoEnum.PL,
        number=1,
        year=2023,
        title="PL 1/2023",
        summary="x",
        presentation_date=date(2023, 1, 1),
        status=StatusTramitacaoEnum.EM_TRAMITACAO,
    )
    sessao.add_all([partido, prop, *politicos])
    sessao.flush()
    votacao = VotingSession(
        external_id="zt-1",
        proposition_id=prop.id,
        legislative_house=CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS,
        session_datetime=datetime(2023, 5, 1, tzinfo=timezone.utc),
        agenda_title="t",
        is_approved=True,
    )
    sessao.add(votacao)
    sessao.commit()
    yield pg_engine, votacao.id, [p.id for p in politicos], partido.id
    sessao.close()
    with pg_engine.begin() as conn:
        conn.execute(text(LIMPAR))


def _gravar(engine, linhas):
    with copia.transacao_de_carga(engine) as cursor:
        return gravar_votos(cursor, linhas)


def _votos(engine):
    with engine.connect() as conn:
        return {
            (r[0], r[1]): (r[2], r[3])
            for r in conn.execute(
                text('SELECT "sessaoVotacaoId", "politicoId", "partidoId", voto::text FROM stg.votos_parlamentares')
            )
        }


def test_grava_votos_novos_com_partido_nulo_quando_ausente(base):
    engine, sessao, pols, partido = base
    assert _gravar(engine, [(sessao, pols[0], partido, "SIM"), (sessao, pols[1], None, "NAO")]) == (2, 0)
    assert _votos(engine) == {(sessao, pols[0]): (partido, "SIM"), (sessao, pols[1]): (None, "NAO")}


def test_voto_ja_gravado_nao_e_sobrescrito_nem_duplicado(base):
    engine, sessao, pols, partido = base
    _gravar(engine, [(sessao, pols[0], partido, "SIM")])
    assert _gravar(engine, [(sessao, pols[0], None, "NAO"), (sessao, pols[2], None, "ABSTENCAO")]) == (1, 1)
    votos = _votos(engine)
    assert votos[(sessao, pols[0])] == (partido, "SIM")
    assert len(votos) == 2


def test_repetido_no_mesmo_lote_vale_o_primeiro(base):
    engine, sessao, pols, _ = base
    assert _gravar(engine, [(sessao, pols[0], None, "SIM"), (sessao, pols[0], None, "NAO")]) == (1, 1)
    assert _votos(engine)[(sessao, pols[0])][1] == "SIM"


def test_lote_vazio_nao_grava_nada(base):
    engine, *_ = base
    assert _gravar(engine, []) == (0, 0)
    assert _votos(engine) == {}


def test_opcao_desconhecida_desfaz_o_lote_inteiro(base):
    engine, sessao, pols, _ = base
    with pytest.raises(psycopg2.errors.InvalidTextRepresentation, match="votoopcaoenum"):  # o cast da opção falhou
        _gravar(engine, [(sessao, pols[0], None, "SIM"), (sessao, pols[1], None, "TALVEZ")])
    assert _votos(engine) == {}


def test_a_tabela_temporaria_some_com_a_transacao(base):
    engine, sessao, pols, _ = base
    # Na MESMA conexão: tabela temporária é da sessão do Postgres, e numa conexão nova do pool ela nunca apareceria
    conexao = engine.raw_connection()
    try:
        cursor = conexao.cursor()
        gravar_votos(cursor, [(sessao, pols[0], None, "SIM")])
        cursor.execute("SELECT to_regclass('pg_temp._voto')")
        assert cursor.fetchone()[0] is not None  # existe enquanto a transação não termina
        conexao.commit()
        cursor.execute("SELECT to_regclass('pg_temp._voto')")
        assert cursor.fetchone()[0] is None  # ON COMMIT DROP
    finally:
        conexao.close()


def test_contagem_de_votos_soma_campo_a_campo():
    assert ContagemDeVotos(10, 8, 2) + ContagemDeVotos(5, 5, 0, 1) == ContagemDeVotos(15, 13, 2, 1)
    assert ContagemDeVotos() == ContagemDeVotos(0, 0, 0, 0)


def test_contagem_de_votos_vai_e_volta_pelos_contadores_do_resumo():
    contagem = ContagemDeVotos(lidas=10, gravadas=7, rejeitadas=3, arquivos_ignorados=2)
    contadores = contagem.como_contadores()
    assert contadores == {"votos_lidos": 10, "votos_gravados": 7, "votos_descartados": 3, "arquivos_ignorados": 2}
    assert ContagemDeVotos.de_contadores(contadores) == contagem
    with pytest.raises(KeyError):  # chave que falta não vira zero em silêncio
        ContagemDeVotos.de_contadores({"votos_lidos": 1})


def test_varios_lotes_na_mesma_transacao_reaproveitam_a_tabela_sem_misturar_linhas(base):
    engine, sessao, pols, _ = base
    with copia.transacao_de_carga(engine) as cursor:
        primeiro = gravar_votos(cursor, [(sessao, pols[0], None, "SIM")])
        segundo = gravar_votos(cursor, [(sessao, pols[1], None, "NAO")])
        terceiro = gravar_votos(cursor, [])
        cursor.execute("SELECT count(*) FROM _voto")
        sobrando = cursor.fetchone()[0]
    assert (primeiro, segundo, terceiro) == ((1, 0), (1, 0), (0, 0))  # o lote 2 não carrega a linha do lote 1
    assert sobrando == 0  # a tabela reaproveitada é esvaziada, para o lote seguinte não reprocessar linhas antigas
    assert len(_votos(engine)) == 2
