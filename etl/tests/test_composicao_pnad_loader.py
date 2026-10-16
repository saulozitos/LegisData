"""Cargas da composição do Congresso, da produção do Executivo, da PNAD e do subsídio parlamentar."""

import copy
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


def test_pnad_percentual_exige_oito_faixas_numericas_finitas():
    assert pnad.percentual_valido([1] * 8) == [1.0] * 8
    for ruim in (
        None,
        [1] * 7,
        "texto",
        [1, 2, 3, 4, 5, 6, 7, "x"],
        [1] * 7 + [float("nan")],
        [1] * 7 + [float("inf")],
    ):
        assert pnad.percentual_valido(ruim) is None


def _ano_basico(**mudancas):
    nacional = {c: {"percentual": [1] * 8} for c in ("domicilios_renda_total", "pessoas_renda_domiciliar")}
    return {"visita": 5, "salario_minimo_brl": 1000, "nacional": nacional, **mudancas}


def test_pnad_ano_so_vale_com_chave_visita_salario_e_as_duas_distribuicoes():
    assert pnad.ano_valido("2024", _ano_basico())
    assert not pnad.ano_valido("2024", _ano_basico(salario_minimo_brl=0))
    assert not pnad.ano_valido("2024", _ano_basico(salario_minimo_brl=-1))
    assert not pnad.ano_valido("2024", _ano_basico(salario_minimo_brl="abc"))
    assert not pnad.ano_valido("2024", _ano_basico(nacional={}))
    assert not pnad.ano_valido("2024", None)
    assert not pnad.ano_valido("1900", _ano_basico())  # antes da janela de 1995
    assert not pnad.ano_valido("abc", _ano_basico())
    assert not pnad.ano_valido("2024", _ano_basico(visita=None))  # visita não é presumida
    assert not pnad.ano_valido("2024", _ano_basico(visita=9))


def test_subsidio_exige_norma_valor_e_ano_dentro_da_janela():
    linhas = [
        {"ano": "1994", "valor": "3000", "norma": "DL 8/1994"},
        {"ano": "1995", "valor": "8000", "norma": "DL 7/1995"},
        {"ano": "1996", "valor": "8000", "norma": ""},
        {"ano": "1997", "valor": "", "norma": "DL 7/1995"},
    ]
    assert eco.observacoes_subsidio(linhas) == [
        eco.Observacao("SUBSIDIO_PARLAMENTAR", date(1995, 1, 1), None, 8000.0, False, "DL 7/1995")
    ]
    assert eco.observacoes_subsidio([{"ano": "1995", "valor": "0", "norma": "DL 7/1995"}]) == []  # zero não é subsídio


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
    nova = copy.deepcopy(COMPOSICAO)
    nova["x-2023"]["camara"]["bancadas"] = [{"partido": "PT", "cadeiras": 70, "alinhamento": "BASE_GOVERNO"}]
    nova["x-2023"]["camara"]["bancadas_eleitas_tse"] = []
    _arquivos(tmp_path, nova, PRODUCAO)
    comp.carregar(pg_engine, tmp_path)
    with pg_engine.connect() as conn:
        siglas = conn.execute(text("SELECT partido_sigla FROM leg.bancada_mandato")).scalars().all()
    assert siglas == ["PT"]


def test_casa_que_saiu_da_curadoria_ou_ficou_sem_total_sai_do_banco(pg_engine, mandato, tmp_path):
    _arquivos(tmp_path, COMPOSICAO, PRODUCAO)
    comp.carregar(pg_engine, tmp_path)
    assert _contagens(pg_engine)["composicao_mandato"] == 2
    nova = copy.deepcopy(COMPOSICAO)
    nova["x-2023"]["senado"]["total_cadeiras"] = 0  # Casa zerada na curadoria
    _arquivos(tmp_path, nova, PRODUCAO)
    comp.carregar(pg_engine, tmp_path)
    assert _contagens(pg_engine)["composicao_mandato"] == 1
    del nova["x-2023"]["camara"]  # a Câmara sai do arquivo
    _arquivos(tmp_path, nova, PRODUCAO)
    comp.carregar(pg_engine, tmp_path)
    contagens = _contagens(pg_engine)
    assert (contagens["composicao_mandato"], contagens["bancada_mandato"], contagens["presidencia_casa_mandato"]) == (
        0,
        0,
        0,
    )


def test_senado_com_bancadas_e_presidente_e_bancada_so_do_tse(pg_engine, mandato, tmp_path):
    composicao = copy.deepcopy(COMPOSICAO)
    composicao["x-2023"]["senado"] = {
        "total_cadeiras": 81,
        "bancadas_origem": "TSE — candidatos eleitos",
        "presidentes": [{"nome": "Primeiro", "partido": "PP", "uf": "AL", "periodo": "2023 - Presente"}],
        "bancadas": [],
        "bancadas_eleitas_tse": [{"partido": "PSD", "cadeiras": 15}, {"partido": "MDB", "cadeiras": 10}],
    }
    _arquivos(tmp_path, composicao, PRODUCAO)
    comp.carregar(pg_engine, tmp_path)
    with pg_engine.connect() as conn:
        senado = conn.execute(
            text(
                "SELECT b.partido_sigla, b.cadeiras, b.cadeiras_tse, b.alinhamento FROM leg.bancada_mandato b "
                "JOIN ref.casa_legislativa k ON k.id = b.casa_id WHERE k.codigo = 'SENADO_FEDERAL' ORDER BY b.ordem"
            )
        ).all()
        origem = conn.execute(
            text(
                "SELECT c.bancadas_origem FROM leg.composicao_mandato c JOIN ref.casa_legislativa k ON k.id = c.casa_id "
                "WHERE k.codigo = 'SENADO_FEDERAL'"
            )
        ).scalar()
        # o mesmo presidente nas duas Casas e em dois mandatos continua sendo uma única pessoa por Casa
        presidencias = conn.execute(text("SELECT count(*) FROM leg.presidencia_casa WHERE nome = 'Primeiro'")).scalar()
    assert [tuple(r) for r in senado] == [
        ("PSD", None, 15, None),
        ("MDB", None, 10, None),
    ]  # TSE puro: sem classificação
    assert origem == "TSE" and presidencias == 2  # um cadastro por Casa, reaproveitado entre mandatos


def test_mesmo_presidente_em_dois_mandatos_reaproveita_o_cadastro(pg_engine, mandato, tmp_path):
    with pg_engine.begin() as conn:
        mid = conn.execute(
            text(
                "INSERT INTO core.mandato (pessoa_id, cargo_id, circunscricao_id, inicio, numero_mandato) VALUES "
                "((SELECT pessoa_id FROM core.mandato WHERE id = :m), (SELECT id FROM ref.cargo WHERE codigo = 'PRESIDENTE'), "
                "(SELECT id FROM ref.circunscricao WHERE tipo = 'BR'), DATE '2027-01-01', 2) RETURNING id"
            ),
            {"m": mandato},
        ).scalar()
        conn.execute(text("INSERT INTO core.mandato_presidencial (mandato_id, slug) VALUES (:m, 'x-2027')"), {"m": mid})
    composicao = {**COMPOSICAO, "x-2027": copy.deepcopy(COMPOSICAO["x-2023"])}
    _arquivos(tmp_path, composicao, PRODUCAO)
    comp.carregar(pg_engine, tmp_path)
    contagens = _contagens(pg_engine)
    assert contagens["presidencia_casa"] == 2 and contagens["presidencia_casa_mandato"] == 4
    # o mandato que sai do arquivo perde a composição (a produção do Executivo segue o CSV, que não mudou)
    _arquivos(tmp_path, COMPOSICAO, PRODUCAO)
    comp.carregar(pg_engine, tmp_path)
    contagens = _contagens(pg_engine)
    assert contagens["composicao_mandato"] == 2 and contagens["presidencia_casa_mandato"] == 2
    assert contagens["producao_executivo"] == 1


def test_mandato_do_arquivo_sem_identificador_falha_e_nao_grava(pg_engine, mandato, tmp_path):
    _arquivos(tmp_path, {**COMPOSICAO, "y-1999": COMPOSICAO["x-2023"]}, PRODUCAO)
    with pytest.raises(RuntimeError, match="y-1999"):
        comp.carregar(pg_engine, tmp_path)
    assert _contagens(pg_engine)["composicao_mandato"] == 0


def test_arquivos_ausentes_sao_erro(pg_engine, mandato, tmp_path):
    with pytest.raises(FileNotFoundError):
        comp.carregar(pg_engine, tmp_path)


# ── PNAD ──────────────────────────────────────────────────────────────────────────────────────────────────────────


def _dist():
    return {"total_estimado": 100, "percentual": [12.5] * 8, "media_nominal_brl": 3000.0}


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


@pytest.fixture()
def pnad_limpo(pg_engine):
    """Tabelas da PNAD vazias antes e depois de cada teste, mesmo que a asserção falhe."""
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE eco.pnad_ano, eco.pnad_metodologia CASCADE"))
    yield pg_engine
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE eco.pnad_ano, eco.pnad_metodologia CASCADE"))


def test_pnad_grava_nacional_e_uf_e_e_idempotente(pnad_limpo, tmp_path):
    (tmp_path / "pnad_faixas_salario_minimo.json").write_text(
        json.dumps({"anos": {"2024": _ano_pnad(), "2023": {"salario_minimo_brl": 0}}, "metodologia": {"a": "texto"}})
    )
    assert pnad.carregar(pnad_limpo, tmp_path) == {"anos": 1, "pulados": 1, "distribuicoes": 5}
    pnad.carregar(pnad_limpo, tmp_path)
    with pnad_limpo.connect() as conn:
        n = conn.execute(text("SELECT count(*) FROM eco.pnad_distribuicao")).scalar()
        uf = conn.execute(text("SELECT escopo FROM eco.pnad_distribuicao WHERE escopo <> 'BR'")).scalar()
        met = conn.execute(text("SELECT texto FROM eco.pnad_metodologia WHERE chave = 'a'")).scalar()
        percentual = conn.execute(
            text("SELECT percentual FROM eco.pnad_distribuicao WHERE escopo = 'BR' LIMIT 1")
        ).scalar()
    assert (n, uf, met) == (5, "SP", "texto") and [float(p) for p in percentual] == [12.5] * 8


def test_pnad_ano_sem_visita_ou_com_nan_e_pulado_e_nao_aborta_os_demais(pnad_limpo, tmp_path):
    sem_visita = {k: v for k, v in _ano_pnad().items() if k != "visita"}
    com_nan = _ano_pnad()
    com_nan["nacional"]["domicilios_renda_total"]["percentual"] = [float("nan")] * 8
    (tmp_path / "pnad_faixas_salario_minimo.json").write_text(
        json.dumps({"anos": {"2022": sem_visita, "2023": com_nan, "2024": _ano_pnad()}})
    )
    assert pnad.carregar(pnad_limpo, tmp_path)["anos"] == 1
    with pnad_limpo.connect() as conn:
        assert conn.execute(text("SELECT array_agg(ano) FROM eco.pnad_ano")).scalar() == [2024]


def test_pnad_sem_ano_valido_nao_apaga_a_base(pnad_limpo, tmp_path):
    (tmp_path / "pnad_faixas_salario_minimo.json").write_text(json.dumps({"anos": {"2024": _ano_pnad()}}))
    pnad.carregar(pnad_limpo, tmp_path)
    (tmp_path / "pnad_faixas_salario_minimo.json").write_text(json.dumps({"anos": {"2024": {"salario_minimo_brl": 0}}}))
    assert pnad.carregar(pnad_limpo, tmp_path)["anos"] == 0
    with pnad_limpo.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM eco.pnad_ano")).scalar() == 1


def test_pnad_arquivo_ausente_e_erro(pg_engine, tmp_path):
    with pytest.raises(FileNotFoundError):
        pnad.carregar(pg_engine, tmp_path)


# ── curadoria real versionada ─────────────────────────────────────────────────────────────────────────────────────


def test_curadoria_real_carrega_nos_nove_mandatos_e_e_idempotente(pg_engine):
    """Os arquivos reais de `etl/data/processed` passam no loader (slug, totais, alinhamentos) e cobrem 1995 em diante."""
    from etl.config import PROCESSED_DATA_DIR

    composicao = json.loads((PROCESSED_DATA_DIR / "composicao_congresso.json").read_text(encoding="utf-8"))
    with open(PROCESSED_DATA_DIR / "producao_executivo.csv", newline="", encoding="utf-8") as fh:
        slugs_producao = [r["mandato_slug"] for r in csv.DictReader(fh)]
    assert set(composicao) == set(slugs_producao) and len(slugs_producao) == 9
    assert "fhc-1995" in composicao and not any(s.startswith("itamar") for s in composicao)
    _limpar(pg_engine)
    try:
        with pg_engine.begin() as conn:
            for slug in sorted(set(composicao) | set(slugs_producao)):
                pessoa = conn.execute(
                    text("INSERT INTO core.pessoa (nome_exibicao) VALUES (:n) RETURNING id"), {"n": slug}
                ).scalar()
                mid = conn.execute(
                    text(
                        "INSERT INTO core.mandato (pessoa_id, cargo_id, circunscricao_id, inicio) VALUES (:p, "
                        "(SELECT id FROM ref.cargo WHERE codigo = 'PRESIDENTE'), "
                        "(SELECT id FROM ref.circunscricao WHERE tipo = 'BR'), DATE '2000-01-01') RETURNING id"
                    ),
                    {"p": pessoa},
                ).scalar()
                conn.execute(
                    text("INSERT INTO core.mandato_presidencial (mandato_id, slug) VALUES (:m, :s)"),
                    {"m": mid, "s": slug},
                )
        primeira = comp.carregar(pg_engine)
        assert primeira["mandatos"] == 9 and primeira["producao"] == 9
        contagens = _contagens(pg_engine)
        assert contagens["composicao_mandato"] == 18 and contagens["producao_executivo"] == 9
        with pg_engine.connect() as conn:
            sem_cadeiras = conn.execute(
                text(
                    "SELECT count(*) FROM leg.composicao_mandato c WHERE NOT EXISTS "
                    "(SELECT 1 FROM leg.bancada_mandato b WHERE b.mandato_id = c.mandato_id AND b.casa_id = c.casa_id)"
                )
            ).scalar()
        assert sem_cadeiras == 0  # toda Casa carregada traz ao menos uma bancada
        comp.carregar(pg_engine)
        assert _contagens(pg_engine) == contagens
    finally:
        _limpar(pg_engine)
