"""Migration 0026 contra dados reais do legado: remove Itamar Franco e seus ministros e preserva o resto.

Usa um banco próprio no servidor de teste (a suíte principal recria os schemas do `legis_test`): sobe até a 0025, semeia
o que a produção tem e aplica a 0026.
"""

import os
import uuid
from datetime import date

import pytest
from app.core.migrations import upgrade_schema
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

SERVIDOR_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg2://test:test_pass@localhost:5433/legis_test")
BANCO = "legis_test_mig"
URL = SERVIDOR_URL.rsplit("/", 1)[0] + f"/{BANCO}"


@pytest.fixture(scope="module")
def engine():
    try:
        admin = create_engine(SERVIDOR_URL, isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS {BANCO}"))
            conn.execute(text(f"CREATE DATABASE {BANCO}"))
        admin.dispose()
    except OperationalError as exc:  # pragma: no cover - ambiente sem banco de teste
        pytest.skip(f"Postgres de teste indisponível ({exc.__class__.__name__}); `make test-db-up`")
    anterior = os.environ.get("ALEMBIC_DATABASE_URL")
    os.environ["ALEMBIC_DATABASE_URL"] = URL
    try:
        upgrade_schema("0025")
        eng = create_engine(URL)
        yield eng
        eng.dispose()
    finally:
        if anterior is None:
            os.environ.pop("ALEMBIC_DATABASE_URL", None)
        else:
            os.environ["ALEMBIC_DATABASE_URL"] = anterior


def _pessoa(conn, nome):
    return conn.execute(
        text("INSERT INTO core.pessoa (nome_exibicao) VALUES (:n) RETURNING id, uid"), {"n": nome}
    ).one()


def _mandato(conn, pessoa_id, cargo, inicio, fim, nomeado_por=None, condicao="TITULAR", funcao=None):
    return conn.execute(
        text(
            "INSERT INTO core.mandato (pessoa_id, cargo_id, circunscricao_id, inicio, fim, condicao, "
            "nomeado_por_mandato_id, funcao_destaque) VALUES (:p, (SELECT id FROM ref.cargo WHERE codigo = :c), "
            "(SELECT id FROM ref.circunscricao WHERE tipo = 'BR'), :i, :f, :cond, :n, :fd) RETURNING id"
        ),
        {"p": pessoa_id, "c": cargo, "i": inicio, "f": fim, "cond": condicao, "n": nomeado_por, "fd": funcao},
    ).scalar()


def _legado(conn, uid, nome, inicio):
    partido = uuid.uuid4()
    conn.execute(
        text('INSERT INTO public.partidos_politicos (id, sigla, "nomeCompleto") VALUES (:i, :s, :s)'),
        {"i": partido, "s": f"P{partido.hex[:6]}"},
    )
    conn.execute(
        text('INSERT INTO public.politicos (id, "nomeCivil", "nomeEleitoral") VALUES (:i, :n, :n)'),
        {"i": uid, "n": nome},
    )
    conn.execute(
        text(
            'INSERT INTO public.mandatos (id, "politicoId", "partidoId", cargo, esfera, "ufJurisdicao", "anoEleicao", '
            "\"numeroMandato\", \"dataInicio\", status) VALUES (:i, :p, :pt, 'PRESIDENTE', 'FEDERAL', 'BR', 1990, 1, "
            ":d, 'CONCLUIDO')"
        ),
        {"i": uuid.uuid4(), "p": uid, "pt": partido, "d": inicio},
    )


def test_remove_itamar_e_ministros_e_preserva_os_demais(engine):
    with engine.begin() as conn:
        itamar_id, itamar_uid = _pessoa(conn, "Itamar Franco")
        m_itamar = _mandato(conn, itamar_id, "PRESIDENTE", date(1992, 10, 2), date(1995, 1, 1))
        ministro_id, _ = _pessoa(conn, "Ministro de Itamar")
        _mandato(
            conn,
            ministro_id,
            "MINISTRO_DE_ESTADO",
            date(1993, 1, 1),
            date(1994, 12, 31),
            m_itamar,
            "NOMEADO",
            "ECONOMIA",
        )
        _legado(conn, itamar_uid, "Itamar Franco", date(1992, 10, 2))

        fhc_id, fhc_uid = _pessoa(conn, "Fernando Henrique Cardoso (FHC 1)")
        m_fhc = _mandato(conn, fhc_id, "PRESIDENTE", date(1995, 1, 1), date(1999, 1, 1))
        conn.execute(
            text("INSERT INTO core.pessoa_nome (pessoa_id, tipo, nome, fonte_id) VALUES (:p, 'ELEITORAL', :n, 11)"),
            {"p": fhc_id, "n": "Fernando Henrique Cardoso (FHC 1)"},
        )
        _legado(conn, fhc_uid, "Fernando Henrique Cardoso (FHC 1)", date(1995, 1, 1))
        # senador homônimo de Itamar, sem relação com o mandato presidencial: não pode ser apagado
        senador_id, _ = _pessoa(conn, "Itamar Franco")

    upgrade_schema("0026")

    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM core.mandato WHERE id = :m"), {"m": m_itamar}).scalar() == 0
        assert (
            conn.execute(text("SELECT count(*) FROM core.mandato WHERE pessoa_id = :p"), {"p": ministro_id}).scalar()
            == 0
        )
        assert conn.execute(text("SELECT count(*) FROM core.pessoa WHERE id = :p"), {"p": itamar_id}).scalar() == 0
        assert conn.execute(text("SELECT count(*) FROM core.pessoa WHERE id = :p"), {"p": senador_id}).scalar() == 1
        assert (
            conn.execute(text("SELECT count(*) FROM public.politicos WHERE id = :u"), {"u": itamar_uid}).scalar() == 0
        )
        # FHC fica, sem o rótulo no nome (pessoa, nome eleitoral e legado) e com identificador público
        assert conn.execute(text("SELECT nome_exibicao FROM core.pessoa WHERE id = :p"), {"p": fhc_id}).scalar() == (
            "Fernando Henrique Cardoso"
        )
        assert conn.execute(text("SELECT nome FROM core.pessoa_nome WHERE pessoa_id = :p"), {"p": fhc_id}).scalar() == (
            "Fernando Henrique Cardoso"
        )
        assert conn.execute(
            text('SELECT "nomeEleitoral" FROM public.politicos WHERE id = :u'), {"u": fhc_uid}
        ).scalar() == ("Fernando Henrique Cardoso")
        slug, rotulo = conn.execute(
            text("SELECT slug, rotulo FROM core.mandato_presidencial WHERE mandato_id = :m"), {"m": m_fhc}
        ).one()
        assert (slug, rotulo) == ("fhc-1995", "FHC 1")
        assert conn.execute(text("SELECT count(*) FROM core.mandato_presidencial")).scalar() == 1


def test_0027_remove_as_tabelas_do_painel_antigo(engine):
    upgrade_schema("0027")
    with engine.connect() as conn:
        restantes = conn.execute(
            text(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' "
                "AND table_name IN ('presidential_mandates', 'mandate_indicators')"
            )
        ).scalar()
    assert restantes == 0
