"""Indicadores avançados do dossiê e endpoints de CEAP/emendas alimentados pelo arquivo do ETL."""

from datetime import date

import pytest
from app.models import (
    AttendanceRecord,
    CasaLegislativaEnum,
    PoliticianAssetDeclaration,
    PoliticianRemuneration,
    TipoPresencaEnum,
)

from .conftest import write_json

BASE = "/api/v1/politicians"


def _add_remuneration(db, seed, months=2):
    for month in range(1, months + 1):
        db.add(
            PoliticianRemuneration(
                politician_id=seed.fulano.id,
                mandate_id=seed.mandate_fulano.id,
                reference_year=2024,
                reference_month=month,
                gross_salary=40000,
                net_salary=30000,
                parliamentary_quota_ceap=100,
                housing_allowance=0,
                other_benefits=0,
                data_source="Portal",
            )
        )


def _add_attendance(db, seed, present=3, absent=1):
    day = 1
    for _ in range(present):
        db.add(
            AttendanceRecord(
                politician_id=seed.fulano.id,
                mandate_id=seed.mandate_fulano.id,
                legislative_house=CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS,
                session_date=date(2024, 3, day),
                attendance_status=TipoPresencaEnum.PRESENTE,
            )
        )
        day += 1
    for _ in range(absent):
        db.add(
            AttendanceRecord(
                politician_id=seed.fulano.id,
                mandate_id=seed.mandate_fulano.id,
                legislative_house=CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS,
                session_date=date(2024, 3, day),
                attendance_status=TipoPresencaEnum.AUSENCIA_NAO_JUSTIFICADA,
            )
        )
        day += 1


def test_roi_is_only_computed_with_ceap_salary_and_attendance(client, db, seed):
    body = client.get(f"{BASE}/{seed.fulano.id}").json()["indices_inteligencia"]["roi_cidadao"]
    assert body["score"] is None and body["nota"] is None  # sem remuneração/presença: sem nota

    _add_remuneration(db, seed)
    _add_attendance(db, seed)
    db.commit()
    roi = client.get(f"{BASE}/{seed.fulano.id}").json()["indices_inteligencia"]["roi_cidadao"]
    assert roi["nota"] is not None and 0 <= roi["nota"] <= 100
    assert roi["score"] in {"A+", "A", "B", "C", "D"}
    assert roi["custo_total_operacional"] == pytest.approx(
        150.0 + 80000.0
    )  # CEAP do banco + subsídios BRUTOS registrados


def test_patrimony_history_growth_and_compatibility(client, db, seed):
    db.add_all(
        [
            PoliticianAssetDeclaration(politician_id=seed.fulano.id, election_year=2018, declared_value_brl=100000),
            PoliticianAssetDeclaration(
                politician_id=seed.fulano.id, election_year=2022, declared_value_brl=150000, asset_details="Imóvel"
            ),
        ]
    )
    db.commit()
    resumo = client.get(f"{BASE}/{seed.fulano.id}").json()["evolucao_patrimonial"]["resumo"]
    assert resumo["possui_dados"] is True and resumo["total_declaracoes"] == 2
    assert (resumo["primeiro_ano"], resumo["ultimo_ano"]) == (2018, 2022)
    assert resumo["crescimento_absoluto"] == 50000.0 and resumo["crescimento_pct"] == 50.0
    assert resumo["ultimo_valor_formatado"] == "R$ 150.000,00"
    # Sem remuneração registrada não há como comparar renda e patrimônio: indicador indisponível (null)
    enrich = client.get(f"{BASE}/{seed.fulano.id}").json()["indices_inteligencia"]["enriquecimento_patrimonial"]
    assert enrich["compatibilidade"] is None and enrich["razao_patrimonio_renda"] is None


@pytest.mark.parametrize("final_value,expected", [(100100, "COMPATÍVEL"), (190000, "MODERADO"), (900000, "ATÍPICO")])
def test_patrimony_compatibility_classification(client, db, seed, final_value, expected):
    _add_remuneration(db, seed, months=2)  # subsídios brutos registrados: 80.000
    db.add_all(
        [
            PoliticianAssetDeclaration(politician_id=seed.fulano.id, election_year=2018, declared_value_brl=100000),
            PoliticianAssetDeclaration(
                politician_id=seed.fulano.id, election_year=2022, declared_value_brl=final_value
            ),
        ]
    )
    db.commit()
    enrich = client.get(f"{BASE}/{seed.fulano.id}").json()["indices_inteligencia"]["enriquecimento_patrimonial"]
    assert enrich["compatibilidade"] == expected


def test_ceap_endpoint_falls_back_to_etl_file_with_exact_name(client, seed, data_dir):
    write_json(
        data_dir,
        "despesas_ceap_2019_2026.json",
        {"BELTRANO": {"total_gasto": 900.0, "total_notas": 3, "por_ano": {"2023": 400, "2024": 500}}},
    )
    body = client.get(f"{BASE}/{seed.beltrano.id}/ceap").json()
    assert body["total_gasto"] == 900.0 and body["total_notas"] == 3
    assert [d["ano"] for d in body["despesas"]] == [2024, 2023]
    assert all(d["cnpj_cpf"] is None for d in body["despesas"])


def test_ceap_endpoint_without_any_source_is_empty(client, seed, data_dir):
    body = client.get(f"{BASE}/{seed.lula_fonte.id}/ceap").json()
    assert body["total_gasto"] == 0.0 and body["despesas"] == []


def test_emendas_endpoint_falls_back_to_etl_file(client, seed, data_dir):
    write_json(
        data_dir,
        "emendas_parlamentares_2019_2026.json",
        [
            {"politician_name": "Beltrano", "ano": 2024, "valor_empenhado": 10, "valor_pago": 5, "codigo_emenda": "X1"},
            {"politician_name": "Beltrano", "ano": 2023, "valor_empenhado": None, "valor_pago": None},
            {"politician_name": "Mariana Beltrano", "ano": 2024, "valor_empenhado": 999, "valor_pago": 999},
        ],
    )
    body = client.get(f"{BASE}/{seed.beltrano.id}/emendas").json()
    assert body["total_empenhado"] == 10.0 and body["total_pago"] == 5.0  # linha de outro nome não entra
    assert len(body["emendas"]) == 2 and body["emendas"][0]["codigo"] == "X1"
    dossier = client.get(f"{BASE}/{seed.beltrano.id}").json()["emendas_parlamentares"]
    assert dossier["possui_dados"] is True and dossier["total_emendas"] == 2


def test_emendas_endpoint_without_any_source_is_empty(client, seed, data_dir):
    body = client.get(f"{BASE}/{seed.lula_fonte.id}/emendas").json()
    assert body["total_pago"] == 0.0 and body["emendas"] == []


def test_dossier_flags_truncated_proposition_list(client, db, seed, monkeypatch):
    from app.api.v1 import politicians as pol_module
    from app.models import Proposition, TipoProposicaoEnum

    monkeypatch.setattr(pol_module, "MAX_PROPOSITIONS_LISTED", 1)
    db.add(
        Proposition(
            proposition_type=TipoProposicaoEnum.PL,
            number=77,
            year=2024,
            title="PL 77/2024",
            summary="s",
            presentation_date=date(2024, 1, 1),
            author_politician_id=seed.fulano.id,
            external_camara_id=7777,
        )
    )
    db.commit()
    rel = client.get(f"{BASE}/{seed.fulano.id}").json()["relevancia_legislativa"]
    assert rel["total_proposicoes"] == 1 and rel["total_proposicoes_registradas"] == 2
    assert rel["amostra_limitada"] is True


def test_remuneration_fields_not_reported_by_the_source_are_null_not_zero(client, db, seed):
    """A fonte oficial só informa o bruto mensal (e o líquido do mês mais recente): o resto é null, nunca 0."""
    db.add_all(
        [
            PoliticianRemuneration(
                politician_id=seed.fulano.id,
                mandate_id=seed.mandate_fulano.id,
                reference_year=2024,
                reference_month=month,
                gross_salary=44008.52,
                net_salary=27822.06 if month == 2 else None,
                parliamentary_quota_ceap=None,
                housing_allowance=None,
                other_benefits=None,
                data_source="Câmara dos Deputados - Portal da Transparência",
            )
            for month in (1, 2)
        ]
    )
    db.commit()
    rem = client.get(f"{BASE}/{seed.fulano.id}").json()["remuneracao"]
    resumo = rem["resumo"]
    assert resumo["salario_bruto_atual"] == 44008.52 and resumo["salario_liquido_atual"] == 27822.06
    assert resumo["media_ceap_mensal"] is None and resumo["total_ceap_2023"] is None
    assert resumo["total_beneficios_2023"] is None
    assert resumo["total_bruto_2023"] == pytest.approx(88017.04) and resumo["ano_referencia"] == 2024
    por_mes = {r["mes"]: r for r in rem["historico"]}
    assert por_mes[1]["salario_liquido"] is None and por_mes[2]["salario_liquido"] == 27822.06
    for linha in por_mes.values():
        assert linha["cota_ceap"] is None and linha["auxilio_moradia"] is None and linha["outros_beneficios"] is None


def test_latest_month_without_net_salary_yields_null_current_net(client, db, seed):
    db.add(
        PoliticianRemuneration(
            politician_id=seed.fulano.id,
            mandate_id=seed.mandate_fulano.id,
            reference_year=2024,
            reference_month=3,
            gross_salary=44008.52,
            net_salary=None,
            data_source="Portal",
        )
    )
    db.commit()
    resumo = client.get(f"{BASE}/{seed.fulano.id}").json()["remuneracao"]["resumo"]
    assert resumo["salario_bruto_atual"] == 44008.52 and resumo["salario_liquido_atual"] is None


def _attend(db, seed, house, day, status):
    db.add(
        AttendanceRecord(
            politician_id=seed.fulano.id,
            mandate_id=seed.mandate_fulano.id,
            legislative_house=house,
            session_date=date(2024, 3, day),
            attendance_status=status,
        )
    )


def test_attendance_exposes_source_unit_and_period_for_the_chamber(client, db, seed):
    _attend(db, seed, CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS, 5, TipoPresencaEnum.PRESENTE)
    _attend(db, seed, CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS, 12, TipoPresencaEnum.AUSENCIA_NAO_JUSTIFICADA)
    db.commit()
    att = client.get(f"{BASE}/{seed.fulano.id}").json()["assiduidade"]
    assert att["faltas_nao_justificadas"] == 1 and att["taxa_presenca_pct"] == 50.0
    assert (att["periodo_inicio"], att["periodo_fim"]) == ("2024-03-05", "2024-03-12")
    assert att["unidade"] == "dia com sessão deliberativa" and "Ato da Mesa" in att["fonte"]


def test_senate_attendance_never_reports_unjustified_absences_as_zero(client, db, seed):
    """O Senado só expõe presença derivada das votações nominais: ausência não justificada é desconhecida."""
    _attend(db, seed, CasaLegislativaEnum.SENADO_FEDERAL, 5, TipoPresencaEnum.PRESENTE)
    _attend(db, seed, CasaLegislativaEnum.SENADO_FEDERAL, 6, TipoPresencaEnum.LICENCA_MEDICA)
    db.commit()
    att = client.get(f"{BASE}/{seed.fulano.id}").json()["assiduidade"]
    assert att["faltas_nao_justificadas"] is None and att["faltas_justificadas"] == 1
    assert att["unidade"] == "dia com votação nominal em plenário" and "Senado" in att["fonte"]


def test_attendance_without_records_has_no_source_and_no_rate(client, seed):
    att = client.get(f"{BASE}/{seed.fulano.id}").json()["assiduidade"]
    assert att["taxa_presenca_pct"] is None and att["total_sessoes"] == 0
    assert att["periodo_inicio"] is None and att["unidade"] is None and att["fonte"] is None
