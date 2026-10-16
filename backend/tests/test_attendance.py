"""Ranking de ausências (parlamentares e partidos) lido de leg.presenca."""

from app.services import attendance_service
from sqlalchemy import text

BASE = "/api/v1/attendance"
PESSOA_BASE = "/api/v1/politicians"


def _pessoa(db, politico):
    return db.execute(text("SELECT id FROM core.pessoa WHERE uid = :u"), {"u": politico.id}).scalar()


def _registrar(db, pessoa_id, linhas, casa="CAMARA_DOS_DEPUTADOS"):
    casa_id = db.execute(text("SELECT id FROM ref.casa_legislativa WHERE codigo = :c"), {"c": casa}).scalar()
    for dia, tipo in linhas:
        db.execute(
            text(
                "INSERT INTO leg.presenca (pessoa_id, casa_id, data_sessao, tipo_codigo) VALUES (:p, :c, :d, :t) "
                "ON CONFLICT DO NOTHING"
            ),
            {"p": pessoa_id, "c": casa_id, "d": dia, "t": tipo},
        )
    db.commit()


def _preparar(client, db, seed):
    client.get(f"{PESSOA_BASE}/{seed.fulano.id}")  # a ponte do conftest cria as pessoas no schema novo
    fulano, beltrano = _pessoa(db, seed.fulano), _pessoa(db, seed.beltrano)
    dias = [f"2024-03-{d:02d}" for d in range(1, 11)]
    _registrar(db, fulano, [(d, "PRESENTE") for d in dias[:5]] + [(d, "AUSENCIA_NAO_JUSTIFICADA") for d in dias[5:]])
    _registrar(db, beltrano, [(d, "PRESENTE") for d in dias[:9]] + [(dias[9], "AUSENCIA_JUSTIFICADA")])
    # antes de 2003 a Câmara só tem presença: fica fora de qualquer contagem de falta
    _registrar(db, fulano, [("1999-05-04", "PRESENTE")])


def test_ranking_orders_by_absences_and_separates_types(client, db, seed):
    _preparar(client, db, seed)
    itens = client.get(f"{BASE}/ranking/politicians", params={"limit": 5}).json()["itens"]
    assert itens[0]["nome_eleitoral"] == "Fulano"
    assert (itens[0]["faltas"], itens[0]["faltas_nao_justificadas"], itens[0]["dias_registrados"]) == (5, 5, 10)
    assert itens[0]["taxa_ausencia_pct"] == 50.0
    beltrano = next(i for i in itens if i["nome_eleitoral"] == "Beltrano")
    assert (beltrano["faltas"], beltrano["faltas_justificadas"]) == (1, 1)


def test_ranking_filters_by_year_and_house(client, db, seed):
    _preparar(client, db, seed)
    assert client.get(f"{BASE}/ranking/politicians", params={"ano_inicio": 2025}).json()["itens"] == []
    assert client.get(f"{BASE}/ranking/politicians", params={"casa": "SENADO"}).json()["itens"] == []
    # taxa e baixa produção exigem amostra mínima de dias: com 10 dias a lista fica vazia, sem erro
    for criterio in ("taxa", "baixa_producao"):
        resposta = client.get(f"{BASE}/ranking/politicians", params={"ordenar": criterio}).json()
        assert resposta["criterio"] == criterio and resposta["itens"] == []


def test_ranking_validates_parameters(client, seed):
    assert client.get(f"{BASE}/ranking/politicians", params={"casa": "XYZ"}).status_code == 422
    assert client.get(f"{BASE}/ranking/politicians", params={"ordenar": "sorte"}).status_code == 422
    assert client.get(f"{BASE}/ranking/politicians", params={"ano_inicio": 2024, "ano_fim": 2020}).status_code == 422
    assert client.get(f"{BASE}/ranking/parties", params={"casa": "XYZ"}).status_code == 422


def test_party_ranking_and_coverage(client, db, seed):
    _preparar(client, db, seed)
    resp = client.get(f"{BASE}/ranking/parties")
    assert resp.status_code == 200 and "aviso" in resp.json()
    # poucos dias de teste ficam abaixo do mínimo por partido: a lista vem vazia, sem erro
    assert resp.json()["itens"] == []
    cobertura = client.get(f"{BASE}/coverage").json()
    anos = {c["ano"] for c in cobertura}
    assert {1999, 2024} <= anos


def test_party_resolution_uses_voted_party_then_nearest_presence(client, db, seed):
    _preparar(client, db, seed)
    fulano = _pessoa(db, seed.fulano)
    partido = db.execute(text("SELECT id FROM core.partido WHERE sigla = 'PT' LIMIT 1")).scalar()
    casa = db.execute(text("SELECT id FROM ref.casa_legislativa WHERE codigo = 'SENADO_FEDERAL'")).scalar()
    db.execute(
        text(
            "INSERT INTO leg.presenca (pessoa_id, casa_id, data_sessao, tipo_codigo, partido_id) "
            "VALUES (:p, :c, '2010-03-01', 'PRESENTE', :pt)"
        ),
        {"p": fulano, "c": casa, "pt": partido},
    )
    db.execute(
        text(
            "INSERT INTO leg.presenca (pessoa_id, casa_id, data_sessao, tipo_codigo) "
            "VALUES (:p, :c, '2010-03-09', 'AUSENCIA_NAO_JUSTIFICADA')"
        ),
        {"p": fulano, "c": casa},
    )
    db.commit()

    resultado = db.execute(text("SELECT etl.resolver_partido_presenca()")).scalar()
    assert resultado["presenca_proxima"] >= 1
    linhas = dict(
        db.execute(
            text(
                "SELECT data_sessao::text, partido_origem FROM leg.presenca "
                "WHERE pessoa_id = :p AND casa_id = :c AND partido_id = :pt"
            ),
            {"p": fulano, "c": casa, "pt": partido},
        ).all()
    )
    assert linhas == {"2010-03-01": "VOTACAO", "2010-03-09": "PRESENCA_PROXIMA"}


def test_dossier_opens_for_parliamentarian_that_exists_only_in_core(client, db):
    """Ex-parlamentar criado pela carga de presença (sem registro legado) abre o Raio-X com os dados do schema novo."""
    pessoa_id = db.execute(
        text("INSERT INTO core.pessoa (nome_exibicao) VALUES ('Ex Deputado Teste') RETURNING id")
    ).scalar()
    uid = db.execute(text("SELECT uid FROM core.pessoa WHERE id = :i"), {"i": pessoa_id}).scalar()
    _registrar(db, pessoa_id, [("2005-03-01", "PRESENTE"), ("2005-03-02", "AUSENCIA_INFERIDA")])

    resp = client.get(f"{PESSOA_BASE}/{uid}")
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["perfil"]["nome_eleitoral"] == "Ex Deputado Teste"
    assert corpo["assiduidade"]["total_sessoes"] == 2 and corpo["assiduidade"]["faltas_inferidas"] == 1
    assert client.get(f"{PESSOA_BASE}/00000000-0000-0000-0000-000000000000").status_code == 404


def _nova_pessoa(db, nome):
    return db.execute(text("INSERT INTO core.pessoa (nome_exibicao) VALUES (:n) RETURNING id"), {"n": nome}).scalar()


def _partido(db, sigla="PT"):
    return db.execute(text("SELECT id FROM core.partido WHERE sigla = :s LIMIT 1"), {"s": sigla}).scalar()


def test_ranking_orders_by_rate_unjustified_and_low_production(client, db, seed, monkeypatch):
    monkeypatch.setattr(attendance_service, "MIN_DIAS_PARA_TAXA", 5)
    _preparar(client, db, seed)
    ordem = lambda criterio: [  # noqa: E731
        i["nome_eleitoral"]
        for i in client.get(f"{BASE}/ranking/politicians", params={"ordenar": criterio}).json()["itens"]
    ]
    assert ordem("taxa")[:2] == ["Fulano", "Beltrano"]  # 50% contra 10%
    assert ordem("nao_justificadas")[:2] == ["Fulano", "Beltrano"]  # 5 contra 0
    itens = client.get(f"{BASE}/ranking/politicians", params={"ordenar": "baixa_producao"}).json()["itens"]
    fulano = next(i for i in itens if i["nome_eleitoral"] == "Fulano")
    # índice = taxa de ausência atenuada pelos pontos IALP: 50% / (100 + pontos)
    assert fulano["indice_baixa_producao"] == round(50.0 / (100 + fulano["pontos_ialp"]), 2)
    assert itens[0]["indice_baixa_producao"] >= itens[1]["indice_baixa_producao"]


def test_taxa_exige_vinte_dias_registrados(client, db):
    com_19, com_20 = _nova_pessoa(db, "Dezenove Dias"), _nova_pessoa(db, "Vinte Dias")
    dias = [f"2024-04-{d:02d}" for d in range(1, 21)]
    _registrar(db, com_19, [(d, "AUSENCIA_NAO_JUSTIFICADA") for d in dias[:19]])
    _registrar(db, com_20, [(d, "AUSENCIA_NAO_JUSTIFICADA") for d in dias])
    itens = client.get(f"{BASE}/ranking/politicians", params={"ordenar": "taxa"}).json()["itens"]
    assert [i["nome_eleitoral"] for i in itens] == ["Vinte Dias"]


def test_unknown_categories_are_null_not_zero(client, db):
    camara_atual, camara_2005, senador = (
        _nova_pessoa(db, "Dep 2024"),
        _nova_pessoa(db, "Dep 2005"),
        _nova_pessoa(db, "Sen"),
    )
    _registrar(db, camara_atual, [("2024-03-01", "PRESENTE"), ("2024-03-02", "AUSENCIA_JUSTIFICADA")])
    _registrar(db, camara_2005, [("2005-03-01", "PRESENTE"), ("2005-03-02", "AUSENCIA_INFERIDA")])
    _registrar(
        db, senador, [("2010-03-01", "PRESENTE"), ("2010-03-02", "AUSENCIA_NAO_JUSTIFICADA")], casa="SENADO_FEDERAL"
    )
    itens = {
        i["nome_eleitoral"]: i for i in client.get(f"{BASE}/ranking/politicians", params={"limit": 50}).json()["itens"]
    }

    atual = itens["Dep 2024"]  # Câmara desde 2020: a fonte informa justificativa e não há falta inferida
    assert (atual["faltas_justificadas"], atual["faltas_nao_justificadas"], atual["faltas_inferidas"]) == (1, 0, None)
    antigo = itens["Dep 2005"]  # Câmara 2003-2019: a falta é inferida e a justificativa é desconhecida
    assert (antigo["faltas_justificadas"], antigo["faltas_nao_justificadas"], antigo["faltas_inferidas"]) == (
        None,
        None,
        1,
    )
    assert antigo["faltas"] == 1
    sen = itens["Sen"]  # Senado: a falta vem da votação, sem inferência
    assert (sen["faltas_justificadas"], sen["faltas_nao_justificadas"], sen["faltas_inferidas"]) == (0, 1, None)


def test_known_absence_starts_on_february_3_2003_in_the_house_only(client, db):
    pessoa, senador = _nova_pessoa(db, "Fronteira"), _nova_pessoa(db, "Senador Antigo")
    _registrar(
        db, pessoa, [("2003-02-02", "PRESENTE"), ("2003-02-03", "PRESENTE"), ("2003-02-04", "AUSENCIA_INFERIDA")]
    )
    _registrar(db, senador, [("2001-01-10", "PRESENTE")], casa="SENADO_FEDERAL")
    itens = {
        i["nome_eleitoral"]: i for i in client.get(f"{BASE}/ranking/politicians", params={"limit": 50}).json()["itens"]
    }
    assert itens["Fronteira"]["dias_registrados"] == 2  # 2003-02-02 fica de fora
    assert itens["Senador Antigo"]["dias_registrados"] == 1  # o Senado conta desde 1995


def test_party_ranking_with_data_and_pending_party_counts(client, db, seed, monkeypatch):
    monkeypatch.setattr(attendance_service, "MIN_DIAS_PARTIDO", 1)
    client.get(f"{PESSOA_BASE}/{seed.fulano.id}")  # a ponte do conftest cria os partidos no schema novo
    com_partido, sem_partido, aproximado = (
        _nova_pessoa(db, "Com Partido"),
        _nova_pessoa(db, "Sem Partido"),
        _nova_pessoa(db, "Partido Aproximado"),
    )
    pt = _partido(db)
    dias = [f"2024-03-{d:02d}" for d in range(1, 11)]
    _registrar(
        db, com_partido, [(d, "PRESENTE") for d in dias[:5]] + [(d, "AUSENCIA_NAO_JUSTIFICADA") for d in dias[5:]]
    )
    _registrar(db, sem_partido, [(d, "PRESENTE") for d in dias[:3]])
    _registrar(db, aproximado, [(dias[0], "AUSENCIA_JUSTIFICADA")])
    db.execute(
        text("UPDATE leg.presenca SET partido_id = :pt, partido_origem = 'VOTACAO' WHERE pessoa_id = :p"),
        {"pt": pt, "p": com_partido},
    )
    db.execute(
        text("UPDATE leg.presenca SET partido_id = :pt, partido_origem = 'PRESENCA_PROXIMA' WHERE pessoa_id = :p"),
        {"pt": pt, "p": aproximado},
    )
    db.commit()
    resp = client.get(f"{BASE}/ranking/parties").json()
    pt_item = next(i for i in resp["itens"] if i["sigla"] == "PT")
    assert pt_item["parlamentares"] == 2  # quem votou no partido e quem teve o partido aproximado
    assert pt_item["dias_registrados"] == 11 and pt_item["faltas"] == 6 and pt_item["faltas_justificadas"] == 1
    assert pt_item["taxa_ausencia_pct"] == round(6 / 11 * 100, 1)
    assert resp["dias_com_partido_aproximado"] == 1
    assert resp["dias_sem_partido_identificado"] == 3  # os dias de quem não tem partido nenhum ficam de fora
    assert resp["minimo_dias"] == 1


def test_party_counters_ignore_the_minimum_threshold(client, db):
    """Com todos os partidos abaixo do mínimo a lista vem vazia, mas os dias sem partido continuam informados."""
    pessoa = _nova_pessoa(db, "Sem Partido Algum")
    _registrar(db, pessoa, [(f"2024-03-{d:02d}", "PRESENTE") for d in range(1, 5)])
    resp = client.get(f"{BASE}/ranking/parties").json()
    assert resp["itens"] == []
    assert resp["dias_sem_partido_identificado"] == 4 and resp["minimo_dias"] == attendance_service.MIN_DIAS_PARTIDO


def test_coverage_counts_by_year_house_and_source(client, db, seed):
    _preparar(client, db, seed)
    linha = next(
        c for c in client.get(f"{BASE}/coverage").json() if c["ano"] == 2024 and c["casa"] == "CAMARA_DOS_DEPUTADOS"
    )
    assert (linha["registros"], linha["dias"], linha["parlamentares"], linha["faltas"]) == (20, 10, 2, 6)


def test_period_filters_the_ialp_points(client, db, seed):
    """Os pontos IALP do ranking acompanham o período pedido (sem ano inicial valem para toda a carreira)."""
    _preparar(client, db, seed)
    todos = client.get(f"{BASE}/ranking/politicians").json()["itens"]
    depois = client.get(f"{BASE}/ranking/politicians", params={"ano_inicio": 2024, "ano_fim": 2024}).json()["itens"]
    pontos_todos = next(i for i in todos if i["nome_eleitoral"] == "Fulano")["pontos_ialp"]
    pontos_2024 = next(i for i in depois if i["nome_eleitoral"] == "Fulano")["pontos_ialp"]
    assert pontos_todos > 0 and pontos_2024 < pontos_todos  # a proposição de 2023 sai do recorte de 2024


def _partidos_do_dia(db, pessoa_id, casa="CAMARA_DOS_DEPUTADOS"):
    return {
        d: (p, o)
        for d, p, o in db.execute(
            text(
                "SELECT data_sessao::text, partido_id, partido_origem FROM leg.presenca pr "
                "JOIN ref.casa_legislativa c ON c.id = pr.casa_id WHERE pessoa_id = :p AND c.codigo = :c"
            ),
            {"p": pessoa_id, "c": casa},
        )
    }


def test_party_resolution_uses_mandate_history_then_affiliation(client, db, seed):
    _preparar(client, db, seed)
    fulano = _pessoa(db, seed.fulano)
    pt, ptb = _partido(db, "PT"), _partido(db, "PTB")
    mandato = db.execute(
        text("SELECT id FROM core.mandato WHERE pessoa_id = :p ORDER BY inicio DESC LIMIT 1"), {"p": fulano}
    ).scalar()
    casa = db.execute(text("SELECT id FROM ref.casa_legislativa WHERE codigo = 'CAMARA_DOS_DEPUTADOS'")).scalar()
    db.execute(
        text(
            "INSERT INTO leg.presenca (pessoa_id, casa_id, data_sessao, tipo_codigo, mandato_id) VALUES (:p, :c, '2024-06-03', 'PRESENTE', :m)"
        ),
        {"p": fulano, "c": casa, "m": mandato},
    )
    db.execute(
        text(
            "INSERT INTO core.mandato_partido (mandato_id, partido_id, periodo) VALUES (:m, :pt, '[2024-06-01,2024-06-30]')"
        ),
        {"m": mandato, "pt": ptb},
    )
    db.commit()
    db.execute(text("SELECT etl.resolver_partido_presenca()"))
    db.commit()
    assert _partidos_do_dia(db, fulano)["2024-06-03"] == (ptb, "MANDATO")  # o histórico do mandato vale para o dia

    # sem mandato ligado à presença, a filiação vigente no dia é a fonte (a mais recente, se houver duas)
    filiado = _nova_pessoa(db, "Só Filiado")
    _registrar(db, filiado, [("2024-06-03", "PRESENTE")])
    db.execute(
        text("INSERT INTO core.filiacao (pessoa_id, partido_id, periodo) VALUES (:p, :pt, '[2020-01-01,2030-01-01)')"),
        {"p": filiado, "pt": pt},
    )
    db.commit()
    db.execute(text("SELECT etl.resolver_partido_presenca()"))
    db.commit()
    assert _partidos_do_dia(db, filiado)["2024-06-03"] == (pt, "FILIACAO")


def test_party_resolution_is_deterministic_prefers_same_house_and_is_idempotent(client, db, seed):
    client.get(f"{PESSOA_BASE}/{seed.fulano.id}")
    pessoa = _nova_pessoa(db, "Dois Partidos")
    pt, ptb = _partido(db, "PT"), _partido(db, "PTB")
    camara = db.execute(text("SELECT id FROM ref.casa_legislativa WHERE codigo = 'CAMARA_DOS_DEPUTADOS'")).scalar()
    senado = db.execute(text("SELECT id FROM ref.casa_legislativa WHERE codigo = 'SENADO_FEDERAL'")).scalar()
    inserir = "INSERT INTO leg.presenca (pessoa_id, casa_id, data_sessao, tipo_codigo, partido_id, partido_origem) VALUES (:p, :c, :d, 'PRESENTE', :pt, 'VOTACAO')"
    # equidistantes do dia sem partido (2024-06-10): PT na Câmara em 06-05 e PTB no Senado em 06-15
    db.execute(text(inserir), {"p": pessoa, "c": camara, "d": "2024-06-05", "pt": pt})
    db.execute(text(inserir), {"p": pessoa, "c": senado, "d": "2024-06-15", "pt": ptb})
    db.execute(
        text(
            "INSERT INTO leg.presenca (pessoa_id, casa_id, data_sessao, tipo_codigo) VALUES (:p, :c, '2024-06-10', 'PRESENTE')"
        ),
        {"p": pessoa, "c": camara},
    )
    db.commit()

    primeira = db.execute(text("SELECT etl.resolver_partido_presenca()")).scalar()
    db.commit()
    assert _partidos_do_dia(db, pessoa)["2024-06-10"] == (pt, "PRESENCA_PROXIMA")  # a mesma Casa vence o empate
    segunda = db.execute(text("SELECT etl.resolver_partido_presenca()")).scalar()
    assert primeira["presenca_proxima"] == 1 and segunda["presenca_proxima"] == 0  # nada muda na segunda execução
    assert _partidos_do_dia(db, pessoa)["2024-06-10"] == (pt, "PRESENCA_PROXIMA")


def _uid(db, pessoa_id):
    return db.execute(text("SELECT uid FROM core.pessoa WHERE id = :i"), {"i": pessoa_id}).scalar()


def test_dossier_attendance_marks_unknown_categories_as_null(client, db):
    antigo, atual = _nova_pessoa(db, "Dossie 2005"), _nova_pessoa(db, "Dossie 2024")
    _registrar(db, antigo, [("2005-03-01", "PRESENTE"), ("2005-03-02", "AUSENCIA_INFERIDA")])
    _registrar(db, atual, [("2024-03-01", "PRESENTE"), ("2024-03-02", "AUSENCIA_JUSTIFICADA")])

    a = client.get(f"{PESSOA_BASE}/{_uid(db, antigo)}").json()["assiduidade"]
    assert (a["faltas_justificadas"], a["faltas_nao_justificadas"], a["faltas_inferidas"]) == (None, None, 1)
    assert a["total_faltas"] == 1 and a["total_sessoes"] == 2

    b = client.get(f"{PESSOA_BASE}/{_uid(db, atual)}").json()["assiduidade"]
    assert (b["faltas_justificadas"], b["faltas_nao_justificadas"], b["faltas_inferidas"]) == (1, 0, None)
    assert b["total_faltas"] == 1
