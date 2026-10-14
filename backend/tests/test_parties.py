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


def test_ippm_ranking_endpoint(client, seed):
    response = client.get("/api/v1/parties/ippm-ranking?ano=2026")
    assert response.status_code == 200
    data = response.json()
    assert "periodo" in data
    assert "resumo_geral" in data
    assert "ranking" in data
    assert data["periodo"]["ano"] == 2026
    assert isinstance(data["ranking"], list)

    if data["ranking"]:
        first = data["ranking"][0]
        assert "sigla" in first
        assert "ippm_score_medio" in first
        assert "cadeiras_dia_equivalentes" in first
        assert "pontuacao_bruta_ialp" in first
        assert "pilares" in first
        assert "fidelidade_partidaria_pct" in first["pilares"]
        assert "taxa_eficacia_pct" in first["pilares"]
        assert "volume_relatorias" in first["pilares"]
        assert "quadrante_eficiencia" in first
        assert "titulo" in first["quadrante_eficiencia"]

    resumo = data["resumo_geral"]
    if all(p["pilares"]["taxa_eficacia_pct"] == 0 for p in data["ranking"]):
        assert resumo["partido_mais_eficaz"] is None


def test_ippm_ranking_filters(client, seed):
    # Test filters by house, bloc, spectrum
    resp_camara = client.get("/api/v1/parties/ippm-ranking?casa=CAMARA&bloco=ALL&espectro=ALL")
    assert resp_camara.status_code == 200
    assert resp_camara.json()["periodo"]["casa"] == "CAMARA"

    resp_bloco = client.get("/api/v1/parties/ippm-ranking?bloco=GOVERNO")
    assert resp_bloco.status_code == 200
    for p in resp_bloco.json()["ranking"]:
        assert p["bloco_politico"] == "BASE_GOVERNO"

    resp_espectro = client.get("/api/v1/parties/ippm-ranking?espectro=ESQUERDA")
    assert resp_espectro.status_code == 200
    for p in resp_espectro.json()["ranking"]:
        assert "ESQUERDA" in p["espectro_politico"].upper()


def test_party_timeline_endpoint(client, seed):
    response = client.get("/api/v1/parties/PT/historico-bancada")
    assert response.status_code == 200
    data = response.json()
    assert data["partido"] == "PT"
    assert "titulares_exercicio" in data
    assert "ministros_licenciados" in data
    assert "suplentes_ativos" in data


def test_cron_consolidation_and_logs(client, db, seed):
    from app.services.party_productivity_service import run_daily_cron_job

    # Run cron service directly (as the API is strictly read-only GET)
    run_data = run_daily_cron_job(db)
    assert run_data["status"] == "SUCESSO"
    assert run_data["tempo_processamento_segundos"] >= 0

    # Get cron logs via API GET endpoint
    logs_resp = client.get("/api/v1/parties/cron/logs")
    assert logs_resp.status_code == 200
    logs_data = logs_resp.json()
    assert len(logs_data) >= 1
    assert logs_data[0]["status_execucao"] == "SUCESSO"


def test_service_sync_mandate_history_and_active_seats(db, seed):
    from datetime import date

    from app.services.party_productivity_service import (
        calculate_party_active_seats,
        sync_mandate_history,
    )

    synced = sync_mandate_history(db)
    assert synced >= 0

    seats_pt = calculate_party_active_seats(
        partido_sigla="PT",
        casa="CAMARA",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        db=db,
    )
    assert "total_parlamentares_ativos" in seats_pt
    assert "cadeiras_dia_equivalentes" in seats_pt
    assert seats_pt["cadeiras_dia_equivalentes"] >= 0.1


def test_list_parties_resolves_official_party_logos(client, seed):
    parties = {p["sigla"]: p for p in client.get("/api/v1/parties").json()}
    assert parties["PT"]["logo_url"] is not None
    assert "wikimedia.org" in parties["PT"]["logo_url"]
    assert parties["PTB"]["logo_url"] is not None
    assert "wikimedia.org" in parties["PTB"]["logo_url"]
