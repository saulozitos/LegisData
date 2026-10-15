"""Ranking de ausências (parlamentares e partidos) lido de leg.presenca."""

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
