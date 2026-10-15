"""Schema legislativo (leg): janela de 1995, ponte legado -> leg, votação unificada e presença particionada."""

from datetime import date, datetime, timezone

import pytest
from app.models import (
    AttendanceRecord,
    CargoPoliticoEnum,
    CasaLegislativaEnum,
    Mandate,
    OrientacaoPartidaria,
    ParliamentaryVote,
    PoliticalParty,
    Politician,
    Proposition,
    PropositionAuthor,
    StatusTramitacaoEnum,
    TipoAutoriaEnum,
    TipoPresencaEnum,
    TipoProposicaoEnum,
    VotacaoProposicao,
    VotingSession,
    VotoNominal,
    VotoOpcaoEnum,
)
from app.services.core_sync import sync_legacy_to_core
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

FAR_FUTURE = date(2999, 1, 31)
INSTANTE = datetime(2023, 5, 4, 12, 0, tzinfo=timezone.utc)


def _scalar(db, sql, **params):
    return db.execute(text(sql), params).scalar()


def _rows(db, sql, **params):
    return [tuple(r) for r in db.execute(text(sql), params)]


def _prop(**over):
    base = dict(proposition_type=TipoProposicaoEnum.PL, number=1, year=2023, title="PL 1/2023", summary="Ementa",
                presentation_date=date(2023, 3, 1), status=StatusTramitacaoEnum.EM_TRAMITACAO)
    return Proposition(**{**base, **over})


@pytest.fixture()
def cenario(db):
    pt = PoliticalParty(acronym="PT", full_name="Partido dos Trabalhadores")
    pl = PoliticalParty(acronym="PL", full_name="Partido Liberal")
    db.add_all([pt, pl])
    ana = Politician(civil_name="Ana Souza", electoral_name="Ana", camara_id=1)
    bia = Politician(civil_name="Beatriz Lima", electoral_name="Bia", camara_id=2)
    db.add_all([ana, bia])
    db.flush()
    mand = Mandate(politician_id=ana.id, party_id=pt.id, office=CargoPoliticoEnum.DEPUTADO_FEDERAL, election_year=2022,
                   start_date=date(2023, 2, 1), end_date=FAR_FUTURE, jurisdiction_state="SP")
    db.add_all([mand, Mandate(politician_id=bia.id, party_id=pl.id, office=CargoPoliticoEnum.DEPUTADO_FEDERAL,
                              election_year=2022, start_date=date(2023, 2, 1), end_date=FAR_FUTURE,
                              jurisdiction_state="RJ")])
    prop = _prop(author_politician_id=ana.id, external_camara_id=77)
    db.add(prop)
    db.flush()
    db.add_all([
        PropositionAuthor(proposition_id=prop.id, politician_id=ana.id, author_name="Ana", authorship_type=TipoAutoriaEnum.AUTOR_PRINCIPAL),
        PropositionAuthor(proposition_id=prop.id, politician_id=None, author_name="Comissão X", authorship_type=TipoAutoriaEnum.INSTITUCIONAL, order=2),
    ])
    db.commit()
    return {"pt": pt, "pl": pl, "ana": ana, "bia": bia, "prop": prop, "mand": mand}


def _votacao_completa(db, c):
    """Mesma votação nas duas representações legadas, com votos divergentes em um deputado."""
    sessao = VotingSession(proposition_id=c["prop"].id, legislative_house=CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS,
                           session_datetime=INSTANTE, agenda_title="Votação do PL 1", is_approved=True,
                           votes_yes_count=0, external_id="CAM-1")
    db.add(sessao)
    db.flush()
    delib = VotacaoProposicao(id=sessao.id, proposicao_id=c["prop"].id, data_hora=INSTANTE,
                              local_deliberacao="Plenário da Câmara dos Deputados", tipo_deliberacao="NOMINAL",
                              resumo_decisao="Aprovado", total_sim=300, aprovada=True)
    db.add(delib)
    db.flush()
    db.add_all([
        ParliamentaryVote(voting_session_id=sessao.id, politician_id=c["ana"].id, party_id=c["pt"].id, vote_choice=VotoOpcaoEnum.SIM),
        ParliamentaryVote(voting_session_id=sessao.id, politician_id=c["bia"].id, party_id=c["pl"].id, vote_choice=VotoOpcaoEnum.NAO),
        VotoNominal(votacao_id=delib.id, parlamentar_id=c["ana"].id, voto="SIM"),
        VotoNominal(votacao_id=delib.id, parlamentar_id=c["bia"].id, voto="ABSTENCAO"),
        OrientacaoPartidaria(votacao_id=delib.id, partido_bancada="PT", orientacao="SIM"),
        OrientacaoPartidaria(votacao_id=delib.id, partido_bancada="Governo", orientacao="SIM"),
    ])
    db.commit()


def test_leg_reference_tables_are_seeded(db):
    assert _scalar(db, "SELECT count(*) FROM ref.tipo_proposicao") == 12
    assert _scalar(db, "SELECT count(*) FROM ref.status_tramitacao") == 9
    assert _scalar(db, "SELECT rotulo FROM ref.opcao_voto WHERE codigo = 'ARTIGO_17'") == "Art. 17"
    assert _scalar(db, "SELECT tem_posicao FROM ref.opcao_voto WHERE codigo = 'AUSENTE'") is False


def test_data_window_starts_in_1995_enforced_by_the_database(db):
    sql = ("INSERT INTO leg.proposicao (tipo_codigo, numero, ano, titulo, ementa, data_apresentacao, status_codigo) "
           "VALUES ('PL', 1, :ano, 't', 'e', :data, 'EM_TRAMITACAO')")
    db.execute(text(sql), {"ano": 1995, "data": date(1995, 1, 2)})
    with pytest.raises(IntegrityError):
        db.execute(text(sql), {"ano": 1994, "data": date(1994, 12, 31)})
    db.rollback()


def test_bridge_copies_proposition_with_author_and_authorships(db, cenario):
    sync_legacy_to_core(db)
    assert _rows(db, "SELECT p.tipo_codigo, p.numero, pe.nome_exibicao FROM leg.proposicao p "
                     "JOIN core.pessoa pe ON pe.id = p.autor_pessoa_id") == [("PL", 1, "Ana")]
    assert _scalar(db, "SELECT uid::text FROM leg.proposicao") == str(cenario["prop"].id)  # uid público preservado
    autorias = _rows(db, "SELECT nome_autor, tipo_codigo, pessoa_id IS NOT NULL FROM leg.autoria ORDER BY ordem")
    assert autorias == [("Ana", "AUTOR_PRINCIPAL", True), ("Comissão X", "INSTITUCIONAL", False)]


def test_bridge_rejects_propositions_before_the_1995_window(db, cenario):
    db.add(_prop(number=2, year=1990, presentation_date=date(1990, 5, 1), title="PL 2/1990"))
    db.commit()
    summary = sync_legacy_to_core(db)
    assert _scalar(db, "SELECT count(*) FROM leg.proposicao") == 1
    assert _rows(db, "SELECT motivo FROM etl.rejeito WHERE recurso = 'proposicao'") == [("FORA_DA_JANELA_1995",)]
    assert summary["legislativo"]["rejeitos"] == 1


def test_both_legacy_vote_representations_become_one_votacao(db, cenario):
    _votacao_completa(db, cenario)
    sync_legacy_to_core(db)
    assert _scalar(db, "SELECT count(*) FROM leg.votacao") == 1
    assert _scalar(db, "SELECT count(*) FROM leg.votacao_legado") == 2  # os dois ids legados continuam rastreáveis
    row = _rows(db, "SELECT tipo_deliberacao, id_externo, local_deliberacao, total_sim_fonte, c.codigo "
                    "FROM leg.votacao v JOIN ref.casa_legislativa c ON c.id = v.casa_id")[0]
    assert row == ("NOMINAL", "CAM-1", "Plenário da Câmara dos Deputados", 300, "CAMARA_DOS_DEPUTADOS")


def test_votes_are_deduplicated_and_nominal_source_wins(db, cenario):
    _votacao_completa(db, cenario)
    sync_legacy_to_core(db)
    votos = dict(_rows(db, "SELECT pe.nome_exibicao, v.opcao_codigo FROM leg.voto v JOIN core.pessoa pe ON pe.id = v.pessoa_id"))
    assert votos == {"Ana": "SIM", "Bia": "ABSTENCAO"}  # votos_nominais prevalece sobre votos_parlamentares (NAO)
    partidos = dict(_rows(db, "SELECT pe.nome_exibicao, pa.sigla FROM leg.voto v JOIN core.pessoa pe ON pe.id = v.pessoa_id "
                              "LEFT JOIN core.partido pa ON pa.id = v.partido_id"))
    assert partidos["Ana"] == "PT" or partidos["Ana"] is None


def test_party_orientation_resolves_party_but_keeps_blocs(db, cenario):
    _votacao_completa(db, cenario)
    sync_legacy_to_core(db)
    rows = dict(_rows(db, "SELECT o.bancada, pa.sigla FROM leg.orientacao o LEFT JOIN core.partido pa ON pa.id = o.partido_id"))
    assert rows == {"PT": "PT", "Governo": None}


def test_session_without_counterpart_keeps_source_totals(db, cenario):
    secreta = VotingSession(proposition_id=cenario["prop"].id, legislative_house=CasaLegislativaEnum.SENADO_FEDERAL,
                            session_datetime=INSTANTE, agenda_title="Secreta", is_approved=True, is_secret_vote=True,
                            votes_yes_count=40, votes_no_count=20, external_id="SEN-1")
    db.add(secreta)
    db.commit()
    sync_legacy_to_core(db)
    assert _rows(db, "SELECT tipo_deliberacao, secreta, total_sim_fonte, total_nao_fonte FROM leg.votacao") == [("SECRETA", True, 40, 20)]


def test_bridge_is_idempotent_for_the_legislative_schema(db, cenario):
    _votacao_completa(db, cenario)
    sync_legacy_to_core(db)
    sql = ("SELECT (SELECT count(*) FROM leg.proposicao), (SELECT count(*) FROM leg.autoria), "
           "(SELECT count(*) FROM leg.votacao), (SELECT count(*) FROM leg.voto), (SELECT count(*) FROM leg.orientacao), "
           "(SELECT min(id) FROM leg.votacao), (SELECT min(id) FROM leg.proposicao)")
    antes = _rows(db, sql)
    sync_legacy_to_core(db)
    assert _rows(db, sql) == antes


def test_attendance_is_deduplicated_and_routed_to_the_year_partition(db, cenario):
    for _ in range(2):  # duplicata típica do legado: um registro por mandato legado duplicado
        db.add(AttendanceRecord(politician_id=cenario["ana"].id, mandate_id=cenario["mand"].id,
                                legislative_house=CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS, session_date=date(2024, 3, 5),
                                attendance_status=TipoPresencaEnum.PRESENTE))
    db.commit()
    sync_legacy_to_core(db)
    assert _rows(db, "SELECT tableoid::regclass::text, tipo_codigo, mandato_id IS NOT NULL FROM leg.presenca") == [
        ("leg.presenca_2024", "PRESENTE", True)
    ]


def test_attendance_before_1995_is_rejected_with_reason(db, cenario):
    db.add(AttendanceRecord(politician_id=cenario["ana"].id, mandate_id=cenario["mand"].id,
                            legislative_house=CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS, session_date=date(1990, 3, 5),
                            attendance_status=TipoPresencaEnum.PRESENTE))
    db.commit()
    sync_legacy_to_core(db)
    assert _scalar(db, "SELECT count(*) FROM leg.presenca") == 0
    assert _rows(db, "SELECT motivo FROM etl.rejeito WHERE recurso = 'presenca'") == [("FORA_DA_JANELA_1995",)]


def test_full_text_search_on_summary(db, cenario):
    sync_legacy_to_core(db)
    assert _scalar(db, "SELECT count(*) FROM leg.proposicao WHERE ementa_tsv @@ plainto_tsquery('portuguese', 'ementas')") == 1
