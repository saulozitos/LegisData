"""Composição do Congresso por mandato, IPLE e blocos de governo, lidos de `leg` (curadoria carregada pelo ETL)."""

import json
from datetime import date

import pytest
from app.core.errors import ErroDeDominio
from app.services import bancadas_service, iple_service
from app.services.party_productivity_service import get_party_bloc_alignments
from app.services.periodos import rotulo_do_periodo
from sqlalchemy import text

from .conftest import criar_mandato_presidencial

BASE = "/api/v1/analytics"
IPLE = "/api/v1/executivo/iple"

BANCADAS = [  # (sigla, cadeiras, alinhamento, cor)
    ("PL", 40, "OPOSICAO", "#1d4ed8"),
    ("PT", 30, "BASE_GOVERNO", "#ef4444"),
    ("MDB", 20, "INDEPENDENTE_CENTRO", "#15803d"),
    ("PSOL", 10, "BASE_GOVERNO", "#facc15"),
]
ESCALA = {"PL": 8.5, "PT": 2.5, "MDB": 5.5, "PSOL": 1.5}  # posição na escala ideológica de 1 a 10


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
    for ordem, (sigla, cadeiras, alinhamento, cor, tse) in enumerate(bancadas):  # cadeiras_tse é o 5º campo
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


def _escala(db, siglas=None):
    """Cadastra os partidos de teste e, para `siglas` (padrão: todos), a posição na escala ideológica."""
    fonte = db.execute(text("SELECT id FROM etl.fonte WHERE codigo = 'CURADORIA'")).scalar()
    for sigla in ESCALA:
        partido = db.execute(
            text("INSERT INTO core.partido (sigla, nome) VALUES (:s, :s) RETURNING id"), {"s": sigla}
        ).scalar()
        if siglas is not None and sigla not in siglas:
            continue
        valor = ESCALA[sigla]
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
    sem_tse = [(s, c, a, cor, None) for s, c, a, cor in BANCADAS]
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


def test_maioria_simples_e_de_pec_dependem_da_base():
    base = [{"alinhamento": "BASE_GOVERNO", "cadeiras": 61}, {"alinhamento": "OPOSICAO", "cadeiras": 39}]
    gov = bancadas_service.governabilidade(100, base)
    assert gov["maioria_simples_atingida"] is True and gov["maioria_pec_atingida"] is True
    limite = bancadas_service.governabilidade(
        100, [{"alinhamento": "BASE_GOVERNO", "cadeiras": 50}, {"alinhamento": "OPOSICAO", "cadeiras": 50}]
    )
    assert limite["maioria_simples_atingida"] is False  # exatamente a metade não é maioria


def test_classificacao_parcial_so_afirma_a_maioria_quando_ja_decidida():
    def gov(base, oposicao, sem_classificar):
        bancadas = [
            {"alinhamento": "BASE_GOVERNO", "cadeiras": base},
            {"alinhamento": "OPOSICAO", "cadeiras": oposicao},
            {"alinhamento": "NAO_CLASSIFICADO", "cadeiras": sem_classificar},
        ]
        return bancadas_service.governabilidade(100, bancadas)

    ja_decidida = gov(55, 5, 40)  # a base já tem 55 de 100: maioria simples, mas a PEC (60) depende dos 40 restantes
    assert ja_decidida["maioria_simples_atingida"] is True and ja_decidida["maioria_pec_atingida"] is None
    assert ja_decidida["nao_classificadas_cadeiras"] == 40
    inalcancavel = gov(10, 70, 20)  # nem com as 20 restantes a base chega a 51
    assert inalcancavel["maioria_simples_atingida"] is False and inalcancavel["maioria_pec_atingida"] is False
    indefinida = gov(40, 20, 40)  # com as 40 restantes chegaria a 80
    assert indefinida["maioria_simples_atingida"] is None and indefinida["maioria_pec_atingida"] is None


def test_senado_aparece_na_composicao_com_total_e_governabilidade_proprios(client, db, mandato):
    _composicao(
        db,
        mandato,
        "SENADO_FEDERAL",
        81,
        [("PT", 30, "BASE_GOVERNO", "#ef4444", None), ("PL", 20, "OPOSICAO", "#1d4ed8", None)],
    )
    db.commit()
    corpo = client.get(f"{BASE}/congress-composition", params={"mandate_id": "lula-2023"}).json()
    assert corpo["senado"]["total_cadeiras"] == 81
    assert [(b["partido"], b["cadeiras"]) for b in corpo["senado"]["bancadas"]] == [("PT", 30), ("PL", 20)]
    gov = corpo["senado"]["governabilidade"]
    assert (gov["base_aliada_cadeiras"], gov["oposicao_cadeiras"], gov["nao_classificadas_cadeiras"]) == (30, 20, 31)
    assert (
        gov["maioria_simples_atingida"] is None
    )  # a base (30) ainda pode chegar a 41 com as 31 cadeiras sem classificar
    assert corpo["senado"]["governabilidade"]["iple"]["variaveis_contextuais"]["total_cadeiras"] == 81
    assert corpo["camara"]["total_cadeiras"] == 100  # a Câmara não é afetada


def test_composicao_sem_o_senado_nao_inventa_o_bloco(client, mandato):
    corpo = client.get(f"{BASE}/congress-composition", params={"mandate_id": "lula-2023"}).json()
    assert corpo["camara"]["total_cadeiras"] == 100
    assert corpo.get("senado") is None


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


def test_iple_do_senado_sem_composicao_carregada_nao_usa_a_oposicao_da_camara(db, mandato):
    senado = iple_service.get_mandate_iple(db, "lula-2023", "senado")
    assert senado["variaveis_contextuais"]["tamanho_oposicao_x1"] is None
    assert senado["variaveis_contextuais"]["total_cadeiras"] is None


def test_iple_sem_posicao_ideologica_dos_partidos_deixa_o_ipp_indisponivel(client, db):
    mid = criar_mandato_presidencial(db, "P", date(2023, 1, 1), None, "p-2023")
    _composicao(db, mid, "CAMARA_DOS_DEPUTADOS", 100, [(s, c, a, cor, None) for s, c, a, cor in BANCADAS])
    _producao(db, mid)
    _escala(db, siglas=())  # partidos cadastrados, nenhum com posição na escala
    db.commit()
    dados = client.get(IPLE, params={"mandate_id": "p-2023"}).json()
    ctx = dados["variaveis_contextuais"]
    assert ctx["polarizacao_ipp_x3"] is None and ctx["cobertura_ipp_pct"] == 0.0
    assert dados["calibragem_crisp_set"]["polarizacao_x3"]["classificacao"] == "Indisponível"
    assert ctx["fragmentacao_nep_x2"] == 3.33  # o NEP não depende da escala


def test_iple_com_escala_parcial_calcula_o_ipp_so_dos_partidos_conhecidos_e_informa_a_cobertura(client, db):
    mid = criar_mandato_presidencial(db, "P", date(2023, 1, 1), None, "p-2023")
    _composicao(db, mid, "CAMARA_DOS_DEPUTADOS", 100, [(s, c, a, cor, None) for s, c, a, cor in BANCADAS])
    _producao(db, mid)
    _escala(db, siglas=("PL", "PT"))  # 70 das 100 cadeiras (PL 40 + PT 30) têm posição conhecida
    db.commit()
    ctx = client.get(IPLE, params={"mandate_id": "p-2023"}).json()["variaveis_contextuais"]
    assert ctx["cobertura_ipp_pct"] == 70.0
    esperado = round(0.4 / 0.7 * 0.3 / 0.7 * (8.5 - 2.5) ** 2, 2)  # variância de dois pontos ponderados
    assert ctx["polarizacao_ipp_x3"] == esperado


def test_iple_com_casa_invalida_e_422(db, mandato):
    with pytest.raises(ErroDeDominio) as erro:
        iple_service.get_mandate_iple(db, "lula-2023", "congresso")
    assert erro.value.status_code == 422


def test_periodo_do_mandato_que_termina_no_meio_do_ano_inclui_o_ano_do_fim(client, db):
    dilma = criar_mandato_presidencial(db, "Dilma", date(2015, 1, 1), date(2016, 8, 31), "dilma-2015", "Dilma 2")
    temer = criar_mandato_presidencial(db, "Temer", date(2016, 8, 31), date(2019, 1, 1), "temer-2016")
    for mid in (dilma, temer):
        _producao(db, mid)
        _composicao(db, mid, "CAMARA_DOS_DEPUTADOS", 100, [(s, c, a, cor, None) for s, c, a, cor in BANCADAS])
    db.commit()
    assert client.get(IPLE, params={"mandate_id": "dilma-2015"}).json()["periodo"] == "2015 - 2016"
    assert client.get(IPLE, params={"mandate_id": "temer-2016"}).json()["periodo"] == "2016 - 2018"
    comp = client.get(f"{BASE}/congress-composition", params={"mandate_id": "dilma-2015"}).json()
    assert comp["periodo"] == "2015 - 2016"


def test_rotulo_do_periodo():
    assert rotulo_do_periodo(date(1995, 1, 1), date(1999, 1, 1)) == "1995 - 1998"
    assert rotulo_do_periodo(date(2015, 1, 1), date(2016, 8, 31)) == "2015 - 2016"
    assert rotulo_do_periodo(date(2023, 1, 1), None) == "2023 - Presente"


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


def test_blocos_ignoram_mandato_recente_sem_classificacao(db, mandato):
    recente = criar_mandato_presidencial(db, "Recente", date(2027, 1, 1), None, "recente-2027")
    _composicao(db, recente, "CAMARA_DOS_DEPUTADOS", 100, [("PT", 100, "NAO_CLASSIFICADO", None, 100)])
    db.commit()
    assert get_party_bloc_alignments(db)["PL"] == "OPOSICAO"  # segue valendo o último mandato classificado


def test_mandato_em_curso_usa_as_proposicoes_reais_quando_superam_a_curadoria(db, mandato):
    for i in range(30):  # anteriores ao mandato (a base cobre desde 1995): não podem entrar na contagem
        db.execute(
            text(
                "INSERT INTO leg.proposicao (tipo_codigo, numero, ano, titulo, ementa, data_apresentacao, status_codigo, "
                "iniciativa_executivo) VALUES ('PL', :n, 2010, 'PL', 'Dispõe sobre algo', DATE '2010-01-01', "
                "'APROVADA_E_SANCIONADA', true)"
            ),
            {"n": 1000 + i},
        )
    for i in range(150):  # a curadoria diz 100 proposições (80 aprovadas)
        db.execute(
            text(
                "INSERT INTO leg.proposicao (tipo_codigo, numero, ano, titulo, ementa, data_apresentacao, status_codigo, "
                "iniciativa_executivo) VALUES ('PL', :n, 2024, 'PL', 'Dispõe sobre algo', DATE '2024-01-01', "
                ":st, true)"
            ),
            {"n": i + 1, "st": "APROVADA_E_SANCIONADA" if i < 120 else "EM_TRAMITACAO"},
        )
    db.execute(
        text(
            "INSERT INTO leg.proposicao (tipo_codigo, numero, ano, titulo, ementa, data_apresentacao, status_codigo, "
            "iniciativa_executivo) VALUES ('PL', 999, 2024, 'PL', 'Institui o Dia Nacional do Teste', "
            "DATE '2024-01-01', 'APROVADA_E_SANCIONADA', true)"
        )
    )
    db.commit()
    base = iple_service.get_mandate_iple(db, "lula-2023")["indicadores_base"]
    assert (base["proposicoes_executivo_total"], base["proposicoes_executivo_aprovadas"]) == (
        150,
        120,
    )  # simbólica fora


def _query_que_falha_no_banco(db, monkeypatch):
    """
    `db.query(Proposicao)` passa a executar SQL inválido de verdade (tabela inexistente), como uma tabela perdida.
    O patch depende de o serviço usar `db.query(Proposicao)`; se isso mudar, o teste de controle abaixo falha e avisa.
    """
    original = db.query

    def falha(*args, **kwargs):
        if args and getattr(args[0], "__name__", "") == "Proposicao":
            db.execute(text("SELECT 1 FROM leg.tabela_que_nao_existe"))
        return original(*args, **kwargs)

    monkeypatch.setattr(db, "query", falha)


def test_falha_de_sql_ao_contar_proposicoes_mantem_a_curadoria_e_a_sessao_utilizavel(db, mandato, monkeypatch):
    _query_que_falha_no_banco(db, monkeypatch)
    dados = iple_service.get_mandate_iple(db, "lula-2023")
    assert dados["indicadores_base"]["proposicoes_executivo_total"] == 100  # curadoria
    assert dados["variaveis_contextuais"]["total_cadeiras"] == 100  # as consultas seguintes na mesma sessão funcionaram
    assert db.execute(text("SELECT 1")).scalar() == 1


def test_sem_o_savepoint_a_mesma_falha_abortaria_a_transacao(db, mandato, monkeypatch):
    """Controle do teste acima: prova que ele é sensível ao `begin_nested` (sem savepoint a sessão fica inutilizável)."""
    from contextlib import nullcontext

    from sqlalchemy.exc import DBAPIError

    _query_que_falha_no_banco(db, monkeypatch)
    monkeypatch.setattr(db, "begin_nested", nullcontext)
    with pytest.raises(
        DBAPIError
    ):  # a falha do SQL é capturada, mas a consulta seguinte já encontra a transação abortada
        iple_service.get_mandate_iple(db, "lula-2023")
    db.rollback()


def test_classificacao_parcial_nao_vira_piso_da_oposicao(client, db):
    mid = criar_mandato_presidencial(db, "P", date(2023, 1, 1), None, "p-2023")
    parcial = [
        ("PL", 40, "OPOSICAO", "#1d4ed8", None),
        ("PT", 30, "BASE_GOVERNO", "#ef4444", None),
        ("MDB", 20, "NAO_CLASSIFICADO", "#15803d", None),
        ("PSOL", 10, "NAO_CLASSIFICADO", "#facc15", None),
    ]
    _composicao(db, mid, "CAMARA_DOS_DEPUTADOS", 100, parcial)
    _composicao(db, mid, "SENADO_FEDERAL", 100, parcial)
    _producao(db, mid, oposicao_camara=45)  # oposição curada da Câmara (total 100)
    _escala(db)
    db.commit()
    camara = client.get(IPLE, params={"mandate_id": "p-2023"}).json()["variaveis_contextuais"]
    assert (camara["oposicao_cadeiras"], camara["tamanho_oposicao_x1"]) == (45, 0.45)  # curadoria, não o piso de 40
    senado = iple_service.get_mandate_iple(db, "p-2023", "senado")["variaveis_contextuais"]
    assert senado["oposicao_cadeiras"] is None and senado["tamanho_oposicao_x1"] is None  # sem reserva: indisponível
    corpo = client.get(f"{BASE}/congress-composition", params={"mandate_id": "p-2023"}).json()
    assert corpo["dados_incompletos"] is True
    assert corpo["camara"]["governabilidade"]["nao_classificadas_cadeiras"] == 30


def _proposicoes_executivo(db, quantas, aprovadas, data, primeiro_numero):
    for i in range(quantas):
        db.execute(
            text(
                "INSERT INTO leg.proposicao (tipo_codigo, numero, ano, titulo, ementa, data_apresentacao, status_codigo, "
                "iniciativa_executivo) VALUES ('PL', :n, 2024, 'PL', 'Dispõe sobre algo', :d, :st, true)"
            ),
            {"n": primeiro_numero + i, "d": data, "st": "APROVADA_E_SANCIONADA" if i < aprovadas else "EM_TRAMITACAO"},
        )


def test_contagem_real_menor_que_a_curadoria_nao_a_reduz(db, mandato):
    _proposicoes_executivo(db, 10, 5, date(2024, 1, 1), 1)  # curadoria: 100 proposições, 80 aprovadas
    db.commit()
    base = iple_service.get_mandate_iple(db, "lula-2023")["indicadores_base"]
    assert (base["proposicoes_executivo_total"], base["proposicoes_executivo_aprovadas"]) == (100, 80)


def test_proposicao_apresentada_no_dia_do_inicio_do_mandato_entra_na_contagem(db, mandato):
    _proposicoes_executivo(db, 120, 90, date(2023, 1, 1), 1)  # exatamente no início do mandato (2023-01-01)
    _proposicoes_executivo(db, 50, 50, date(2022, 12, 31), 500)  # um dia antes: fora
    db.commit()
    base = iple_service.get_mandate_iple(db, "lula-2023")["indicadores_base"]
    assert (base["proposicoes_executivo_total"], base["proposicoes_executivo_aprovadas"]) == (120, 90)
