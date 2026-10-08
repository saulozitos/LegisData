from datetime import date

from app.models import CargoPoliticoEnum, Mandate, PartyAffiliation, Politician, StatusMandatoEnum


def test_list_parties_counts_only_current_mandates(client, seed):
    response = client.get("/api/v1/parties")
    assert response.status_code == 200
    by_sigla = {p["sigla"]: p for p in response.json()}

    # PT: Fulano e Lula da Fonte em mandato vigente (+ o presidente, que NÃO é deputado/senador)
    assert by_sigla["PT"]["total_deputados"] == 2
    # PTB: Beltrano e as duas Maria Silva; o mandato histórico (encerrado em 2010) do Fulano não conta
    assert by_sigla["PTB"]["total_deputados"] == 3
    assert by_sigla["PT"]["total_senadores"] == 0
    assert by_sigla["PT"]["total_parlamentares"] == 2
    assert by_sigla["PT"]["total_filiados_ativos"] == 2
    assert by_sigla["PTB"]["total_filiados_ativos"] == 1
    assert by_sigla["PT"]["cor_hex"] == "#ef4444"
    assert by_sigla["PTB"]["cor_hex"] == "#64748b"  # sem cor cadastrada: cinza neutro


def test_list_parties_excludes_placeholder_party_and_sorts_by_caucus(client, seed):
    siglas = [p["sigla"] for p in client.get("/api/v1/parties").json()]
    assert "S.PART." not in siglas
    assert siglas == ["PTB", "PT"]  # maior bancada primeiro


def test_list_parties_does_not_invent_ideology_motto_or_spectrum(client, seed):
    for party in client.get("/api/v1/parties").json():
        assert party["ideologia"] is None
        assert party["lema"] is None
        assert party["espectro_politico"] is None


def test_same_politician_is_counted_once_per_party(client, db, seed):
    db.add(
        Mandate(
            politician_id=seed.fulano.id,
            party_id=seed.pt.id,
            office=CargoPoliticoEnum.DEPUTADO_FEDERAL,
            election_year=2026,
            term_number=2,
            start_date=date(2027, 2, 1),
            end_date=date(2999, 1, 31),
            jurisdiction_state="SP",
        )
    )
    db.commit()
    pt = next(p for p in client.get("/api/v1/parties").json() if p["sigla"] == "PT")
    assert pt["total_deputados"] == 2


def test_inactive_status_is_not_part_of_the_current_caucus(client, db, seed):
    fora = Politician(civil_name="Licenciado", electoral_name="Licenciado", camara_id=900)
    db.add(fora)
    db.flush()
    db.add(
        Mandate(
            politician_id=fora.id,
            party_id=seed.pt.id,
            office=CargoPoliticoEnum.DEPUTADO_FEDERAL,
            election_year=2022,
            start_date=date(2023, 2, 1),
            end_date=date(2999, 1, 31),
            status=StatusMandatoEnum.LICENCIADO,
        )
    )
    db.commit()
    pt = next(p for p in client.get("/api/v1/parties").json() if p["sigla"] == "PT")
    assert pt["total_deputados"] == 2


def test_senators_are_counted_separately(client, db, seed):
    senador = Politician(civil_name="Senador", electoral_name="Senador", senado_id=77)
    db.add(senador)
    db.flush()
    db.add(
        Mandate(
            politician_id=senador.id,
            party_id=seed.pt.id,
            office=CargoPoliticoEnum.SENADOR,
            election_year=2022,
            start_date=date(2023, 2, 1),
            end_date=date(2999, 1, 31),
            jurisdiction_state="SP",
        )
    )
    db.add(
        PartyAffiliation(politician_id=senador.id, party_id=seed.pt.id, start_date=date(2020, 1, 1), is_current=True)
    )
    db.commit()
    pt = next(p for p in client.get("/api/v1/parties").json() if p["sigla"] == "PT")
    assert (pt["total_deputados"], pt["total_senadores"], pt["total_parlamentares"]) == (2, 1, 3)


def test_list_parties_empty_database(client):
    assert client.get("/api/v1/parties").json() == []
