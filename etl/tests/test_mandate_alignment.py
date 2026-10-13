"""Alinhamento de séries econômicas a mandatos: fim exclusivo, mês de posse e ausência de dados."""

from datetime import datetime

import pandas as pd
import pytest

from etl.transformers.economic_normalizer import EconomicNormalizer, intervalo_mandato, mes_pertence


def serie_mensal(valores_por_mes):
    """valores_por_mes: {'AAAA-MM': valor} -> DataFrame no formato do BCBExtractor."""
    linhas = []
    for ym, valor in valores_por_mes.items():
        dt = pd.Timestamp(f"{ym}-01")
        linhas.append({"data": dt, "ano": dt.year, "mes": dt.month, "dia": 1, "valor": valor})
    return pd.DataFrame(linhas)


def test_intervalo_mandato_fim_exclusivo_nao_inclui_ano_do_sucessor():
    ini, fim, ano_ini, ano_fim = intervalo_mandato({"data_inicio": "1995-01-01", "data_fim": "1999-01-01"})
    assert (ano_ini, ano_fim) == (1995, 1998)
    assert fim == pd.Timestamp("1999-01-01")


def test_intervalo_mandato_em_curso_termina_hoje():
    agora = datetime(2026, 10, 8)
    ini, fim, ano_ini, ano_fim = intervalo_mandato({"data_inicio": "2023-01-01", "data_fim": None}, agora=agora)
    assert ano_fim == 2026
    assert fim == pd.Timestamp("2026-10-09")


def test_janeiro_do_sucessor_nao_conta_nos_dois_mandatos():
    datas = pd.Series(pd.to_datetime(["1998-12-01", "1999-01-01"]))
    fhc1 = mes_pertence(datas, pd.Timestamp("1995-01-01"), pd.Timestamp("1999-01-01")).tolist()
    fhc2 = mes_pertence(datas, pd.Timestamp("1999-01-01"), pd.Timestamp("2003-01-01")).tolist()
    assert fhc1 == [True, False]
    assert fhc2 == [False, True]


def test_mes_de_posse_no_meio_do_mes():
    # Itamar assumiu em 02/10/1992: o IPCA de outubro/1992 é dele (antes era perdido)
    datas = pd.Series(pd.to_datetime(["1992-09-01", "1992-10-01"]))
    assert mes_pertence(datas, pd.Timestamp("1992-10-02"), pd.Timestamp("1995-01-01")).tolist() == [False, True]
    # Temer assumiu em 31/08/2016: agosto é de Dilma, setembro de Temer
    datas = pd.Series(pd.to_datetime(["2016-08-01", "2016-09-01"]))
    assert mes_pertence(datas, pd.Timestamp("2015-01-01"), pd.Timestamp("2016-08-31")).tolist() == [True, False]
    assert mes_pertence(datas, pd.Timestamp("2016-08-31"), pd.Timestamp("2019-01-01")).tolist() == [False, True]


PRESIDENTES = [
    {
        "id_referencia": "a-1995",
        "nome_eleitoral": "A",
        "partido_sigla": "X",
        "data_inicio": "1995-01-01",
        "data_fim": "1997-01-01",
        "status_mandato": "CONCLUIDO",
        "ministros_fazenda_chave": [],
        "marcos_economicos": [],
    },
    {
        "id_referencia": "b-1997",
        "nome_eleitoral": "B",
        "partido_sigla": "Y",
        "data_inicio": "1997-01-01",
        "data_fim": "1999-01-01",
        "status_mandato": "CONCLUIDO",
        "ministros_fazenda_chave": [],
        "marcos_economicos": [],
    },
]


def test_align_nao_duplica_janeiro_nem_ano_e_nao_zera_sem_dados():
    meses = {f"{a}-{m:02d}": 1.0 for a in (1995, 1996, 1997, 1998) for m in range(1, 13)}
    ipca = serie_mensal(meses)
    cambio = serie_mensal({k: 1.0 for k in meses})
    pib = pd.DataFrame([{"data": pd.Timestamp(f"{a}-01-01"), "ano": a, "valor": 2.0} for a in (1995, 1996, 1997, 1998)])
    vazio = pd.DataFrame(columns=["data", "ano", "mes", "dia", "valor"])

    res = EconomicNormalizer.align_indicators_to_mandates(
        presidents=PRESIDENTES,
        ipca_df=ipca,
        cambio_df=cambio,
        pib_anual_df=pib,
        divida_df=vazio,
        salario_min_df=vazio,
    )
    a, b = res
    # 24 meses de 1% por mandato; antes o primeiro mandato recebia 25 (janeiro do sucessor)
    assert a["ipca_acumulado_pct"] == pytest.approx((1.01**24 - 1) * 100, abs=1e-3)
    assert b["ipca_acumulado_pct"] == pytest.approx((1.01**24 - 1) * 100, abs=1e-3)
    assert [v["ano"] for v in a["valores_anuais"]] == [1995, 1996]
    assert [v["ano"] for v in b["valores_anuais"]] == [1997, 1998]
    assert a["anos_cobertos"] == "1995 - 1996"
    # Sem série de dívida/salário: None (e não 0)
    assert a["divida_liquida_inicial_pct_pib"] is None
    assert a["salario_minimo_inicial_brl"] is None


def test_sem_nenhum_dado_devolve_none_e_nao_zero():
    vazio = pd.DataFrame(columns=["data", "ano", "mes", "dia", "valor"])
    res = EconomicNormalizer.align_indicators_to_mandates(
        presidents=PRESIDENTES[:1],
        ipca_df=vazio,
        cambio_df=vazio,
        pib_anual_df=vazio,
        divida_df=vazio,
        salario_min_df=vazio,
    )
    assert res[0]["ipca_acumulado_pct"] is None
    assert res[0]["pib_crescimento_acumulado_pct"] is None
    assert res[0]["pib_medio_anual_pct"] is None


def test_dolar_fechamento_nao_usa_media_mensal():
    ipca = serie_mensal({"1995-12": 1.0})
    cambio = serie_mensal({"1995-12": 5.0})
    pib = pd.DataFrame([{"data": pd.Timestamp("1995-01-01"), "ano": 1995, "valor": 1.0}])
    vazio = pd.DataFrame(columns=["data", "ano", "mes", "dia", "valor"])
    df = EconomicNormalizer.build_annual_summaries(
        ipca_df=ipca,
        pib_anual_df=pib,
        cambio_df=cambio,
        salario_min_df=vazio,
        divida_df=vazio,
        presidents=PRESIDENTES,
    )
    assert df.loc[df["ano"] == 1995, "cotacao_dolar_fechamento"].isna().all()
    assert df.loc[df["ano"] == 1995, "cambio_dolar_medio"].iloc[0] == 5.0


def test_ano_em_curso_nao_tem_dolar_de_fechamento():
    ano_atual = datetime.now().year
    ipca = serie_mensal({f"{ano_atual}-01": 1.0, "1995-12": 1.0})
    pib = pd.DataFrame([{"data": pd.Timestamp("1995-01-01"), "ano": 1995, "valor": 1.0}])
    cambio = serie_mensal({f"{ano_atual}-01": 5.0, "1995-12": 1.0})
    ptax = pd.DataFrame(
        [
            {"data": pd.Timestamp("1995-12-28"), "ano": 1995, "mes": 12, "dia": 28, "valor": 0.97},
            {"data": pd.Timestamp(f"{ano_atual}-01-05"), "ano": ano_atual, "mes": 1, "dia": 5, "valor": 5.1},
        ]
    )
    vazio = pd.DataFrame(columns=["data", "ano", "mes", "dia", "valor"])
    df = EconomicNormalizer.build_annual_summaries(
        ipca_df=ipca,
        pib_anual_df=pib,
        cambio_df=cambio,
        salario_min_df=vazio,
        divida_df=vazio,
        presidents=PRESIDENTES,
        dolar_fechamento_df=ptax,
    ).set_index("ano")
    assert df.loc[1995, "cotacao_dolar_fechamento"] == 0.97  # último pregão do ano
    assert pd.isna(df.loc[ano_atual, "cotacao_dolar_fechamento"])
