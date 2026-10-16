"""Cargas da composição do Congresso, da produção do Executivo, da PNAD e do subsídio parlamentar."""

import csv
import json
from datetime import date

import pytest
from sqlalchemy import text

from etl.pipelines import composicao_loader as comp
from etl.pipelines import economia_loader as eco
from etl.pipelines import pnad_loader as pnad

# ── funções puras ─────────────────────────────────────────────────────────────────────────────────────────────────


def test_bancadas_unem_a_lista_exibida_e_a_do_tse_e_guardam_a_ordem():
    casa = {
        "bancadas": [
            {"partido": "PL", "cadeiras": 40, "alinhamento": "OPOSICAO", "cor_hex": "#111111"},
            {"partido": "PT", "cadeiras": 40, "alinhamento": "INVENTADO"},
        ],
        "bancadas_eleitas_tse": [
            {"partido": "PL", "cadeiras": 38},
            {"partido": "NOVO", "cadeiras": 5},
            {"partido": "", "cadeiras": 1},
        ],
    }
    linhas = {b["sigla"]: b for b in comp.bancadas_da_casa(casa)}
    assert linhas["PL"]["cadeiras"] == 40 and linhas["PL"]["cadeiras_tse"] == 38
    assert linhas["PT"]["alinhamento"] == "NAO_CLASSIFICADO"  # alinhamento desconhecido não é aceito
    assert linhas["NOVO"]["cadeiras"] is None and linhas["NOVO"]["alinhamento"] is None  # só consta no TSE
    assert [linhas[s]["ordem"] for s in ("PL", "PT", "NOVO")] == [0, 1, 2]


def test_inteiro_e_texto_tratam_vazios():
    assert (
        comp.inteiro("7") == 7 and comp.inteiro("") is None and comp.inteiro(None) is None and comp.inteiro("x") is None
    )
    assert comp.texto("  a ") == "a" and comp.texto("   ") is None and comp.texto(None) is None


def test_pnad_percentual_exige_oito_faixas_numericas():
    assert pnad.percentual_valido([1] * 8) == [1.0] * 8
    for ruim in (None, [1] * 7, "texto", [1, 2, 3, 4, 5, 6, 7, "x"]):
        assert pnad.percentual_valido(ruim) is None


def test_pnad_ano_so_vale_com_salario_e_as_duas_distribuicoes():
    bom = {
        "salario_minimo_brl": 1000,
        "nacional": {c: {"percentual": [1] * 8} for c in ("domicilios_renda_total", "pessoas_renda_domiciliar")},
    }
    assert pnad.ano_valido(bom)
    assert not pnad.ano_valido({**bom, "salario_minimo_brl": 0})
    assert not pnad.ano_valido({"salario_minimo_brl": 1000, "nacional": {}})
    assert not pnad.ano_valido(None)


def test_subsidio_exige_norma_valor_e_ano_dentro_da_janela():
    linhas = [
        {"ano": "1994", "valor": "3000", "norma": "DL 8/1994"},
        {"ano": "1995", "valor": "8000", "norma": "DL 7/1995"},
        {"ano": "1996", "valor": "8000", "norma": ""},
        {"ano": "1997", "valor": "", "norma": "DL 7/1995"},
    ]
    observacoes, notas = eco.observacoes_subsidio(linhas)
    assert observacoes == [("SUBSIDIO_PARLAMENTAR", date(1995, 1, 1), None, 8000.0, False)]
    assert notas == {("SUBSIDIO_PARLAMENTAR", date(1995, 1, 1)): "DL 7/1995"}


# ── composição, produção e presidentes das Casas ──────────────────────────────────────────────────────────────────


def _limpar(engine):
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE core.pessoa, core.mandato, core.mandato_presidencial, leg.composicao_mandato, "
                "leg.presidencia_casa, leg.producao_executivo RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture()
def mandato(pg_engine):
    _limpar(pg_engine)
    with pg_engine.begin() as conn:
        pessoa = conn.execute(text("INSERT INTO core.pessoa (nome_exibicao) VALUES ('Fulano') RETURNING id")).scalar()
        mid = conn.execute(
            text(
                "INSERT INTO core.mandato (pessoa_id, cargo_id, circunscricao_id, inicio) VALUES (:p, "
                "(SELECT id FROM ref.cargo WHERE codigo = 'PRESIDENTE'), "
                "(SELECT id FROM ref.circunscricao WHERE tipo = 'BR'), DATE '2023-01-01') RETURNING id"
            ),
            {"p": pessoa},
        ).scalar()
        conn.execute(text("INSERT INTO core.mandato_presidencial (mandato_id, slug) VALUES (:m, 'x-2023')"), {"m": mid})
    yield mid
    _limpar(pg_engine)


def _arquivos(pasta, composicao, producao):
    (pasta / "composicao_congresso.json").write_text(json.dumps(composicao), encoding="utf-8")
    with open(pasta / "producao_executivo.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "mandato_slug",
                "proposicoes_executivo",
                "proposicoes_aprovadas",
                "vetos_apreciados",
                "vetos_mantidos",
                "vetos_pendentes",
                "oposicao_cadeiras_camara",
                "total_cadeiras_camara",
                "fonte",
            ]
        )
        for linha in producao:
            w.writerow(linha)


COMPOSICAO = {
    "x-2023": {
        "fonte_curadoria": "Curadoria",
        "observacao": "Obs",
        "camara": {
            "total_cadeiras": 513,
            "presidentes": [
                {
                    "nome": "Primeiro",
                    "partido": "PP",
                    "uf": "AL",
                    "periodo": "2023 - 2025",
                    "foto_url": "http://x/1.jpg",
                },
                {"nome": "Segundo", "partido": "PP", "uf": "AL", "periodo": "2025 - Presente"},
            ],
            "bancadas": [{"partido": "PL", "cadeiras": 99, "alinhamento": "OPOSICAO", "cor_hex": "#1d4ed8"}],
            "bancadas_eleitas_tse": [{"partido": "PL", "cadeiras": 98}],
            "verificacao_tse": {
                "status": "divergente",
                "ano_legislatura": 2023,
                "divergencias": [{"partido": "PL", "curado": 99, "tse": 98}],
            },
        },
        "senado": {"total_cadeiras": 81, "presidentes": [], "bancadas": []},
    }
}
PRODUCAO = [["x-2023", 10, 8, 4, 3, 1, 121, 513, "Curadoria"]]


def _contagens(engine):
    with engine.connect() as conn:
        return {
            t: conn.execute(text(f"SELECT count(*) FROM leg.{t}")).scalar()
            for t in (
                "composicao_mandato",
                "bancada_mandato",
                "presidencia_casa",
                "presidencia_casa_mandato",
                "producao_executivo",
            )
        }


def test_composicao_grava_tudo_e_e_idempotente(pg_engine, mandato, tmp_path):
    _arquivos(tmp_path, COMPOSICAO, PRODUCAO)
    resumo = comp.carregar(pg_engine, tmp_path)
    assert resumo == {"mandatos": 1, "bancadas": 1, "presidentes": 2, "producao": 1}
    antes = _contagens(pg_engine)
    assert antes == {
        "composicao_mandato": 2,
        "bancada_mandato": 1,
        "presidencia_casa": 2,
        "presidencia_casa_mandato": 2,
        "producao_executivo": 1,
    }
    comp.carregar(pg_engine, tmp_path)
    assert _contagens(pg_engine) == antes
    with pg_engine.connect() as conn:
        linha = conn.execute(text("SELECT cadeiras, cadeiras_tse, alinhamento, cor_hex FROM leg.bancada_mandato")).one()
        meta = conn.execute(
            text(
                "SELECT tse_status, tse_divergencias, observacao FROM leg.composicao_mandato WHERE total_cadeiras = 513"
            )
        ).one()
    assert tuple(linha) == (99, 98, "OPOSICAO", "#1d4ed8")
    assert meta[0] == "divergente" and meta[1] == [{"partido": "PL", "curado": 99, "tse": 98}] and meta[2] == "Obs"


def test_recarga_substitui_as_bancadas_do_mandato(pg_engine, mandato, tmp_path):
    _arquivos(tmp_path, COMPOSICAO, PRODUCAO)
    comp.carregar(pg_engine, tmp_path)
    COMPOSICAO["x-2023"]["camara"]["bancadas"] = [{"partido": "PT", "cadeiras": 70, "alinhamento": "BASE_GOVERNO"}]
    COMPOSICAO["x-2023"]["camara"]["bancadas_eleitas_tse"] = []
    try:
        _arquivos(tmp_path, COMPOSICAO, PRODUCAO)
        comp.carregar(pg_engine, tmp_path)
    finally:
        COMPOSICAO["x-2023"]["camara"]["bancadas"] = [
            {"partido": "PL", "cadeiras": 99, "alinhamento": "OPOSICAO", "cor_hex": "#1d4ed8"}
        ]
        COMPOSICAO["x-2023"]["camara"]["bancadas_eleitas_tse"] = [{"partido": "PL", "cadeiras": 98}]
    with pg_engine.connect() as conn:
        siglas = conn.execute(text("SELECT partido_sigla FROM leg.bancada_mandato")).scalars().all()
    assert siglas == ["PT"]


def test_mandato_do_arquivo_sem_identificador_falha_e_nao_grava(pg_engine, mandato, tmp_path):
    _arquivos(tmp_path, {**COMPOSICAO, "y-1999": COMPOSICAO["x-2023"]}, PRODUCAO)
    with pytest.raises(RuntimeError, match="y-1999"):
        comp.carregar(pg_engine, tmp_path)
    assert _contagens(pg_engine)["composicao_mandato"] == 0


def test_arquivos_ausentes_sao_erro(pg_engine, mandato, tmp_path):
    with pytest.raises(FileNotFoundError):
        comp.carregar(pg_engine, tmp_path)


# ── PNAD ──────────────────────────────────────────────────────────────────────────────────────────────────────────


def _dist(escala=1.0):
    return {"total_estimado": 100, "percentual": [round(12.5 * escala, 2)] * 8, "media_nominal_brl": 3000.0}


def _ano_pnad(salario=1412.0):
    nacional = {
        c: _dist()
        for c in (
            "domicilios_renda_total",
            "pessoas_renda_domiciliar",
            "pessoas_renda_per_capita",
            "ocupados_renda_trabalho",
        )
    }
    return {
        "ano": 2024,
        "visita": 5,
        "salario_minimo_brl": salario,
        "nacional": nacional,
        "uf": {"SP": {"domicilios_renda_total": _dist()}},
    }


def _limpar_pnad(engine):
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE eco.pnad_ano, eco.pnad_metodologia CASCADE"))


def test_pnad_grava_nacional_e_uf_e_e_idempotente(pg_engine, tmp_path):
    _limpar_pnad(pg_engine)
    (tmp_path / "pnad_faixas_salario_minimo.json").write_text(
        json.dumps({"anos": {"2024": _ano_pnad(), "2023": {"salario_minimo_brl": 0}}, "metodologia": {"a": "texto"}})
    )
    assert pnad.carregar(pg_engine, tmp_path) == {"anos": 1, "pulados": 1, "distribuicoes": 5}
    pnad.carregar(pg_engine, tmp_path)
    with pg_engine.connect() as conn:
        n = conn.execute(text("SELECT count(*) FROM eco.pnad_distribuicao")).scalar()
        uf = conn.execute(text("SELECT escopo FROM eco.pnad_distribuicao WHERE escopo <> 'BR'")).scalar()
        met = conn.execute(text("SELECT texto FROM eco.pnad_metodologia WHERE chave = 'a'")).scalar()
    assert (n, uf, met) == (5, "SP", "texto")
    _limpar_pnad(pg_engine)


def test_pnad_sem_ano_valido_nao_apaga_a_base(pg_engine, tmp_path):
    _limpar_pnad(pg_engine)
    (tmp_path / "pnad_faixas_salario_minimo.json").write_text(json.dumps({"anos": {"2024": _ano_pnad()}}))
    pnad.carregar(pg_engine, tmp_path)
    (tmp_path / "pnad_faixas_salario_minimo.json").write_text(json.dumps({"anos": {"2024": {"salario_minimo_brl": 0}}}))
    assert pnad.carregar(pg_engine, tmp_path)["anos"] == 0
    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM eco.pnad_ano")).scalar() == 1
    _limpar_pnad(pg_engine)


def test_pnad_arquivo_ausente_e_erro(pg_engine, tmp_path):
    with pytest.raises(FileNotFoundError):
        pnad.carregar(pg_engine, tmp_path)
