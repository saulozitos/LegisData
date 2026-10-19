"""Indicadores avançados do dossiê e endpoints de CEAP/emendas alimentados pelo schema `fin`."""

from datetime import date

import pytest
from app.models import AttendanceRecord, CasaLegislativaEnum, TipoPresencaEnum

from .conftest import fonte_id, inserir_fin, pessoa_do

BASE = "/api/v1/politicians"


def _add_remuneration(db, seed, months=2, ano=2024, bruto=40000):
    pessoa = pessoa_do(db, seed.fulano)
    for month in range(1, months + 1):
        inserir_fin(
            db,
            "remuneracao",
            pessoa_id=pessoa,
            ano=ano,
            mes=month,
            salario_bruto=bruto,
            salario_liquido=30000,
            cota_ceap=100,
            auxilio_moradia=0,
            outros_beneficios=0,
            fonte_id=fonte_id(db, "CAMARA_PORTAL"),
        )


def _subsidio_de_2019_a_2022(db, seed):
    for ano in (2019, 2020, 2021, 2022):  # um registro por ano da janela: sem buraco no divisor
        _add_remuneration(db, seed, months=1, ano=ano, bruto=20000)


def _declarar_patrimonio(db, politico, ano, valor, detalhes=None):
    inserir_fin(
        db,
        "declaracao_patrimonio",
        pessoa_id=pessoa_do(db, politico),
        ano_eleicao=ano,
        valor_declarado=valor,
        detalhes=detalhes,
        fonte_id=fonte_id(db, "TSE"),
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


def test_roi_is_only_computed_with_ceap_salary_and_attendance(client, db, seed, financas):
    body = client.get(f"{BASE}/{seed.fulano.id}").json()["indices_inteligencia"]["roi_cidadao"]
    assert body["score"] is None and body["nota"] is None  # sem remuneração/presença: sem nota

    _add_remuneration(db, seed)
    _add_attendance(db, seed)
    db.commit()
    roi = client.get(f"{BASE}/{seed.fulano.id}").json()["indices_inteligencia"]["roi_cidadao"]
    assert roi["nota"] is not None and 0 <= roi["nota"] <= 100
    assert roi["score"] in {"A+", "A", "B", "C", "D"}
    assert roi["pontos_ialp"] is not None and roi["custo_por_ponto_ialp"] is not None
    assert roi["custo_total_operacional"] == pytest.approx(
        150.0 + 80000.0
    )  # CEAP do banco + subsídios BRUTOS registrados


def test_patrimony_history_growth_and_compatibility(client, db, seed):
    _declarar_patrimonio(db, seed.fulano, 2018, 100000)
    _declarar_patrimonio(db, seed.fulano, 2022, 150000, "Imóvel")
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
    _subsidio_de_2019_a_2022(db, seed)  # 80.000 no total: 20.000 por ano
    _declarar_patrimonio(db, seed.fulano, 2018, 100000)  # a base: a última declaração até o início da remuneração
    _declarar_patrimonio(db, seed.fulano, 2022, final_value)
    db.commit()
    enrich = client.get(f"{BASE}/{seed.fulano.id}").json()["indices_inteligencia"]["enriquecimento_patrimonial"]
    assert enrich["compatibilidade"] == expected


def test_patrimonio_so_e_comparado_na_janela_da_remuneracao_e_a_declaracao_antiga_nao_infla_a_razao(client, db, seed):
    _subsidio_de_2019_a_2022(db, seed)  # 80.000 de subsídio na janela
    _declarar_patrimonio(db, seed.fulano, 1998, 1000)  # antes da janela: não entra na comparação
    _declarar_patrimonio(db, seed.fulano, 2018, 100000)
    _declarar_patrimonio(db, seed.fulano, 2022, 150000)
    db.commit()
    enrich = client.get(f"{BASE}/{seed.fulano.id}").json()["indices_inteligencia"]["enriquecimento_patrimonial"]
    assert enrich["periodo_comparado"] == {"de": 2018, "ate": 2022, "subsidio_de": 2019, "subsidio_ate": 2022}
    assert enrich["delta_patrimonio"] == 50000.0  # 150.000 - 100.000 (e não - 1.000)
    assert enrich["razao_patrimonio_renda"] == 0.62 and enrich["compatibilidade"] == "COMPATÍVEL"


def test_patrimonio_sem_declaracao_depois_da_base_nao_e_comparado(client, db, seed):
    _add_remuneration(db, seed, months=2, ano=2024)
    _declarar_patrimonio(db, seed.fulano, 2018, 100000)  # a base seria 2018 e não há declaração depois dela
    db.commit()
    enrich = client.get(f"{BASE}/{seed.fulano.id}").json()["indices_inteligencia"]["enriquecimento_patrimonial"]
    assert enrich["periodo_comparado"] is None and enrich["compatibilidade"] is None
    assert "Dados insuficientes" in enrich["diagnostico"]


def test_declaracoes_na_janela_da_remuneracao_e_funcao_pura():
    from app.services.financas_service import declaracoes_na_janela_da_remuneracao as janela

    declaracoes = [{"ano": a} for a in (1998, 2006, 2018, 2022)]
    assert [d["ano"] for d in janela(declaracoes, 2019, 2026)] == [2018, 2022]
    assert [d["ano"] for d in janela(declaracoes, 2018, 2022)] == [
        2018,
        2022,
    ]  # a base pode ser do próprio primeiro ano
    assert [d["ano"] for d in janela(declaracoes, 1999, 2022)] == [1998, 2006, 2018, 2022]  # base colada no início
    # o fim também é cortado: a declaração de 2022 fica fora de uma remuneração que parou em 2021
    assert janela(declaracoes, 1999, 2021) == [{"ano": 1998}, {"ano": 2006}, {"ano": 2018}]
    # base distante do início do subsídio: a fonte não tem o subsídio dos anos entre as duas, não há o que comparar
    assert janela(declaracoes, 2000, 2022) == [] and janela(declaracoes, 2021, 2022) == []
    assert janela(declaracoes, 2019, 2021) == []  # só a base cabe na janela: não há o que comparar
    assert janela(declaracoes, 1990, 2022) == [] and janela(declaracoes, None, 2022) == []
    assert janela(declaracoes, 2019, None) == [] and janela([], 2019, 2022) == []


def test_reeleito_compara_o_patrimonio_so_ate_a_ultima_declaracao_dentro_do_subsidio(client, db, seed):
    """Remuneração 2019-2026, declarações 2018 e 2022: o divisor é o subsídio de 2019-2022, não o dos 8 anos."""
    for ano in (2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026):
        _add_remuneration(db, seed, months=1, ano=ano)  # 40.000 por ano
    _declarar_patrimonio(db, seed.fulano, 2018, 100000)
    _declarar_patrimonio(db, seed.fulano, 2022, 220000)
    db.commit()
    enrich = client.get(f"{BASE}/{seed.fulano.id}").json()["indices_inteligencia"]["enriquecimento_patrimonial"]
    assert enrich["periodo_comparado"] == {"de": 2018, "ate": 2022, "subsidio_de": 2019, "subsidio_ate": 2022}
    assert enrich["salario_acumulado_estimado"] == 160000.0  # 2019, 2020, 2021 e 2022
    assert enrich["razao_patrimonio_renda"] == 0.75 and enrich["compatibilidade"] == "COMPATÍVEL"


def test_ex_parlamentar_nao_compara_declaracao_posterior_ao_fim_do_subsidio(client, db, seed):
    """Remuneração 2019-2023, declarações 2018, 2022 e 2026: a de 2026 (candidatura) fica fora da janela."""
    for ano in (2019, 2020, 2021, 2022, 2023):
        _add_remuneration(db, seed, months=1, ano=ano)
    _declarar_patrimonio(db, seed.fulano, 2018, 100000)
    _declarar_patrimonio(db, seed.fulano, 2022, 150000)
    _declarar_patrimonio(db, seed.fulano, 2026, 900000)
    db.commit()
    enrich = client.get(f"{BASE}/{seed.fulano.id}").json()["indices_inteligencia"]["enriquecimento_patrimonial"]
    assert enrich["periodo_comparado"]["ate"] == 2022 and enrich["delta_patrimonio"] == 50000.0
    assert enrich["compatibilidade"] == "COMPATÍVEL"


def test_sem_despesa_da_ceap_a_concentracao_e_o_custo_do_roi_ficam_desconhecidos_e_nao_zero(client, db, seed):
    dossie = client.get(f"{BASE}/{seed.lula_fonte.id}").json()  # nenhuma despesa de CEAP registrada
    assert dossie["custos_ceap"]["possui_dados"] is False and dossie["custos_ceap"]["gasto_total_recente"] is None
    concentracao = dossie["indices_inteligencia"]["concentracao_ceap"]
    assert concentracao["indice_hhi"] is None and concentracao["percentual_maior_fornecedor"] is None
    assert concentracao["nivel_risco"] is None and concentracao["maior_fornecedor"] is None
    assert dossie["indices_inteligencia"]["roi_cidadao"]["custo_total_operacional"] is None


def test_suplente_que_assume_depois_da_base_nao_tem_o_patrimonio_comparado_com_subsidio_parcial(client, db, seed):
    """Remuneração só de 2021-2022 e base de 2018: o patrimônio de 2019-2020 não tem subsídio registrado."""
    _add_remuneration(db, seed, months=1, ano=2021, bruto=20000)
    _add_remuneration(db, seed, months=1, ano=2022, bruto=20000)
    _declarar_patrimonio(db, seed.fulano, 2018, 100000)
    _declarar_patrimonio(db, seed.fulano, 2022, 250000)
    db.commit()
    enrich = client.get(f"{BASE}/{seed.fulano.id}").json()["indices_inteligencia"]["enriquecimento_patrimonial"]
    assert enrich["periodo_comparado"] is None and enrich["razao_patrimonio_renda"] is None
    assert enrich["compatibilidade"] is None and "Dados insuficientes" in enrich["diagnostico"]


def test_ano_sem_remuneracao_no_meio_da_janela_deixa_a_comparacao_indisponivel(client, db, seed):
    for ano in (2019, 2021, 2022):  # falta 2020
        _add_remuneration(db, seed, months=1, ano=ano, bruto=20000)
    _declarar_patrimonio(db, seed.fulano, 2018, 100000)
    _declarar_patrimonio(db, seed.fulano, 2022, 250000)
    db.commit()
    enrich = client.get(f"{BASE}/{seed.fulano.id}").json()["indices_inteligencia"]["enriquecimento_patrimonial"]
    assert enrich["periodo_comparado"] is None and enrich["compatibilidade"] is None


def test_subsidio_na_janela_exclui_o_ano_da_base_e_nao_inventa_zero(db, seed):
    from app.services import financas_service

    _add_remuneration(db, seed, months=1, ano=2018)
    _add_remuneration(db, seed, months=2, ano=2019)
    db.commit()
    pessoas = [pessoa_do(db, seed.fulano)]
    assert financas_service.subsidio_na_janela(db, pessoas, 2018, 2019) == 80000.0  # o ano da base (2018) fica de fora
    assert (
        financas_service.subsidio_na_janela(db, pessoas, 2019, 2022) is None
    )  # sem remuneração na faixa: desconhecido
    assert financas_service.subsidio_na_janela(db, [], 2018, 2019) is None
    _add_remuneration(db, seed, months=1, ano=2021)
    db.commit()
    assert financas_service.subsidio_na_janela(db, pessoas, 2018, 2021) is None  # faltam 2020: buraco no divisor


def test_remuneracao_devolve_float_e_o_primeiro_ano_da_fonte(client, db, seed):
    _add_remuneration(db, seed, months=2, ano=2021)
    db.commit()
    resumo = client.get(f"{BASE}/{seed.fulano.id}").json()["remuneracao"]["resumo"]
    assert resumo["total_bruto_2023"] == 80000.0 and resumo["ano_referencia"] == 2021
    from app.services import financas_service

    fonte = financas_service.remuneracao(db, [pessoa_do(db, seed.fulano)])
    assert fonte["primeiro_ano"] == 2021 and isinstance(fonte["total_bruto_ano"], float)
    assert isinstance(fonte["total_ceap_ano"], float) and fonte["total_beneficios_ano"] == 0.0


def test_ceap_endpoint_totals_by_year_and_type_from_fin(client, db, seed):
    pessoa = pessoa_do(db, seed.beltrano)
    for ano, tipo, valor in ((2023, "Passagem", 400), (2024, "Passagem", 300), (2024, "Telefonia", 200)):
        inserir_fin(db, "despesa_cota", pessoa_id=pessoa, ano=ano, tipo_despesa=tipo, valor_liquido=valor)
    inserir_fin(db, "despesa_cota_resumo", pessoa_id=pessoa, total_notas=3)
    db.commit()
    body = client.get(f"{BASE}/{seed.beltrano.id}/ceap").json()
    assert body["total_gasto"] == 900.0 and body["total_notas"] == 3
    assert [(d["ano"], d["tipo"], d["valor"]) for d in body["despesas"]] == [
        (2024, "Passagem", 300.0),
        (2024, "Telefonia", 200.0),
        (2023, "Passagem", 400.0),
    ]


def test_ceap_endpoint_without_any_data_is_empty(client, seed):
    body = client.get(f"{BASE}/{seed.lula_fonte.id}/ceap").json()
    assert body["total_gasto"] is None and body["possui_dados"] is False and body["despesas"] == []


def test_emendas_endpoint_lists_only_the_authors_emendas(client, db, seed):
    base = dict(
        autor_texto="BELTRANO",
        tipo_autor="INDIVIDUAL",
        autor_situacao="IDENTIFICADO",
        tipo_emenda="INDIVIDUAL",
        localidade_destino="RJ",
        fonte_id=fonte_id(db, "PORTAL_TRANSPARENCIA"),
    )
    pessoa = pessoa_do(db, seed.beltrano)
    inserir_fin(db, "emenda", pessoa_id=pessoa, ano=2024, codigo_emenda="X1", valor_empenhado=10, valor_pago=5, **base)
    inserir_fin(db, "emenda", pessoa_id=pessoa, ano=2023, codigo_emenda=None, valor_empenhado=20, valor_pago=0, **base)
    inserir_fin(
        db,
        "emenda",
        pessoa_id=pessoa_do(db, seed.lula_fonte),
        ano=2024,
        codigo_emenda="Y1",
        valor_empenhado=999,
        valor_pago=999,
        **{**base, "autor_texto": "LULA DA FONTE"},
    )
    db.commit()
    body = client.get(f"{BASE}/{seed.beltrano.id}/emendas").json()
    assert body["total_empenhado"] == 30.0 and body["total_pago"] == 5.0  # a emenda de outro autor não entra
    assert [e["codigo"] for e in body["emendas"]] == ["X1", None]
    dossier = client.get(f"{BASE}/{seed.beltrano.id}").json()["emendas_parlamentares"]
    assert dossier["possui_dados"] is True and dossier["total_emendas"] == 2


def test_emendas_endpoint_without_any_data_is_empty(client, seed):
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
    pessoa = pessoa_do(db, seed.fulano)
    for month in (1, 2):
        inserir_fin(
            db,
            "remuneracao",
            pessoa_id=pessoa,
            ano=2024,
            mes=month,
            salario_bruto=44008.52,
            salario_liquido=27822.06 if month == 2 else None,
            fonte_id=fonte_id(db, "CAMARA_PORTAL"),
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
    inserir_fin(
        db,
        "remuneracao",
        pessoa_id=pessoa_do(db, seed.fulano),
        ano=2024,
        mes=3,
        salario_bruto=44008.52,
        fonte_id=fonte_id(db, "CAMARA_PORTAL"),
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


def test_senate_attendance_counts_unjustified_absences(client, db, seed):
    """No Senado a presença vem das votações nominais; o código NCom (não compareceu) é a falta não justificada."""
    _attend(db, seed, CasaLegislativaEnum.SENADO_FEDERAL, 5, TipoPresencaEnum.PRESENTE)
    _attend(db, seed, CasaLegislativaEnum.SENADO_FEDERAL, 6, TipoPresencaEnum.LICENCA_MEDICA)
    db.commit()
    att = client.get(f"{BASE}/{seed.fulano.id}").json()["assiduidade"]
    assert att["faltas_nao_justificadas"] == 0 and att["faltas_justificadas"] == 1
    assert att["unidade"] == "dia com votação nominal em plenário" and "Senado" in att["fonte"]


def test_attendance_without_records_has_no_source_and_no_rate(client, seed):
    att = client.get(f"{BASE}/{seed.fulano.id}").json()["assiduidade"]
    assert att["taxa_presenca_pct"] is None and att["total_sessoes"] == 0
    assert att["periodo_inicio"] is None and att["unidade"] is None and att["fonte"] is None


def test_dossier_weighted_legislative_indicators(client, db, seed):

    from app.models.legislative import Proposition, PropositionAuthor, TipoAutoriaEnum, TipoProposicaoEnum

    # Add a co-authored proposition for fulano
    prop_co = Proposition(
        proposition_type=TipoProposicaoEnum.PEC,
        number=99,
        year=2024,
        title="PEC 99/2024",
        summary="PEC importante",
        presentation_date=date(2024, 1, 1),
        external_camara_id=8899,
    )
    db.add(prop_co)
    db.flush()

    pa1 = PropositionAuthor(
        proposition_id=prop_co.id,
        politician_id=seed.fulano.id,
        author_name="Fulano",
        authorship_type=TipoAutoriaEnum.COAUTOR,
        order=2,
    )
    pa2 = PropositionAuthor(
        proposition_id=seed.proposition.id,
        politician_id=seed.fulano.id,
        author_name="Fulano",
        authorship_type=TipoAutoriaEnum.AUTOR_PRINCIPAL,
        order=1,
    )
    # a fonte repete o mesmo parlamentar como coautor da proposição em que já é autor principal
    pa3 = PropositionAuthor(
        proposition_id=seed.proposition.id,
        politician_id=seed.fulano.id,
        author_name="Fulano",
        authorship_type=TipoAutoriaEnum.COAUTOR,
        order=2,
    )
    db.add_all([pa1, pa2, pa3])
    db.commit()

    dossier = client.get(f"{BASE}/{seed.fulano.id}").json()
    ids = [m["id"] for m in dossier["materias_propostas"]]
    assert len(ids) == len(set(ids))
    rel = dossier["relevancia_legislativa"]
    assert "lideranca_legislativa_count" in rel
    assert "apoio_politico_count" in rel
    assert "taxa_eficiencia_pct" in rel
    assert "score_atividade_ponderada" in rel
    assert "distribuicao_complexidade" in rel
    assert rel["lideranca_legislativa_count"] >= 1
    assert rel["apoio_politico_count"] >= 1

    props = dossier["materias_propostas"]
    assert len(props) >= 2
    p_dict = {p["titulo"]: p for p in props}
    assert "PEC 99/2024" in p_dict
    pec_item = p_dict["PEC 99/2024"]
    assert pec_item["papel_autoria"] == "COAUTOR"
    assert pec_item["peso_participacao"] == 0.05  # assinatura de apoio a PEC
    assert pec_item["peso_complexidade"] == 3.0  # PEC = 3.0
    assert pec_item["score_calculado"] == 0.15  # 0.05 * 3.0 * 1.0


def test_roi_rewards_ialp_delivery_not_proposition_count(client, db, seed):
    """Muitas assinaturas de apoio e requerimentos não levam à nota máxima: a entrega é medida em pontos IALP."""
    from app.models.legislative import Proposition, PropositionAuthor, TipoAutoriaEnum, TipoProposicaoEnum

    _add_remuneration(db, seed)
    _add_attendance(db, seed)
    for i in range(30):
        prop = Proposition(
            proposition_type=TipoProposicaoEnum.REQ,
            number=500 + i,
            year=2024,
            title=f"REQ {500 + i}/2024",
            summary="Requerimento",
            presentation_date=date(2024, 1, 1),
            external_camara_id=70000 + i,
        )
        db.add(prop)
        db.flush()
        db.add(
            PropositionAuthor(
                proposition_id=prop.id,
                politician_id=seed.fulano.id,
                author_name="Fulano",
                authorship_type=TipoAutoriaEnum.COAUTOR,
                order=2,
            )
        )
    db.commit()
    roi = client.get(f"{BASE}/{seed.fulano.id}").json()["indices_inteligencia"]["roi_cidadao"]
    assert roi["pontos_ialp"] < 10
    assert roi["score"] != "A+"


def test_attendance_reads_leg_presenca_with_inferred_absences(client, db, seed):
    """Falta inferida entra na taxa e é separada da oficial; presença anterior a 2003 não entra na taxa."""
    from sqlalchemy import text

    client.get(f"{BASE}/{seed.fulano.id}")  # a ponte do conftest cria a pessoa no schema novo
    pessoa_id = db.execute(text("SELECT id FROM core.pessoa WHERE uid = :u"), {"u": seed.fulano.id}).scalar()
    casa = db.execute(text("SELECT id FROM ref.casa_legislativa WHERE codigo = 'CAMARA_DOS_DEPUTADOS'")).scalar()
    linhas = [
        ("1999-05-04", "PRESENTE"),
        ("2005-03-01", "PRESENTE"),
        ("2005-03-02", "PRESENTE"),
        ("2005-03-03", "AUSENCIA_INFERIDA"),
        ("2005-03-04", "AUSENCIA_INFERIDA"),
        ("2024-03-05", "AUSENCIA_JUSTIFICADA"),
    ]
    for dia, tipo in linhas:
        db.execute(
            text(
                "INSERT INTO leg.presenca (pessoa_id, casa_id, data_sessao, tipo_codigo) VALUES (:p, :c, :d, :t) "
                "ON CONFLICT DO NOTHING"
            ),
            {"p": pessoa_id, "c": casa, "d": dia, "t": tipo},
        )
    db.commit()

    att = client.get(f"{BASE}/{seed.fulano.id}").json()["assiduidade"]
    assert att["total_sessoes"] == 5  # a presença de 1999 fica fora
    assert (att["total_presencas"], att["faltas_inferidas"], att["faltas_justificadas"]) == (2, 2, 1)
    assert att["taxa_presenca_pct"] == 40.0
    assert att["periodo_inicio"] == "2005-03-01" and "inferidas" in (att["observacao"] or "")
    tipos = {f["tipo"] for f in att["amostra_faltas"]}
    assert "AUSENCIA_INFERIDA" in tipos
