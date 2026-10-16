"""Bancadas eleitas (TSE) e conferência da curadoria da composição do Congresso."""

import pandas as pd

from etl.extractors import composicao_tse as tse
from etl.extractors.composicao_extractor import (
    COMPOSICAO_CONGRESSO_HISTORICO,
    comparar_bancadas,
    enriquecer_com_tse,
)


def linhas(*regs):
    return pd.DataFrame(
        [
            {
                "SG_UF": uf,
                "NR_CANDIDATO": nr,
                "NM_CANDIDATO": nome,
                "DS_CARGO": cargo,
                "SG_PARTIDO": partido,
                "DS_SIT_TOT_TURNO": sit,
            }
            for uf, nr, nome, cargo, partido, sit in regs
        ]
    )


def test_contar_eleitos_aceita_rotulos_antigos_e_nao_conta_suplente_nem_duplicata():
    df = linhas(
        ("SP", "1", "A", "DEPUTADO FEDERAL", "PT", "ELEITO"),
        ("SP", "2", "B", "DEPUTADO FEDERAL", "PT", "MÉDIA"),  # rótulo dos arquivos antigos
        ("SP", "3", "C", "DEPUTADO FEDERAL", "PL", "ELEITO POR QP"),
        ("SP", "4", "D", "DEPUTADO FEDERAL", "PL", "SUPLENTE"),
        ("SP", "5", "E", "DEPUTADO FEDERAL", "PL", "NÃO ELEITO"),
        ("SP", "1", "A", "DEPUTADO FEDERAL", "PT", "ELEITO"),  # linha duplicada do mesmo candidato
        ("SP", "9", "F", "SENADOR", "PT", "ELEITO"),  # outro cargo
    )
    assert tse.contar_eleitos(df, tse.CARGO_CAMARA) == {"PT": 2, "PL": 1}
    assert tse.contar_eleitos(df, tse.CARGO_SENADO) == {"PT": 1}


def test_candidatos_com_mesmo_sq_mas_identidades_distintas_nao_se_fundem():
    # `SQ_CANDIDATO` repetido nos arquivos antigos: a identidade é UF + número + nome (não está nas colunas lidas)
    df = linhas(
        ("SP", "1", "A", "DEPUTADO FEDERAL", "PT", "ELEITO"),
        ("RJ", "1", "A", "DEPUTADO FEDERAL", "PT", "ELEITO"),
    )
    assert tse.contar_eleitos(df, tse.CARGO_CAMARA) == {"PT": 2}


def test_bancada_senado_soma_duas_eleicoes_e_nao_publica_parcial(monkeypatch):
    eleitos = {2022: {"PT": 3}, 2018: {"PT": 5, "PL": 1}}
    monkeypatch.setattr(tse, "eleitos_por_partido", lambda ano, cargo, **_: eleitos.get(ano))
    assert tse.bancada_senado(2023) == {"PT": 8, "PL": 1}  # 2022 (1/3) + 2018 (2/3)
    assert tse.bancada_senado(1995) is None  # a eleição de 1990 não existe nos dados abertos


def test_comparar_bancadas_aponta_divergencias_e_outros():
    curadas = [
        {"partido": "PT", "cadeiras": 68},
        {"partido": "PL", "cadeiras": 99},
        {"partido": "Outros", "cadeiras": 10},
    ]
    res = comparar_bancadas(curadas, {"PT": 69, "PL": 99, "PSD": 5})
    assert res["conferido"] is False and res["total_eleitos_tse"] == 173
    assert {d["partido"]: (d["curado"], d["tse"]) for d in res["divergencias"]} == {"PT": (68, 69), "Outros": (10, 5)}
    assert comparar_bancadas([{"partido": "pt", "cadeiras": 1}], {"PT": 1})["conferido"] is True


def modelo():
    return {
        "lula-2023": {
            "camara": {"bancadas": [{"partido": "PT", "cadeiras": 513, "percentual": 100.0}]},
            "senado": {"bancadas": []},
        },
        "temer-2016": {"camara": {"bancadas": []}, "senado": {"bancadas": []}},
        "itamar-franco-1992": {"camara": {"bancadas": []}, "senado": {"bancadas": []}},
    }


def test_enriquecimento_marca_status_de_cada_casa():
    historico = modelo()
    r = enriquecer_com_tse(
        historico,
        bancada_camara=lambda leg: {"PT": 513},
        bancada_senado=lambda leg: {"PT": 80},  # 80 != 81: o recorte do TSE não fecha
    )
    assert r["lula-2023"]["camara"]["verificacao_tse"]["status"] == "conferido"
    assert r["lula-2023"]["senado"]["verificacao_tse"]["status"] == "total_inesperado"
    assert r["lula-2023"]["senado"]["bancadas"] == []  # total que não fecha não substitui nada
    assert r["itamar-franco-1992"]["camara"]["verificacao_tse"]["status"] == "nao_aplicavel"
    assert all(d["fonte_curadoria"] for d in r.values())
    assert historico == modelo()  # não altera o catálogo original


def test_mandato_sem_curadoria_recebe_bancada_do_tse_sem_classificar_base_ou_oposicao():
    r = enriquecer_com_tse(modelo(), lambda leg: {"PMDB": 300, "PT": 213}, lambda leg: None)
    camara = r["temer-2016"]["camara"]
    assert camara["verificacao_tse"]["status"] == "preenchido_pelo_tse"
    assert {b["partido"]: b["alinhamento"] for b in camara["bancadas"]} == {
        "PMDB": "NAO_CLASSIFICADO",
        "PT": "NAO_CLASSIFICADO",
    }
    assert "TSE" in camara["bancadas_origem"]
    assert r["temer-2016"]["senado"]["verificacao_tse"]["status"] == "indisponivel"


def test_falha_do_tse_nao_derruba_a_curadoria():
    def quebra(_leg):
        raise RuntimeError("sem rede")

    r = enriquecer_com_tse(modelo(), quebra, quebra)
    assert r["lula-2023"]["camara"]["bancadas"][0]["cadeiras"] == 513
    assert r["lula-2023"]["camara"]["verificacao_tse"]["status"] == "indisponivel"


def test_catalogo_real_tem_legislatura_para_todos_os_mandatos():
    from etl.extractors.composicao_extractor import LEGISLATURA_POR_MANDATO

    assert set(COMPOSICAO_CONGRESSO_HISTORICO) <= set(LEGISLATURA_POR_MANDATO)


def test_comparar_bancadas_ignora_espaco_e_caixa_da_sigla():
    res = comparar_bancadas([{"partido": "PCdoB", "cadeiras": 10}], {"PC DO B": 10})
    assert res["conferido"] is True and res["divergencias"] == []
