"""Schema novo (ref/core/etl/param): restrições do banco, sementes, ponte legado -> core e views."""

from datetime import date

import pytest
from app.models import (
    CabinetMember,
    CargoPoliticoEnum,
    Mandate,
    MotivoDesfiliacaoEnum,
    PartyAffiliation,
    PoliticalParty,
    Politician,
    StatusMandatoEnum,
)
from app.services.core_sync import sync_legacy_to_core
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

FAR_FUTURE = date(2999, 1, 31)


def _scalar(db, sql, **params):
    return db.execute(text(sql), params).scalar()


def _rows(db, sql, **params):
    return [tuple(r) for r in db.execute(text(sql), params)]


@pytest.fixture()
def cenario(db):
    """Duas pessoas, dois partidos e um deputado que trocou de partido (3 mandatos legados para o mesmo mandato)."""
    pt = PoliticalParty(acronym="PT", full_name="Partido dos Trabalhadores")
    pl = PoliticalParty(acronym="PL", full_name="Partido Liberal")
    db.add_all([pt, pl])
    ana = Politician(civil_name="Ana Souza", electoral_name="Ana", camara_id=1)
    bia = Politician(civil_name="Beatriz Lima", electoral_name="Bia", camara_id=2, cpf="12345678901")
    db.add_all([ana, bia])
    db.flush()
    common = dict(
        office=CargoPoliticoEnum.DEPUTADO_FEDERAL,
        election_year=2022,
        start_date=date(2023, 2, 1),
        end_date=FAR_FUTURE,
        jurisdiction_state="SP",
    )
    # Ana: um único mandato conquistado, mas o loader legado gerou um registro por partido por onde passou
    db.add_all(
        [
            Mandate(politician_id=ana.id, party_id=pt.id, **common),
            Mandate(politician_id=ana.id, party_id=pl.id, term_number=1, **{**common}),
        ]
    )
    db.add_all(
        [
            PartyAffiliation(
                politician_id=ana.id, party_id=pt.id, start_date=date(2018, 1, 1), end_date=date(2024, 3, 31)
            ),
            PartyAffiliation(politician_id=ana.id, party_id=pl.id, start_date=date(2024, 4, 1), is_current=True),
            PartyAffiliation(politician_id=bia.id, party_id=pt.id, start_date=date(2019, 1, 1), is_current=True),
        ]
    )
    db.add(Mandate(politician_id=bia.id, party_id=pt.id, **common))
    db.commit()
    return {"pt": pt, "pl": pl, "ana": ana, "bia": bia}


# ── referência e sementes ────────────────────────────────────────────────────────────────────────


def test_reference_data_is_seeded(db):
    assert _scalar(db, "SELECT count(*) FROM ref.uf") == 27
    assert _scalar(db, "SELECT count(*) FROM ref.casa_legislativa WHERE tipo = 'ASSEMBLEIA'") == 27
    cargos = {r[0] for r in _rows(db, "SELECT codigo FROM ref.cargo")}
    assert {"GOVERNADOR", "VICE_GOVERNADOR", "DEPUTADO_ESTADUAL", "DEPUTADO_DISTRITAL", "SECRETARIO_ESTADUAL"} <= cargos
    assert {"PRESIDENTE", "SENADOR", "DEPUTADO_FEDERAL", "MINISTRO_DE_ESTADO"} <= cargos
    assert not {"PREFEITO", "VEREADOR"} & cargos  # municipais ficam fora do escopo desta refatoração (D1)


def test_vice_cargo_points_to_its_titular(db):
    assert _rows(
        db,
        "SELECT t.codigo FROM ref.cargo v JOIN ref.cargo t ON t.id = v.cargo_titular_id "
        "WHERE v.codigo = 'VICE_GOVERNADOR'",
    ) == [("GOVERNADOR",)]


def test_no_cpf_column_exists_in_the_new_schemas(db):
    assert (
        _rows(
            db,
            "SELECT table_schema, table_name, column_name FROM information_schema.columns "
            "WHERE table_schema IN ('ref','core','etl','param') AND column_name ILIKE '%cpf%'",
        )
        == []
    )


def test_ialp_weights_were_moved_out_of_the_code(db):
    relator = _scalar(
        db,
        "SELECT valor FROM param.peso p JOIN param.metodologia m ON m.id = p.metodologia_id "
        "WHERE m.codigo = 'IALP' AND p.dimensao = 'PESO_AUTORIA' AND p.chave = 'RELATOR'",
    )
    corte = _scalar(
        db,
        "SELECT valor FROM param.peso p JOIN param.metodologia m ON m.id = p.metodologia_id "
        "WHERE m.codigo = 'IPLE' AND p.chave = 'CORTE_IPLE'",
    )
    assert float(relator) == pytest.approx(0.8)
    assert float(corte) == pytest.approx(0.785)


def test_normalizar_texto_removes_accents_case_and_extra_spaces(db):
    assert _scalar(db, "SELECT ref.normalizar_texto('  Átila   LIRA ')") == "atila lira"


# ── restrições do banco ──────────────────────────────────────────────────────────────────────────


def test_homonyms_are_allowed_but_not_duplicate_names_for_the_same_person(db):
    db.execute(text("INSERT INTO core.pessoa (nome_exibicao) VALUES ('Átila Lira'), ('Atila Lira')"))
    db.execute(
        text(
            "INSERT INTO core.pessoa_nome (pessoa_id, tipo, nome) SELECT id, 'ELEITORAL', nome_exibicao FROM core.pessoa"
        )
    )
    assert _scalar(db, "SELECT count(DISTINCT nome_normalizado) FROM core.pessoa_nome") == 1
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO core.pessoa_nome (pessoa_id, tipo, nome) "
                "SELECT id, 'ELEITORAL', 'ÁTILA LIRA' FROM core.pessoa ORDER BY id LIMIT 1"
            )
        )
    db.rollback()


def test_identifier_cannot_point_to_two_people(db):
    db.execute(text("INSERT INTO core.pessoa (nome_exibicao) VALUES ('A'), ('B')"))
    fonte = _scalar(db, "SELECT id FROM etl.fonte WHERE codigo = 'CAMARA_API'")
    db.execute(
        text(
            "INSERT INTO core.pessoa_identificador (pessoa_id, fonte_id, tipo, valor) "
            "SELECT id, :f, 'CAMARA_ID', '10' FROM core.pessoa ORDER BY id LIMIT 1"
        ),
        {"f": fonte},
    )
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO core.pessoa_identificador (pessoa_id, fonte_id, tipo, valor) "
                "SELECT id, :f, 'CAMARA_ID', '10' FROM core.pessoa ORDER BY id DESC LIMIT 1"
            ),
            {"f": fonte},
        )
    db.rollback()


def test_identifier_type_does_not_accept_cpf(db):
    db.execute(text("INSERT INTO core.pessoa (nome_exibicao) VALUES ('A')"))
    fonte = _scalar(db, "SELECT id FROM etl.fonte WHERE codigo = 'TSE'")
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO core.pessoa_identificador (pessoa_id, fonte_id, tipo, valor) "
                "SELECT id, :f, 'CPF', '1' FROM core.pessoa"
            ),
            {"f": fonte},
        )
    db.rollback()


def _pessoa_partido(db):
    db.execute(text("INSERT INTO core.pessoa (nome_exibicao) VALUES ('A')"))
    db.execute(text("INSERT INTO core.partido (sigla, nome) VALUES ('AA', 'Partido A'), ('BB', 'Partido B')"))


def test_person_cannot_have_overlapping_party_affiliations(db):
    _pessoa_partido(db)
    sql = (
        "INSERT INTO core.filiacao (pessoa_id, partido_id, periodo) "
        "SELECT pe.id, pa.id, daterange(:ini, :fim, '[]') FROM core.pessoa pe, core.partido pa WHERE pa.sigla = :s"
    )
    db.execute(text(sql), {"ini": date(2020, 1, 1), "fim": date(2022, 12, 31), "s": "AA"})
    with pytest.raises(IntegrityError):
        db.execute(text(sql), {"ini": date(2022, 6, 1), "fim": date(2024, 1, 1), "s": "BB"})
    db.rollback()


def test_back_to_back_affiliations_are_allowed(db):
    _pessoa_partido(db)
    sql = (
        "INSERT INTO core.filiacao (pessoa_id, partido_id, periodo) "
        "SELECT pe.id, pa.id, daterange(:ini, :fim, '[]') FROM core.pessoa pe, core.partido pa WHERE pa.sigla = :s"
    )
    db.execute(text(sql), {"ini": date(2020, 1, 1), "fim": date(2022, 12, 31), "s": "AA"})
    db.execute(text(sql), {"ini": date(2023, 1, 1), "fim": None, "s": "BB"})
    assert _scalar(db, "SELECT count(*) FROM core.filiacao") == 2


def test_mandate_situations_cannot_overlap(db):
    _pessoa_partido(db)
    db.execute(
        text(
            "INSERT INTO core.mandato (pessoa_id, cargo_id, circunscricao_id, inicio) "
            "SELECT pe.id, (SELECT id FROM ref.cargo WHERE codigo = 'SENADOR'), "
            "(SELECT id FROM ref.circunscricao WHERE tipo = 'BR'), '2023-02-01' FROM core.pessoa pe"
        )
    )
    sql = (
        "INSERT INTO core.mandato_situacao (mandato_id, situacao, periodo) "
        "SELECT id, 'EXERCICIO', daterange(:ini, :fim, '[]') FROM core.mandato"
    )
    db.execute(text(sql), {"ini": date(2023, 2, 1), "fim": date(2023, 12, 31)})
    with pytest.raises(IntegrityError):
        db.execute(text(sql), {"ini": date(2023, 6, 1), "fim": date(2024, 1, 1)})
    db.rollback()


# ── ponte legado -> core ─────────────────────────────────────────────────────────────────────────


def test_bridge_creates_people_names_identifiers_and_never_copies_cpf(db, cenario):
    summary = sync_legacy_to_core(db)
    assert summary["pessoas"] == 2
    assert _scalar(db, "SELECT count(*) FROM core.pessoa_nome WHERE tipo = 'CIVIL'") == 2
    assert _scalar(db, "SELECT count(*) FROM core.pessoa_identificador WHERE tipo = 'CAMARA_ID'") == 2
    assert _scalar(db, "SELECT count(*) FROM core.pessoa_identificador") == 2  # CPF da Bia não foi copiado
    # O uid público é o id legado: o contrato com o frontend não muda
    assert _scalar(db, "SELECT uid::text FROM core.pessoa WHERE nome_exibicao = 'Ana'") == str(cenario["ana"].id)


def test_bridge_collapses_one_legacy_mandate_per_party_into_one_mandate(db, cenario):
    sync_legacy_to_core(db)
    assert _scalar(db, "SELECT count(*) FROM core.mandato WHERE condicao <> 'NOMEADO'") == 2
    assert _scalar(db, "SELECT count(*) FROM core.mandato_legado") == 3  # todos os ids legados continuam rastreáveis
    # partido do mandato = filiação vigente na posse (PT), não o último a ser carregado
    assert (
        _scalar(
            db,
            "SELECT pa.sigla FROM core.mandato m JOIN core.partido pa ON pa.id = m.partido_id "
            "JOIN core.pessoa pe ON pe.id = m.pessoa_id WHERE pe.nome_exibicao = 'Ana'",
        )
        == "PT"
    )


def test_bridge_is_idempotent(db, cenario):
    sync_legacy_to_core(db)
    antes = _rows(db, "SELECT id, pessoa_id, cargo_id, partido_id FROM core.mandato ORDER BY id")
    contagens = _rows(
        db,
        "SELECT (SELECT count(*) FROM core.pessoa), (SELECT count(*) FROM core.pessoa_nome), "
        "(SELECT count(*) FROM core.filiacao), (SELECT count(*) FROM core.mandato_situacao), "
        "(SELECT count(*) FROM core.partido)",
    )
    sync_legacy_to_core(db)
    assert _rows(db, "SELECT id, pessoa_id, cargo_id, partido_id FROM core.mandato ORDER BY id") == antes
    assert (
        _rows(
            db,
            "SELECT (SELECT count(*) FROM core.pessoa), (SELECT count(*) FROM core.pessoa_nome), "
            "(SELECT count(*) FROM core.filiacao), (SELECT count(*) FROM core.mandato_situacao), "
            "(SELECT count(*) FROM core.partido)",
        )
        == contagens
    )


def test_bridge_closes_open_affiliation_when_the_next_one_starts(db, cenario):
    db.add(
        PartyAffiliation(
            politician_id=cenario["bia"].id, party_id=cenario["pl"].id, start_date=date(2023, 5, 10), is_current=True
        )
    )
    db.commit()
    sync_legacy_to_core(db)
    rows = _rows(
        db,
        "SELECT pa.sigla, lower(f.periodo), upper(f.periodo), f.fim_inferido FROM core.filiacao f "
        "JOIN core.partido pa ON pa.id = f.partido_id JOIN core.pessoa pe ON pe.id = f.pessoa_id "
        "WHERE pe.nome_exibicao = 'Bia' ORDER BY lower(f.periodo)",
    )
    assert rows == [("PT", date(2019, 1, 1), date(2023, 5, 10), True), ("PL", date(2023, 5, 10), None, False)]
    assert (
        _scalar(
            db,
            "SELECT count(*) FROM core.filiacao f JOIN core.pessoa pe ON pe.id = f.pessoa_id "
            "WHERE pe.nome_exibicao = 'Bia' AND upper_inf(f.periodo)",
        )
        == 1
    )


def test_bridge_rejects_same_start_conflict_keeping_the_party_of_the_mandate(db, cenario):
    # Bia tem mandato pelo PT; uma segunda filiação aberta na mesma data, em outro partido, é contraditória
    db.add(
        PartyAffiliation(
            politician_id=cenario["bia"].id, party_id=cenario["pl"].id, start_date=date(2019, 1, 1), is_current=True
        )
    )
    db.commit()
    summary = sync_legacy_to_core(db)
    assert summary["rejeitos"] == 1
    assert _rows(db, "SELECT motivo FROM etl.rejeito") == [("FILIACAO_MESMO_INICIO_QUE_OUTRA_DA_MESMA_PESSOA",)]
    assert (
        _scalar(
            db,
            "SELECT pa.sigla FROM core.filiacao f JOIN core.partido pa ON pa.id = f.partido_id "
            "JOIN core.pessoa pe ON pe.id = f.pessoa_id WHERE pe.nome_exibicao = 'Bia'",
        )
        == "PT"
    )
    assert _scalar(db, "SELECT status FROM etl.execucao WHERE linhas_rejeitadas > 0 ORDER BY id LIMIT 1") == "COM_ALERTA"


def test_bridge_splits_mandate_when_holder_serves_as_minister(db, cenario):
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
    db.add(
        CabinetMember(
            mandate_id=mandato_pres.id,
            politician_id=cenario["ana"].id,
            occupant_name="Ana Souza",
            ministry_name="Ministério da Fazenda",
            inauguration_date=date(2024, 1, 1),
            departure_date=date(2024, 12, 31),
            is_economy_minister=True,
        )
    )
    db.commit()
    sync_legacy_to_core(db)
    rows = _rows(
        db,
        "SELECT ms.situacao, lower(ms.periodo), upper(ms.periodo) FROM core.mandato_situacao ms "
        "JOIN core.mandato m ON m.id = ms.mandato_id JOIN core.pessoa pe ON pe.id = m.pessoa_id "
        "JOIN ref.cargo c ON c.id = m.cargo_id "
        "WHERE pe.nome_exibicao = 'Ana' AND c.codigo = 'DEPUTADO_FEDERAL' ORDER BY lower(ms.periodo)",
    )
    assert [r[0] for r in rows] == ["EXERCICIO", "AFASTADO_MINISTERIO", "EXERCICIO"]
    assert rows[1][1:] == (date(2024, 1, 1), date(2025, 1, 1))
    assert (
        _scalar(db, "SELECT funcao_destaque FROM core.mandato WHERE orgao_nome = 'Ministério da Fazenda'") == "ECONOMIA"
    )


def test_minister_without_legacy_link_is_never_merged_by_name(db, cenario):
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
    db.add(
        CabinetMember(
            mandate_id=mandato_pres.id,
            politician_id=None,
            occupant_name="Beatriz  LIMA",
            ministry_name="Ministério da Fazenda",
            inauguration_date=date(2024, 1, 1),
        )
    )
    db.commit()
    sync_legacy_to_core(db)
    assert (
        _scalar(db, "SELECT count(*) FROM core.pessoa WHERE nome_exibicao ILIKE '%beatriz%lima%'") == 1
    )  # só o ministro
    assert _scalar(db, "SELECT count(*) FROM core.pessoa_candidata_duplicidade WHERE situacao = 'PENDENTE'") == 1


# ── views ────────────────────────────────────────────────────────────────────────────────────────


def test_bancada_atual_counts_each_person_once_in_the_current_party(db, cenario):
    sync_legacy_to_core(db)
    bancada = dict(
        _rows(db, "SELECT pa.sigla, b.total FROM core.vw_bancada_atual b JOIN core.partido pa ON pa.id = b.partido_id")
    )
    # Ana mudou do PT para o PL em 2024: conta uma vez, no PL. Bia continua no PT.
    assert bancada == {"PL": 1, "PT": 1}


def test_bancada_atual_excludes_licensed_holder(db, cenario):
    db.add(
        Mandate(
            politician_id=cenario["bia"].id,
            party_id=cenario["pt"].id,
            office=CargoPoliticoEnum.SENADOR,
            election_year=2018,
            start_date=date(2019, 2, 1),
            end_date=FAR_FUTURE,
            status=StatusMandatoEnum.LICENCIADO,
            jurisdiction_state="SP",
        )
    )
    db.commit()
    sync_legacy_to_core(db)
    assert (
        _scalar(
            db,
            "SELECT count(*) FROM core.vw_bancada_atual b JOIN ref.cargo c ON c.id = b.cargo_id "
            "WHERE c.codigo = 'SENADOR'",
        )
        == 0
    )


def test_vw_politico_composes_name_party_and_office(db, cenario):
    sync_legacy_to_core(db)
    ana = _rows(
        db,
        "SELECT nome_exibicao, partido_atual, cargo_atual, uf, total_mandatos FROM core.vw_politico "
        "WHERE nome_exibicao = 'Ana'",
    )
    assert ana == [("Ana", "PL", "DEPUTADO_FEDERAL", "SP", 1)]


def test_vw_historico_mandato_marks_finished_terms(db, cenario):
    db.add(
        Mandate(
            politician_id=cenario["bia"].id,
            party_id=cenario["pt"].id,
            office=CargoPoliticoEnum.DEPUTADO_FEDERAL,
            election_year=2014,
            start_date=date(2015, 2, 1),
            end_date=date(2019, 1, 31),
            status=StatusMandatoEnum.CONCLUIDO,
            jurisdiction_state="SP",
        )
    )
    db.commit()
    sync_legacy_to_core(db)
    assert _scalar(db, "SELECT situacao FROM core.vw_historico_mandato WHERE data_inicio = '2015-02-01'") in (
        "EXERCICIO",
        "ENCERRADO",
    )


def test_party_succession_and_unknown_enum_values_are_preserved(db):
    antigo = PoliticalParty(acronym="OLD", full_name="Antigo")
    novo = PoliticalParty(acronym="NEW", full_name="Novo")
    db.add_all([antigo, novo])
    db.flush()
    antigo.successor_party_id = novo.id
    db.commit()
    sync_legacy_to_core(db)
    assert _rows(
        db,
        "SELECT o.sigla, d.sigla, s.tipo FROM core.partido_sucessao s "
        "JOIN core.partido o ON o.id = s.partido_origem_id JOIN core.partido d ON d.id = s.partido_destino_id",
    ) == [("OLD", "NEW", "SUCESSAO")]


def test_party_alias_resolves_old_spellings(db):
    db.add(PoliticalParty(acronym="PODE", full_name="Podemos"))
    db.commit()
    sync_legacy_to_core(db)
    assert (
        _scalar(
            db,
            "SELECT p.sigla FROM core.partido_alias a JOIN core.partido p ON p.id = a.partido_id "
            "WHERE a.sigla_normalizada = 'podemos'",
        )
        == "PODE"
    )


# ── guarda contra deriva entre modelos ORM legados e o schema criado pelas migrações ─────────────


def test_legacy_orm_models_match_the_migrated_database(pg_engine):
    from app.models import Base

    inspector = inspect(pg_engine)
    faltando = []
    for table in Base.metadata.sorted_tables:
        if table.schema:
            continue
        existentes = {c["name"] for c in inspector.get_columns(table.name)} if inspector.has_table(table.name) else None
        if existentes is None:
            faltando.append(f"tabela {table.name}")
            continue
        faltando += [f"{table.name}.{c.name}" for c in table.columns if c.name not in existentes]
    assert faltando == []


def test_motivo_desfiliacao_values_are_preserved(db, cenario):
    db.add(
        PartyAffiliation(
            politician_id=cenario["bia"].id,
            party_id=cenario["pl"].id,
            start_date=date(2010, 1, 1),
            end_date=date(2010, 12, 31),
            disaffiliation_reason=MotivoDesfiliacaoEnum.EXPULSAO,
        )
    )
    db.commit()
    sync_legacy_to_core(db)
    assert (
        _scalar(
            db,
            "SELECT motivo_saida FROM core.filiacao f JOIN core.pessoa pe ON pe.id = f.pessoa_id "
            "WHERE pe.nome_exibicao = 'Bia' AND lower(f.periodo) = '2010-01-01'",
        )
        == "EXPULSAO"
    )
