"""Composição do Congresso por mandato, IPLE e blocos de governo, lidos de `leg` (curadoria carregada pelo ETL)."""

import json
from datetime import date

import pytest
from app.services import composicao_service, iple_service
from app.services.party_productivity_service import get_party_bloc_alignments
from sqlalchemy import text

from .conftest import criar_mandato_presidencial

BASE = "/api/v1/analytics"
IPLE = "/api/v1/executivo/iple"

BANCADAS = [  # (sigla, cadeiras, alinhamento, cor, posição na escala ideológica)
    ("PL", 40, "OPOSICAO", "#1d4ed8", 8.5),
    ("PT", 30, "BASE_GOVERNO", "#ef4444", 2.5),
    ("MDB", 20, "INDEPENDENTE_CENTRO", "#15803d", 5.5),
    ("PSOL", 10, "BASE_GOVERNO", "#facc15", 1.5),
]


def _casa(db, codigo):
    return db.execute(text("SELECT id FROM ref.casa_legislativa WHERE codigo = :c"), {"c": codigo}).scalar()


def _composicao(db, mandato_id, codigo, total, bancadas, **meta):
    casa = _casa(db, codigo)
    db.execute(
        text(
            "INSERT INTO leg.composicao_mandato (mandato_id, casa_id, total_cadeiras, bancadas_origem, tse_status, "
            "tse_total_eleitos, tse_divergencias, observacao, fonte_texto) VALUES "
            "(:m, :c, :t, :o, :s, :te, CAST(:dv AS jsonb), :ob, 'Curadoria de teste')"
        ),
        {
            "m": mandato_id,
            "c": casa,
            "t": total,
            "o": meta.get("origem", "CURADORIA"),
            "s": meta.get("status"),
            "te": meta.get("total_tse"),
            "dv": json.dumps(meta["divergencias"]) if meta.get("divergencias") else None,
            "ob": meta.get("observacao"),
        },
    )
    for ordem, (sigla, cadeiras, alinhamento, cor, tse) in enumerate(bancadas):
        db.execute(
            text(
                "INSERT INTO leg.bancada_mandato (mandato_id, casa_id, partido_sigla, cadeiras, cadeiras_tse, "
                "alinhamento, cor_hex, ordem) VALUES (:m, :c, :s, :ca, :ct, :al, :cor, :o)"
            ),
            {
                "m": mandato_id,
                "c": casa,
                "s": sigla,
                "ca": cadeiras,
                "ct": tse,
                "al": alinhamento,
                "cor": cor,
                "o": ordem,
            },
        )


def _producao(db, mandato_id, oposicao_camara=99):
    db.execute(
        text(
            "INSERT INTO leg.producao_executivo (mandato_id, proposicoes_executivo, proposicoes_aprovadas, "
            "vetos_apreciados, vetos_mantidos, vetos_pendentes, oposicao_cadeiras_camara, total_cadeiras_camara, "
            "fonte_texto) VALUES (:m, 100, 80, 10, 7, 1, :o, 100, 'Curadoria de teste')"
        ),
        {"m": mandato_id, "o": oposicao_camara},
    )


def _escala(db):
    fonte = db.execute(text("SELECT id FROM etl.fonte WHERE codigo = 'CURADORIA'")).scalar()
    for sigla, _c, _a, _cor, _t in BANCADAS:
        partido = db.execute(
            text("INSERT INTO core.partido (sigla, nome) VALUES (:s, :s) RETURNING id"), {"s": sigla}
        ).scalar()
        valor = {"PL": 8.5, "PT": 2.5, "MDB": 5.5, "PSOL": 1.5}[sigla]
        db.execute(
            text(
                "INSERT INTO core.partido_posicao_ideologica (partido_id, escala, valor, fonte_id) "
                "VALUES (:p, 'ESCALA_1_10', :v, :f)"
            ),
            {"p": partido, "f": fonte, "v": valor},
        )


@pytest.fixture()
def mandato(db):
    mid = criar_mandato_presidencial(db, "Presidente", date(2023, 1, 1), None, "lula-2023", "Lula 3")
    sem_tse = [(s, c, a, cor, None) for s, c, a, cor, _ in BANCADAS]
    _composicao(db, mid, "CAMARA_DOS_DEPUTADOS", 100, sem_tse)
    _producao(db, mid)
    _escala(db)
    db.commit()
    return mid


def test_governabilidade_e_calculada_das_bancadas(client, mandato):
    cam = client.get(f"{BASE}/congress-composition", params={"mandate_id": "lula-2023"}).json()["camara"]
    gov = cam["governabilidade"]
    assert (gov["base_aliada_cadeiras"], gov["centro_cadeiras"], gov["oposicao_cadeiras"]) == (40, 20, 40)
    assert (gov["base_aliada_pct"], gov["oposicao_pct"]) == (40.0, 40.0)
    assert gov["maioria_simples_atingida"] is False and gov["maioria_pec_atingida"] is False  # PEC pede 60
    assert [b["partido"] for b in cam["bancadas"]] == ["PL", "PT", "MDB", "PSOL"]  # ordem da curadoria
    assert cam["bancadas"][0] == {
        "partido": "PL",
        "cadeiras": 40,
        "percentual": 40.0,
        "alinhamento": "OPOSICAO",
        "cor_hex": "#1d4ed8",
    }


def test_maioria_simples_e_de_pec_dependem_da_base(db):
    base = [{"alinhamento": "BASE_GOVERNO", "cadeiras": 61}, {"alinhamento": "OPOSICAO", "cadeiras": 39}]
    gov = composicao_service.governabilidade(100, base)
    assert gov["maioria_simples_atingida"] is True and gov["maioria_pec_atingida"] is True
    limite = composicao_service.governabilidade(
        100, [{"alinhamento": "BASE_GOVERNO", "cadeiras": 50}, {"alinhamento": "OPOSICAO", "cadeiras": 50}]
    )
    assert limite["maioria_simples_atingida"] is False  # exatamente a metade não é maioria


def test_bancadas_sem_classificacao_nao_inventam_governabilidade(client, db):
    mid = criar_mandato_presidencial(db, "Antigo", date(2007, 1, 1), date(2011, 1, 1), "antigo-2007")
    _composicao(
        db,
        mid,
        "CAMARA_DOS_DEPUTADOS",
        100,
        [("PT", 60, "NAO_CLASSIFICADO", None, 60), ("PL", 40, "NAO_CLASSIFICADO", None, 40)],
        origem="TSE",
        status="preenchido_pelo_tse",
        observacao="Composição partidária não curada para este mandato.",
    )
    db.commit()
    corpo = client.get(f"{BASE}/congress-composition", params={"mandate_id": "antigo-2007"}).json()
    gov = corpo["camara"]["governabilidade"]
    assert all(gov[k] is None for k in ("base_aliada_cadeiras", "oposicao_cadeiras", "maioria_simples_atingida"))
    assert corpo["dados_incompletos"] is True and "não curada" in corpo["observacao"]
    assert corpo["camara"]["bancadas_origem"].startswith("TSE")
    assert corpo["camara"]["bancadas"][0]["cor_hex"] == "#64748b"  # cor padrão, nunca vazia


def test_conferencia_com_o_tse_expoe_eleitos_e_divergencias(client, db):
    mid = criar_mandato_presidencial(db, "P", date(2023, 1, 1), None, "p-2023")
    _composicao(
        db,
        mid,
        "CAMARA_DOS_DEPUTADOS",
        100,
        [("PL", 40, "OPOSICAO", "#111111", 38), ("PT", 60, "BASE_GOVERNO", "#222222", 62)],
        status="divergente",
        total_tse=100,
        divergencias=[{"partido": "PL", "curado": 40, "tse": 38}],
    )
    db.commit()
    cam = client.get(f"{BASE}/congress-composition", params={"mandate_id": "p-2023"}).json()["camara"]
    assert [(b["partido"], b["cadeiras"]) for b in cam["bancadas_eleitas_tse"]] == [("PT", 62), ("PL", 38)]
    assert cam["verificacao_tse"]["status"] == "divergente"
    assert cam["verificacao_tse"]["divergencias"] == [{"partido": "PL", "curado": 40, "tse": 38}]


def test_presidentes_das_casas_seguem_a_ordem_do_mandato(client, db, mandato):
    casa = _casa(db, "CAMARA_DOS_DEPUTADOS")
    for ordem, (nome, rotulo) in enumerate((("Primeiro", "2023 - 2025"), ("Segundo", "2025 - Presente"))):
        pid = db.execute(
            text("INSERT INTO leg.presidencia_casa (casa_id, nome, partido_sigla) VALUES (:c, :n, 'PP') RETURNING id"),
            {"c": casa, "n": nome},
        ).scalar()
        db.execute(
            text(
                "INSERT INTO leg.presidencia_casa_mandato (mandato_id, presidencia_id, ordem, rotulo_periodo) "
                "VALUES (:m, :p, :o, :r)"
            ),
            {"m": mandato, "p": pid, "o": ordem, "r": rotulo},
        )
    db.commit()
    cam = client.get(f"{BASE}/congress-composition", params={"mandate_id": "lula-2023"}).json()["camara"]
    assert [(p["nome"], p["periodo"]) for p in cam["presidentes"]] == [
        ("Primeiro", "2023 - 2025"),
        ("Segundo", "2025 - Presente"),
    ]


def test_mandato_desconhecido_ou_invalido_e_404(client, mandato):
    assert client.get(f"{BASE}/congress-composition", params={"mandate_id": "inventado"}).status_code == 404
    assert client.get(f"{BASE}/congress-composition", params={"mandate_id": "../x"}).status_code == 404


def test_sem_composicao_carregada_e_404(client):
    assert client.get(f"{BASE}/congress-composition").status_code == 404


def test_composicao_nao_grava_em_disco(client, mandato, data_dir):
    client.get(f"{BASE}/congress-composition", params={"mandate_id": "lula-2023"})
    assert list(data_dir.iterdir()) == []


def test_iple_calcula_ts_tmv_e_variaveis_contextuais(client, mandato):
    dados = client.get(IPLE, params={"mandate_id": "lula-2023"}).json()
    base = dados["indicadores_base"]
    assert (base["taxa_sucesso_ts"], base["taxa_manutencao_vetos_tmv"], base["iple_score"]) == (0.8, 0.7, 0.75)
    ctx = dados["variaveis_contextuais"]
    assert (ctx["oposicao_cadeiras"], ctx["total_cadeiras"], ctx["tamanho_oposicao_x1"]) == (40, 100, 0.4)
    assert ctx["fragmentacao_nep_x2"] == 3.33  # 1 / (0,4² + 0,3² + 0,2² + 0,1²)
    assert ctx["polarizacao_ipp_x3"] == 7.89  # variância ponderada na escala 1 a 10 da tabela de posições
    crisp = dados["calibragem_crisp_set"]
    assert crisp["oposicao_x1"]["crisp_val"] == 1 and crisp["fragmentacao_x2"]["crisp_val"] == 0
    assert dados["periodo"] == "2023 - Presente" and dados["presidente"] == "Presidente (Lula 3)"


def test_iple_sem_bancadas_fica_indisponivel_e_nao_vira_zero(client, db):
    mid = criar_mandato_presidencial(db, "Antigo", date(2007, 1, 1), date(2011, 1, 1), "antigo-2007")
    _producao(db, mid, oposicao_camara=40)
    db.commit()
    ctx = client.get(IPLE, params={"mandate_id": "antigo-2007"}).json()["variaveis_contextuais"]
    # Câmara: a oposição curada (40 de 100) segue valendo; sem bancadas não há NEP nem polarização
    assert (ctx["oposicao_cadeiras"], ctx["tamanho_oposicao_x1"]) == (40, 0.4)
    assert ctx["fragmentacao_nep_x2"] is None and ctx["polarizacao_ipp_x3"] is None
    crisp = client.get(IPLE, params={"mandate_id": "antigo-2007"}).json()["calibragem_crisp_set"]
    assert crisp["fragmentacao_x2"] == {
        "score": None,
        "corte": 8.45,
        "crisp_val": None,
        "classificacao": "Indisponível",
    }


def test_iple_do_senado_sem_classificacao_nao_usa_a_oposicao_da_camara(db, mandato):
    senado = iple_service.get_mandate_iple(db, "lula-2023", "SENADO")
    assert senado["variaveis_contextuais"]["tamanho_oposicao_x1"] is None
    assert senado["variaveis_contextuais"]["total_cadeiras"] is None


def test_iple_lista_todos_os_mandatos_com_producao(client, db, mandato):
    outro = criar_mandato_presidencial(db, "Antigo", date(2019, 1, 1), date(2023, 1, 1), "antigo-2019")
    _producao(db, outro)
    db.commit()
    ids = [m["mandato_id"] for m in client.get(IPLE).json()]
    assert ids == ["antigo-2019", "lula-2023"]
    assert client.get(IPLE, params={"mandate_id": "desconhecido-9999"}).status_code == 404


def test_iple_chave_de_sigla_ignora_espaco_e_acento():
    assert iple_service.chave_sigla("PC do B") == iple_service.chave_sigla("PCdoB") == "PCDOB"
    assert iple_service.chave_sigla("UNIÃO") == "UNIAO"


def test_blocos_de_governo_vem_da_camara_do_mandato_mais_recente(db, mandato):
    assert get_party_bloc_alignments(db) == {
        "PL": "OPOSICAO",
        "PT": "BASE_GOVERNO",
        "MDB": "INDEPENDENTE_CENTRO",
        "PSOL": "BASE_GOVERNO",
    }
