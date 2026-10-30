from datetime import date

from app.models import CargoPoliticoEnum, Mandate, PartyAffiliation, Politician, StatusMandatoEnum
from app.services.staging_merge import merge_staging

from .conftest import criar_mandato_presidencial
from .test_composicao import _composicao


def test_list_parties_counts_only_current_mandates(client, db, seed):
    merge_staging(db)
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


def test_list_parties_excludes_placeholder_party_and_sorts_by_caucus(client, db, seed):
    merge_staging(db)
    siglas = [p["sigla"] for p in client.get("/api/v1/parties").json()]
    assert "S.PART." not in siglas
    assert siglas == ["PTB", "PT"]  # maior bancada primeiro


def test_list_parties_does_not_invent_ideology_motto_or_spectrum(client, db, seed):
    from app.models import PoliticalParty

    db.add(PoliticalParty(acronym="SEMDADOS", full_name="Partido Sem Dados"))
    db.commit()
    merge_staging(db)
    parties = {p["sigla"]: p for p in client.get("/api/v1/parties").json()}
    sem_dados = parties["SEMDADOS"]
    # Sigla fora da tabela de sementes e sem dado no legado: tudo permanece nulo, nada é inventado
    assert sem_dados["ideologia"] is None
    assert sem_dados["lema"] is None
    assert sem_dados["espectro_politico"] is None
    assert sem_dados["logo_url"] is None
    assert sem_dados["cor_hex"] == "#64748b"
    # Sigla presente na semente curada (ref.partido_semente): o dado vem do banco
    assert parties["PT"]["espectro_politico"] == "ESQUERDA"


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
    merge_staging(db)
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
    merge_staging(db)
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
    merge_staging(db)
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

    if resumo.get("partido_mais_produtivo") and any(p["total_cadeiras_ativas"] >= 3 for p in data["ranking"]):
        produtivo_sigla = resumo["partido_mais_produtivo"]["sigla"]
        party_in_ranking = next(p for p in data["ranking"] if p["sigla"] == produtivo_sigla)
        assert party_in_ranking["total_cadeiras_ativas"] >= 3


def test_ippm_ranking_filters(client, seed, db):
    # O bloco vem da classificação da Câmara no mandato presidencial mais recente com bancadas classificadas
    mandato = criar_mandato_presidencial(db, "Presidente", date(2023, 1, 1), None, "p-2023")
    _composicao(
        db,
        mandato,
        "CAMARA_DOS_DEPUTADOS",
        100,
        [("PT", 60, "BASE_GOVERNO", "#ef4444", None), ("PTB", 40, "OPOSICAO", "#64748b", None)],
    )
    db.commit()
    # Test filters by house, bloc, spectrum
    resp_camara = client.get("/api/v1/parties/ippm-ranking?casa=CAMARA&bloco=ALL&espectro=ALL")
    assert resp_camara.status_code == 200
    assert resp_camara.json()["periodo"]["casa"] == "CAMARA"

    resp_bloco = client.get("/api/v1/parties/ippm-ranking?bloco=GOVERNO")
    assert resp_bloco.status_code == 200
    governo = resp_bloco.json()["ranking"]
    assert governo, "o filtro de bloco não pode devolver ranking vazio quando há bancadas classificadas"
    assert {p["sigla"] for p in governo} == {"PT"}
    assert all(p["bloco_politico"] == "BASE_GOVERNO" for p in governo)
    oposicao = client.get("/api/v1/parties/ippm-ranking?bloco=OPOSICAO").json()["ranking"]
    assert {p["sigla"] for p in oposicao} == {"PTB"}

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
    from app.models.analytics import LogExecucaoCron

    # O cron real vive em `etl.pipelines.cron_daily_consolidation` (testado no ETL); aqui a rota de logs lê o que ele grava
    db.add(
        LogExecucaoCron(
            status_execucao="SUCESSO",
            registros_atualizados=3,
            tempo_processamento_segundos=1,
            etapa="CONSOLIDACAO_DIARIA_COMPLETA",
        )
    )
    db.commit()

    # Get cron logs via API GET endpoint
    logs_resp = client.get("/api/v1/parties/cron/logs")
    assert logs_resp.status_code == 200
    logs_data = logs_resp.json()
    assert len(logs_data) >= 1
    assert logs_data[0]["status_execucao"] == "SUCESSO"


def test_cron_logs_so_repete_etapa_e_classe_da_excecao(client, db):
    from app.models.analytics import LogExecucaoCron

    db.add_all(
        [
            LogExecucaoCron(
                status_execucao="FALHA",
                erro_mensagem='connection to server at "10.0.0.5", port 5432 failed: FATAL: password for user "app"',
                etapa="CONSOLIDACAO_DIARIA_COMPLETA",
            ),
            LogExecucaoCron(
                status_execucao="FALHA",
                erro_mensagem="votações: OperationalError; presença: HTTPError",
                etapa="CONSOLIDACAO_DIARIA_COMPLETA",
            ),
        ]
    )
    db.commit()
    corpo = client.get("/api/v1/parties/cron/logs")
    mensagens = {item["erro_mensagem"] for item in corpo.json()}
    assert mensagens == {
        "votações: OperationalError; presença: HTTPError",
        "Falha registrada; o detalhe está no log do servidor.",
    }
    for vazamento in ("10.0.0.5", "5432", "password", '"app"'):
        assert vazamento not in corpo.text


def test_service_merge_staging_and_active_seats(db, seed):
    from datetime import date

    from app.services.party_productivity_service import calculate_party_active_seats
    from app.services.staging_merge import merge_staging

    synced = int(merge_staging(db)["situacoes"])
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


def test_list_parties_resolves_official_party_logos(client, db, seed):
    from urllib.parse import urlparse

    merge_staging(db)

    parties = {p["sigla"]: p for p in client.get("/api/v1/parties").json()}
    assert parties["PT"]["logo_url"] is not None
    parsed_pt = urlparse(parties["PT"]["logo_url"])
    assert parsed_pt.hostname is not None
    assert parsed_pt.hostname == "wikimedia.org" or parsed_pt.hostname.endswith(".wikimedia.org")

    assert parties["PTB"]["logo_url"] is not None
    parsed_ptb = urlparse(parties["PTB"]["logo_url"])
    assert parsed_ptb.hostname is not None
    assert parsed_ptb.hostname == "wikimedia.org" or parsed_ptb.hostname.endswith(".wikimedia.org")
