from datetime import date

import pytest
from app.api.v1.politicians import _normalize_name
from app.core.query_utils import escape_like as _escape_like
from app.models import (
    AttendanceRecord,
    CasaLegislativaEnum,
    Politician,
    ProcessoJudicial,
    TipoPresencaEnum,
)
from app.services import financas_service
from sqlalchemy import text

from .conftest import criar_mandato_presidencial, fonte_id, inserir_fin, pessoa_do

BASE = "/api/v1/politicians"


# ---------------------------------------------------------------------------
# Helpers puros
# ---------------------------------------------------------------------------
def test_normalize_name():
    assert _normalize_name("Joãoção DA SÍLVA") == "JOAOCAO DA SILVA"
    assert _normalize_name(None) == ""
    assert _normalize_name("  ") == ""


def test_escape_like_neutralizes_wildcards():
    assert _escape_like("100%_ok\\") == "100\\%\\_ok\\\\"


# ---------------------------------------------------------------------------
# /presidents
# ---------------------------------------------------------------------------
def test_presidents_list_and_detail(client, db):
    mandato = criar_mandato_presidencial(db, "Lula", date(2003, 1, 1), date(2007, 1, 1), "lula-2003", "Lula 1")
    db.execute(
        text(
            "UPDATE core.mandato_presidencial SET vice_texto = 'José Alencar', status = 'CONCLUIDO' WHERE mandato_id = :m"
        ),
        {"m": mandato},
    )
    db.execute(
        text("INSERT INTO core.marco_governo (mandato_id, ordem, texto) VALUES (:m, 1, 'Marco')"), {"m": mandato}
    )
    db.commit()
    lista = client.get(f"{BASE}/presidents").json()
    assert [p["id_referencia"] for p in lista] == ["lula-2003"]
    detalhe = client.get(f"{BASE}/presidents/lula-2003").json()
    assert detalhe["nome_eleitoral"] == "Lula (Lula 1)" and detalhe["vice_presidente"] == "José Alencar"
    assert detalhe["marcos_economicos"] == ["Marco"] and detalhe["cpf"] is None
    assert detalhe["foto_url"] is None and detalhe["genero"] is None and detalhe["data_fim"] == "2007-01-01"
    assert client.get(f"{BASE}/presidents/{detalhe['db_id']}").json()["id_referencia"] == "lula-2003"
    assert client.get(f"{BASE}/presidents/ninguem").status_code == 404
    # a busca ignora maiúsculas; slug fora do formato (barra codificada, 61 caracteres) é rejeitado pelo serviço
    assert client.get(f"{BASE}/presidents/LULA-2003").status_code == 200
    for invalido in ("%2e%2e%2fetc", "a" * 61):
        assert client.get(f"{BASE}/presidents/{invalido}").status_code == 404


def test_presidents_without_dataset_is_404(client):
    assert client.get(f"{BASE}/presidents").status_code == 404
    assert client.get(f"{BASE}/presidents/lula-2003").status_code == 404


# ---------------------------------------------------------------------------
# Busca
# ---------------------------------------------------------------------------
def names(response):
    return [p["nome_eleitoral"] for p in response.json()["politicos"]]


def test_search_lists_everyone_with_pagination(client, seed):
    body = client.get(BASE, params={"limit": 2, "offset": 0}).json()
    assert body["total"] == 6 and len(body["politicos"]) == 2 and body["limit"] == 2
    all_names = names(client.get(BASE, params={"limit": 100}))
    assert all_names == sorted(all_names)  # ordenação determinística
    second_page = names(client.get(BASE, params={"limit": 2, "offset": 2}))
    assert second_page == all_names[2:4]


def test_search_by_electoral_or_civil_name_case_insensitive(client, seed):
    assert names(client.get(BASE, params={"search": "fulan"})) == ["Fulano"]
    assert names(client.get(BASE, params={"search": "DE TAL"})) == ["Fulano"]


@pytest.mark.parametrize("term", ["%", "_", "\\", "' OR 1=1 --", "'; DROP TABLE politicos; --"])
def test_search_treats_special_characters_literally(client, db, seed, term):
    response = client.get(BASE, params={"search": term})
    assert response.status_code == 200
    assert response.json()["total"] == 0  # '%' e '_' não são curingas
    assert db.execute(text("SELECT COUNT(*) FROM politicos")).scalar() == 6  # a tabela continua intacta


def test_search_party_filter_is_exact_and_current_only(client, seed):
    pt = names(client.get(BASE, params={"party": "pt"}))
    assert sorted(pt) == ["Fulano", "Lula", "Lula da Fonte"]  # PTB (e o mandato antigo do Fulano em PTB) não entram
    ptb = names(client.get(BASE, params={"partido": "PTB"}))
    assert sorted(ptb) == ["Beltrano", "Maria Silva", "Maria Silva"]


def test_search_filters_by_office_and_uf(client, seed):
    assert names(client.get(BASE, params={"office": "presidente"})) == ["Lula"]
    assert sorted(names(client.get(BASE, params={"uf": "sp"}))) == ["Fulano", "Lula da Fonte"]
    assert names(client.get(BASE, params={"uf": "RJ", "office": "DEPUTADO_FEDERAL"})) == ["Beltrano"]


def test_search_all_keywords_disable_filters(client, seed):
    assert client.get(BASE, params={"office": "todos", "uf": "ALL", "party": "todas"}).json()["total"] == 6


@pytest.mark.parametrize("params", [{"office": "REI"}, {"uf": "SPP"}, {"uf": "1A"}])
def test_search_invalid_filters_are_422_not_silently_ignored(client, seed, params):
    assert client.get(BASE, params=params).status_code == 422


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 801}, {"offset": -1}, {"search": "x" * 101}])
def test_search_validates_pagination_bounds(client, seed, params):
    assert client.get(BASE, params=params).status_code == 422


def test_search_row_uses_current_party_and_real_photo_fallbacks(client, seed):
    rows = {p["nome_eleitoral"]: p for p in client.get(BASE, params={"limit": 100}).json()["politicos"]}
    assert rows["Fulano"]["partido_sigla"] == "PT" and rows["Fulano"]["uf"] == "SP"
    assert rows["Fulano"]["foto_url"].endswith("/111.jpg")
    assert rows["Lula"]["foto_url"] == "/presidents/lula.jpg"  # foto local só para quem exerceu a Presidência
    assert rows["Lula da Fonte"]["foto_url"].endswith("/222.jpg")  # homônimo parcial NÃO herda a foto do presidente


def test_senator_photo_url_is_canonical_https(client, db):
    from app.models.politician import Politician

    senador = Politician(
        civil_name="Izalci Lucas",
        electoral_name="Izalci Lucas",
        senado_id=4770,
        photo_url="http://www.senado.leg.br/senadores/img/fotos-oficiais/senador4770.jpg",
    )
    db.add(senador)
    db.commit()
    res = client.get(f"{BASE}/{senador.id}").json()
    assert res["perfil"]["foto_url"] == "https://legis.senado.leg.br/senadores/fotos-oficiais/4770"


# ---------------------------------------------------------------------------
# Resolução de político
# ---------------------------------------------------------------------------
def test_resolve_by_uuid_camara_id_and_exact_slug(client, seed):
    by_uuid = client.get(f"{BASE}/{seed.fulano.id}").json()["perfil"]["nome_eleitoral"]
    by_camara = client.get(f"{BASE}/111").json()["perfil"]["nome_eleitoral"]
    by_slug = client.get(f"{BASE}/fulano").json()["perfil"]["nome_eleitoral"]
    by_civil_slug = client.get(f"{BASE}/fulano-de-tal").json()["perfil"]["nome_eleitoral"]
    assert by_uuid == by_camara == by_slug == by_civil_slug == "Fulano"


def test_resolve_ambiguous_name_is_409_instead_of_picking_one(client, seed):
    response = client.get(f"{BASE}/maria-silva")
    assert response.status_code == 409
    assert "ambíguo" in response.json()["detail"]
    assert client.get(f"{BASE}/444").json()["perfil"]["uf"] == "MG"  # o ID desambigua


@pytest.mark.parametrize("identifier", ["ful", "lul", "%", "_ulano", "fulano%", "99999"])
def test_resolve_never_matches_by_partial_name_or_wildcard(client, seed, identifier):
    assert client.get(f"{BASE}/{identifier}").status_code == 404


def test_resolve_unknown_uuid_is_404(client, seed):
    assert client.get(f"{BASE}/{seed.unknown_uuid}").status_code == 404


@pytest.mark.parametrize("suffix", ["ceap", "emendas", "certidoes", "doacoes"])
def test_sub_resources_404_for_unknown_politician(client, seed, suffix):
    assert client.get(f"{BASE}/{seed.unknown_uuid}/{suffix}").status_code == 404


# ---------------------------------------------------------------------------
# Dossiê
# ---------------------------------------------------------------------------
def test_dossier_does_not_expose_politician_cpf(client, seed):
    body = client.get(f"{BASE}/{seed.fulano.id}").json()
    assert "cpf" not in body["perfil"]
    assert "12345678901" not in client.get(f"{BASE}/{seed.fulano.id}").text


def test_dossier_exposes_only_cnpj_and_masked_cpf(client, seed, financas):
    """Fornecedor só aparece com CNPJ formatado; o documento do doador chega mascarado (a proteção contra CPF fica no
    ETL e no CHECK da tabela, testados em test_fin_schema e test_financas_loader)."""
    body = client.get(f"{BASE}/{seed.fulano.id}").json()
    assert body["custos_ceap"]["maiores_fornecedores"][0]["cnpj_cpf"] == "12.345.678/0001-99"
    donor = body["financiamento_campanha"]["top_doadores"][0]
    assert donor["cpf_cnpj_doador"] == "***.654.321-**"
    assert body["indices_inteligencia"]["concentracao_ceap"]["cnpj_maior_fornecedor"] == "12.345.678/0001-99"
    ceap = client.get(
        f"{BASE}/{seed.fulano.id}/ceap"
    ).json()  # só totais por ano e tipo: nenhum documento de fornecedor
    assert (
        ceap["despesas"] == [{"ano": 2024, "tipo": "Combustível", "valor": 150.0}] and "cnpj" not in str(ceap).lower()
    )
    assert "***.654.321-**" in client.get(f"{BASE}/{seed.fulano.id}/doacoes").text


def test_dossier_missing_data_is_null_never_invented(client, seed):
    body = client.get(f"{BASE}/{seed.fulano.id}").json()
    perfil = body["perfil"]
    assert perfil["email"] is None and perfil["gabinete_sala"] is None and perfil["gabinete_telefone"] is None
    assert perfil["naturalidade"] is None  # antes caía no texto genérico "Brasil"
    summary = body["remuneracao"]["resumo"]
    assert summary["salario_bruto_atual"] is None and summary["media_ceap_mensal"] is None
    assert summary["ano_referencia"] is None
    assert body["assiduidade"]["taxa_presenca_pct"] is None  # sem registros: não assume 100%
    ficha = body["ficha_limpa"]
    assert ficha["dados_certidoes_disponiveis"] is False and ficha["certidoes"] == []
    assert ficha["status_geral"] is None  # sem certidão registrada não se afirma "Nada Consta"
    assert body["evolucao_patrimonial"]["resumo"]["possui_dados"] is False


def test_dossier_basometro_and_roi_are_unavailable_instead_of_made_up(client, seed):
    body = client.get(f"{BASE}/{seed.fulano.id}").json()
    baso = body["basometro"]
    assert baso["dados_suficientes"] is False
    assert baso["taxa_governismo_pct"] is None and baso["votos_alinhados"] is None and baso["classificacao"] is None
    assert "orientação da bancada do Governo" in baso["metodologia"]
    roi = body["indices_inteligencia"]["roi_cidadao"]
    assert roi["score"] is None and roi["nota"] is None
    assert body["indices_inteligencia"]["enriquecimento_patrimonial"]["compatibilidade"] is None


def test_dossier_votes_and_thematic_alignment_are_aggregated(client, seed):
    body = client.get(f"{BASE}/{seed.fulano.id}").json()
    assert [v["decisao"] for v in body["votacoes_principais"]] == ["SIM", "SIM"]
    axis = body["alinhamento_tematico"][0]
    assert (axis["total_votacoes"], axis["votos_sim"], axis["votos_nao"]) == (2, 2, 0)
    assert body["relevancia_legislativa"]["total_proposicoes"] == 1
    assert body["materias_propostas"][0]["url_oficial"].endswith("idProposicao=999")


def test_dossier_ceap_totals_come_from_the_database(client, seed, financas):
    ceap = client.get(f"{BASE}/{seed.fulano.id}").json()["custos_ceap"]
    assert ceap["possui_dados"] is True and ceap["gasto_total_recente"] == 150.0 and ceap["total_notas"] == 2
    assert ceap["gastos_por_tipo"] == [{"tipo_despesa": "Combustível", "total_gasto": 150.0, "percentual": 100.0}]


def test_dossier_ceap_exposes_year_totals_and_suppliers_with_cnpj_only(client, seed, financas):
    ceap = client.get(f"{BASE}/{seed.fulano.id}").json()["custos_ceap"]
    assert ceap["gastos_por_ano"] == [{"ano": 2024, "total_gasto": 150.0}]
    assert ceap["maiores_fornecedores"] == [
        {"nome_fornecedor": "Posto X", "cnpj_cpf": "12.345.678/0001-99", "total_recebido": 150.0, "num_notas": 2}
    ]


def test_dossier_reaches_finance_stored_on_the_duplicate_with_the_official_id(client, db, seed):
    """O dado fica no cadastro com `CAMARA_ID`; o dossiê (endereçado pelo cadastro do legado) chega nele pelo id."""
    pessoa_com_id = db.execute(
        text("INSERT INTO core.pessoa (nome_exibicao) VALUES ('Beltrano') RETURNING id")
    ).scalar_one()
    db.execute(
        text(
            "INSERT INTO core.pessoa_identificador (pessoa_id, fonte_id, tipo, valor) VALUES (:p, :f, 'CAMARA_ID', '333')"
        ),
        {"p": pessoa_com_id, "f": fonte_id(db, "CAMARA_CSV")},
    )
    inserir_fin(db, "despesa_cota", pessoa_id=pessoa_com_id, ano=2024, tipo_despesa="Passagem", valor_liquido=900)
    db.commit()
    beltrano = client.get(f"{BASE}/{seed.beltrano.id}").json()["custos_ceap"]
    assert beltrano["possui_dados"] is True and beltrano["gasto_total_recente"] == 900.0
    # quem tem outro identificador não herda nada
    lula = client.get(f"{BASE}/{seed.lula_fonte.id}").json()["custos_ceap"]
    assert lula["possui_dados"] is False and lula["gasto_total_recente"] == 0.0


def test_dossier_for_politician_without_any_data_has_empty_sections(client, db, seed):
    novo = Politician(civil_name="Novato", electoral_name="Novato", camara_id=777)
    db.add(novo)
    db.commit()
    body = client.get(f"{BASE}/{novo.id}").json()
    assert body["perfil"]["cargo_atual"] == "PARLAMENTAR" and body["trajetoria_mandatos"] == []
    assert body["custos_ceap"]["possui_dados"] is False and body["custos_ceap"]["total_notas"] is None
    assert body["remuneracao"]["resumo"]["total_bruto_2023"] is None  # sem folha registrada o total é desconhecido
    assert body["emendas_parlamentares"]["possui_dados"] is False
    assert body["financiamento_campanha"]["possui_dados"] is False
    assert body["materias_propostas"] == [] and body["votacoes_principais"] == []


def test_executive_initiatives_only_for_who_held_the_presidency(client, seed):
    president = client.get(f"{BASE}/{seed.presidente.id}").json()
    assert [m["titulo"] for m in president["materias_propostas"]] == ["MPV 1/2023"]
    # Nome parecido ("Lula da Fonte") não herda as iniciativas do Executivo
    homonym = client.get(f"{BASE}/{seed.lula_fonte.id}").json()
    assert homonym["materias_propostas"] == []
    assert homonym["perfil"]["foto_url"].endswith("/222.jpg")
    assert president["perfil"]["foto_url"] == "/presidents/lula.jpg"


def test_executive_initiatives_respect_the_presidential_term_window(client, db, seed):
    # Iniciativa anterior à posse não pertence ao mandato
    from app.models import Proposition, TipoProposicaoEnum

    db.add(
        Proposition(
            proposition_type=TipoProposicaoEnum.MPV,
            number=9,
            year=2020,
            title="MPV 9/2020",
            summary="Antiga",
            presentation_date=date(2020, 1, 1),
            is_executive_initiative=True,
            external_camara_id=2000,
        )
    )
    db.commit()
    titles = [m["titulo"] for m in client.get(f"{BASE}/{seed.presidente.id}").json()["materias_propostas"]]
    assert titles == ["MPV 1/2023"]


def test_name_based_certidoes_hack_is_gone_real_processes_are_shown(client, db, seed):
    """Antes, qualquer nome contendo 'Lula da Fonte' tinha os processos escondidos e 'Nada Consta' forçado."""
    db.add(
        ProcessoJudicial(
            politician_id=seed.lula_fonte.id,
            process_number="0001234-56.2020.1.00.0000",
            court_agency="STF",
            process_date="2020-05-01",
            case_class="Ação Penal",
            description="d",
            legal_status="Em curso",
            proof_url="https://exemplo/p",
            status_summary="Em andamento",
        )
    )
    db.commit()
    ficha = client.get(f"{BASE}/{seed.lula_fonte.id}").json()["ficha_limpa"]
    assert ficha["possui_processos_declarados"] is True
    assert ficha["status_geral"] == "Processos Declarados"
    assert ficha["processos_detalhados"][0]["numero_processo"] == "0001234-56.2020.1.00.0000"


def test_certidoes_never_get_invented_numbers_dates_or_codes(client, db, seed):
    inserir_fin(
        db,
        "certidao",
        pessoa_id=pessoa_do(db, seed.beltrano),
        orgao="TSE",
        tipo="Eleitoral",
        situacao="Positiva",
        fonte_id=fonte_id(db, "TSE"),
    )
    db.commit()
    data = client.get(f"{BASE}/{seed.beltrano.id}/certidoes").json()
    cert = data["certidoes"][0]
    assert cert["numero_processo"] is None and cert["data_emissao"] is None and cert["codigo_autenticidade"] is None
    assert cert["link_comprovacao"] is None
    # Certidão positiva registrada: nunca pode sair "Nada Consta"
    assert data["status_geral"] == "Processos Declarados" and data["possui_processos_declarados"] is True
    assert data["orgaos_declarados"] == ["TSE"]
    assert (
        data["link_tse_divulgacand"] == "https://divulgacandcontas.tse.jus.br/divulga/#/"
    )  # portal geral, sem candidato fixo
    assert data["dados_certidoes_disponiveis"] is True


def test_certidoes_with_real_values_are_passed_through(client, db, seed):
    inserir_fin(
        db,
        "certidao",
        pessoa_id=pessoa_do(db, seed.beltrano),
        orgao="TSE",
        tipo="Registro 2018",
        situacao="Declarada: registro indeferido",
        detalhes="Eleição 2018",
        numero_processo="123",
        fonte_id=fonte_id(db, "TSE"),
    )
    db.commit()
    cert = client.get(f"{BASE}/{seed.beltrano.id}/certidoes").json()["certidoes"][0]
    assert (cert["numero_processo"], cert["detalhes"], cert["status_ficha"]) == (
        "123",
        "Eleição 2018",
        "Declarada: registro indeferido",
    )
    assert cert["data_emissao"] is None and cert["codigo_autenticidade"] is None  # o TSE não informa


def test_remuneration_summary_uses_latest_year_with_data(client, db, seed):
    inserir_fin(  # um ano anterior com valores bem diferentes: não pode entrar nos totais do ano de referência
        db,
        "remuneracao",
        pessoa_id=pessoa_do(db, seed.fulano),
        ano=2023,
        mes=12,
        salario_bruto=1000,
        salario_liquido=900,
        cota_ceap=7000,
        auxilio_moradia=111,
        outros_beneficios=222,
        fonte_id=fonte_id(db, "CAMARA_PORTAL"),
    )
    for month, ceap in ((1, 100), (2, 300)):
        inserir_fin(
            db,
            "remuneracao",
            pessoa_id=pessoa_do(db, seed.fulano),
            ano=2024,
            mes=month,
            salario_bruto=40000,
            salario_liquido=30000,
            cota_ceap=ceap,
            auxilio_moradia=10,
            outros_beneficios=5,
            fonte_id=fonte_id(db, "CAMARA_PORTAL"),
        )
    db.commit()
    summary = client.get(f"{BASE}/{seed.fulano.id}").json()["remuneracao"]["resumo"]
    assert summary["ano_referencia"] == 2024
    assert summary["salario_bruto_atual"] == 40000.0
    assert summary["media_ceap_mensal"] == 200.0
    assert summary["total_ceap_2023"] == 400.0 and summary["total_beneficios_2023"] == 30.0
    assert summary["total_bruto_2023"] == 80000.0  # só 2024; os 1.000 de 2023 ficam de fora
    acumulado = financas_service.remuneracao(db, [pessoa_do(db, seed.fulano)])["acumulado"]
    assert acumulado == 81000.0  # o acumulado, sim, soma todos os anos


def test_attendance_rate_is_computed_from_real_records(client, db, seed):
    for day, status in (
        (1, TipoPresencaEnum.PRESENTE),
        (2, TipoPresencaEnum.PRESENTE),
        (3, TipoPresencaEnum.AUSENCIA_NAO_JUSTIFICADA),
        (4, TipoPresencaEnum.AUSENCIA_JUSTIFICADA),
    ):
        db.add(
            AttendanceRecord(
                politician_id=seed.fulano.id,
                mandate_id=seed.mandate_fulano.id,
                legislative_house=CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS,
                session_date=date(2024, 3, day),
                attendance_status=status,
            )
        )
    db.commit()
    att = client.get(f"{BASE}/{seed.fulano.id}").json()["assiduidade"]
    assert att["total_sessoes"] == 4 and att["total_presencas"] == 2
    assert att["faltas_justificadas"] == 1 and att["faltas_nao_justificadas"] == 1
    assert att["taxa_presenca_pct"] is not None and 0 < att["taxa_presenca_pct"] < 100


def test_emendas_endpoint_and_dossier_agree(client, seed, financas):
    emendas = client.get(f"{BASE}/{seed.fulano.id}/emendas").json()
    assert emendas["total_empenhado"] == 100.0 and emendas["total_pago"] == 50.0
    dossier = client.get(f"{BASE}/{seed.fulano.id}").json()["emendas_parlamentares"]
    assert (dossier["total_empenhado"], dossier["total_pago"]) == (100.0, 50.0)
    assert dossier["percentual_execucao"] == 50.0


def test_dossier_trajectory_is_most_recent_first_and_current_party_comes_from_affiliation(client, seed):
    body = client.get(f"{BASE}/{seed.fulano.id}").json()
    assert [m["ano_eleicao"] for m in body["trajetoria_mandatos"]] == [2022, 2006]
    assert body["perfil"]["partido_atual"] == "PT" and body["perfil"]["cargo_atual"] == "DEPUTADO_FEDERAL"
    assert body["filiacoes_partidarias"][0]["is_atual"] is True


def test_search_politicians_filters_active_by_presidential_mandate(client, seed, db):
    # fulano had mandates in 2006 and 2022 (covers lula-2023)
    resp = client.get(BASE, params={"mandate_id": "lula-2023"})
    assert resp.status_code == 200
    ids = [p["id"] for p in resp.json()["politicos"]]
    assert str(seed.fulano.id) in ids


def test_search_politicians_uses_the_period_of_the_presidential_mandate_from_the_database(client, seed, db):
    criar_mandato_presidencial(db, "Presidente Antigo", date(2000, 1, 1), date(2004, 1, 1), "antigo-2000")
    criar_mandato_presidencial(db, "Presidente Atual", date(2023, 1, 1), None, "atual-2023")
    db.commit()
    # ninguém do seed tinha mandato entre 2000 e 2004; todos os atuais tinham em 2023
    assert client.get(BASE, params={"mandate_id": "antigo-2000"}).json()["politicos"] == []
    assert str(seed.fulano.id) in [
        p["id"] for p in client.get(BASE, params={"mandate_id": "atual-2023"}).json()["politicos"]
    ]


def test_dossier_vote_summary_lists_every_yes_vote_with_its_total(client, seed):
    resumo = client.get(f"{BASE}/{seed.fulano.id}").json()["resumo_votos"]
    assert (resumo["sim"]["total"], resumo["nao"]["total"], resumo["ausente"]["total"]) == (2, 0, 0)
    assert len(resumo["sim"]["itens"]) == resumo["sim"]["total"] and resumo["nao"]["itens"] == []
    assert {"proposicao_numero", "data", "url_oficial"} <= set(resumo["sim"]["itens"][0])


def test_dossier_vote_summary_no_and_absent_groups(client, seed):
    nao = client.get(f"{BASE}/{seed.lula_fonte.id}").json()["resumo_votos"]
    assert nao["nao"]["total"] == 1 and nao["sim"]["total"] == 0 and len(nao["nao"]["itens"]) == 1
    ausente = client.get(f"{BASE}/{seed.maria_a.id}").json()["resumo_votos"]
    assert ausente["ausente"]["total"] == 1 and len(ausente["ausente"]["itens"]) == 1


def test_dossier_vote_summary_for_someone_without_votes_is_zero_and_empty(client, seed):
    resumo = client.get(f"{BASE}/{seed.presidente.id}").json()["resumo_votos"]
    for grupo in resumo.values():
        assert grupo == {"total": 0, "itens": []}


def test_dossier_vote_summary_ignores_other_options(client, seed):
    """Obstrução e Art. 17 não entram em nenhum dos três grupos."""
    resumo = client.get(f"{BASE}/{seed.beltrano.id}").json()["resumo_votos"]
    assert sum(g["total"] for g in resumo.values()) == 0


def test_financiamento_considera_so_a_campanha_mais_recente_e_conta_doadores_distintos(client, db, seed, financas):
    pessoa = pessoa_do(db, seed.fulano)
    for ano, nome, valor in ((2018, "Doador Antigo", 9000), (2022, "Fulana Doadora", 250)):
        inserir_fin(
            db,
            "doacao_campanha",
            pessoa_id=pessoa,
            ano_eleicao=ano,
            doador_nome=nome,
            doador_documento="***.654.321-**" if nome == "Fulana Doadora" else None,
            valor=valor,
            fonte_id=fonte_id(db, "TSE"),
        )
    db.commit()
    campanha = client.get(f"{BASE}/{seed.fulano.id}").json()["financiamento_campanha"]
    assert campanha["ano_eleicao"] == 2022 and campanha["total_arrecadado"] == 750.0
    assert campanha["total_doadores"] == 1  # a campanha de 2022 tem um doador (dois recibos), a de 2018 não entra
    assert {d["ano_eleicao"] for d in campanha["todas_doacoes"]} == {2022}
    assert campanha["top_doadores"][0]["valor_doado"] == 750.0 and campanha["top_doadores"][0]["percentual"] == 100.0
    avulsa = client.get(f"{BASE}/{seed.fulano.id}/doacoes").json()
    assert avulsa["ano_eleicao"] == 2022 and avulsa["total_arrecadado"] == 750.0
    assert {d["ano_eleicao"] for d in avulsa["doacoes"]} == {2022}


def test_ceap_avulsa_sem_despesa_devolve_gasto_desconhecido_e_nao_zero(client, seed):
    ceap = client.get(f"{BASE}/{seed.beltrano.id}/ceap").json()
    assert ceap["possui_dados"] is False and ceap["total_gasto"] is None and ceap["despesas"] == []
