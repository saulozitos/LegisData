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
    base = dict(
        proposition_type=TipoProposicaoEnum.PL,
        number=1,
        year=2023,
        title="PL 1/2023",
        summary="Ementa",
        presentation_date=date(2023, 3, 1),
        status=StatusTramitacaoEnum.EM_TRAMITACAO,
    )
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
    mand = Mandate(
        politician_id=ana.id,
        party_id=pt.id,
        office=CargoPoliticoEnum.DEPUTADO_FEDERAL,
        election_year=2022,
        start_date=date(2023, 2, 1),
        end_date=FAR_FUTURE,
        jurisdiction_state="SP",
    )
    db.add_all(
        [
            mand,
            Mandate(
                politician_id=bia.id,
                party_id=pl.id,
                office=CargoPoliticoEnum.DEPUTADO_FEDERAL,
                election_year=2022,
                start_date=date(2023, 2, 1),
                end_date=FAR_FUTURE,
                jurisdiction_state="RJ",
            ),
        ]
    )
    prop = _prop(author_politician_id=ana.id, external_camara_id=77)
    db.add(prop)
    db.flush()
    db.add_all(
        [
            PropositionAuthor(
                proposition_id=prop.id,
                politician_id=ana.id,
                author_name="Ana",
                authorship_type=TipoAutoriaEnum.AUTOR_PRINCIPAL,
            ),
            PropositionAuthor(
                proposition_id=prop.id,
                politician_id=None,
                author_name="Comissão X",
                authorship_type=TipoAutoriaEnum.INSTITUCIONAL,
                order=2,
            ),
        ]
    )
    db.commit()
    return {"pt": pt, "pl": pl, "ana": ana, "bia": bia, "prop": prop, "mand": mand}


def _votacao_completa(db, c):
    """Mesma votação nas duas representações legadas, com votos divergentes em um deputado."""
    sessao = VotingSession(
        proposition_id=c["prop"].id,
        legislative_house=CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS,
        session_datetime=INSTANTE,
        agenda_title="Votação do PL 1",
        is_approved=True,
        votes_yes_count=0,
        external_id="CAM-1",
    )
    db.add(sessao)
    db.flush()
    delib = VotacaoProposicao(
        id=sessao.id,
        proposicao_id=c["prop"].id,
        data_hora=INSTANTE,
        local_deliberacao="Plenário da Câmara dos Deputados",
        tipo_deliberacao="NOMINAL",
        resumo_decisao="Aprovado",
        total_sim=300,
        aprovada=True,
    )
    db.add(delib)
    db.flush()
    db.add_all(
        [
            ParliamentaryVote(
                voting_session_id=sessao.id,
                politician_id=c["ana"].id,
                party_id=c["pt"].id,
                vote_choice=VotoOpcaoEnum.SIM,
            ),
            ParliamentaryVote(
                voting_session_id=sessao.id,
                politician_id=c["bia"].id,
                party_id=c["pl"].id,
                vote_choice=VotoOpcaoEnum.NAO,
            ),
            VotoNominal(votacao_id=delib.id, parlamentar_id=c["ana"].id, voto="SIM"),
            VotoNominal(votacao_id=delib.id, parlamentar_id=c["bia"].id, voto="ABSTENCAO"),
            OrientacaoPartidaria(votacao_id=delib.id, partido_bancada="PT", orientacao="SIM"),
            OrientacaoPartidaria(votacao_id=delib.id, partido_bancada="Governo", orientacao="SIM"),
        ]
    )
    db.commit()


def test_leg_reference_tables_are_seeded(db):
    assert _scalar(db, "SELECT count(*) FROM ref.tipo_proposicao") == 21
    assert _scalar(db, "SELECT count(*) FROM ref.status_tramitacao") == 10
    assert _scalar(db, "SELECT rotulo FROM ref.opcao_voto WHERE codigo = 'ARTIGO_17'") == "Art. 17"
    assert _scalar(db, "SELECT tem_posicao FROM ref.opcao_voto WHERE codigo = 'AUSENTE'") is False


def test_data_window_starts_in_1995_enforced_by_the_database(db):
    sql = (
        "INSERT INTO leg.proposicao (tipo_codigo, numero, ano, titulo, ementa, data_apresentacao, status_codigo) "
        "VALUES ('PL', 1, :ano, 't', 'e', :data, 'EM_TRAMITACAO')"
    )
    db.execute(text(sql), {"ano": 1995, "data": date(1995, 1, 2)})
    with pytest.raises(IntegrityError):
        db.execute(text(sql), {"ano": 1994, "data": date(1994, 12, 31)})
    db.rollback()


def test_bridge_copies_proposition_with_author_and_authorships(db, cenario):
    sync_legacy_to_core(db)
    assert _rows(
        db,
        "SELECT p.tipo_codigo, p.numero, pe.nome_exibicao FROM leg.proposicao p "
        "JOIN core.pessoa pe ON pe.id = p.autor_pessoa_id",
    ) == [("PL", 1, "Ana")]
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
    row = _rows(
        db,
        "SELECT tipo_deliberacao, id_externo, local_deliberacao, total_sim_fonte, c.codigo "
        "FROM leg.votacao v JOIN ref.casa_legislativa c ON c.id = v.casa_id",
    )[0]
    assert row == ("NOMINAL", "CAM-1", "Plenário da Câmara dos Deputados", 300, "CAMARA_DOS_DEPUTADOS")


def test_votes_are_deduplicated_and_nominal_source_wins(db, cenario):
    _votacao_completa(db, cenario)
    sync_legacy_to_core(db)
    votos = dict(
        _rows(db, "SELECT pe.nome_exibicao, v.opcao_codigo FROM leg.voto v JOIN core.pessoa pe ON pe.id = v.pessoa_id")
    )
    assert votos == {"Ana": "SIM", "Bia": "ABSTENCAO"}  # votos_nominais prevalece sobre votos_parlamentares (NAO)
    partidos = dict(
        _rows(
            db,
            "SELECT pe.nome_exibicao, pa.sigla FROM leg.voto v JOIN core.pessoa pe ON pe.id = v.pessoa_id "
            "LEFT JOIN core.partido pa ON pa.id = v.partido_id",
        )
    )
    assert partidos["Ana"] == "PT" or partidos["Ana"] is None


def test_party_orientation_resolves_party_but_keeps_blocs(db, cenario):
    _votacao_completa(db, cenario)
    sync_legacy_to_core(db)
    rows = dict(
        _rows(db, "SELECT o.bancada, pa.sigla FROM leg.orientacao o LEFT JOIN core.partido pa ON pa.id = o.partido_id")
    )
    assert rows == {"PT": "PT", "Governo": None}


def test_session_without_counterpart_keeps_source_totals(db, cenario):
    secreta = VotingSession(
        proposition_id=cenario["prop"].id,
        legislative_house=CasaLegislativaEnum.SENADO_FEDERAL,
        session_datetime=INSTANTE,
        agenda_title="Secreta",
        is_approved=True,
        is_secret_vote=True,
        votes_yes_count=40,
        votes_no_count=20,
        external_id="SEN-1",
    )
    db.add(secreta)
    db.commit()
    sync_legacy_to_core(db)
    assert _rows(db, "SELECT tipo_deliberacao, secreta, total_sim_fonte, total_nao_fonte FROM leg.votacao") == [
        ("SECRETA", True, 40, 20)
    ]


def test_bridge_is_idempotent_for_the_legislative_schema(db, cenario):
    _votacao_completa(db, cenario)
    sync_legacy_to_core(db)
    sql = (
        "SELECT (SELECT count(*) FROM leg.proposicao), (SELECT count(*) FROM leg.autoria), "
        "(SELECT count(*) FROM leg.votacao), (SELECT count(*) FROM leg.voto), (SELECT count(*) FROM leg.orientacao), "
        "(SELECT min(id) FROM leg.votacao), (SELECT min(id) FROM leg.proposicao)"
    )
    antes = _rows(db, sql)
    sync_legacy_to_core(db)
    assert _rows(db, sql) == antes


def test_attendance_is_deduplicated_and_routed_to_the_year_partition(db, cenario):
    for _ in range(2):  # duplicata típica do legado: um registro por mandato legado duplicado
        db.add(
            AttendanceRecord(
                politician_id=cenario["ana"].id,
                mandate_id=cenario["mand"].id,
                legislative_house=CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS,
                session_date=date(2024, 3, 5),
                attendance_status=TipoPresencaEnum.PRESENTE,
            )
        )
    db.commit()
    sync_legacy_to_core(db)
    assert _rows(db, "SELECT tableoid::regclass::text, tipo_codigo, mandato_id IS NOT NULL FROM leg.presenca") == [
        ("leg.presenca_2024", "PRESENTE", True)
    ]


def test_attendance_before_1995_is_rejected_with_reason(db, cenario):
    db.add(
        AttendanceRecord(
            politician_id=cenario["ana"].id,
            mandate_id=cenario["mand"].id,
            legislative_house=CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS,
            session_date=date(1990, 3, 5),
            attendance_status=TipoPresencaEnum.PRESENTE,
        )
    )
    db.commit()
    sync_legacy_to_core(db)
    assert _scalar(db, "SELECT count(*) FROM leg.presenca") == 0
    assert _rows(db, "SELECT motivo FROM etl.rejeito WHERE recurso = 'presenca'") == [("FORA_DA_JANELA_1995",)]


def test_full_text_search_on_summary(db, cenario):
    sync_legacy_to_core(db)
    assert (
        _scalar(db, "SELECT count(*) FROM leg.proposicao WHERE ementa_tsv @@ plainto_tsquery('portuguese', 'ementas')")
        == 1
    )


# ── pesos em param, autoria pontuada, placar e cadeiras-dia ──────────────────────────────────────


def test_peso_de_returns_the_configured_weight(db):
    assert float(_scalar(db, "SELECT param.peso_de('IALP', 'PESO_TIPO', 'PEC')")) == 3.0
    assert float(_scalar(db, "SELECT param.peso_de('IALP', 'PESO_AUTORIA', 'RELATOR')")) == 0.8
    assert float(_scalar(db, "SELECT param.peso_de('IALP', 'PESO_STATUS', 'VETADA_PARCIAL')")) == 1.5
    assert float(_scalar(db, "SELECT param.peso_de('IALP', 'PESO_STATUS', 'VETADA_TOTAL')")) == 0.8
    assert float(_scalar(db, "SELECT param.peso_de('IALP', 'PESO_TIPO', 'DECRETO_PRES')")) == 1.0


def test_peso_de_fails_when_the_weight_is_missing_there_is_no_silent_default(db):
    with pytest.raises(Exception, match="Peso não configurado"):
        db.execute(text("SELECT param.peso_de('IALP', 'PESO_TIPO', 'TIPO_NOVO')"))
    db.rollback()
    with pytest.raises(Exception, match="Peso não configurado"):
        db.execute(text("SELECT param.peso_de('INEXISTENTE', 'PESO_TIPO', 'PEC')"))
    db.rollback()


def test_single_methodology_has_a_weight_for_every_reference_code_and_no_wildcard(db):
    assert _rows(db, "SELECT codigo, versao FROM param.metodologia WHERE codigo IN ('IALP', 'IPPM') ORDER BY 1, 2") == [
        ("IALP", 2),
        ("IALP", 3),
    ]
    assert _scalar(db, "SELECT count(*) FROM param.peso WHERE chave = '*'") == 0
    sem_peso = _rows(
        db,
        """
        SELECT 'PESO_TIPO', codigo FROM ref.tipo_proposicao t
          WHERE NOT EXISTS (SELECT 1 FROM param.peso p JOIN param.metodologia m ON m.id = p.metodologia_id
                             WHERE m.codigo = 'IALP' AND m.versao = 3 AND p.dimensao = 'PESO_TIPO' AND p.chave = t.codigo)
        UNION ALL SELECT 'PESO_STATUS', codigo FROM ref.status_tramitacao t
          WHERE NOT EXISTS (SELECT 1 FROM param.peso p JOIN param.metodologia m ON m.id = p.metodologia_id
                             WHERE m.codigo = 'IALP' AND m.versao = 3 AND p.dimensao = 'PESO_STATUS' AND p.chave = t.codigo)
        UNION ALL SELECT 'PESO_AUTORIA', codigo FROM ref.tipo_autoria t
          WHERE NOT EXISTS (SELECT 1 FROM param.peso p JOIN param.metodologia m ON m.id = p.metodologia_id
                             WHERE m.codigo = 'IALP' AND m.versao = 3 AND p.dimensao = 'PESO_AUTORIA' AND p.chave = t.codigo)""",
    )
    assert sem_peso == []


def test_sancionado_is_not_a_status_and_has_no_weight(db):
    assert _scalar(db, "SELECT count(*) FROM param.peso WHERE chave = 'SANCIONADO'") == 0


def test_python_loader_is_strict(db):
    from app.services.ialp_pesos import PesoNaoConfigurado, carregar_pesos_ialp

    pesos = carregar_pesos_ialp(db)
    assert pesos.peso_status("VETADA_TOTAL") == 0.8
    with pytest.raises(PesoNaoConfigurado):
        pesos.peso_status("SANCIONADO")


def test_author_is_scored_in_the_party_he_belonged_to_when_the_bill_was_filed(db, cenario):
    from app.models import PartyAffiliation

    ana, pt, pl = cenario["ana"], cenario["pt"], cenario["pl"]
    db.add_all(
        [
            PartyAffiliation(
                politician_id=ana.id, party_id=pt.id, start_date=date(2018, 1, 1), end_date=date(2024, 3, 31)
            ),
            PartyAffiliation(politician_id=ana.id, party_id=pl.id, start_date=date(2024, 4, 1), is_current=True),
        ]
    )
    depois = _prop(number=2, title="PL 2/2024", presentation_date=date(2024, 6, 1), year=2024)
    db.add(depois)
    db.flush()
    db.add(
        PropositionAuthor(
            proposition_id=depois.id,
            politician_id=ana.id,
            author_name="Ana",
            authorship_type=TipoAutoriaEnum.AUTOR_PRINCIPAL,
        )
    )
    db.commit()
    sync_legacy_to_core(db)
    rows = _rows(
        db,
        "SELECT p.numero, pa.sigla, v.pontos_ialp FROM leg.vw_autoria_pontuada v "
        "JOIN leg.proposicao p ON p.id = v.proposicao_id JOIN core.partido pa ON pa.id = v.partido_id "
        "WHERE v.tipo_autoria = 'AUTOR_PRINCIPAL' ORDER BY p.numero",
    )
    # PL (peso 2.0) x autor principal (1.0) x em tramitação (1.0) = 2.0 para ambas; o partido muda com a data
    assert [(r[0], r[1], float(r[2])) for r in rows] == [(1, "PT", 2.0), (2, "PL", 2.0)]


def test_institutional_authorship_does_not_score(db, cenario):
    sync_legacy_to_core(db)
    assert _scalar(db, "SELECT count(*) FROM leg.vw_autoria_pontuada WHERE tipo_autoria = 'INSTITUCIONAL'") == 0


def test_placar_counts_nominal_votes_and_falls_back_to_source_totals(db, cenario):
    _votacao_completa(db, cenario)
    db.add(
        VotingSession(
            proposition_id=cenario["prop"].id,
            legislative_house=CasaLegislativaEnum.SENADO_FEDERAL,
            session_datetime=datetime(2023, 6, 1, 12, tzinfo=timezone.utc),
            agenda_title="Secreta",
            is_approved=True,
            is_secret_vote=True,
            votes_yes_count=40,
            votes_no_count=20,
        )
    )
    db.commit()
    sync_legacy_to_core(db)
    placares = _rows(
        db,
        "SELECT v.tipo_deliberacao, p.tem_voto_nominal, p.sim, p.nao, p.abstencao "
        "FROM leg.vw_votacao_placar p JOIN leg.votacao v ON v.id = p.votacao_id ORDER BY v.data_hora",
    )
    assert placares == [("NOMINAL", True, 1, 0, 1), ("SECRETA", False, 40, 20, 0)]


def test_party_seat_days_follow_affiliation_changes_inside_the_period(db, cenario):
    from app.models import PartyAffiliation
    from app.services.party_productivity_service import calculate_party_active_seats

    ana = cenario["ana"]
    db.add_all(
        [
            PartyAffiliation(
                politician_id=ana.id, party_id=cenario["pt"].id, start_date=date(2018, 1, 1), end_date=date(2024, 3, 31)
            ),
            PartyAffiliation(
                politician_id=ana.id, party_id=cenario["pl"].id, start_date=date(2024, 4, 1), is_current=True
            ),
        ]
    )
    db.commit()
    sync_legacy_to_core(db)
    inicio, fim = date(2024, 1, 1), date(2024, 12, 31)  # 2024 é bissexto: 366 dias
    pt = calculate_party_active_seats("PT", "CAMARA", inicio, fim, db)
    pl = calculate_party_active_seats("PL", "CAMARA", inicio, fim, db)
    assert pt["cadeiras_dia_equivalentes"] == pytest.approx(91 / 366, abs=0.01)  # 1º jan a 31 mar
    assert pl["cadeiras_dia_equivalentes"] == pytest.approx(275 / 366 + 1.0, abs=0.01)  # Ana + Bia (PL o ano todo)
    assert pt["total_parlamentares_ativos"] == 1


def test_seat_days_exclude_the_period_holder_serves_as_minister(db, cenario):
    from app.services.party_productivity_service import calculate_party_active_seats

    presidente = Politician(civil_name="Presidente X", electoral_name="Presidente X", camara_id=9)
    db.add(presidente)
    db.flush()
    mandato_pres = Mandate(
        politician_id=presidente.id,
        party_id=cenario["pt"].id,
        office=CargoPoliticoEnum.PRESIDENTE,
        election_year=2022,
        start_date=date(2023, 1, 1),
        end_date=FAR_FUTURE,
        jurisdiction_state="BR",
    )
    db.add(mandato_pres)
    db.flush()
    from app.models import CabinetMember, PartyAffiliation

    db.add_all(
        [
            PartyAffiliation(
                politician_id=cenario["ana"].id, party_id=cenario["pt"].id, start_date=date(2018, 1, 1), is_current=True
            ),
            CabinetMember(
                mandate_id=mandato_pres.id,
                politician_id=cenario["ana"].id,
                occupant_name="Ana Souza",
                ministry_name="Ministério X",
                inauguration_date=date(2025, 7, 1),
                departure_date=date(2025, 12, 31),
            ),
        ]
    )
    db.commit()
    sync_legacy_to_core(db)
    seats = calculate_party_active_seats("PT", "CAMARA", date(2025, 1, 1), date(2025, 12, 31), db)
    assert seats["cadeiras_dia_equivalentes"] == pytest.approx(181 / 365, abs=0.01)  # 1º jan a 30 jun


def test_government_orientation_applies_to_the_party_of_the_sitting_president(client, db, cenario):
    presidente = Politician(civil_name="Presidente X", electoral_name="Presidente X", camara_id=9)
    db.add(presidente)
    db.flush()
    db.add(
        Mandate(
            politician_id=presidente.id,
            party_id=cenario["pl"].id,
            office=CargoPoliticoEnum.PRESIDENTE,
            election_year=2022,
            start_date=date(2023, 1, 1),
            end_date=FAR_FUTURE,
            jurisdiction_state="BR",
        )
    )
    _votacao_completa(db, cenario)
    sync_legacy_to_core(db)
    # A orientação "Governo" (SIM) vale para o partido do presidente em exercício (PL, aqui), não para o PT
    ranking = {r["sigla"]: r for r in client.get("/api/v1/parties/ippm-ranking?ano=2023").json()["ranking"]}
    assert ranking["PL"]["pilares"]["fidelidade_partidaria_pct"] == 0.0  # Bia (PL) se absteve contra SIM do Governo
    assert ranking["PT"]["pilares"]["fidelidade_partidaria_pct"] == 100.0  # PT segue a própria orientação (SIM)


def test_modelos_migrados_coincidem_com_o_banco(db):
    """Guarda: toda coluna mapeada em um modelo MigratedBase existe na tabela criada pelas migrações."""
    from app.models.base import MigratedBase
    from sqlalchemy import text

    faltando = []
    for tabela in MigratedBase.metadata.tables.values():
        existentes = {
            r[0]
            for r in db.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_schema = :s AND table_name = :t"),
                {"s": tabela.schema, "t": tabela.name},
            )
        }
        assert existentes, f"tabela {tabela.fullname} não existe no banco"
        faltando += [f"{tabela.fullname}.{c.name}" for c in tabela.columns if c.name not in existentes]
    assert faltando == []
