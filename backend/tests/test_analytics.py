import math
from datetime import date
from decimal import Decimal

import pytest
from app.api.v1.analytics import (
    _calculate_mandate_prosperity_score,
    _clean_val,
    _delta,
    _get_mandate_years,
    _num,
    _relative,
)
from app.core import data_files
from app.models import (
    AnnualSocialIndicator,
    FederalTransferByState,
    PartyAffiliation,
    StatePresidentialElectionResult,
    StateSocialIndicator,
)

from .conftest import criar_mandato_presidencial, observar_serie, write_json

BASE = "/api/v1/analytics"

FULL_MANDATE = {
    "pib_medio_anual_pct": 2.5,
    "ipca_acumulado_pct": 15.0,
    "valores_anuais": [1, 2, 3, 4],
    "salario_minimo_inicial_usd": 100,
    "salario_minimo_final_usd": 150,
    "fome_media_pct": 5.0,
    "desemprego_medio_pct": 8.0,
    "desmatamento_medio_anual_km2": 5000.0,
}


# ---------------------------------------------------------------------------
# Helpers puros
# ---------------------------------------------------------------------------
def test_clean_val():
    assert _clean_val(None) is None
    assert _clean_val("invalid") is None
    assert _clean_val(float("nan")) is None
    assert _clean_val(math.inf) is None
    assert _clean_val(10.555) == 10.55
    assert _clean_val("20.123") == 20.12
    assert _clean_val(0) == 0.0  # zero é valor legítimo


def test_num_treats_zero_as_a_value_and_missing_as_none():
    assert _num({"a": 0}, "a") == 0.0
    assert _num({"a": None, "b": 3}, "a", "b") == 3.0
    assert _num({"a": float("nan")}, "a") is None
    assert _num({}, "a") is None


def test_delta_and_relative():
    assert _delta(1.0, 3.5) == 2.5
    assert _delta(None, 3) is None and _delta(2, None) is None
    assert _delta(0.0, 4.0) == 4.0  # zero não é "ausente"
    assert _relative(50.0, 75.0) == 50.0
    assert _relative(0.0, 5.0) is None  # divisão por zero indefinida
    assert _relative(None, 5.0) is None


@pytest.mark.parametrize(
    "mandate,expected",
    [
        ({"id_mandato": "sem-datas"}, []),
        ({"data_inicio": "1992-10-02", "data_fim": "1999-01-01"}, [1995, 1996, 1997, 1998]),
        # a data de fim é exclusiva: mandato que termina em 01/01/2023 NÃO inclui 2023 (antes havia off-by-one)
        ({"data_inicio": "2019-01-01", "data_fim": "2023-01-01"}, [2019, 2020, 2021, 2022]),
        ({"data_inicio": "2010-01-01", "data_fim": "2014-12-31"}, [2010, 2011, 2012, 2013, 2014]),
    ],
)
def test_get_mandate_years(mandate, expected):
    assert _get_mandate_years(mandate) == expected


def test_get_mandate_years_open_mandate_runs_until_current_year():
    years = _get_mandate_years({"data_inicio": "2023-01-01", "data_fim": None})
    assert years[0] == 2023 and years[-1] == date.today().year


# ---------------------------------------------------------------------------
# Score de prosperidade
# ---------------------------------------------------------------------------
def test_prosperity_score_with_all_pillars():
    score = _calculate_mandate_prosperity_score(FULL_MANDATE)
    # pib 75, ipca 85, sm 70, fome 77.5, desemprego 60, desmatamento 90
    assert score["subscore_economico"] == 80.0
    assert score["subscore_social"] == 73.8
    assert score["subscore_estabilidade"] == 75.0
    assert score["score_geral"] == 76.3
    assert score["classificacao"] == "Crescimento Consistente"
    assert score["pilares_ausentes"] == []
    assert score["dados_incompletos"] is False


@pytest.mark.parametrize(
    "overrides,expected_score,expected_class",
    [
        (
            {
                "pib_medio_anual_pct": 5.0,
                "ipca_acumulado_pct": 4.0,
                "fome_media_pct": 0.0,
                "desemprego_medio_pct": 0.0,
                "desmatamento_medio_anual_km2": 0.0,
                "salario_minimo_final_usd": 300,
            },
            99.3,
            "Alta Prosperidade",
        ),
        (
            {
                "pib_medio_anual_pct": -3.0,
                "ipca_acumulado_pct": 200.0,
                "fome_media_pct": 30.0,
                "desemprego_medio_pct": 20.0,
                "desmatamento_medio_anual_km2": 30000.0,
                "salario_minimo_final_usd": 50,
            },
            None,
            "Cenário Desafiador",
        ),
    ],
)
def test_prosperity_score_class_boundaries(overrides, expected_score, expected_class):
    score = _calculate_mandate_prosperity_score({**FULL_MANDATE, **overrides})
    assert score["classificacao"] == expected_class
    if expected_score is not None:
        assert score["score_geral"] == expected_score
    else:
        assert score["score_geral"] < 55


def test_prosperity_score_missing_pillars_are_dropped_and_weights_renormalized():
    score = _calculate_mandate_prosperity_score({"pib_medio_anual_pct": 2.5})
    assert score["score_geral"] == 75.0  # só o pilar PIB (75) existe; nenhum valor padrão inventado
    assert set(score["pilares_ausentes"]) == {"ipca", "salario_minimo", "fome", "desemprego", "desmatamento"}
    assert score["dados_incompletos"] is True
    assert score["subscore_social"] is None and score["subscore_estabilidade"] is None


def test_prosperity_score_without_any_data_is_null_not_a_made_up_grade():
    score = _calculate_mandate_prosperity_score({})
    assert score["score_geral"] is None
    assert score["classificacao"] is None
    assert len(score["pilares_ausentes"]) == 6


def test_prosperity_score_zero_values_are_data_not_missing():
    score = _calculate_mandate_prosperity_score({"pib_medio_anual_pct": 0.0, "desemprego_medio_pct": 0.0})
    assert "pib" not in score["pilares_ausentes"] and "desemprego" not in score["pilares_ausentes"]
    assert score["subscore_economico"] == 50.0  # 50 + 0 * 10
    assert score["subscore_estabilidade"] == 100.0


def test_prosperity_score_ignores_nan_inputs():
    score = _calculate_mandate_prosperity_score({"pib_medio_anual_pct": float("nan"), "fome_media_pct": 0.0})
    assert "pib" in score["pilares_ausentes"] and "fome" not in score["pilares_ausentes"]


def test_prosperity_score_derives_years_from_dates_when_series_missing():
    mandate = {"ipca_acumulado_pct": 20.0, "data_inicio": "2019-01-01", "data_fim": "2023-01-01"}
    score = _calculate_mandate_prosperity_score(mandate)
    # 20% / 4 anos = 5% ao ano -> 100 - 5*4 = 80
    assert score["subscore_economico"] == 80.0


# ---------------------------------------------------------------------------
# mandates-performance / compare-mandates
# ---------------------------------------------------------------------------
@pytest.fixture()
def mandates_db(db):
    """Dois mandatos: A com IPCA zero, PIB e salário; B com IPCA e salário, sem PIB."""
    criar_mandato_presidencial(db, "Alfa", date(2011, 1, 1), date(2015, 1, 1), "a-2011")
    criar_mandato_presidencial(db, "Beta", date(2015, 1, 1), date(2019, 1, 1), "b-2015")
    observar_serie(db, "IPCA_MENSAL", date(2012, 1, 1), 0.0)
    observar_serie(db, "PIB_CRESC_REAL", date(2011, 1, 1), 1.0)
    observar_serie(db, "SALARIO_MINIMO_MENSAL", date(2014, 12, 1), 700.0)
    observar_serie(db, "IPCA_MENSAL", date(2016, 1, 1), 5.0)
    observar_serie(db, "SALARIO_MINIMO_MENSAL", date(2018, 12, 1), 900.0)
    db.commit()


def test_mandates_performance_adds_score_and_is_stable(client, mandates_db):
    first = client.get(f"{BASE}/mandates-performance").json()
    second = client.get(f"{BASE}/mandates-performance").json()
    assert first == second
    assert first[0]["score_prosperidade"]["pilares_ausentes"]  # dados incompletos sinalizados
    assert [m["id_mandato"] for m in first] == ["a-2011", "b-2015"]
    assert first[0]["ipca_acumulado_pct"] == 0.0 and first[1]["pib_medio_anual_pct"] is None


def test_mandates_performance_without_mandates_is_404(client):
    assert client.get(f"{BASE}/mandates-performance").status_code == 404


def test_compare_mandates_preserves_zero_and_nulls_for_missing_values(client, mandates_db):
    body = client.get(f"{BASE}/compare-mandates", params={"mandate1": "a-2011", "mandate2": "b-2015"}).json()
    deltas = body["deltas"]
    assert deltas["ipca_acumulado_diff_pp"] == 5.0  # 0 -> 5: o zero do mandato A é um valor válido
    assert deltas["ipca_acumulado_relative_pct"] is None  # base zero: variação relativa indefinida
    assert deltas["pib_medio_diff_pp"] is None  # mandato B não tem PIB: nada de 0 inventado
    assert deltas["salario_minimo_brl_diff"] == 200.0
    assert deltas["salario_minimo_brl_relative_pct"] == pytest.approx(28.57)
    assert body["scores_prosperidade"]["delta_score_geral"] is None or isinstance(
        body["scores_prosperidade"]["delta_score_geral"], float
    )


def test_compare_mandates_trajectory_uses_exclusive_end_years(client, mandates_db):
    body = client.get(f"{BASE}/compare-mandates", params={"mandate1": "a-2011", "mandate2": "b-2015"}).json()
    years = [row["m1_calendar_year"] for row in body["normalized_trajectory"]]
    assert years == [2011, 2012, 2013, 2014]
    assert [row["m2_calendar_year"] for row in body["normalized_trajectory"]] == [2015, 2016, 2017, 2018]


def test_compare_mandates_joins_optional_datasets(client, db, mandates_db):
    observar_serie(db, "PIB_CRESC_REAL", date(2015, 1, 1), -3.5)
    observar_serie(db, "IPCA_ACUM_ANO", date(2011, 1, 1), 6.5)
    db.add_all(
        [
            _transfer(mandate_id_ref="a-2011", valor_pago_brl=Decimal("100.00"), valor_per_capita_brl=Decimal("2.00")),
            _transfer(mandate_id_ref="b-2015", valor_pago_brl=Decimal("150.00"), valor_per_capita_brl=Decimal("3.00")),
        ]
    )
    db.commit()
    body = client.get(f"{BASE}/compare-mandates", params={"mandate1": "a-2011", "mandate2": "b-2015"}).json()
    assert body["normalized_trajectory"][0]["m1_pib"] == 1.0 and body["normalized_trajectory"][0]["m1_ipca"] == 6.5
    assert body["normalized_trajectory"][0]["m2_pib"] == -3.5
    assert body["repasses_comparison"]["by_area"]["Saúde"]["growth_pct"] == 50.0
    assert body["repasses_comparison"]["summary"]["diff_total_brl"] == 50.0
    assert body["termometro_repasses_apoio"]["m2_lider_per_capita"]["uf"] == "SP"


def test_compare_mandates_unknown_mandate_is_404(client, mandates_db):
    response = client.get(f"{BASE}/compare-mandates", params={"mandate1": "a-2011", "mandate2": "zzz"})
    assert response.status_code == 404
    assert "zzz" in response.json()["detail"]


def test_compare_mandates_requires_both_parameters(client, mandates_db):
    assert client.get(f"{BASE}/compare-mandates", params={"mandate1": "a-2011"}).status_code == 422


# ---------------------------------------------------------------------------
# wage-disparity / congress-composition
# ---------------------------------------------------------------------------
WAGE = {
    "serie_historica": [
        {
            "ano": 2023,
            "presidente_dominante": "X",
            "salario_minimo_brl": 1320.0,
            "salario_parlamentar_brl": 41650.92,
            "multiplo_salarios_minimos": 31.5,
            "indice_salario_minimo_base100": 100.0,
            "indice_salario_parlamentar_base100": 100.0,
            "indice_ipca_base100": 100.0,
        }
    ],
    "votacao_salario_minimo": {
        "proposicao_titulo": "MPV 1172/2023",
        "ementa": "Salário mínimo",
        "data_votacao": "2023-06-01",
        "casa": "Câmara",
        "placar": {"SIM": 439},
        "votos_amostra": [],
    },
    "estatisticas_disparidade": {"multiplo_atual": 31.5},
}


def test_wage_disparity_returns_dataset_contents(client, data_dir):
    write_json(data_dir, "salario_vs_inflacao.json", WAGE)
    response = client.get(f"{BASE}/wage-disparity")
    assert response.status_code == 200
    assert response.json()["serie_historica"][0]["salario_parlamentar_brl"] == 41650.92
    assert response.json()["estatisticas_disparidade"] == {"multiplo_atual": 31.5}


def test_wage_disparity_without_dataset_is_404(client, data_dir):
    response = client.get(f"{BASE}/wage-disparity")
    assert response.status_code == 404
    assert "ETL" in response.json()["detail"]


CHAMBER = {
    "total_cadeiras": 513,
    "presidentes": [],
    "governabilidade": {},
    "bancadas": [
        {"partido": "PT", "cadeiras": 68, "percentual": 13.3, "alinhamento": "BASE_GOVERNO", "cor_hex": "#f00"}
    ],
}


def test_congress_composition_known_and_unknown_mandate(client, data_dir):
    write_json(
        data_dir,
        "composicao_congresso.json",
        {
            "lula-2023": {
                "mandato_id": "lula-2023",
                "presidente_republica": "Lula",
                "periodo": "2023-",
                "camara": CHAMBER,
                "senado": {**CHAMBER, "total_cadeiras": 81},
            }
        },
    )
    ok = client.get(f"{BASE}/congress-composition", params={"mandate_id": "lula-2023"})
    assert ok.status_code == 200 and ok.json()["senado"]["total_cadeiras"] == 81
    # Mandato desconhecido NÃO cai silenciosamente em outro mandato
    missing = client.get(f"{BASE}/congress-composition", params={"mandate_id": "inventado"})
    assert missing.status_code == 404


def test_congress_composition_missing_dataset_is_404(client, data_dir):
    assert client.get(f"{BASE}/congress-composition").status_code == 404


def test_congress_composition_never_touches_the_filesystem_to_generate_data(client, data_dir):
    client.get(f"{BASE}/congress-composition")
    assert list(data_dir.iterdir()) == []  # GET não grava em disco


# ---------------------------------------------------------------------------
# federal-transfers
# ---------------------------------------------------------------------------
def _transfer(**kw):
    base = dict(
        mandate_id_ref="lula-2023",
        ano=2023,
        uf="SP",
        estado_nome="São Paulo",
        regiao="Sudeste",
        area_tematica="Saúde",
        valor_pago_brl=Decimal("100.00"),
        populacao_estimada=1000,
        valor_per_capita_brl=Decimal("0.10"),
    )
    base.update(kw)
    return FederalTransferByState(**base)


@pytest.fixture()
def known_mandates(db):
    criar_mandato_presidencial(db, "Lula", date(2023, 1, 1), None, "lula-2023")
    criar_mandato_presidencial(db, "Outro", date(2019, 1, 1), date(2023, 1, 1), "outro-2019")
    db.commit()


def test_federal_transfers_from_database(client, db, known_mandates):
    db.add_all(
        [_transfer(), _transfer(uf="RJ", estado_nome="Rio", area_tematica="Educação", valor_pago_brl=Decimal("50.00"))]
    )
    db.commit()
    body = client.get(f"{BASE}/federal-transfers", params={"mandate_id": "lula-2023"}).json()
    assert body["total_repassado_brl"] == 150.0
    assert body["areas_resumo"] == {"Saúde": 100.0, "Educação": 50.0}
    assert [i["uf"] for i in body["por_uf"]] == ["RJ", "SP"]


def test_federal_transfers_report_the_period_actually_covered(client, db, known_mandates):
    db.add_all(
        [
            _transfer(periodo_inicio="2023-01", periodo_fim="2026-09", meses_cobertos=45, parcial=False),
            _transfer(uf="RJ", estado_nome="Rio", periodo_inicio="2023-01", periodo_fim="2026-09", meses_cobertos=45),
        ]
    )
    db.commit()
    body = client.get(f"{BASE}/federal-transfers", params={"mandate_id": "lula-2023"}).json()
    assert body["periodo_inicio"] == "2023-01" and body["periodo_fim"] == "2026-09"
    assert body["meses_cobertos"] == 45 and body["cobertura_parcial"] is False
    assert "2023-01 a 2026-09" in body["periodo"] and "parcial" not in body["periodo"]


def test_federal_transfers_flag_partial_coverage_in_the_period_text(client, db, known_mandates):
    db.add(_transfer(periodo_inicio="2014-01", periodo_fim="2014-12", meses_cobertos=12, parcial=True))
    db.commit()
    body = client.get(f"{BASE}/federal-transfers", params={"mandate_id": "lula-2023"}).json()
    assert body["cobertura_parcial"] is True and "cobertura parcial" in body["periodo"]


def test_federal_transfers_without_period_info_do_not_invent_one(client, db, known_mandates):
    db.add(_transfer())  # linha legada, sem período
    db.commit()
    body = client.get(f"{BASE}/federal-transfers", params={"mandate_id": "lula-2023"}).json()
    assert body["periodo_inicio"] is None and body["cobertura_parcial"] is None
    assert "não informado" in body["periodo"]


def test_federal_transfers_area_filter_is_literal_not_a_wildcard(client, db, known_mandates):
    db.add(_transfer())
    db.commit()
    assert (
        client.get(f"{BASE}/federal-transfers", params={"mandate_id": "lula-2023", "area": "%"}).json()["por_uf"] == []
    )
    assert (
        client.get(f"{BASE}/federal-transfers", params={"mandate_id": "lula-2023", "area": "_____"}).json()["por_uf"]
        == []
    )
    assert (
        len(client.get(f"{BASE}/federal-transfers", params={"mandate_id": "lula-2023", "area": "saú"}).json()["por_uf"])
        == 1
    )


def test_federal_transfers_area_filter_without_hits_is_empty(client, db, known_mandates):
    db.add(_transfer())
    db.commit()
    body = client.get(f"{BASE}/federal-transfers", params={"mandate_id": "lula-2023", "area": "Segurança"}).json()
    assert body["por_uf"] == [] and body["total_repassado_brl"] == 0.0


def test_federal_transfers_mandate_without_rows_is_empty_not_filled_from_files(client, known_mandates):
    body = client.get(f"{BASE}/federal-transfers", params={"mandate_id": "outro-2019"}).json()
    assert body["por_uf"] == [] and body["total_repassado_brl"] == 0.0


def test_federal_transfers_unknown_mandate_is_404(client, known_mandates):
    assert client.get(f"{BASE}/federal-transfers", params={"mandate_id": "nao-existe"}).status_code == 404


# ---------------------------------------------------------------------------
# indicadores sociais / classes / eleições
# ---------------------------------------------------------------------------
def test_social_indicators_zero_is_preserved(client, db):
    db.add(
        AnnualSocialIndicator(
            year=2020, illiteracy_rate_pct=Decimal("0.00"), extreme_poverty_pct=None, gini_index=Decimal("0.000")
        )
    )
    db.commit()
    row = client.get(f"{BASE}/social-indicators").json()[0]
    assert row["analfabetismo_pct"] == 0.0 and row["gini"] == 0.0  # zero NÃO vira null
    assert row["extrema_pobreza_pct"] is None


def test_social_indicators_expose_official_series_fields(client, db):
    db.add(
        AnnualSocialIndicator(
            year=2024,
            gini_index=Decimal("0.504"),
            gini_series="PNAD Contínua — rendimento domiciliar per capita (t7435)",
            poverty_pct=Decimal("26.50"),
            food_insecurity_total_pct=Decimal("24.20"),
            unemployment_pct=Decimal("6.9"),
            data_source="IBGE / SIDRA (PNAD, PNAD Contínua, ODS)",
        )
    )
    db.commit()
    row = client.get(f"{BASE}/social-indicators").json()[0]
    assert row["pobreza_pct"] == 26.5 and row["inseguranca_alimentar_total_pct"] == 24.2
    assert row["desemprego_pct"] == 6.9 and "t7435" in row["serie_gini"]
    assert row["analfabetismo_pct"] is None  # lacuna de pesquisa continua null, nunca zero


def test_social_indicators_empty_table_is_an_empty_list(client):
    assert client.get(f"{BASE}/social-indicators").json() == []


def test_social_classes_use_latest_minimum_wage_from_the_series(client, db, data_dir):
    observar_serie(db, "SALARIO_MINIMO", date(2023, 1, 1), 1320.0)
    observar_serie(db, "SALARIO_MINIMO", date(2024, 1, 1), 1412.0)
    db.commit()
    body = client.get(f"{BASE}/social-classes").json()
    assert body["salario_minimo_referencia_brl"] == 1412.0
    assert body["ano_referencia"] == 2024
    classe_a = next(c for c in body["classes"] if c["classe"] == "Classe A")
    assert classe_a["renda_familiar_min_brl"] == pytest.approx(20 * 1412.0)
    assert classe_a["renda_familiar_max_brl"] is None
    assert classe_a["faixa_renda_formatada"].startswith("Acima de R$ 28.240,00")


def test_social_classes_without_wage_series_has_null_incomes(client, data_dir):
    body = client.get(f"{BASE}/social-classes").json()
    assert body["salario_minimo_referencia_brl"] is None and body["ano_referencia"] is None
    assert all(c["renda_familiar_min_brl"] is None and c["faixa_renda_formatada"] is None for c in body["classes"])
    assert "referência" in body["fonte"] or "estimativa" in body["fonte"]


def _pnad_year(ano, sm, dom, pessoas):
    return {
        "ano": ano,
        "visita": 5,
        "salario_minimo_brl": sm,
        "nacional": {
            "domicilios_renda_total": {"total_estimado": 78_000_000, "percentual": dom, "media_nominal_brl": 5000.0},
            "pessoas_renda_domiciliar": {
                "total_estimado": 210_000_000,
                "percentual": pessoas,
                "media_nominal_brl": 5500.0,
            },
            "pessoas_renda_per_capita": {
                "total_estimado": 210_000_000,
                "percentual": pessoas,
                "media_nominal_brl": 1900.0,
            },
            "ocupados_renda_trabalho": {"total_estimado": 98_000_000, "percentual": dom, "media_nominal_brl": 3200.0},
        },
    }


PNAD_DOM = [2.0, 4.0, 7.0, 27.0, 33.0, 20.0, 5.0, 2.0]  # soma 100
PNAD_PESSOAS = [1.0, 3.0, 6.0, 24.0, 35.0, 24.0, 5.0, 2.0]  # soma 100


@pytest.fixture
def pnad_file(data_dir):
    payload = {
        "fonte": "IBGE — PNAD Contínua",
        "is_synthetic": False,
        "faixas": [{"id": f"f{i}"} for i in range(8)],
        "metodologia": {"ponderacao": "V1032"},
        "anos": {
            "2023": _pnad_year(2023, 1320.0, PNAD_DOM, PNAD_PESSOAS),
            "2024": _pnad_year(2024, 1412.0, PNAD_DOM, PNAD_PESSOAS),
        },
    }
    write_json(data_dir, "pnad_faixas_salario_minimo.json", payload)
    return payload


def test_social_classes_come_from_pnad_microdata_when_available(client, pnad_file):
    body = client.get(f"{BASE}/social-classes").json()
    assert body["origem"] == "pnad"
    assert body["ano_referencia"] == 2024 and body["anos_disponiveis"] == [2023, 2024]
    assert body["salario_minimo_referencia_brl"] == 1412.0
    classes = {c["classe"]: c for c in body["classes"]}
    # Classe E = sem rendimento + até 2 SM (faixas 0 a 3); A = acima de 20 SM
    assert classes["Classe E"]["percentual_domicilios"] == 40.0
    assert classes["Classe E"]["percentual_populacao"] == 34.0
    assert classes["Classe A"]["percentual_domicilios"] == 2.0
    assert sum(c["percentual_domicilios"] for c in classes.values()) == pytest.approx(100.0)
    assert body["resumo_populacional"]["maioria_populacao_acumulada_d_e_pct"] == 73.0
    assert "PNAD" in body["fonte"] and "2024" in body["fonte"]
    assert body["distribuicoes"]["ocupados_renda_trabalho"]["media_nominal_brl"] == 3200.0
    assert classes["Classe A"]["renda_familiar_min_brl"] == pytest.approx(20 * 1412.0)


def test_social_classes_year_param_uses_that_years_minimum_wage(client, pnad_file):
    body = client.get(f"{BASE}/social-classes", params={"ano": 2023}).json()
    assert body["ano_referencia"] == 2023 and body["salario_minimo_referencia_brl"] == 1320.0


def test_social_classes_unknown_year_is_404_with_available_years(client, pnad_file):
    response = client.get(f"{BASE}/social-classes", params={"ano": 1999})
    assert response.status_code == 404 and "2023" in response.json()["detail"]


def test_social_classes_year_without_any_pnad_file_is_404(client, data_dir):
    assert client.get(f"{BASE}/social-classes", params={"ano": 2024}).status_code == 404


def test_social_classes_ignore_corrupt_pnad_years_and_fall_back(client, data_dir, pnad_file):
    broken = {
        "anos": {"2024": {"salario_minimo_brl": 1412.0, "nacional": {"domicilios_renda_total": {"percentual": [1]}}}}
    }
    write_json(data_dir, "pnad_faixas_salario_minimo.json", broken)
    data_files._cache.clear()
    body = client.get(f"{BASE}/social-classes").json()
    assert body["origem"] == "referencia_fixa"


def test_social_classes_without_pnad_keep_labelled_reference_estimate(client, data_dir):
    body = client.get(f"{BASE}/social-classes").json()
    assert body["origem"] == "referencia_fixa"


def _election(uf, year=2022, region="Sudeste", **kw):
    base = dict(
        election_year=year,
        mandate_ref_id="x",
        uf=uf,
        state_name=uf,
        region=region,
        winner_candidate_name="A",
        winner_party_acronym="PT",
        winner_votes_pct=Decimal("55.0"),
        runner_up_candidate_name="B",
        runner_up_party_acronym="PL",
        runner_up_votes_pct=Decimal("45.0"),
    )
    base.update(kw)
    return StatePresidentialElectionResult(**base)


def test_social_elections_joins_same_year_only_and_keeps_missing_as_null(client, db):
    db.add_all([_election("SP"), _election("RJ"), _election("AC", region="Norte")])
    db.add(
        StateSocialIndicator(
            year=2022,
            uf="SP",
            state_name="SP",
            region="Sudeste",
            extreme_poverty_pct=Decimal("0.00"),
            illiteracy_rate_pct=Decimal("2.5"),
        )
    )
    # Indicador de OUTRO ano para o RJ: nunca pode ser usado no cruzamento de 2022
    db.add(
        StateSocialIndicator(year=2018, uf="RJ", state_name="RJ", region="Sudeste", extreme_poverty_pct=Decimal("9.9"))
    )
    db.commit()

    body = client.get(f"{BASE}/social-elections", params={"ano": 2022}).json()
    by_uf = {e["uf"]: e for e in body["estados"]}
    assert by_uf["SP"]["extrema_pobreza_pct"] == 0.0  # zero preservado
    assert by_uf["RJ"]["extrema_pobreza_pct"] is None
    assert by_uf["AC"]["indice_gini"] is None
    assert body["estados"][0]["uf"] == "SP"  # com dado primeiro, sem dado depois
    sudeste = next(r for r in body["regioes_resumo"] if r["regiao"] == "Sudeste")
    assert sudeste["total_estados"] == 2 and sudeste["media_extrema_pobreza_pct"] == 0.0
    norte = next(r for r in body["regioes_resumo"] if r["regiao"] == "Norte")
    assert norte["media_extrema_pobreza_pct"] is None


@pytest.mark.parametrize("year", [1999, 0, 2023])
def test_social_elections_invalid_year_is_422(client, year):
    response = client.get(f"{BASE}/social-elections", params={"ano": year})
    assert response.status_code == 422
    assert "2022" in response.json()["detail"]


def test_social_elections_valid_year_without_rows_is_empty_not_an_error(client):
    body = client.get(f"{BASE}/social-elections", params={"ano": 1994}).json()
    assert body["estados"] == [] and body["total_estados"] == 0


# ---------------------------------------------------------------------------
# party-fidelity
# ---------------------------------------------------------------------------
def test_party_fidelity_empty_database(client):
    body = client.get(f"{BASE}/party-fidelity").json()
    assert body["dados_disponiveis"] is False
    assert body["party_balance"] == [] and body["top_nomads"] == []


def test_party_fidelity_counts_only_sitting_parliamentarians(client, db, seed):
    db.add(
        PartyAffiliation(
            politician_id=seed.fulano.id,
            party_id=seed.ptb.id,
            start_date=date(2015, 1, 1),
            end_date=date(2019, 12, 31),
            is_current=False,
        )
    )
    db.commit()
    body = client.get(f"{BASE}/party-fidelity").json()
    assert body["dados_disponiveis"] is True
    # Fulano, Lula da Fonte e Beltrano têm filiação; o presidente (PRESIDENTE) e as duas Maria (sem filiação) não entram
    assert body["summary"]["total_parlamentares"] == 3
    assert body["summary"]["total_nomades"] == 1
    assert body["summary"]["taxa_migracao_pct"] == 33.3
    balance = {p["partido"]: p for p in body["party_balance"]}
    assert (balance["PT"]["ganhos"], balance["PT"]["saldo_liquido"], balance["PT"]["bancada_atual"]) == (1, 1, 2)
    assert (balance["PTB"]["perdas"], balance["PTB"]["saldo_liquido"], balance["PTB"]["bancada_inicial"]) == (1, -1, 2)
    nomad = body["top_nomads"][0]
    assert nomad["nome_eleitoral"] == "Fulano" and nomad["siglas_sequencia"] == ["PTB", "PT"]
    assert nomad["total_trocas"] == 1 and nomad["cargo"] == "DEPUTADO FEDERAL" and nomad["uf"] == "SP"
    assert body["summary"]["partido_maior_ganho"] == "PT" and body["summary"]["partido_maior_perda"] == "PTB"
