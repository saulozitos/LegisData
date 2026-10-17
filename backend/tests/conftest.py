"""Fixtures compartilhadas: Postgres de teste, override único de get_db e diretório de dados isolado."""

import json
import os
import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace

# Garante variáveis mínimas para a suíte de testes sem vazar credenciais (antes de importar a aplicação)
os.environ.setdefault("POSTGRES_PASSWORD", "test_db_password_ci")
os.environ.setdefault("ENVIRONMENT", "test")

import pytest  # noqa: E402
from app import main as main_module  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.database import get_db  # noqa: E402
from app.core.migrations import upgrade_schema  # noqa: E402
from app.models import (  # noqa: E402
    Base,
    CargoPoliticoEnum,
    CasaLegislativaEnum,
    Mandate,
    ParliamentaryVote,
    PartyAffiliation,
    PoliticalParty,
    Politician,
    Proposition,
    StatusMandatoEnum,
    TipoProposicaoEnum,
    VotingSession,
    VotoOpcaoEnum,
)
from app.services import cidadania_service  # noqa: E402
from app.services.core_sync import sync_legacy_to_core  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

FAR_FUTURE = date(2999, 1, 31)


@pytest.fixture(autouse=True)
def _isolation(monkeypatch):
    """Zera estado global entre testes: rate limiter e cache do serviço de cidadania."""
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 0)
    monkeypatch.setattr(cidadania_service, "_cache_data", None)
    monkeypatch.setattr(cidadania_service, "_cache_timestamp", 0.0)
    main_module._rate_limiter._hits.clear()
    yield
    main_module._rate_limiter._hits.clear()


TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg2://test:test_pass@localhost:5433/legis_test"
)


# Tabelas de dados (não de referência) fora do schema public, esvaziadas a cada teste
_ETL_DATA_TABLES = (
    "etl.execucao",
    "etl.arquivo_bruto",
    "etl.rejeito",
    "etl.verificacao",
    "eco.observacao",
    "eco.pnad_ano",
    "eco.pnad_metodologia",
)


@pytest.fixture(scope="session")
def pg_engine():
    """Engine do Postgres de teste: o schema é criado uma vez por sessão, pelas migrações Alembic."""
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    try:
        with engine.begin() as conn:
            for schema in ("api", "stg", "fin", "leg", "param", "etl", "eco", "core", "ref", "public"):
                conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
    except OperationalError as exc:  # pragma: no cover - ambiente sem banco de teste
        pytest.exit(
            f"Postgres de teste indisponível em {TEST_DATABASE_URL}: {exc}. Suba-o com `make test-db-up`.",
            returncode=2,
        )
    previous = os.environ.get("ALEMBIC_DATABASE_URL")
    os.environ["ALEMBIC_DATABASE_URL"] = TEST_DATABASE_URL
    try:
        upgrade_schema()
    finally:
        if previous is None:
            os.environ.pop("ALEMBIC_DATABASE_URL", None)
        else:
            os.environ["ALEMBIC_DATABASE_URL"] = previous
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def _truncate_sql(pg_engine):
    """TRUNCATE de todas as tabelas de dados: legado (public), core e tabelas de execução do ETL."""
    with pg_engine.connect() as conn:
        core = [
            r[0]
            for r in conn.execute(
                text(
                    "SELECT format('%I.%I', n.nspname, c.relname) FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname IN ('core', 'leg', 'fin') AND c.relkind IN ('r', 'p') AND NOT c.relispartition"
                )
            )
        ]
    legacy = [f'"{t.name}"' for t in Base.metadata.sorted_tables if not t.schema]
    return "TRUNCATE " + ", ".join(legacy + core + list(_ETL_DATA_TABLES)) + " RESTART IDENTITY CASCADE"


@pytest.fixture()
def session_factory(pg_engine, _truncate_sql):
    """Postgres real, limpo a cada teste via TRUNCATE (isolamento total, sem ordem de execução relevante)."""
    factory = sessionmaker(bind=pg_engine, expire_on_commit=False)
    yield factory
    with pg_engine.begin() as conn:
        conn.execute(text(_truncate_sql))


@pytest.fixture()
def db(session_factory):
    session = session_factory()
    yield session
    session.close()


@pytest.fixture()
def client(session_factory):
    """TestClient com override de get_db. Define e remove somente a própria chave (nunca `clear()`)."""

    def _override():
        session = session_factory()
        try:
            # Os testes semeiam o schema legado; os endpoints leem o schema novo. A ponte projeta o legado antes de
            # cada requisição (só quando há dados legados, para não apagar dados escritos direto nos schemas novos).
            if session.execute(
                text("SELECT EXISTS (SELECT 1 FROM politicos) OR EXISTS (SELECT 1 FROM proposicoes)")
            ).scalar():
                sync_legacy_to_core(session)
            yield session
        finally:
            session.close()

    main_module.app.dependency_overrides[get_db] = _override
    try:
        # Sem `with`: o lifespan (migração DDL do Postgres) não deve rodar na suíte
        yield TestClient(main_module.app)
    finally:
        main_module.app.dependency_overrides.pop(get_db, None)


def criar_mandato_presidencial(db, nome, inicio, fim, slug, rotulo=None, partido=None):
    """Presidente, mandato de `PRESIDENTE` e identificador público (`mandato_presidencial`); devolve o id do mandato."""
    pessoa = db.execute(text("INSERT INTO core.pessoa (nome_exibicao) VALUES (:n) RETURNING id"), {"n": nome}).scalar()
    if partido:
        db.execute(
            text(
                "INSERT INTO core.partido (sigla, nome) SELECT :s, :s WHERE NOT EXISTS "
                "(SELECT 1 FROM core.partido WHERE sigla = :s)"
            ),
            {"s": partido},
        )
    mandato = db.execute(
        text(
            "INSERT INTO core.mandato (pessoa_id, cargo_id, circunscricao_id, inicio, fim, partido_id) VALUES "
            "(:p, (SELECT id FROM ref.cargo WHERE codigo = 'PRESIDENTE'), "
            "(SELECT id FROM ref.circunscricao WHERE tipo = 'BR'), :i, :f, "
            "(SELECT id FROM core.partido WHERE sigla = :partido LIMIT 1)) RETURNING id"
        ),
        {"p": pessoa, "i": inicio, "f": fim, "partido": partido},
    ).scalar()
    db.execute(
        text("INSERT INTO core.mandato_presidencial (mandato_id, slug, rotulo) VALUES (:m, :s, :r)"),
        {"m": mandato, "s": slug, "r": rotulo},
    )
    return mandato


def observar_serie(db, codigo, referencia, valor):
    """Grava uma observação de `eco.observacao` para a série do catálogo."""
    db.execute(
        text(
            "INSERT INTO eco.observacao (serie_id, referencia, valor) "
            "VALUES ((SELECT id FROM eco.serie WHERE codigo = :c), :r, :v)"
        ),
        {"c": codigo, "r": referencia, "v": valor},
    )


def write_json(directory, name, payload):
    path = directory / name
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def write_text(directory, name, content):
    path = directory / name
    path.write_text(content, encoding="utf-8")
    return path


def pessoa_do(db, politico):
    """`core.pessoa` do político do legado (a ponte cria o cadastro com o mesmo `uid`)."""
    sync_legacy_to_core(db)
    return db.execute(text("SELECT id FROM core.pessoa WHERE uid = :uid"), {"uid": politico.id}).scalar_one()


def fonte_id(db, codigo="CAMARA_CSV"):
    return db.execute(text("SELECT id FROM etl.fonte WHERE codigo = :c"), {"c": codigo}).scalar_one()


def inserir_fin(db, tabela, **colunas):
    """Insere uma linha em `fin.<tabela>`; `fonte_id` entra sozinho (CAMARA_CSV) quando a tabela o exige."""
    colunas.setdefault("fonte_id", fonte_id(db))
    nomes = ", ".join(colunas)
    valores = ", ".join(f":{c}" for c in colunas)
    db.execute(text(f"INSERT INTO fin.{tabela} ({nomes}) VALUES ({valores})"), colunas)  # nosec B608 - só em teste


def semear_financas(db, fulano, lula_fonte):
    """CEAP, emenda e doação do Fulano e uma certidão do Lula da Fonte, no schema `fin`."""
    pessoa = pessoa_do(db, fulano)
    inserir_fin(db, "despesa_cota", pessoa_id=pessoa, ano=2024, tipo_despesa="Combustível", valor_liquido=150)
    inserir_fin(
        db, "despesa_cota_fornecedor", pessoa_id=pessoa, nome="Posto X", cnpj="12345678000199", valor_total=150, notas=2
    )
    inserir_fin(db, "despesa_cota_resumo", pessoa_id=pessoa, total_notas=2)
    inserir_fin(
        db,
        "emenda",
        pessoa_id=pessoa,
        autor_texto="FULANO",
        tipo_autor="INDIVIDUAL",
        autor_situacao="IDENTIFICADO",
        ano=2024,
        codigo_emenda="E1",
        tipo_emenda="INDIVIDUAL",
        valor_empenhado=100,
        valor_pago=50,
        localidade_destino="SP",
        fonte_id=fonte_id(db, "PORTAL_TRANSPARENCIA"),
    )
    inserir_fin(
        db,
        "doacao_campanha",
        pessoa_id=pessoa,
        ano_eleicao=2022,
        doador_nome="Fulana Doadora",
        doador_documento="***.654.321-**",
        valor=500,
        fonte_id=fonte_id(db, "TSE"),
    )
    inserir_fin(
        db,
        "certidao",
        pessoa_id=pessoa_do(db, lula_fonte),
        orgao="STF",
        tipo="Criminal",
        situacao="Nada Consta",
        fonte_id=fonte_id(db, "TSE"),
    )
    db.commit()


@pytest.fixture()
def financas(db, seed):
    """Finanças do seed em `fin`. Fixture à parte porque criar o cadastro em `core` exige a ponte do legado, e rodá-la
    antes do teste impede os que acrescentam dados legados depois (a ponte não é reentrante com sessões já projetadas).
    """
    semear_financas(db, seed.fulano, seed.lula_fonte)


@pytest.fixture()
def seed(db):
    """
    Dados mínimos e determinísticos:
      - PT e PTB (siglas parecidas para testar match exato), partido S.PART.
      - Fulano (CPF, CEAP, doação), "Lula da Fonte" (deputado comum), Beltrano (PTB),
        duas "Maria Silva" (nome ambíguo) e um presidente real (mandato de PRESIDENTE).
      - Uma proposição com duas sessões na Câmara (mérito com mais quórum + destaque) para testar placar.
    """
    pt = PoliticalParty(acronym="PT", full_name="Partido dos Trabalhadores")
    ptb = PoliticalParty(acronym="PTB", full_name="Partido Trabalhista Brasileiro")
    sem_partido = PoliticalParty(acronym="S.PART.", full_name="Sem Partido")
    db.add_all([pt, ptb, sem_partido])
    db.flush()

    fulano = Politician(civil_name="Fulano de Tal", electoral_name="Fulano", camara_id=111, cpf="12345678901")
    lula_fonte = Politician(civil_name="Lula da Fonte", electoral_name="Lula da Fonte", camara_id=222)
    beltrano = Politician(civil_name="Beltrano", electoral_name="Beltrano", camara_id=333)
    maria_a = Politician(civil_name="Maria Silva", electoral_name="Maria Silva", camara_id=444)
    maria_b = Politician(civil_name="Maria Silva", electoral_name="Maria Silva", camara_id=445)
    presidente = Politician(civil_name="Luiz Inacio Lula da Silva", electoral_name="Lula", tse_id="9999")
    db.add_all([fulano, lula_fonte, beltrano, maria_a, maria_b, presidente])
    db.flush()

    def deputado(pol, party, uf="SP", end=FAR_FUTURE, year=2022, start=date(2023, 2, 1), **kw):
        mandate = Mandate(
            politician_id=pol.id,
            party_id=party.id,
            office=CargoPoliticoEnum.DEPUTADO_FEDERAL,
            election_year=year,
            start_date=start,
            end_date=end,
            jurisdiction_state=uf,
            **kw,
        )
        db.add(mandate)
        return mandate

    m_fulano = deputado(fulano, pt)
    deputado(lula_fonte, pt)
    deputado(beltrano, ptb, uf="RJ")
    deputado(maria_a, ptb, uf="MG")
    deputado(maria_b, ptb, uf="BA")
    # Mandato histórico (encerrado): NÃO pode contar na bancada atual
    deputado(fulano, ptb, uf="SP", end=date(2010, 1, 31), year=2006, start=date(2007, 2, 1))
    db.add(
        Mandate(
            politician_id=presidente.id,
            party_id=pt.id,
            office=CargoPoliticoEnum.PRESIDENTE,
            election_year=2022,
            start_date=date(2023, 1, 1),
            end_date=None,
            jurisdiction_state="BR",
            status=StatusMandatoEnum.TITULAR_ATIVO,
        )
    )
    for pol, party in ((fulano, pt), (lula_fonte, pt), (beltrano, ptb)):
        db.add(PartyAffiliation(politician_id=pol.id, party_id=party.id, start_date=date(2020, 1, 1), is_current=True))
    db.flush()

    proposition = Proposition(
        proposition_type=TipoProposicaoEnum.PL,
        number=10,
        year=2023,
        title="PL 10/2023",
        summary="Ementa do PL 10",
        thematic_area="Economia",
        presentation_date=date(2023, 3, 1),
        author_politician_id=fulano.id,
        author_name="Fulano",
        external_camara_id=999,
    )
    # Mesma numeração, outro ano e outro id externo: número de matéria nunca identifica a proposição
    outra = Proposition(
        proposition_type=TipoProposicaoEnum.PL,
        number=10,
        year=2024,
        title="PL 10/2024",
        summary="Outra matéria com o mesmo número",
        thematic_area="Saúde",
        presentation_date=date(2024, 3, 1),
        external_camara_id=1000,
    )
    executiva = Proposition(
        proposition_type=TipoProposicaoEnum.MPV,
        number=1,
        year=2023,
        title="MPV 1/2023",
        summary="Medida do Executivo",
        presentation_date=date(2023, 5, 1),
        is_executive_initiative=True,
        external_camara_id=1001,
    )
    db.add_all([proposition, outra, executiva])
    db.flush()

    merito = VotingSession(
        proposition_id=proposition.id,
        legislative_house=CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS,
        session_datetime=datetime(2023, 5, 2, 15, 0, tzinfo=timezone.utc),
        agenda_title="Votação de mérito",
        is_approved=True,
        external_id="sess-merito",
    )
    destaque = VotingSession(
        proposition_id=proposition.id,
        legislative_house=CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS,
        session_datetime=datetime(2023, 5, 3, 15, 0, tzinfo=timezone.utc),
        agenda_title="Destaque",
        is_approved=False,
        external_id="sess-destaque",
    )
    db.add_all([merito, destaque])
    db.flush()
    for pol, choice in (
        (fulano, VotoOpcaoEnum.SIM),
        (lula_fonte, VotoOpcaoEnum.NAO),
        (beltrano, VotoOpcaoEnum.OBSTRUCAO),
        (maria_a, VotoOpcaoEnum.AUSENTE),
        (maria_b, VotoOpcaoEnum.ARTIGO_17),
    ):
        db.add(ParliamentaryVote(voting_session_id=merito.id, politician_id=pol.id, party_id=pt.id, vote_choice=choice))
    db.add(
        ParliamentaryVote(
            voting_session_id=destaque.id, politician_id=fulano.id, party_id=pt.id, vote_choice=VotoOpcaoEnum.SIM
        )
    )
    db.commit()

    return SimpleNamespace(
        pt=pt,
        ptb=ptb,
        fulano=fulano,
        lula_fonte=lula_fonte,
        beltrano=beltrano,
        maria_a=maria_a,
        maria_b=maria_b,
        presidente=presidente,
        mandate_fulano=m_fulano,
        proposition=proposition,
        outra=outra,
        executiva=executiva,
        merito=merito,
        destaque=destaque,
        unknown_uuid=str(uuid.uuid4()),
    )
