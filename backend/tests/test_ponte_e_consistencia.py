"""Ponte do legado (migrações 0017 a 0022), pontuação única de autoria e consistência entre as telas."""

import uuid
from datetime import date, datetime, timezone

from app.models import AttendanceRecord, CasaLegislativaEnum, PoliticalParty
from app.models.legislative import (
    Proposition,
    PropositionAuthor,
    TipoAutoriaEnum,
    TipoProposicaoEnum,
    VotacaoProposicao,
)
from app.services.staging_merge import merge_staging
from sqlalchemy import text

BASE = "/api/v1"


def _ponte(db):
    merge_staging(db)
    db.commit()


def _pessoa(db, politico):
    return db.execute(text("SELECT id FROM core.pessoa WHERE uid = :u"), {"u": politico.id}).scalar()


def test_ponte_adota_partido_criado_pelo_etl_com_mesma_sigla(db):
    """Migração 0020: o partido já criado pelo ETL em lote com a mesma sigla não colide com o do legado."""
    uid_etl = uuid.uuid4()
    db.execute(
        text("INSERT INTO core.partido (uid, sigla, nome) VALUES (:u, 'PHS', 'Partido Humanista')"), {"u": uid_etl}
    )
    db.commit()
    legado = PoliticalParty(acronym="PHS", full_name="Partido Humanista da Solidariedade")
    db.add(legado)
    db.commit()

    _ponte(db)  # antes da 0020 isto falhava com partido_sigla_key

    linhas = db.execute(text("SELECT uid FROM core.partido WHERE sigla = 'PHS'")).all()
    assert [r[0] for r in linhas] == [legado.id]


def test_autoria_implicita_some_quando_o_legado_ganha_autor_principal_explicito(client, db, seed):
    """Migração 0021: a proposição não conta o autor duas vezes (implícita + explícita)."""
    _ponte(db)
    pessoa = _pessoa(db, seed.fulano)
    contar = text(
        "SELECT count(*) FROM leg.autoria a JOIN leg.proposicao p ON p.id = a.proposicao_id "
        "WHERE p.uid = :u AND a.pessoa_id = :p AND a.tipo_codigo = 'AUTOR_PRINCIPAL'"
    )
    assert db.execute(contar, {"u": seed.proposition.id, "p": pessoa}).scalar() == 1  # implícita (autorPoliticoId)

    db.add(
        PropositionAuthor(
            proposition_id=seed.proposition.id,
            politician_id=seed.fulano.id,
            author_name="Fulano",
            authorship_type=TipoAutoriaEnum.AUTOR_PRINCIPAL,
            order=1,
        )
    )
    db.commit()
    _ponte(db)
    assert db.execute(contar, {"u": seed.proposition.id, "p": pessoa}).scalar() == 1  # só a explícita


def test_ponte_mantem_o_partido_das_presencas_do_legado(client, db, seed):
    """Migração 0021: a ponte regrava a presença do legado e o partido do dia volta a ser resolvido."""
    mandato = seed.mandate_fulano
    db.add(
        AttendanceRecord(
            politician_id=seed.fulano.id,
            mandate_id=mandato.id,
            legislative_house=CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS,
            session_date=date(2024, 3, 5),
            attendance_status="PRESENTE",
        )
    )
    db.commit()
    for _ in range(2):  # a segunda execução também apaga e regrava as linhas do legado
        _ponte(db)
        linha = db.execute(
            text(
                "SELECT partido_id, partido_origem FROM leg.presenca WHERE pessoa_id = :p AND data_sessao = '2024-03-05'"
            ),
            {"p": _pessoa(db, seed.fulano)},
        ).one()
        assert linha[0] is not None and linha[1] in {"MANDATO", "FILIACAO"}


def test_visao_de_autoria_unica_prevalece_principal_sobre_relator_e_coautor(client, db, seed):
    _ponte(db)
    pessoa = _pessoa(db, seed.fulano)
    proposta = Proposition(
        proposition_type=TipoProposicaoEnum.PEC,
        number=7,
        year=2024,
        title="PEC 7/2024",
        summary="PEC com papéis repetidos",
        presentation_date=date(2024, 2, 1),
        external_camara_id=7007,
    )
    db.add(proposta)
    db.flush()
    for tipo, ordem in (
        (TipoAutoriaEnum.COAUTOR, 3),
        (TipoAutoriaEnum.RELATOR, 2),
        (TipoAutoriaEnum.AUTOR_PRINCIPAL, 1),
    ):
        db.add(
            PropositionAuthor(
                proposition_id=proposta.id,
                politician_id=seed.fulano.id,
                author_name="Fulano",
                authorship_type=tipo,
                order=ordem,
            )
        )
    db.commit()
    _ponte(db)

    bruto = db.execute(
        text(
            "SELECT count(*) FROM leg.vw_autoria_pontuada v JOIN leg.proposicao p ON p.id = v.proposicao_id "
            "WHERE p.uid = :u AND v.pessoa_id = :p"
        ),
        {"u": proposta.id, "p": pessoa},
    ).scalar()
    unica = db.execute(
        text(
            "SELECT tipo_autoria FROM leg.vw_autoria_pontuada_unica v JOIN leg.proposicao p ON p.id = v.proposicao_id "
            "WHERE p.uid = :u AND v.pessoa_id = :p"
        ),
        {"u": proposta.id, "p": pessoa},
    ).all()
    assert bruto == 3 and [r[0] for r in unica] == ["AUTOR_PRINCIPAL"]


def test_dossie_usa_papel_de_relator_e_os_mesmos_pontos_do_ranking(client, db, seed):
    proposta = Proposition(
        proposition_type=TipoProposicaoEnum.PEC,
        number=8,
        year=2024,
        title="PEC 8/2024",
        summary="PEC relatada",
        presentation_date=date(2024, 2, 2),
        external_camara_id=7008,
    )
    db.add(proposta)
    db.flush()
    for tipo, ordem in ((TipoAutoriaEnum.COAUTOR, 2), (TipoAutoriaEnum.RELATOR, 1)):
        db.add(
            PropositionAuthor(
                proposition_id=proposta.id,
                politician_id=seed.fulano.id,
                author_name="Fulano",
                authorship_type=tipo,
                order=ordem,
            )
        )
    db.commit()

    dossie = client.get(f"{BASE}/politicians/{seed.fulano.id}").json()
    item = next(m for m in dossie["materias_propostas"] if m["titulo"] == "PEC 8/2024")
    assert item["papel_autoria"] == "RELATOR"  # relator pesa mais que a assinatura de apoio de PEC (0,05)
    assert item["peso_participacao"] > 0.05

    ranking = client.get(f"{BASE}/legislative/ranking/authors", params={"limit": 50}).json()
    fulano = next(r for r in ranking if r["nome_eleitoral"] == "Fulano")
    assert dossie["indices_inteligencia"]["roi_cidadao"]["pontos_ialp"] == round(fulano["score_ialp"], 1)


def test_roi_pontos_usam_a_base_inteira_alem_da_lista_truncada(client, db, seed, monkeypatch):
    from app.api.v1 import politicians

    monkeypatch.setattr(politicians, "MAX_PROPOSITIONS_LISTED", 1)
    for i in range(3):
        proposta = Proposition(
            proposition_type=TipoProposicaoEnum.PL,
            number=900 + i,
            year=2024,
            title=f"PL {900 + i}/2024",
            summary="PL de teste",
            presentation_date=date(2024, 3, 1 + i),
            external_camara_id=8000 + i,
        )
        db.add(proposta)
        db.flush()
        db.add(
            PropositionAuthor(
                proposition_id=proposta.id,
                politician_id=seed.fulano.id,
                author_name="Fulano",
                authorship_type=TipoAutoriaEnum.AUTOR_PRINCIPAL,
                order=1,
            )
        )
    db.commit()
    dossie = client.get(f"{BASE}/politicians/{seed.fulano.id}").json()
    assert len(dossie["materias_propostas"]) == 1  # a lista está truncada em 1
    ranking = client.get(f"{BASE}/legislative/ranking/authors", params={"limit": 50}).json()
    fulano = next(r for r in ranking if r["nome_eleitoral"] == "Fulano")
    assert dossie["indices_inteligencia"]["roi_cidadao"]["pontos_ialp"] == round(fulano["score_ialp"], 1)


def test_link_antigo_de_sessao_ainda_resolve_pelo_legado(client, db, seed):
    """Quando a votação tem registro em `votacoes_proposicao`, o id público passa a ser o dele e o antigo ainda vale."""
    deliberacao = VotacaoProposicao(
        proposicao_id=seed.proposition.id,
        data_hora=datetime(2023, 5, 2, 15, 0, tzinfo=timezone.utc),  # a mesma sessão de mérito do seed
        local_deliberacao="Plenário da Câmara dos Deputados",
        tipo_deliberacao="NOMINAL",
        resumo_decisao="Aprovada",
    )
    db.add(deliberacao)
    db.commit()
    url = f"{BASE}/legislative/propositions/{seed.proposition.id}/votes"
    atual = client.get(url, params={"session_id": str(deliberacao.id)})
    assert atual.status_code == 200 and atual.json()["sessao_ativa"]["id"] == str(deliberacao.id)
    antigo = client.get(url, params={"session_id": str(seed.merito.id)})  # link salvo antes da unificação
    assert antigo.status_code == 200 and antigo.json()["sessao_ativa"]["id"] == str(deliberacao.id)
    assert client.get(url, params={"session_id": str(uuid.uuid4())}).status_code == 404  # id que nunca existiu


def test_placar_e_o_mesmo_no_explorer_e_na_deliberacao(client, seed):
    itens = client.get(f"{BASE}/legislative/explorer", params={"apenas_votadas": "true"}).json()["items"]
    item = next(i for i in itens if i["titulo"] == "PL 10/2023")
    delib = client.get(f"{BASE}/legislative/deliberacoes/{item['sessao_id']}").json()
    placar = delib["placar"]
    assert item["placar"]["sim"] == placar["sim"] and item["placar"]["nao"] == placar["nao"]
    assert item["placar"]["abstencao"] == placar["abstencao"] + placar["obstrucao"]  # a tela soma a obstrução
    assert item["placar"]["total"] == placar["total"]


def test_sessao_principal_e_a_mesma_nas_tres_telas(client, seed):
    explorer = next(
        i
        for i in client.get(f"{BASE}/legislative/explorer", params={"apenas_votadas": "true"}).json()["items"]
        if i["titulo"] == "PL 10/2023"
    )
    votos = client.get(f"{BASE}/legislative/propositions/{seed.proposition.id}/votes").json()
    divididos = client.get(f"{BASE}/legislative/propositions/{seed.proposition.id}/nominal-votes").json()
    assert explorer["sessao_id"] == votos["sessao_ativa"]["id"] == divididos["sessao"]["id"] == str(seed.merito.id)


def test_filtro_de_partido_do_ranking_de_autores_usa_o_partido_atual(client, seed):
    com_pt = client.get(f"{BASE}/legislative/ranking/authors", params={"partido": "PT", "limit": 50}).json()
    com_ptb = client.get(f"{BASE}/legislative/ranking/authors", params={"partido": "PTB", "limit": 50}).json()
    assert "Fulano" in [r["nome_eleitoral"] for r in com_pt]
    assert "Fulano" not in [r["nome_eleitoral"] for r in com_ptb]
    assert all(r["partido_sigla"] == "PT" for r in com_pt)  # o rótulo e o filtro vêm da mesma definição


def test_filtro_de_partido_do_explorer_escapa_curingas_e_le_os_apelidos_da_tabela(client, seed):
    assert client.get(f"{BASE}/legislative/explorer", params={"partido": "%"}).json()["total"] == 0
    assert client.get(f"{BASE}/legislative/explorer", params={"partido": "_"}).json()["total"] == 0
    governo = client.get(f"{BASE}/legislative/explorer", params={"partido": "governo"}).json()
    assert [i["titulo"] for i in governo["items"]] == ["MPV 1/2023"]
    sem = client.get(f"{BASE}/legislative/explorer", params={"partido": "sem partido"}).json()
    assert "MPV 1/2023" not in [i["titulo"] for i in sem["items"]]


def test_erro_de_dominio_vira_resposta_http_em_portugues(client, seed):
    resp = client.get(f"{BASE}/legislative/propositions/{seed.proposition.id}/votes", params={"house": "assembleia"})
    assert resp.status_code == 422 and "Casa inválida" in resp.json()["detail"]
    assert client.get(f"{BASE}/legislative/propositions/nao-existe/votes").status_code == 404
