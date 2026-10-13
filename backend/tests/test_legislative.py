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
