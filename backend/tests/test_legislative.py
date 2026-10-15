import uuid
from datetime import date, datetime, timezone

import pytest
from app.api.v1.legislative import _build_house_placar, _parse_enum, _parse_house, _placar_from_counts
from app.models import (
    CasaLegislativaEnum,
    ParliamentaryVote,
    Politician,
    Proposition,
    TipoProposicaoEnum,
    VotingSession,
    VotoOpcaoEnum,
)
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from .conftest import write_json

BASE = "/api/v1/legislative"


# ---------------------------------------------------------------------------
# Placar: uma única definição para todas as telas
# ---------------------------------------------------------------------------
def test_placar_definition_counts_obstruction_as_abstention_and_excludes_absent():
    placar = _placar_from_counts(
        {
            VotoOpcaoEnum.SIM: 10,
            VotoOpcaoEnum.NAO: 5,
            VotoOpcaoEnum.ABSTENCAO: 2,
            VotoOpcaoEnum.OBSTRUCAO: 3,
            VotoOpcaoEnum.AUSENTE: 7,
            VotoOpcaoEnum.ARTIGO_17: 1,
        }
    )
    assert placar["SIM"] == 10 and placar["NAO"] == 5
    assert placar["ABSTENCAO"] == 5 and placar["OBSTRUCAO"] == 3 and placar["AUSENTE"] == 7
    assert placar["TOTAL"] == placar["SIM"] + placar["NAO"] + placar["ABSTENCAO"] == 20


def test_placar_of_empty_session_is_all_zero():
    placar = _placar_from_counts({})
    assert placar["TOTAL"] == 0 and placar["ABSTENCAO"] == 0


def test_build_house_placar_without_sessions():
    placar, session, details = _build_house_placar([], {})
    assert placar["TOTAL"] == 0 and session is None and details == []


def test_parse_helpers():
    assert _parse_house("camara") == CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS
    assert _parse_house("SENADO_FEDERAL") == CasaLegislativaEnum.SENADO_FEDERAL
    assert _parse_house(None) is None and _parse_house("todos") is None
    with pytest.raises(HTTPException) as exc:
        _parse_house("assembleia")
    assert exc.value.status_code == 422
    assert _parse_enum(TipoProposicaoEnum, "pl", "Tipo") == TipoProposicaoEnum.PL
    with pytest.raises(HTTPException):
        _parse_enum(TipoProposicaoEnum, "XYZ", "Tipo")


# ---------------------------------------------------------------------------
# /propositions
# ---------------------------------------------------------------------------
def test_propositions_primary_session_is_the_one_with_most_quorum(client, seed):
    rows = {r["titulo"]: r for r in client.get(f"{BASE}/propositions").json()}
    pl = rows["PL 10/2023"]
    # A sessão de destaque é mais recente, mas a de mérito tem mais quórum e define o placar
    assert pl["sessao"]["titulo"] == "Votação de mérito"
    placar = pl["placar"]
    assert (placar["SIM"], placar["NAO"], placar["ABSTENCAO"], placar["TOTAL"]) == (1, 1, 1, 3)
    assert placar["TOTAL"] == placar["SIM"] + placar["NAO"] + placar["ABSTENCAO"]
    assert placar["AUSENTE"] == 1  # ausente e Art. 17 aparecem à parte, fora do TOTAL
    assert [s["titulo"] for s in pl["sessoes_camara_lista"]] == ["Votação de mérito", "Destaque"]
    assert pl["placar_senado"]["TOTAL"] == 0 and pl["sessao_senado"] is None


def test_propositions_without_votes_have_empty_placar_and_no_session(client, seed):
    rows = {r["titulo"]: r for r in client.get(f"{BASE}/propositions").json()}
    sem_voto = rows["PL 10/2024"]
    assert sem_voto["placar"]["TOTAL"] == 0 and sem_voto["sessao"] is None
    assert sem_voto["autor_nome"] == "Comissão / Parlamentares"
    assert rows["MPV 1/2023"]["autor_nome"] == "Poder Executivo"


def test_propositions_pagination_and_total_header(client, seed):
    first = client.get(f"{BASE}/propositions", params={"limit": 1, "offset": 0})
    second = client.get(f"{BASE}/propositions", params={"limit": 1, "offset": 1})
    assert first.headers["x-total-count"] == "3" == second.headers["x-total-count"]
    assert len(first.json()) == 1 and len(second.json()) == 1
    assert first.json()[0]["id"] != second.json()[0]["id"]
    beyond = client.get(f"{BASE}/propositions", params={"offset": 10})
    assert beyond.json() == [] and beyond.headers["x-total-count"] == "3"


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 1001}, {"offset": -1}])
def test_propositions_validates_pagination(client, seed, params):
    assert client.get(f"{BASE}/propositions", params=params).status_code == 422


def test_propositions_database_failure_is_503_not_stale_fallback_data(client, data_dir, session_factory, monkeypatch):
    """Antes um erro de banco devolvia dados de 2023 com status 200."""
    write_json(data_dir, "proposicoes_2023.json", [{"camara_id": 1, "titulo": "Dado antigo"}])
    from app import main as main_module
    from app.core.database import get_db

    class BrokenSession:
        def query(self, *args, **kwargs):
            raise OperationalError("SELECT", {}, Exception("connection refused"))

        def close(self):
            pass

    main_module.app.dependency_overrides[get_db] = lambda: BrokenSession()
    try:
        response = client.get(f"{BASE}/propositions")
    finally:
        main_module.app.dependency_overrides.pop(get_db, None)
    assert response.status_code == 503
    assert "Dado antigo" not in response.text


def test_propositions_empty_database_without_files_is_empty_list(client, data_dir):
    response = client.get(f"{BASE}/propositions")
    assert response.status_code == 200 and response.json() == []
    assert response.headers["x-total-count"] == "0"


def test_propositions_empty_database_uses_etl_files_in_development(client, data_dir):
    write_json(
        data_dir,
        "proposicoes_2023.json",
        [
            {
                "camara_id": 10,
                "tipo": "PL",
                "numero": 1,
                "ano": 2023,
                "titulo": "PL 1/2023",
                "ementa": "e",
                "iniciativa_executivo": True,
            },
            {"camara_id": None, "titulo": "sem id"},
        ],
    )
    write_json(
        data_dir,
        "votos_nominais_2023.json",
        [
            {"proposicao_camara_id": 10, "voto": "SIM"},
            {"proposicao_camara_id": 10, "voto": "OBSTRUCAO"},
            {"proposicao_camara_id": 10, "voto": "AUSENTE"},
        ],
    )
    response = client.get(f"{BASE}/propositions")
    rows = response.json()
    assert len(rows) == 1 and response.headers["x-total-count"] == "1"
    assert rows[0]["autor_nome"] == "Poder Executivo"
    assert rows[0]["placar"] == {"SIM": 1, "NAO": 0, "ABSTENCAO": 1, "TOTAL": 2}  # AUSENTE fora do total
    assert rows[0]["sessao"] is None  # nenhuma data/sessão inventada


# ---------------------------------------------------------------------------
# Resolução de proposição e votos nominais
# ---------------------------------------------------------------------------
def test_votes_resolve_by_uuid_or_external_id(client, seed):
    by_uuid = client.get(f"{BASE}/propositions/{seed.proposition.id}/votes")
    by_external = client.get(f"{BASE}/propositions/999/votes")
    assert by_uuid.status_code == by_external.status_code == 200
    assert by_uuid.json()["proposicao"]["id"] == by_external.json()["proposicao"]["id"] == str(seed.proposition.id)


@pytest.mark.parametrize("identifier", ["10", "99", "PL-10", "%", "1"])
def test_votes_never_resolve_by_proposition_number_or_partial_match(client, seed, identifier):
    """O número da matéria não é único (PL 10/2023 e PL 10/2024): jamais devolver o placar de outra matéria."""
    assert client.get(f"{BASE}/propositions/{identifier}/votes").status_code == 404
    assert client.get(f"{BASE}/propositions/{identifier}/nominal-votes").status_code == 404


def test_votes_unknown_uuid_is_404(client, seed):
    assert client.get(f"{BASE}/propositions/{seed.unknown_uuid}/votes").status_code == 404


def test_votes_listing_uses_real_mandate_context_and_lists_all_choices(client, seed):
    body = client.get(f"{BASE}/propositions/{seed.proposition.id}/votes").json()
    assert body["sessao_ativa"]["titulo"] == "Votação de mérito"
    assert body["total"] == 5 and body["truncado"] is False
    by_name = {}
    for v in body["votos"]:
        by_name.setdefault(v["nome_eleitoral"], []).append(v)
    assert by_name["Fulano"][0]["uf"] == "SP" and by_name["Beltrano"][0]["uf"] == "RJ"
    assert {v["decisao"] for v in body["votos"]} == {"SIM", "NAO", "OBSTRUCAO", "AUSENTE", "ARTIGO_17"}
    assert [s["titulo"] for s in body["sessoes_disponiveis"]] == ["Destaque", "Votação de mérito"]


def test_votes_politician_without_mandate_has_null_uf_not_a_default_state(client, db, seed):
    sem_mandato = Politician(civil_name="Sem Mandato", electoral_name="Sem Mandato", camara_id=888)
    db.add(sem_mandato)
    db.flush()
    db.add(
        ParliamentaryVote(voting_session_id=seed.merito.id, politician_id=sem_mandato.id, vote_choice=VotoOpcaoEnum.SIM)
    )
    db.commit()
    votes = client.get(f"{BASE}/propositions/{seed.proposition.id}/votes", params={"search": "sem mandato"}).json()[
        "votos"
    ]
    assert len(votes) == 1
    # Sem mandato cadastrado a UF fica null (antes era "DF" inventado); o cargo é inferido da casa onde votou
    assert votes[0]["uf"] is None
    assert votes[0]["cargo"] == "DEPUTADO_FEDERAL"


def test_votes_filters(client, seed):
    url = f"{BASE}/propositions/{seed.proposition.id}/votes"
    assert [v["decisao"] for v in client.get(url, params={"vote_choice": "nao"}).json()["votos"]] == ["NAO"]
    assert [v["nome_eleitoral"] for v in client.get(url, params={"search": "fulan"}).json()["votos"]] == ["Fulano"]
    only_destaque = client.get(url, params={"session_id": str(seed.destaque.id)}).json()
    assert only_destaque["total"] == 1 and only_destaque["sessao_ativa"]["titulo"] == "Destaque"
    assert client.get(url, params={"search": "%"}).json()["votos"] == []
    senado = client.get(url, params={"house": "SENADO"}).json()
    assert senado["votos"] == [] and senado["sessoes_disponiveis"] == []


@pytest.mark.parametrize("params", [{"house": "assembleia"}, {"vote_choice": "TALVEZ"}])
def test_votes_invalid_filters_are_422(client, seed, params):
    assert client.get(f"{BASE}/propositions/{seed.proposition.id}/votes", params=params).status_code == 422


def test_nominal_votes_split_agrees_with_placar_definition(client, seed):
    body = client.get(f"{BASE}/propositions/{seed.proposition.id}/nominal-votes").json()
    assert body["sessao"]["titulo"] == "Votação de mérito"
    assert [v["nome_eleitoral"] for v in body["votos_sim"]] == ["Fulano"]
    assert [v["nome_eleitoral"] for v in body["votos_nao"]] == ["Lula da Fonte"]
    assert [v["nome_eleitoral"] for v in body["votos_obstrucao"]] == ["Beltrano"]
    placar = body["placar"]
    assert (placar["sim"], placar["nao"], placar["obstrucao"]) == (1, 1, 1)
    assert placar["total"] == placar["sim"] + placar["nao"] + placar["abstencao"] + placar["obstrucao"]


def test_nominal_votes_of_proposition_without_sessions_is_empty(client, seed):
    body = client.get(f"{BASE}/propositions/{seed.outra.id}/nominal-votes").json()
    assert body["sessao"] is None and body["votos_sim"] == [] and body["placar"]["total"] == 0


# ---------------------------------------------------------------------------
# Explorer
# ---------------------------------------------------------------------------
def test_explorer_voted_filter_does_not_duplicate_propositions_with_many_sessions(client, seed):
    body = client.get(f"{BASE}/explorer", params={"apenas_votadas": "true"}).json()
    # PL 10/2023 tem DUAS sessões: com JOIN apareceria duas vezes e o total divergiria da lista
    assert body["total"] == 1 and len(body["items"]) == 1 and body["total_pages"] == 1
    assert body["items"][0]["titulo"] == "PL 10/2023" and body["items"][0]["tem_votacao"] is True
    placar = body["items"][0]["placar"]
    assert placar["sim"] + placar["nao"] + placar["abstencao"] == placar["total"] == 3


def test_explorer_pagination_covers_every_item_exactly_once(client, db, seed):
    for n in range(1, 6):
        db.add(
            Proposition(
                proposition_type=TipoProposicaoEnum.PL,
                number=100 + n,
                year=2025,
                title=f"PL {100 + n}/2025",
                summary="x",
                presentation_date=date(2025, 1, n),
                external_camara_id=5000 + n,
            )
        )
    db.commit()
    seen = []
    for page in (1, 2, 3):
        body = client.get(f"{BASE}/explorer", params={"limit": 3, "page": page}).json()
        seen += [i["id"] for i in body["items"]]
    assert body["total"] == 8 and body["total_pages"] == 3
    assert len(seen) == len(set(seen)) == 8
    assert client.get(f"{BASE}/explorer", params={"limit": 3, "page": 9}).json()["items"] == []


def test_explorer_filters(client, seed):
    assert [i["titulo"] for i in client.get(f"{BASE}/explorer", params={"tipo": "mpv"}).json()["items"]] == [
        "MPV 1/2023"
    ]
    assert [i["titulo"] for i in client.get(f"{BASE}/explorer", params={"setor": "saúde"}).json()["items"]] == [
        "PL 10/2024"
    ]
    assert client.get(f"{BASE}/explorer", params={"setor": "todos", "tipo": "todos"}).json()["total"] == 3
    assert client.get(f"{BASE}/explorer", params={"search": "fulano"}).json()["total"] == 1
    assert client.get(f"{BASE}/explorer", params={"status": "ARQUIVADA"}).json()["total"] == 0
    assert set(client.get(f"{BASE}/explorer").json()["setores_disponiveis"]) == {"Economia", "Saúde"}


@pytest.mark.parametrize("term", ["%", "_", "' OR '1'='1", "'; DROP TABLE proposicoes; --"])
def test_explorer_search_is_literal_and_injection_safe(client, db, seed, term):
    response = client.get(f"{BASE}/explorer", params={"search": term})
    assert response.status_code == 200 and response.json()["total"] == 0
    assert db.execute(text("SELECT COUNT(*) FROM proposicoes")).scalar() == 3


@pytest.mark.parametrize("params", [{"tipo": "XYZ"}, {"status": "NADA"}, {"page": 0}, {"limit": 101}])
def test_explorer_rejects_invalid_filters(client, seed, params):
    assert client.get(f"{BASE}/explorer", params=params).status_code == 422


def test_explorer_author_party_comes_from_real_mandate(client, seed):
    item = next(i for i in client.get(f"{BASE}/explorer").json()["items"] if i["titulo"] == "PL 10/2023")
    assert (item["autor_partido"], item["autor_uf"]) == ("PT", "SP")
    executive = next(i for i in client.get(f"{BASE}/explorer").json()["items"] if i["titulo"] == "MPV 1/2023")
    assert executive["autor_partido"] == "GOV" and executive["autor_nome"] == "Poder Executivo"


def test_explorer_party_filter(client, seed):
    # Filter by party of author (PT)
    resp_pt = client.get(f"{BASE}/explorer", params={"partido": "PT"}).json()
    assert resp_pt["total"] == 1
    assert resp_pt["items"][0]["titulo"] == "PL 10/2023"
    assert resp_pt["items"][0]["autor_partido"] == "PT"

    # Filter by GOV (Poder Executivo)
    resp_gov = client.get(f"{BASE}/explorer", params={"partido": "GOV"}).json()
    assert resp_gov["total"] == 1
    assert resp_gov["items"][0]["titulo"] == "MPV 1/2023"
    assert resp_gov["items"][0]["autor_partido"] == "GOV"

    # Filter by party with no propositions
    resp_empty = client.get(f"{BASE}/explorer", params={"partido": "PL"}).json()
    assert resp_empty["total"] == 0

    # Todos returns all
    resp_all = client.get(f"{BASE}/explorer", params={"partido": "Todos"}).json()
    assert resp_all["total"] == 3


# ---------------------------------------------------------------------------
# Calendário
# ---------------------------------------------------------------------------
def test_calendar_defaults_to_latest_year_with_votes(client, seed):
    body = client.get(f"{BASE}/calendar").json()
    assert body["ano_selecionado"] == 2023 and body["anos_disponiveis"] == [2023]
    assert body["estatisticas_anuais"]["dias_com_votacao"] == 2
    assert body["estatisticas_anuais"]["total_sessoes_ano"] == 2
    assert body["estatisticas_anuais"]["total_dias_ano"] == 365
    assert [d["data"] for d in body["dias"]] == ["2023-05-03", "2023-05-02"]  # mais recente primeiro


def test_calendar_placar_is_consistent_with_the_other_screens(client, seed):
    day = next(
        d for d in client.get(f"{BASE}/calendar", params={"year": 2023}).json()["dias"] if d["data"] == "2023-05-02"
    )
    placar = day["sessoes"][0]["placar"]
    assert placar == {"sim": 1, "nao": 1, "abstencao": 1, "total": 3}  # AUSENTE não conta como abstenção
    assert day["camara_count"] == 1 and day["senado_count"] == 0 and day["total_votacoes"] == 1


def test_calendar_counts_each_house_separately(client, db, seed):
    db.add(
        VotingSession(
            proposition_id=seed.proposition.id,
            legislative_house=CasaLegislativaEnum.SENADO_FEDERAL,
            session_datetime=datetime(2023, 5, 2, 18, 0, tzinfo=timezone.utc),
            agenda_title="Senado",
            is_approved=True,
            external_id="sess-senado",
        )
    )
    db.commit()
    day = next(d for d in client.get(f"{BASE}/calendar").json()["dias"] if d["data"] == "2023-05-02")
    assert (day["camara_count"], day["senado_count"], day["total_votacoes"]) == (1, 1, 2)


def test_calendar_year_without_votes_is_404_and_invalid_year_is_422(client, seed):
    assert client.get(f"{BASE}/calendar", params={"year": 2001}).status_code == 404
    assert client.get(f"{BASE}/calendar", params={"year": 1800}).status_code == 422


def test_calendar_empty_database(client):
    body = client.get(f"{BASE}/calendar", params={"year": 2024}).json()
    assert body["dias"] == [] and body["anos_disponiveis"] == []
    assert body["estatisticas_anuais"]["total_dias_ano"] == 366  # 2024 é bissexto
    assert body["estatisticas_anuais"]["dias_com_votacao"] == 0


# ---------------------------------------------------------------------------
# Ranking de autores
# ---------------------------------------------------------------------------
def test_ranking_authors_party_filter_is_exact(client, seed):
    pt = client.get(f"{BASE}/ranking/authors", params={"partido": "PT"}).json()
    assert [r["nome_eleitoral"] for r in pt] == ["Fulano"] and pt[0]["posicao"] == 1
    assert client.get(f"{BASE}/ranking/authors", params={"partido": "PTB"}).json() == []
    assert client.get(f"{BASE}/ranking/authors", params={"partido": "P"}).json() == []


def test_ranking_authors_criteria_and_validation(client, seed):
    assert client.get(f"{BASE}/ranking/authors", params={"criterio": "volume"}).status_code == 200
    assert client.get(f"{BASE}/ranking/authors", params={"criterio": "sorte"}).status_code == 422
    assert client.get(f"{BASE}/ranking/authors", params={"limit": 0}).status_code == 422
    assert (
        client.get(f"{BASE}/ranking/authors", params={"setor": "economia"}).json()[0]["principal_setor"] == "Economia"
    )


def test_senado_secret_vote_returns_totals_without_individual_voters(client, seed, db):
    prop = seed.proposition
    secret_sess = VotingSession(
        id=uuid.uuid4(),
        proposition_id=prop.id,
        legislative_house=CasaLegislativaEnum.SENADO_FEDERAL,
        session_datetime=datetime(2023, 7, 10, 14, 0, tzinfo=timezone.utc),
        agenda_title="Votação secreta de autoridade",
        is_secret_vote=True,
        is_approved=True,
        votes_yes_count=45,
        votes_no_count=10,
        votes_abstain_count=2,
        votes_obstruction_count=0,
        external_id="sess-secreta-123",
    )
    db.add(secret_sess)
    db.commit()

    resp = client.get(f"{BASE}/propositions/{prop.id}/votes", params={"session_id": str(secret_sess.id)})
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_votacao_secreta"] is True
    assert data["votos"] == []
    assert data["placar"]["SIM"] == 45
    assert data["placar"]["NAO"] == 10
    assert data["placar"]["ABSTENCAO"] == 2
    assert "Votação secreta" in data["aviso"]


def test_ranking_authors_weighted_indicators_and_new_criteria(client, seed):
    # Test valid criteria 'lideranca' and 'coautoria'
    res_lider = client.get(f"{BASE}/ranking/authors", params={"criterio": "lideranca"})
    assert res_lider.status_code == 200
    res_coaut = client.get(f"{BASE}/ranking/authors", params={"criterio": "coautoria"})
    assert res_coaut.status_code == 200

    # Test returned fields in ranking items
    items = res_lider.json()
    if items:
        first = items[0]
        assert "autoria_principal_count" in first
        assert "coautoria_count" in first
        assert "score_ponderado" in first
        assert "taxa_eficiencia_pct" in first
        assert first["autoria_principal_count"] >= 0
        assert first["coautoria_count"] >= 0


def test_calculate_proposition_score_ialp_formula(db):
    from app.models.legislative import StatusTramitacaoEnum, TipoAutoriaEnum, TipoProposicaoEnum
    from app.services.ialp_pesos import carregar_pesos_ialp
    from app.services.legislative_scoring import calculate_proposition_score

    pesos = carregar_pesos_ialp(db)

    # 1. Autor Principal (1.0) em PEC (3.0) Sancionada (3.0): 3.0 * 1.0 * 3.0 = 9.0
    score_pec_sanc = calculate_proposition_score(
        TipoProposicaoEnum.PEC,
        TipoAutoriaEnum.AUTOR_PRINCIPAL,
        StatusTramitacaoEnum.APROVADA_E_SANCIONADA,
        pesos,
    )
    assert score_pec_sanc == 9.0

    # 2. Assinatura de apoio a PEC (coautor, 0.05) (3.0) Tramitando (1.0): 3.0 * 0.05 * 1.0 = 0.15
    score_pec_coaut = calculate_proposition_score(
        TipoProposicaoEnum.PEC,
        TipoAutoriaEnum.COAUTOR,
        StatusTramitacaoEnum.EM_TRAMITACAO,
        pesos,
    )
    assert score_pec_coaut == 0.15

    # Coautor em PL mantém o peso geral de coautoria (0.2)
    assert pesos.peso_autoria(TipoAutoriaEnum.COAUTOR, TipoProposicaoEnum.PL) == 0.2

    # 3. Relator (0.8) em PLP (2.5) Aprovado em Plenário (2.0): 2.5 * 0.8 * 2.0 = 4.0
    score_plp_relator = calculate_proposition_score(
        TipoProposicaoEnum.PLP,
        TipoAutoriaEnum.RELATOR,
        StatusTramitacaoEnum.APROVADO_PLENARIO,
        pesos,
    )
    assert score_plp_relator == 4.0

    # 4. Autor Institucional (0.0): score zero sem crédito individual
    score_inst = calculate_proposition_score(
        TipoProposicaoEnum.PL,
        TipoAutoriaEnum.INSTITUCIONAL,
        StatusTramitacaoEnum.APROVADA_E_SANCIONADA,
        pesos,
    )
    assert score_inst == 0.0

    # 5. Requerimento Burocrático REQ (0.1) Autor Principal (1.0): 0.1 * 1.0 * 1.0 = 0.1
    score_req = calculate_proposition_score(
        TipoProposicaoEnum.REQ,
        TipoAutoriaEnum.AUTOR_PRINCIPAL,
        StatusTramitacaoEnum.EM_TRAMITACAO,
        pesos,
    )
    assert score_req == 0.1


def test_coauthorship_network_endpoint_and_louvain_metrics(client, seed, db):
    from app.models.legislative import PropositionAuthor, TipoAutoriaEnum

    # Seed proposition authors connecting fulano and lula_fonte
    pa1 = PropositionAuthor(
        proposition_id=seed.proposition.id,
        politician_id=seed.fulano.id,
        author_name="Fulano",
        authorship_type=TipoAutoriaEnum.AUTOR_PRINCIPAL,
        order=1,
    )
    pa2 = PropositionAuthor(
        proposition_id=seed.proposition.id,
        politician_id=seed.lula_fonte.id,
        author_name="Lula da Fonte",
        authorship_type=TipoAutoriaEnum.COAUTOR,
        order=2,
    )
    db.add_all([pa1, pa2])
    db.commit()

    resp = client.get(f"{BASE}/network", params={"limit_nodes": 20, "min_weight": 1})
    assert resp.status_code == 200
    data = resp.json()

    assert "nodes" in data
    assert "edges" in data
    assert "communities" in data
    assert "stats" in data

    stats = data["stats"]
    assert "total_nodes" in stats
    assert "total_edges" in stats
    assert "total_communities" in stats
    assert "density" in stats
    assert "top_articulators" in stats

    if data["nodes"]:
        first_node = data["nodes"][0]
        assert "id" in first_node
        assert "name" in first_node
        assert "party" in first_node
        assert "uf" in first_node
        assert "house" in first_node
        assert "community" in first_node
        assert "betweenness_centrality" in first_node
        assert "degree" in first_node
        assert first_node["betweenness_centrality"] >= 0.0

    if data["communities"]:
        first_comm = data["communities"][0]
        assert "community_id" in first_comm
        assert "color" in first_comm
        assert "label" in first_comm
        assert "total_parlamentares" in first_comm

    # Test dynamic filters
    resp_pec = client.get(f"{BASE}/network", params={"tipo_proposta": "PEC", "limit_nodes": 10})
    assert resp_pec.status_code == 200
    assert resp_pec.json()["stats"]["tipo_filtro"] == "PEC"


def test_politician_productivity_ialp_endpoint(client, seed):
    # Encontrar um parlamentar válido na base
    pol_id = str(seed.fulano.id)
    resp = client.get(f"{BASE}/politicians/{pol_id}/productivity")
    assert resp.status_code == 200
    data = resp.json()

    assert data["politician_id"] == pol_id
    assert "score_ialp_total" in data
    assert "total_proposicoes" in data
    assert "taxa_eficacia_pct" in data
    assert "desvio_foco" in data
    assert "distribuicao_autoria" in data
    assert "top_coautores" in data

    desvio = data["desvio_foco"]
    assert "estruturais" in desvio
    assert "burocraticas" in desvio
    assert "proporcao_estrutural_pct" in desvio
    assert "diagnostico" in desvio

    autoria = data["distribuicao_autoria"]
    assert "autor_principal" in autoria
    assert "relator" in autoria
    assert "coautor" in autoria

    # Test 404 for non-existent UUID
    import uuid

    random_uuid = str(uuid.uuid4())
    resp_404 = client.get(f"{BASE}/politicians/{random_uuid}/productivity")
    assert resp_404.status_code == 404


def test_deliberacoes_history_and_module_3_specification(client, seed, db):
    """
    Testes de conformidade com o MÓDULO 3: HISTÓRICO DE DELIBERAÇÕES E TRANSPARÊNCIA DE VOTOS:
    6.1 Classificação das deliberações em COMISSAO, SIMBOLICA e NOMINAL.
    6.2 Modelagem relacional votacoes_proposicao, votos_nominais, orientacoes_partidarias.
    6.3 Regras de exibição para cada tipo de deliberação.
    """
    import uuid
    from datetime import datetime, timezone

    from app.models.legislative import (
        OrientacaoPartidaria,
        VotacaoProposicao,
        VotoNominal,
    )

    prop = seed.proposition
    prop_id = str(prop.id)

    # 1. Criar uma deliberação em COMISSAO
    vot_comissao = VotacaoProposicao(
        id=uuid.uuid4(),
        proposicao_id=prop.id,
        data_hora=datetime(2023, 4, 15, 10, 0, tzinfo=timezone.utc),
        local_deliberacao="CCJC - Comissão de Constituição e Justiça",
        tipo_deliberacao="COMISSAO",
        resumo_decisao="Aprovado parecer do relator pela admissibilidade",
        nome_comissao="Comissão de Constituição e Justiça e de Cidadania",
        link_ata_reuniao="https://www.camara.leg.br/atas/ccjc",
        relator_nome="Dep. Fulano de Tal",
        parecer_relator_numero="Parecer nº 05/2023-CCJC",
        parecer_relator_texto="Parecer favorável pela constitucionalidade.",
        link_parecer_relator="https://www.camara.leg.br/pareceres/123",
        aprovada=True,
    )
    db.add(vot_comissao)

    # 2. Criar uma deliberação SIMBOLICA
    vot_simbolica = VotacaoProposicao(
        id=uuid.uuid4(),
        proposicao_id=prop.id,
        data_hora=datetime(2023, 5, 20, 16, 0, tzinfo=timezone.utc),
        local_deliberacao="Plenário da Câmara dos Deputados",
        tipo_deliberacao="SIMBOLICA",
        resumo_decisao="Aprovado requerimento de urgência em votação simbólica",
        aprovada=True,
    )
    db.add(vot_simbolica)
    db.flush()

    op1 = OrientacaoPartidaria(votacao_id=vot_simbolica.id, partido_bancada="PT", orientacao="SIM")
    op2 = OrientacaoPartidaria(votacao_id=vot_simbolica.id, partido_bancada="PL", orientacao="LIBERADO")
    db.add_all([op1, op2])

    # 3. Criar uma deliberação NOMINAL
    vot_nominal = VotacaoProposicao(
        id=uuid.uuid4(),
        proposicao_id=prop.id,
        data_hora=datetime(2023, 6, 10, 19, 0, tzinfo=timezone.utc),
        local_deliberacao="Plenário da Câmara dos Deputados",
        tipo_deliberacao="NOMINAL",
        resumo_decisao="Aprovada redação final com registro nominal",
        total_sim=1,
        total_nao=1,
        total_abstencao=0,
        total_obstrucao=0,
        aprovada=True,
    )
    db.add(vot_nominal)
    db.flush()

    vn1 = VotoNominal(votacao_id=vot_nominal.id, parlamentar_id=seed.fulano.id, voto="SIM")
    vn2 = VotoNominal(votacao_id=vot_nominal.id, parlamentar_id=seed.beltrano.id, voto="NAO")
    op_gov = OrientacaoPartidaria(votacao_id=vot_nominal.id, partido_bancada="Governo", orientacao="SIM")
    db.add_all([vn1, vn2, op_gov])
    db.commit()

    # GET /propositions/{prop_id}/deliberacoes
    resp = client.get(f"{BASE}/propositions/{prop_id}/deliberacoes")
    assert resp.status_code == 200
    data = resp.json()
    assert data["proposicao"]["id"] == prop_id
    assert len(data["deliberacoes"]) >= 3

    tipos = [d["tipo_deliberacao"] for d in data["deliberacoes"]]
    assert "COMISSAO" in tipos
    assert "SIMBOLICA" in tipos
    assert "NOMINAL" in tipos

    # GET /deliberacoes/{vot_comissao.id} -> COMISSAO rule 6.3
    resp_com = client.get(f"{BASE}/deliberacoes/{str(vot_comissao.id)}")
    assert resp_com.status_code == 200
    data_com = resp_com.json()
    assert data_com["tipo_deliberacao"] == "COMISSAO"
    assert data_com["nome_comissao"] == "Comissão de Constituição e Justiça e de Cidadania"
    assert data_com["link_ata_reuniao"] == "https://www.camara.leg.br/atas/ccjc"
    assert data_com["relator_nome"] == "Dep. Fulano de Tal"
    assert data_com["parecer_relator_numero"] == "Parecer nº 05/2023-CCJC"
    assert data_com["parecer_relator_texto"] == "Parecer favorável pela constitucionalidade."
    assert data_com["link_parecer_relator"] == "https://www.camara.leg.br/pareceres/123"

    # GET /deliberacoes/{vot_simbolica.id} -> SIMBOLICA rule 6.3
    resp_simb = client.get(f"{BASE}/deliberacoes/{str(vot_simbolica.id)}")
    assert resp_simb.status_code == 200
    data_simb = resp_simb.json()
    assert data_simb["tipo_deliberacao"] == "SIMBOLICA"
    assert "aviso_educativo" in data_simb
    assert len(data_simb["orientacoes_partidarias"]) >= 2
    # Individual votes should not be present in SIMBOLICA
    assert "votos_sim" not in data_simb

    # GET /deliberacoes/{vot_nominal.id} -> NOMINAL rule 6.3
    resp_nom = client.get(f"{BASE}/deliberacoes/{str(vot_nominal.id)}")
    assert resp_nom.status_code == 200
    data_nom = resp_nom.json()
    assert data_nom["tipo_deliberacao"] == "NOMINAL"
    assert data_nom["placar"]["sim"] == 1
    assert data_nom["placar"]["nao"] == 1
    assert len(data_nom["votos_sim"]) == 1
    assert len(data_nom["votos_nao"]) == 1
    assert data_nom["votos_sim"][0]["politico_id"] == str(seed.fulano.id)
    assert data_nom["votos_nao"][0]["politico_id"] == str(seed.beltrano.id)

    # 404 & 422 validations
    resp_404 = client.get(f"{BASE}/deliberacoes/{str(uuid.uuid4())}")
    assert resp_404.status_code == 404
    resp_422 = client.get(f"{BASE}/deliberacoes/invalid-uuid")
    assert resp_422.status_code == 422
