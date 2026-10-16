"""Indicadores de cada mandato presidencial: funções puras de cálculo e a matriz lida do banco."""

from datetime import date

import pytest
from app.services.mandato_economia_service import indicadores_do_mandato, matriz_de_mandatos
from app.services.periodos import composto, do_mandato, intervalo_de_anos, nome_do_mandato

from .conftest import criar_mandato_presidencial, observar_serie


def test_composto_vazio_e_ausencia_e_zero_e_valor():
    assert composto([]) is None
    assert composto([0.0, 0.0]) == 0.0
    assert composto([10.0, 10.0]) == pytest.approx(21.0)


def test_do_mandato_usa_o_dia_15_e_fim_exclusivo():
    serie = [(date(2016, 8, 1), 1.0), (date(2016, 9, 1), 2.0), (date(2016, 12, 1), 3.0)]
    # Temer assume em 31/08/2016: agosto (dia 15) é da antecessora; setembro e dezembro são dele
    assert do_mandato(serie, date(2016, 8, 31), date(2019, 1, 1)) == [(date(2016, 9, 1), 2.0), (date(2016, 12, 1), 3.0)]
    # fim exclusivo em 01/09: o mês de agosto fica, setembro não
    assert do_mandato(serie, date(2016, 1, 1), date(2016, 9, 1)) == [(date(2016, 8, 1), 1.0)]


def test_intervalo_de_anos_corta_na_janela_e_trata_fim_exclusivo():
    assert intervalo_de_anos(date(1992, 10, 2), date(1999, 1, 1), 2026) == (1995, 1998)
    assert intervalo_de_anos(date(2019, 1, 1), date(2023, 1, 1), 2026) == (2019, 2022)
    assert intervalo_de_anos(date(2023, 1, 1), None, 2026) == (2023, 2026)


def test_nome_do_mandato():
    assert nome_do_mandato("Lula", "Lula 2") == "Lula (Lula 2)"
    assert nome_do_mandato("Temer", None) == "Temer"


def _series(**kw):
    vazio = {
        c: []
        for c in (
            "IPCA_MENSAL",
            "CAMBIO_MENSAL",
            "DIVIDA_LIQUIDA_PIB_MENSAL",
            "SALARIO_MINIMO_MENSAL",
            "PIB_CRESC_REAL",
            "DESEMPREGO_ANUAL",
            "DESMATAMENTO_AMAZONIA",
            "INSEGURANCA_ALIMENTAR_PCT",
            "HOMICIDIOS_TAXA",
            "IPCA_ACUM_ANO",
            "CAMBIO_MEDIO_ANO",
            "CAMBIO_FECHAMENTO_ANO",
            "SALARIO_MINIMO",
        )
    }
    vazio.update(kw)
    return vazio


def test_indicadores_sem_nenhuma_fonte_sao_todos_nulos_e_nunca_zero():
    from app.services.mandato_economia_service import _Anuais

    series = _series()
    indic = indicadores_do_mandato(series, _Anuais(series), date(2019, 1, 1), date(2023, 1, 1), [2019, 2020])
    assert all(v is None for v in indic.values())


def test_indicadores_calculam_cambio_divida_salario_em_dolar_e_medias():
    from app.services.mandato_economia_service import _Anuais

    series = _series(
        CAMBIO_MENSAL=[(date(2019, 1, 1), 4.0), (date(2022, 12, 1), 5.0)],
        DIVIDA_LIQUIDA_PIB_MENSAL=[(date(2019, 1, 1), 50.0), (date(2022, 12, 1), 56.0)],
        SALARIO_MINIMO_MENSAL=[(date(2019, 1, 1), 1000.0), (date(2022, 12, 1), 1500.0)],
        PIB_CRESC_REAL=[(date(2019, 1, 1), 2.0), (date(2020, 1, 1), -4.0)],
        DESEMPREGO_ANUAL=[(date(2019, 1, 1), 12.0), (date(2020, 1, 1), 14.0)],
        DESMATAMENTO_AMAZONIA=[(date(2019, 1, 1), 1000.0), (date(2020, 1, 1), 2000.0)],
        INSEGURANCA_ALIMENTAR_PCT=[(date(2020, 1, 1), 9.0)],
        HOMICIDIOS_TAXA=[(date(2019, 1, 1), 22.0), (date(2020, 1, 1), 24.0)],
    )
    indic = indicadores_do_mandato(series, _Anuais(series), date(2019, 1, 1), date(2023, 1, 1), [2019, 2020])
    assert (indic["cambio_inicial_usd_brl"], indic["cambio_final_usd_brl"], indic["cambio_variacao_pct"]) == (
        4.0,
        5.0,
        25.0,
    )
    assert (indic["divida_liquida_inicial_pct_pib"], indic["divida_liquida_delta_pct"]) == (50.0, 6.0)
    assert (indic["salario_minimo_inicial_usd"], indic["salario_minimo_final_usd"]) == (250.0, 300.0)
    assert indic["pib_crescimento_acumulado_pct"] == pytest.approx(-2.08) and indic["pib_medio_anual_pct"] == -1.0
    assert (indic["desemprego_inicial_pct"], indic["desemprego_final_pct"], indic["desemprego_medio_pct"]) == (
        12.0,
        14.0,
        13.0,
    )
    assert (indic["desmatamento_acumulado_km2"], indic["desmatamento_medio_anual_km2"]) == (3000.0, 1500.0)
    assert (indic["fome_inicial_pct"], indic["fome_final_pct"], indic["fome_media_pct"]) == (9.0, 9.0, 9.0)
    assert (indic["homicidios_inicial"], indic["homicidios_final"], indic["homicidios_medio"]) == (22.0, 24.0, 23.0)
    assert indic["feminicidios_medio"] is None  # sem fonte aberta automatizável


def test_matriz_de_mandato_em_curso_usa_a_data_injetada(db):
    criar_mandato_presidencial(db, "Fechado", date(2019, 1, 1), date(2023, 1, 1), "fechado-2019", "F 1", "PT")
    criar_mandato_presidencial(db, "Aberto", date(2023, 1, 1), None, "aberto-2023", None)
    for ano in (2019, 2023):
        observar_serie(db, "PIB_CRESC_REAL", date(ano, 1, 1), 1.0)
    observar_serie(db, "IPCA_MENSAL", date(2023, 3, 1), 1.0)
    db.commit()
    fechado, aberto = matriz_de_mandatos(db, hoje=date(2024, 6, 15))
    assert (fechado["id_mandato"], fechado["presidente"], fechado["partido"]) == ("fechado-2019", "Fechado (F 1)", "PT")
    assert (fechado["data_inicio"], fechado["data_fim"], fechado["anos_cobertos"]) == (
        "2019-01-01",
        "2023-01-01",
        "2019 - 2022",
    )
    # mandato em curso: o fim é a data injetada e os anos vão até o último ano com IPCA mensal na base (2023)
    assert (aberto["data_fim"], aberto["anos_cobertos"]) == ("2024-06-15", "2023 - 2023")
    assert aberto["presidente"] == "Aberto" and aberto["ipca_acumulado_pct"] == 1.0
    assert [v["ano"] for v in aberto["valores_anuais"]] == [2023]
    assert aberto["valores_anuais"][0]["pib_crescimento_real_pct"] == 1.0
    assert aberto["valores_anuais"][0]["taxa_desemprego_anual"] is None
