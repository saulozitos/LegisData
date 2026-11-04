"""
Carga no banco (Postgres de teste): idempotência, proveniência e resolução inequívoca de pessoas.

Usa os models reais do backend e o fluxo completo de `load_all` (create_all + migrações Alembic + ponte para o
schema `core`), por isso exige o Postgres de teste (`make test-db-up`).
"""

import json
import os

import pytest
from app.models import (  # noqa: E402
    Mandate,
    ParliamentaryVote,
    PartyAffiliation,
    PoliticalParty,
    Politician,
    Proposition,
    VotingSession,
)
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from etl.extractors.presidents_extractor import PresidentsExtractor  # noqa: E402
from etl.pipelines import db_loader  # noqa: E402


def escrever(dir_, nome, dados):
    (dir_ / nome).write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg2://test:test_pass@localhost:5433/legis_test")
    engine = create_engine(url)
    with engine.begin() as conn:
        for schema in ("api", "stg", "fin", "leg", "param", "etl", "eco", "core", "ref", "public"):
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", url)
    Sessao = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(db_loader, "SessionLocal", Sessao)

    dados = tmp_path / "processed"
    dados.mkdir()
    escrever(dados, "presidentes_historico.json", PresidentsExtractor.get_presidents())
    escrever(
        dados,
        "deputados_camara.json",
        [
            # duplicado (como o arquivo legado) + contato real só em um dos registros
            {
                "camara_id": 1,
                "nome_eleitoral": "Eduardo Bolsonaro",
                "nome_civil": "Eduardo Nantes Bolsonaro",
                "partido_sigla": "PL",
                "uf": "SP",
                "id_legislatura": 57,
            },
            {
                "camara_id": 1,
                "nome_eleitoral": "Eduardo Bolsonaro",
                "partido_sigla": "PL",
                "uf": "SP",
                "email": "dep.eduardo@camara.leg.br",
                "gabinete_sala": "Anexo 4, Gabinete 100",
                "uf_nascimento": "RJ",
            },
            {
                "camara_id": 2,
                "nome_eleitoral": "Flávio Dino",
                "nome_civil": "Flávio Dino de Castro e Costa",
                "partido_sigla": "PSB",
                "uf": "MA",
            },
            {"camara_id": 3, "nome_eleitoral": "Dr. Flávio", "partido_sigla": "PTB", "uf": "RJ"},
            {"camara_id": 4, "nome_eleitoral": "Lula da Fonte", "partido_sigla": "PP", "uf": "PE"},
        ],
    )
    escrever(
        dados,
        "senadores_senado.json",
        [
            {
                "senado_id": 100,
                "nome_eleitoral": "Senadora Sem Datas",
                "nome_civil": "Senadora Sem Datas",
                "partido_sigla": "PSD",
                "uf": "MG",
            },
            {
                "senado_id": 101,
                "nome_eleitoral": "Senador Com Datas",
                "nome_civil": "Senador Com Datas",
                "partido_sigla": "PT",
                "uf": "BA",
                "mandato_inicio": "2019-02-01",
                "mandato_fim": "2027-01-31",
            },
        ],
    )
    escrever(
        dados,
        "filiacoes_partidarias.json",
        [
            {
                "politico_nome": "Eduardo Bolsonaro",
                "fonte": "teste",
                "camara_id": 1,
                "partido_sigla": "PSL",
                "data_filiacao": "2018-03-06",
                "data_desfiliacao": "2021-11-29",
                "is_atual": False,
                "motivo_desfiliacao": "MUDANCA_VOLUNTARIA",
            },
            {
                "politico_nome": "Eduardo Bolsonaro",
                "fonte": "teste",
                "camara_id": 1,
                "partido_sigla": "PL",
                "data_filiacao": None,
                "is_atual": True,
            },
            {"politico_nome": "Fulano Sem Id", "partido_sigla": "PL", "data_filiacao": "2020-01-01", "fonte": "teste"},
            {
                "politico_nome": "Flávio Dino",
                "camara_id": 2,
                "partido_sigla": "DEM",
                "data_filiacao": "2018-04-05",
            },  # legado: sem proveniência
        ],
    )
    return dados, Sessao


def carregar(dados, **kwargs):
    return db_loader.DatabaseLoader(data_dir=dados, **kwargs).load_all()


def test_politicos_deduplicados_e_sem_contato_inventado(ambiente):
    dados, Sessao = ambiente
    carregar(dados)
    with Sessao() as s:
        deputados = {p.camara_id: p for p in s.query(Politician).filter(Politician.camara_id.isnot(None))}
        assert len(deputados) == 4
        edu = deputados[1]
        assert edu.email == "dep.eduardo@camara.leg.br"  # vem da fonte
        assert edu.cabinet_room == "Anexo 4, Gabinete 100" and edu.birthplace_state == "RJ"
        flavio = deputados[2]
        assert flavio.email is None and flavio.cabinet_room is None and flavio.cabinet_phone is None
        assert flavio.birthplace_state is None  # UF eleitoral não é naturalidade


def test_carga_e_idempotente(ambiente):
    dados, Sessao = ambiente
    primeira = carregar(dados)
    segunda = carregar(dados)
    assert primeira == segunda


def test_filiacoes_partidos_extintos_e_data_desconhecida(ambiente):
    dados, Sessao = ambiente
    carregar(dados)
    with Sessao() as s:
        siglas = {p.acronym for p in s.query(PoliticalParty)}
        assert {"PSL", "PTB", "PL"} <= siglas  # extintos viram partidos reais, não "Sem Partido"
        edu = s.query(Politician).filter_by(camara_id=1).one()
        afs = s.query(PartyAffiliation).filter_by(politician_id=edu.id).all()
        assert len(afs) == 2
        atual = next(a for a in afs if a.is_current)
        assert atual.start_date.isoformat() == "2023-02-01"  # limite inferior de observação, não data real inventada
        assert s.query(PartyAffiliation).count() == 2  # linha sem id e com nome não único/desconhecido não vira vínculo


def test_mandatos_de_senadores_usam_datas_da_fonte(ambiente):
    dados, Sessao = ambiente
    carregar(dados)
    with Sessao() as s:
        sen_ok = s.query(Politician).filter_by(senado_id=101).one()
        m = s.query(Mandate).filter_by(politician_id=sen_ok.id).one()
        assert (m.start_date.isoformat(), m.end_date.isoformat(), m.election_year) == ("2019-02-01", "2027-01-31", 2018)
        sen_sem = s.query(Politician).filter_by(senado_id=100).one()
        m2 = s.query(Mandate).filter_by(politician_id=sen_sem.id).one()
        assert m2.end_date is None  # sem datas na fonte: não se inventa término em 2031
        dep = s.query(Politician).filter_by(camara_id=1).one()
        md = s.query(Mandate).filter_by(politician_id=dep.id).one()
        assert (md.start_date.isoformat(), md.end_date.isoformat(), md.election_year) == (
            "2023-02-01",
            "2027-01-31",
            2022,
        )


def proposicoes_e_votacoes(dados):
    escrever(
        dados,
        "proposicoes_2023.json",
        [
            {
                "camara_id": 10,
                "tipo": "PL",
                "numero": 74,
                "ano": 2023,
                "titulo": "PL 74/2023",
                "ementa": "Assunto neutro",
                "autor_nome": "Flávio Dino",
                "autor_fonte": "API",
                "autor_camara_id": None,
                "data_apresentacao": "2023-03-01",
                "url_oficial": None,
            },
            {
                "camara_id": 11,
                "tipo": "PL",
                "numero": 75,
                "ano": 2023,
                "titulo": "PL 75/2023",
                "ementa": "Assunto neutro",
                "autor_nome": "Dr. Flávio, Fulano",
                "autor_fonte": "API",
                "data_apresentacao": None,
            },
            {
                "camara_id": 12,
                "tipo": "PLP",
                "numero": 93,
                "ano": 2023,
                "titulo": "Arcabouço",
                "ementa": "arcabouço fiscal",
                "autor_nome": "Poder Executivo",
                "autor_fonte": "API",
                "iniciativa_executivo": True,
                "data_apresentacao": "2023-04-18",
            },
        ],
    )
    escrever(
        dados,
        "proposicoes_senado.json",
        [
            # mesmo tipo/número/ano de um PL da Câmara, mas é OUTRA proposição (id do Senado distinto)
            {
                "senado_id": 900,
                "tipo": "PL",
                "numero": 74,
                "ano": 2023,
                "titulo": "PL 74/2023 (Senado)",
                "ementa": "Outra coisa",
                "autor_nome": "Senador Com Datas",
                "autor_fonte": "API",
                "data_apresentacao": "2023-05-02",
            },
        ],
    )
    escrever(
        dados,
        "sessoes_votacao_2023.json",
        [
            {
                "sessao_externa_id": "S-CAM-1",
                "proposicao_camara_id": 12,
                "data_hora": "2023-05-10T19:00:00",
                "descricao": "Aprovada",
                "aprovada": True,
            },
            {"sessao_externa_id": "S-ORFA", "proposicao_camara_id": 999, "data_hora": "2023-05-10T19:00:00"},
        ],
    )
    escrever(
        dados,
        "votos_nominais_2023.json",
        [
            {"sessao_externa_id": "S-CAM-1", "deputado_camara_id": 1, "voto": "SIM", "partido_sigla": "PL"},
            {"sessao_externa_id": "S-CAM-1", "deputado_camara_id": 2, "voto": "NAO", "partido_sigla": "PSB"},
            {"sessao_externa_id": "S-CAM-1", "deputado_camara_id": 3, "voto": "ARTIGO_17"},
            {
                "sessao_externa_id": "S-CAM-1",
                "deputado_camara_id": 4,
                "voto": "OPCAO_NOVA",
            },  # antes: KeyError derrubava a carga
        ],
    )
    escrever(
        dados,
        "sessoes_votacao_senado.json",
        [
            {
                "sessao_externa_id": "SEN-1",
                "materia_sigla": "PLP",
                "materia_numero": 93,
                "materia_ano": 2023,
                "data_hora": "2023-06-01T10:00:00",
                "aprovada": True,
            },
            # matéria desconhecida: antes caía em "a primeira proposição qualquer"
            {
                "sessao_externa_id": "SEN-2",
                "materia_sigla": "PL",
                "materia_numero": 5555,
                "materia_ano": 2023,
                "data_hora": "2023-06-02T10:00:00",
            },
            {
                "sessao_externa_id": "SEN-3",
                "materia_sigla": "PLP",
                "materia_numero": 93,
                "materia_ano": 2023,
            },  # sem data
        ],
    )
    escrever(
        dados,
        "votos_nominais_senado.json",
        [
            {"sessao_externa_id": "SEN-1", "senador_id": 101, "voto": "SIM"},
            {"sessao_externa_id": "SEN-1", "senador_id": 100, "voto": "AUSENTE"},
            {"sessao_externa_id": "SEN-2", "senador_id": 101, "voto": "SIM"},
        ],
    )


def test_autoria_exata_e_senado_nao_funde_com_camara(ambiente):
    dados, Sessao = ambiente
    proposicoes_e_votacoes(dados)
    carregar(dados)
    with Sessao() as s:
        dino = s.query(Politician).filter_by(camara_id=2).one()
        drflavio = s.query(Politician).filter_by(camara_id=3).one()
        p74 = s.query(Proposition).filter_by(external_camara_id=10).one()
        assert p74.author_politician_id == dino.id  # "Flávio Dino" != "Dr. Flávio"
        p75 = s.query(Proposition).filter_by(external_camara_id=11).one()
        # "Dr. Flávio" (1 token após normalização) não pode virar autor por subconjunto de tokens; aqui é igualdade exata
        assert p75.author_politician_id == drflavio.id
        assert s.query(Proposition).filter_by(external_senado_id=900).one().id != p74.id
        assert s.query(Proposition).count() == 4  # nada foi fundido
        exec_ = s.query(Proposition).filter_by(external_camara_id=12).one()
        assert (
            exec_.author_politician_id is None
            and exec_.author_name == "Poder Executivo"
            and exec_.is_executive_initiative
        )
        # sem eixo aleatório e sem área temática inventada
        assert p74.impact_axis is None and p74.thematic_area is None


def test_votacoes_sem_proposicao_unica_sao_descartadas_e_voto_invalido_nao_derruba(ambiente):
    dados, Sessao = ambiente
    proposicoes_e_votacoes(dados)
    carregar(dados)
    with Sessao() as s:
        externos = {v.external_id for v in s.query(VotingSession)}
        assert externos == {"S-CAM-1", "SEN-1"}  # órfã, matéria desconhecida e sem data ficaram de fora
        cam = s.query(VotingSession).filter_by(external_id="S-CAM-1").one()
        assert (cam.votes_yes_count, cam.votes_no_count) == (1, 1)  # recalculado dos votos nominais
        assert s.query(ParliamentaryVote).filter_by(voting_session_id=cam.id).count() == 3  # voto "OPCAO_NOVA" ignorado
        sen = s.query(VotingSession).filter_by(external_id="SEN-1").one()
        arcabouco = s.query(Proposition).filter_by(external_camara_id=12).one()
        assert sen.proposition_id == arcabouco.id


def test_vinculo_errado_antigo_e_corrigido_na_recarga(ambiente):
    dados, Sessao = ambiente
    proposicoes_e_votacoes(dados)
    carregar(dados)
    with Sessao() as s:
        edu = s.query(Politician).filter_by(camara_id=1).one()
        p = s.query(Proposition).filter_by(external_camara_id=10).one()
        p.author_politician_id = edu.id  # vínculo errado como o do caso Eduardo Bolsonaro
        s.commit()
    carregar(dados)
    with Sessao() as s:
        dino = s.query(Politician).filter_by(camara_id=2).one()
        assert s.query(Proposition).filter_by(external_camara_id=10).one().author_politician_id == dino.id


def test_mandato_presidencial_nao_usa_vice_como_coligacao(ambiente):
    dados, Sessao = ambiente
    carregar(dados)
    with Sessao() as s:
        presidenciais = s.query(Mandate).filter(Mandate.jurisdiction_state == "BR").all()
        assert presidenciais and all(m.coalition_name is None for m in presidenciais)


def test_autoria_legada_sem_proveniencia_e_ignorada_a_menos_que_autorizada(ambiente):
    dados, Sessao = ambiente
    escrever(
        dados,
        "proposicoes_2023.json",
        [
            # como o arquivo legado: autor sorteado (round-robin) quando a API falhava, sem `autor_fonte`
            {
                "camara_id": 10,
                "tipo": "PL",
                "numero": 1,
                "ano": 2023,
                "titulo": "PL 1/2023",
                "ementa": "x",
                "autor_nome": "Flávio Dino",
                "autor_camara_id": 2,
                "data_apresentacao": "2023-03-01",
            },
            {
                "camara_id": 11,
                "tipo": "MPV",
                "numero": 2,
                "ano": 2023,
                "titulo": "MPV 2/2023",
                "ementa": "x",
                "autor_nome": "Comissão / Parlamentares",
                "iniciativa_executivo": True,
                "data_apresentacao": "2023-03-01",
            },
        ],
    )
    carregar(dados)
    with Sessao() as s:
        p1 = s.query(Proposition).filter_by(external_camara_id=10).one()
        assert p1.author_politician_id is None and p1.author_name is None
        p2 = s.query(Proposition).filter_by(external_camara_id=11).one()
        assert p2.author_name == "Poder Executivo"  # iniciativa do Executivo é fato curado, não palpite
    carregar(dados, allow_unverified=True)
    with Sessao() as s:
        dino = s.query(Politician).filter_by(camara_id=2).one()
        assert s.query(Proposition).filter_by(external_camara_id=10).one().author_politician_id == dino.id


def test_filiacoes_legadas_sem_proveniencia_sao_ignoradas(ambiente):
    dados, Sessao = ambiente
    carregar(dados)
    with Sessao() as s:
        dino = s.query(Politician).filter_by(camara_id=2).one()
        assert s.query(PartyAffiliation).filter_by(politician_id=dino.id).count() == 0
    carregar(dados, allow_unverified=True)
    with Sessao() as s:
        dino = s.query(Politician).filter_by(camara_id=2).one()
        assert s.query(PartyAffiliation).filter_by(politician_id=dino.id).count() == 1


def test_sessoes_legadas_do_senado_sem_ano_usam_materias_conhecidas(ambiente):
    dados, Sessao = ambiente
    proposicoes_e_votacoes(dados)
    escrever(
        dados,
        "sessoes_votacao_senado.json",
        [
            {
                "sessao_externa_id": "SEN-LEG",
                "materia_sigla": "PLP",
                "materia_numero": 93,
                "data_hora": "2023-06-01T10:00:00",
                "aprovada": True,
            },
        ],
    )
    escrever(dados, "votos_nominais_senado.json", [{"sessao_externa_id": "SEN-LEG", "senador_id": 101, "voto": "SIM"}])
    carregar(dados)
    with Sessao() as s:
        assert s.query(VotingSession).filter_by(external_id="SEN-LEG").count() == 1


def test_fusao_do_staging_que_falha_sobe_para_a_etapa_nao_aparecer_como_ok(monkeypatch):
    """A carga do staging já foi confirmada, mas `core`/`leg` ficaram sem ela: a esteira tem de registrar a falha."""
    from unittest.mock import MagicMock

    def quebra(_sessao):
        raise RuntimeError("fusão quebrou")

    monkeypatch.setattr("app.services.staging_merge.merge_staging", quebra)
    sessao = MagicMock()
    with pytest.raises(RuntimeError, match="fusão quebrou"):
        db_loader.DatabaseLoader._fundir_staging(sessao)
    sessao.rollback.assert_called_once()
