"""Cadastro do político lido de `core`: busca, resolução, cadastros duplicados e situação do mandato."""

from datetime import date

import pytest
from app.api.v1.politicians import _status_do_mandato
from app.models import CargoPoliticoEnum, PartyAffiliation
from app.models.enums import MotivoDesfiliacaoEnum, StatusMandatoEnum
from app.services import politico_service
from sqlalchemy import text

BASE = "/api/v1/politicians"


def _pessoa_so_do_historico(
    db, nome, camara_id=None, cargo="DEPUTADO_FEDERAL", inicio=date(2003, 2, 1), fim=date(2007, 1, 31)
):
    """Parlamentar que existe só em `core` (como os do histórico da Câmara), com um mandato encerrado."""
    pessoa = db.execute(text("INSERT INTO core.pessoa (nome_exibicao) VALUES (:n) RETURNING id"), {"n": nome}).scalar()
    if camara_id is not None:
        db.execute(
            text(
                "INSERT INTO core.pessoa_identificador (pessoa_id, fonte_id, tipo, valor) "
                "SELECT :p, id, 'CAMARA_ID', CAST(:v AS text) FROM etl.fonte WHERE codigo = 'CAMARA_PORTAL'"
            ),
            {"p": pessoa, "v": camara_id},
        )
    db.execute(
        text(
            "INSERT INTO core.mandato (pessoa_id, cargo_id, circunscricao_id, inicio, fim) VALUES "
            "(:p, (SELECT id FROM ref.cargo WHERE codigo = :c), "
            "(SELECT id FROM ref.circunscricao WHERE tipo = 'UF' AND uf = 'SP'), :i, :f)"
        ),
        {"p": pessoa, "c": cargo, "i": inicio, "f": fim},
    )
    return pessoa


def _nomes(client, **params):
    return [p["nome_eleitoral"] for p in client.get(BASE, params={"limit": 800, **params}).json()["politicos"]]


# ── situação do mandato ───────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "condicao, motivo, fim, esperado",
    [
        ("TITULAR", None, None, "TITULAR_ATIVO"),
        ("TITULAR", None, date(2999, 1, 1), "TITULAR_ATIVO"),
        ("SUPLENTE", None, None, "SUPLENTE_EM_EXERCICIO"),
        ("TITULAR", None, date(2020, 1, 1), "CONCLUIDO"),  # acabou sem motivo registrado
        ("SUPLENTE", None, date(2020, 1, 1), "CONCLUIDO"),
        ("TITULAR", "RENUNCIA", date(2020, 1, 1), "RENUNCIA"),
        ("TITULAR", "CASSACAO", date(2020, 1, 1), "CASSADO"),
        ("TITULAR", "FALECIMENTO", date(2020, 1, 1), "FALECIDO"),
        ("TITULAR", "IMPEACHMENT", date(2016, 8, 31), "IMPEACHMENT"),
        ("TITULAR", "CONCLUIDO", date(2020, 1, 1), "CONCLUIDO"),
    ],
)
def test_status_do_mandato_volta_ao_codigo_que_o_dossie_mostra(condicao, motivo, fim, esperado):
    assert _status_do_mandato(condicao, motivo, fim, date(2026, 10, 27)) == esperado


def test_dossie_mostra_renuncia_filiacao_com_fim_inclusivo_e_motivo(client, db, seed):
    seed.mandate_fulano.status = StatusMandatoEnum.RENUNCIA
    seed.mandate_fulano.end_date = date(2024, 12, 31)
    db.add(
        PartyAffiliation(
            politician_id=seed.fulano.id,
            party_id=seed.ptb.id,
            start_date=date(2015, 1, 1),
            end_date=date(2019, 12, 31),
            is_current=False,
            disaffiliation_reason=MotivoDesfiliacaoEnum.MUDANCA_VOLUNTARIA,
        )
    )
    db.commit()
    corpo = client.get(f"{BASE}/{seed.fulano.id}").json()
    assert corpo["trajetoria_mandatos"][0]["status"] == "RENUNCIA"
    antiga = corpo["filiacoes_partidarias"][-1]
    assert (antiga["data_filiacao"], antiga["data_desfiliacao"]) == (
        "2015-01-01",
        "2019-12-31",
    )  # o último dia, não o seguinte
    assert antiga["motivo_desfiliacao"] == "MUDANCA_VOLUNTARIA" and antiga["is_atual"] is False


# ── busca ─────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_lista_inclui_quem_so_existe_no_historico_e_nao_quem_nunca_teve_mandato(client, db, seed):
    _pessoa_so_do_historico(db, "Ex Deputado Antigo", camara_id=900001)
    db.execute(text("INSERT INTO core.pessoa (nome_exibicao) VALUES ('Autor Sem Mandato')"))
    db.commit()
    nomes = _nomes(client)
    assert "Ex Deputado Antigo" in nomes and "Fulano" in nomes
    assert "Autor Sem Mandato" not in nomes
    antigo = next(p for p in client.get(BASE, params={"search": "Ex Deputado"}).json()["politicos"])
    assert (antigo["cargo"], antigo["uf"], antigo["camara_id"]) == ("DEPUTADO_FEDERAL", "SP", 900001)
    assert antigo["partido_sigla"] == "S.PART."


def test_filtros_de_cargo_uf_e_busca_valem_para_o_historico(client, db, seed):
    _pessoa_so_do_historico(db, "Senador Antigo", cargo="SENADOR")
    db.commit()
    assert "Senador Antigo" in _nomes(client, office="SENADOR")
    assert "Senador Antigo" not in _nomes(client, office="DEPUTADO_FEDERAL")
    assert "Senador Antigo" in _nomes(client, uf="SP") and "Senador Antigo" not in _nomes(client, uf="RJ")
    assert _nomes(client, search="antigo") == ["Senador Antigo"]
    assert _nomes(client, search="%") == []  # curinga do usuário é texto


def test_total_vale_para_o_filtro_inteiro_mesmo_numa_pagina_alem_do_fim(client, seed):
    corpo = client.get(BASE, params={"limit": 2, "offset": 0}).json()
    total = corpo["total"]
    assert total >= 5 and len(corpo["politicos"]) == 2
    alem = client.get(BASE, params={"limit": 2, "offset": 10_000}).json()
    assert alem["politicos"] == [] and alem["total"] == total


def test_pagina_segue_a_ordem_do_nome_sem_repetir(client, seed):
    primeira = client.get(BASE, params={"limit": 3, "offset": 0}).json()["politicos"]
    segunda = client.get(BASE, params={"limit": 3, "offset": 3}).json()["politicos"]
    nomes = [p["nome_eleitoral"] for p in primeira + segunda]
    assert nomes == sorted(nomes) and len({p["id"] for p in primeira + segunda}) == 6


# ── cadastro público x cadastro do histórico (duplicata) ──────────────────────────────────────────────────────────


def _pessoa_id(db, uid):
    return db.execute(text("SELECT id FROM core.pessoa WHERE uid = :u"), {"u": uid}).scalar()


@pytest.fixture()
def duplicado(client, db, seed):
    """Fulano (cadastro público, camara_id 111) cujo identificador oficial ficou com um cadastro do histórico."""
    client.get(BASE)  # a ponte do legado projeta o cadastro público em `core`
    historico = _pessoa_so_do_historico(db, "Fulano de Tal (histórico)", inicio=date(1999, 2, 1), fim=date(2003, 1, 31))
    db.execute(
        text("UPDATE core.pessoa_identificador SET pessoa_id = :h WHERE tipo = 'CAMARA_ID' AND valor = '111'"),
        {"h": historico},
    )
    db.execute(
        text("UPDATE core.pessoa SET email = 'historico@exemplo.leg.br', biografia = 'Do histórico' WHERE id = :h"),
        {"h": historico},
    )
    db.commit()
    return historico


def test_a_sincronizacao_une_o_cadastro_do_historico_ao_publico_e_o_uid_sobrevive(client, db, seed, duplicado):
    client.get(BASE)  # a próxima sincronização do legado une os dois cadastros
    assert db.execute(text("SELECT count(*) FROM core.pessoa WHERE id = :h"), {"h": duplicado}).scalar() == 0
    publico = _pessoa_id(db, seed.fulano.id)
    assert (
        db.execute(
            text("SELECT pessoa_id FROM core.pessoa_identificador WHERE tipo = 'CAMARA_ID' AND valor = '111'")
        ).scalar()
        == publico
    )
    # o mandato do histórico foi para o cadastro público, junto com o do legado
    anos = (
        db.execute(
            text("SELECT extract(year FROM inicio)::int FROM core.mandato WHERE pessoa_id = :p ORDER BY 1"),
            {"p": publico},
        )
        .scalars()
        .all()
    )
    assert anos == [1999, 2007, 2023]  # o do histórico (1999) e os dois do legado
    pol = politico_service.resolver(db, str(seed.fulano.id))
    assert pol.camara_id == 111
    assert client.get(f"{BASE}/{seed.fulano.id}").json()["perfil"]["camara_id"] == 111


def test_unir_completa_so_o_que_esta_vazio_e_nao_troca_o_que_o_cadastro_publico_ja_tem(client, db, seed, duplicado):
    seed.fulano.email = "publico@exemplo.leg.br"  # o legado tem e-mail e não tem biografia
    db.commit()
    client.get(BASE)
    pol = politico_service.resolver(db, str(seed.fulano.id))
    assert pol.email == "publico@exemplo.leg.br" and pol.biography == "Do histórico"


def test_a_pessoa_aparece_uma_vez_so_na_lista_e_com_todos_os_mandatos(client, seed, duplicado):
    nomes = _nomes(client)
    assert nomes.count("Fulano") == 1 and "Fulano de Tal (histórico)" not in nomes
    trajetoria = client.get(f"{BASE}/{seed.fulano.id}").json()["trajetoria_mandatos"]
    assert sorted(m["ano_eleicao"] or 0 for m in trajetoria) != [] and len(trajetoria) >= 2


def test_resolver_pelo_identificador_oficial_chega_ao_cadastro_publico(client, db, seed, duplicado):
    client.get(BASE)
    assert politico_service.resolver(db, "111").id == seed.fulano.id


def test_o_uid_do_cadastro_apagado_deixa_de_existir(client, db, seed, duplicado):
    uid_historico = db.execute(text("SELECT uid FROM core.pessoa WHERE id = :i"), {"i": duplicado}).scalar()
    client.get(BASE)
    assert client.get(f"{BASE}/{uid_historico}").status_code == 404


def test_unificar_e_idempotente_e_nao_mexe_em_outro_politico_do_legado(client, db, seed, duplicado):
    client.get(BASE)
    assert db.execute(text("SELECT core.unificar_duplicadas()")).scalar() == 0  # nada a unir na segunda vez
    # o ID da Câmara de outro político do legado nunca leva à fusão com ele
    outro = _pessoa_id(db, seed.lula_fonte.id)
    antes = db.execute(text("SELECT count(*) FROM core.pessoa")).scalar()
    db.execute(text("SELECT core.unificar_pessoas(:a, :a)"), {"a": outro})  # mesma pessoa: nada acontece
    assert db.execute(text("SELECT count(*) FROM core.pessoa")).scalar() == antes


def test_colisao_descarta_a_linha_do_duplicado_e_move_o_resto(client, db, seed, duplicado):
    publico = _pessoa_id(db, seed.fulano.id)
    client.get(BASE)  # cria o que a ponte projeta para o cadastro público
    segundo = _pessoa_so_do_historico(db, "Fulano outro", inicio=date(1999, 2, 1), fim=date(2003, 1, 31))
    # nome que colide com um do cadastro público e mandato igual ao dele (mesmo cargo, eleição e número)
    nome = db.execute(
        text("SELECT tipo, nome FROM core.pessoa_nome WHERE pessoa_id = :p LIMIT 1"), {"p": publico}
    ).one()
    db.execute(
        text(
            "INSERT INTO core.pessoa_nome (pessoa_id, tipo, nome, fonte_id) SELECT :s, :t, :n, fonte_id FROM core.pessoa_nome WHERE pessoa_id = :p LIMIT 1"
        ),
        {"s": segundo, "t": nome.tipo, "n": nome.nome, "p": publico},
    )
    db.execute(text("SELECT core.unificar_pessoas(:m, :a)"), {"m": publico, "a": segundo})
    db.commit()
    assert db.execute(text("SELECT count(*) FROM core.pessoa WHERE id = :s"), {"s": segundo}).scalar() == 0
    assert (
        db.execute(
            text("SELECT count(*) FROM core.pessoa_nome WHERE pessoa_id = :p AND nome = :n"),
            {"p": publico, "n": nome.nome},
        ).scalar()
        == 1
    )


def test_nome_ambiguo_e_409_e_desconhecido_e_404(client, seed):
    assert client.get(f"{BASE}/maria-silva").status_code == 409
    assert client.get(f"{BASE}/ninguem-com-esse-nome").status_code == 404
    assert client.get(f"{BASE}/00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.get(f"{BASE}/999999").status_code == 404
    assert client.get(f"{BASE}/fulano").status_code == 200  # nome exato (eleitoral), sem diferenciar maiúsculas


def test_cargo_invalido_continua_422(client, seed):
    assert client.get(BASE, params={"office": "REI"}).status_code == 422
    assert CargoPoliticoEnum.PRESIDENTE.name in client.get(BASE, params={"office": "REI"}).json()["detail"]
