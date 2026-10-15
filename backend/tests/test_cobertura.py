"""Cobertura de proposições e de cadeiras: merge dos CSV da Câmara, entidades autoras, período do IPPM e pesos v3."""

import sys
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etl.extractors.camara_bulk_extractor import ArquivoBaixado  # noqa: E402
from etl.pipelines import camara_bulk_loader, camara_historico_loader  # noqa: E402

CABECALHO_PROPOSICOES = [
    "id", "uri", "siglaTipo", "numero", "ano", "codTipo", "descricaoTipo", "ementa", "ementaDetalhada", "keywords",
    "dataApresentacao", "uriOrgaoNumerador", "uriPropAnterior", "uriPropPrincipal", "uriPropPosterior",
    "urlInteiroTeor", "urnFinal", "ultimoStatus_dataHora", "ultimoStatus_sequencia", "ultimoStatus_uriRelator",
    "ultimoStatus_idOrgao", "ultimoStatus_siglaOrgao", "ultimoStatus_uriOrgao", "ultimoStatus_regime",
    "ultimoStatus_descricaoTramitacao", "ultimoStatus_idTipoTramitacao", "ultimoStatus_descricaoSituacao",
    "ultimoStatus_idSituacao", "ultimoStatus_despacho", "ultimoStatus_apreciacao", "ultimoStatus_url",
]  # fmt: skip
CABECALHO_AUTORES = [
    "idProposicao", "uriProposicao", "idDeputadoAutor", "uriAutor", "codTipoAutor", "tipoAutor", "nomeAutor",
    "siglaPartidoAutor", "uriPartidoAutor", "siglaUFAutor", "ordemAssinatura", "proponente",
]  # fmt: skip


def _scalar(db, sql, **params):
    return db.execute(text(sql), params).scalar()


def _rows(db, sql, **params):
    return [tuple(r) for r in db.execute(text(sql), params)]


def _csv(caminho: Path, cabecalho, linhas):
    def campo(v):
        return '"' + str(v).replace('"', '""') + '"'

    conteudo = ";".join(campo(c) for c in cabecalho) + "\n"
    for linha in linhas:
        completo = {**{c: "" for c in cabecalho}, **linha}
        conteudo += ";".join(campo(completo[c]) for c in cabecalho) + "\n"
    caminho.write_text(conteudo, encoding="utf-8-sig")
    return caminho


def _arquivo(recurso, ano, caminho):
    return ArquivoBaixado(
        recurso, ano, f"https://exemplo/{recurso}-{ano}.csv", caminho, caminho.stat().st_size, "a" * 64
    )


@pytest.fixture()
def carga_lote(db, pg_engine, tmp_path):
    """Duas proposições de 2024 e uma de 2023 com autores de vários tipos, carregadas pelo caminho real."""
    from app.models import PoliticalParty
    from app.services.core_sync import sync_legacy_to_core

    db.add(PoliticalParty(acronym="REPUBLICANOS", full_name="Republicanos"))  # destino do alias "REPUBLIC"
    db.commit()
    sync_legacy_to_core(db)
    props = _csv(
        tmp_path / "proposicoes-2024.csv",
        CABECALHO_PROPOSICOES,
        [
            {
                "id": "100",
                "siglaTipo": "PL",
                "numero": "1",
                "ano": "2024",
                "ementa": "Cria programa X",
                "dataApresentacao": "2024-03-01T10:00",
                "ultimoStatus_descricaoSituacao": "Transformado em Norma Jurídica",
                "ultimoStatus_dataHora": "2024-09-10T12:00",
            },
            {
                "id": "101",
                "siglaTipo": "PEC",
                "numero": "2",
                "ano": "2024",
                "ementa": "Altera a Constituição",
                "dataApresentacao": "2024-04-01T10:00",
                "ultimoStatus_descricaoSituacao": "Aguardando Parecer",
            },
            {
                "id": "102",
                "siglaTipo": "REQ",
                "numero": "3",
                "ano": "2024",
                "ementa": "Pede informação",
                "dataApresentacao": "2024-05-01T10:00",
                "ultimoStatus_descricaoSituacao": "Arquivada",
            },
            {
                "id": "103",
                "siglaTipo": "PRL",
                "numero": "4",
                "ano": "2024",
                "ementa": "Parecer (fora do escopo)",
                "dataApresentacao": "2024-05-02T10:00",
                "ultimoStatus_descricaoSituacao": "",
            },
            {
                "id": "104",
                "siglaTipo": "PL",
                "numero": "5",
                "ano": "2024",
                "ementa": "Situação nova",
                "dataApresentacao": "2024-05-03T10:00",
                "ultimoStatus_descricaoSituacao": "Situação Inventada",
            },
        ],
    )
    props23 = _csv(
        tmp_path / "proposicoes-2023.csv",
        CABECALHO_PROPOSICOES,
        [
            {
                "id": "90",
                "siglaTipo": "PL",
                "numero": "9",
                "ano": "2023",
                "ementa": "Projeto antigo",
                "dataApresentacao": "2023-02-01T10:00",
                "ultimoStatus_descricaoSituacao": "Tramitando em Conjunto",
            },
        ],
    )
    autores = _csv(
        tmp_path / "proposicoesAutores-2024.csv",
        CABECALHO_AUTORES,
        [
            {
                "idProposicao": "100",
                "idDeputadoAutor": "555",
                "tipoAutor": "Deputado(a)",
                "nomeAutor": "Ana Souza",
                "siglaPartidoAutor": "PT",
                "siglaUFAutor": "SP",
                "ordemAssinatura": "1",
                "proponente": "1",
            },
            {
                "idProposicao": "101",
                "idDeputadoAutor": "555",
                "tipoAutor": "Deputado(a)",
                "nomeAutor": "Ana Souza",
                "siglaPartidoAutor": "PT",
                "siglaUFAutor": "SP",
                "ordemAssinatura": "1",
                "proponente": "1",
            },
            {
                "idProposicao": "101",
                "idDeputadoAutor": "556",
                "tipoAutor": "Deputado(a)",
                "nomeAutor": "Bia Lima",
                "siglaPartidoAutor": "PL*",
                "siglaUFAutor": "RJ",
                "ordemAssinatura": "2",
                "proponente": "0",
            },
            {
                "idProposicao": "101",
                "idDeputadoAutor": "",
                "tipoAutor": "Senador(a)",
                "nomeAutor": "Caio Senador",
                "siglaPartidoAutor": "REPUBLIC",
                "siglaUFAutor": "MG",
                "ordemAssinatura": "3",
                "proponente": "0",
            },
            {
                "idProposicao": "102",
                "idDeputadoAutor": "",
                "tipoAutor": "Órgão do Poder Executivo",
                "nomeAutor": "Presidência da República",
                "ordemAssinatura": "1",
                "proponente": "1",
            },
            {
                "idProposicao": "104",
                "idDeputadoAutor": "",
                "tipoAutor": "Tipo Desconhecido",
                "nomeAutor": "Fulano",
                "ordemAssinatura": "1",
                "proponente": "1",
            },
        ],
    )
    autores23 = _csv(
        tmp_path / "proposicoesAutores-2023.csv",
        CABECALHO_AUTORES,
        [
            {
                "idProposicao": "90",
                "idDeputadoAutor": "555",
                "tipoAutor": "Deputado(a)",
                "nomeAutor": "Ana Souza",
                "siglaPartidoAutor": "PT",
                "siglaUFAutor": "SP",
                "ordemAssinatura": "1",
                "proponente": "1",
            },
        ],
    )
    arquivos = [
        _arquivo("proposicoes", 2024, props),
        _arquivo("proposicoes", 2023, props23),
        _arquivo("proposicoesAutores", 2024, autores),
        _arquivo("proposicoesAutores", 2023, autores23),
    ]
    resumo = camara_bulk_loader.carregar(pg_engine, arquivos)
    db.expire_all()
    return resumo


def test_status_comes_from_the_source_situation_mapping(db, carga_lote):
    status = dict(_rows(db, "SELECT id_camara, status_codigo FROM leg.proposicao"))
    assert status == {100: "APROVADA_E_SANCIONADA", 101: "EM_TRAMITACAO", 102: "ARQUIVADA", 90: "EM_TRAMITACAO"}


def test_only_in_scope_types_are_loaded_and_the_rest_is_reported(db, carga_lote):
    assert _scalar(db, "SELECT count(*) FROM leg.proposicao WHERE id_camara = 103") == 0  # PRL: parecer, fora do escopo
    detalhe = _scalar(
        db,
        "SELECT detalhe->'fora_de_escopo_por_tipo'->>'PRL' FROM etl.verificacao WHERE nome = 'camara_bulk_cobertura'",
    )
    assert detalhe == "1"


def test_unmapped_situation_is_rejected_not_defaulted(db, carga_lote):
    assert _scalar(db, "SELECT count(*) FROM leg.proposicao WHERE id_camara = 104") == 0
    assert _rows(db, "SELECT motivo, chave_natural FROM etl.rejeito WHERE recurso = 'camara_proposicao'") == [
        ("SITUACAO_SEM_MAPEAMENTO", "104")
    ]
    assert _scalar(db, "SELECT passou FROM etl.verificacao WHERE nome = 'camara_bulk_cobertura'") is False


def test_promulgated_vs_sanctioned_depends_on_the_type(db, carga_lote, tmp_path, pg_engine):
    assert _scalar(db, "SELECT status_codigo FROM leg.proposicao WHERE id_camara = 100") == "APROVADA_E_SANCIONADA"
    assert (
        _scalar(
            db,
            "SELECT status_codigo FROM ref.situacao_camara WHERE descricao = 'Transformado em Norma Jurídica' AND tipo_codigo = 'PEC'",
        )
        == "APROVADA_E_PROMULGADA"
    )


def test_deputies_are_created_by_source_id_and_never_merged_by_name(db, carga_lote):
    assert (
        _scalar(
            db, "SELECT count(*) FROM core.pessoa_identificador WHERE tipo = 'CAMARA_ID' AND valor IN ('555', '556')"
        )
        == 2
    )
    # a mesma pessoa em várias proposições é uma só
    assert _scalar(db, "SELECT count(DISTINCT pessoa_id) FROM leg.autoria WHERE nome_autor = 'Ana Souza'") == 1


def test_non_person_authors_become_entities_and_do_not_score(db, carga_lote):
    assert _rows(db, "SELECT e.categoria, e.nome FROM leg.autoria a JOIN core.entidade e ON e.id = a.entidade_id") == [
        ("PODER_EXECUTIVO", "Presidência da República")
    ]
    assert (
        _scalar(
            db,
            "SELECT count(*) FROM leg.vw_autoria_pontuada v JOIN leg.proposicao p ON p.id = v.proposicao_id WHERE p.id_camara = 102",
        )
        == 0
    )
    assert _scalar(db, "SELECT tipo_codigo FROM leg.autoria WHERE entidade_id IS NOT NULL") == "INSTITUCIONAL"


def test_senator_without_id_is_kept_by_name_and_counted_for_his_party(db, carga_lote):
    linha = _rows(
        db,
        "SELECT a.pessoa_id IS NULL, pa.sigla, a.uf FROM leg.autoria a JOIN core.partido pa ON pa.id = a.partido_id WHERE a.nome_autor = 'Caio Senador'",
    )
    assert linha == [(True, "REPUBLICANOS", "MG")]  # a variante truncada da fonte resolve para o partido (alias)
    assert (
        _scalar(db, "SELECT count(*) FROM leg.vw_autoria_pontuada WHERE tipo_autoria = 'COAUTOR' AND pessoa_id IS NULL")
        == 1
    )


def test_historical_party_without_registry_is_created_outside_the_catalog(db, carga_lote):
    db.execute(text("UPDATE leg.autoria SET partido_id = NULL"))
    assert (
        _scalar(db, "SELECT catalogo FROM core.partido WHERE sigla = 'PL'") is False
    )  # veio da fonte, sem cadastro oficial


def test_pec_support_signature_has_reduced_weight_and_is_flagged(db, carga_lote):
    linhas = _rows(
        db,
        "SELECT v.tipo_autoria, v.apoio_quorum, v.pontos_ialp FROM leg.vw_autoria_pontuada v "
        "JOIN leg.proposicao p ON p.id = v.proposicao_id WHERE p.id_camara = 101 ORDER BY v.autoria_id",
    )
    por_tipo = {(t, a): float(p) for t, a, p in linhas}
    assert por_tipo[("AUTOR_PRINCIPAL", False)] == 3.0  # PEC 3,0 x autor 1,0 x em tramitação 1,0
    assert por_tipo[("COAUTOR", True)] == pytest.approx(0.15)  # 3,0 x 0,05 (apoio de quórum) x 1,0


def test_reload_is_idempotent(db, carga_lote, pg_engine, tmp_path):
    antes = _rows(
        db,
        "SELECT (SELECT count(*) FROM leg.proposicao), (SELECT count(*) FROM leg.autoria), (SELECT count(*) FROM core.pessoa), (SELECT count(*) FROM core.entidade)",
    )
    camara_bulk_loader.mesclar(pg_engine)
    db.expire_all()
    assert (
        _rows(
            db,
            "SELECT (SELECT count(*) FROM leg.proposicao), (SELECT count(*) FROM leg.autoria), (SELECT count(*) FROM core.pessoa), (SELECT count(*) FROM core.entidade)",
        )
        == antes
    )


def test_layout_change_in_the_source_is_detected(pg_engine, tmp_path):
    ruim = tmp_path / "proposicoes-2024.csv"
    ruim.write_text('"id";"uri"\n"1";"x"\n', encoding="utf-8-sig")
    with pytest.raises(ValueError, match="layout da fonte mudou"):
        camara_bulk_loader.carregar_staging(pg_engine, [_arquivo("proposicoes", 2024, ruim)])


def test_bridge_adopts_the_legacy_uid_of_a_proposition_loaded_in_bulk(db, carga_lote):
    from app.models import Proposition, StatusTramitacaoEnum, TipoProposicaoEnum
    from app.services.core_sync import sync_legacy_to_core

    legado = Proposition(
        proposition_type=TipoProposicaoEnum.PL,
        number=1,
        year=2024,
        title="PL 1/2024",
        summary="Cria programa X",
        presentation_date=date(2024, 3, 1),
        status=StatusTramitacaoEnum.EM_TRAMITACAO,
        external_camara_id=100,
        thematic_area="Economia",
    )
    db.add(legado)
    db.commit()
    sync_legacy_to_core(db)
    linha = _rows(db, "SELECT uid::text, status_codigo, area_tematica FROM leg.proposicao WHERE id_camara = 100")
    # uid público preservado, status real da fonte mantido, enriquecimento do legado aproveitado
    assert linha == [(str(legado.id), "APROVADA_E_SANCIONADA", "Economia")]
    assert _scalar(db, "SELECT count(*) FROM leg.proposicao WHERE id_camara = 100") == 1


# ── IPPM no período, fidelidade sem dado e cadeiras com histórico de partido ──────────────────────


@pytest.fixture()
def ranking_periodo(db, client, carga_lote):
    """Ana (PT) e Bia (PL) com cadeira em exercício na legislatura 57: sem cadeiras o IPPM não é calculado."""
    db.execute(
        text(
            """
        INSERT INTO core.mandato (pessoa_id, cargo_id, circunscricao_id, partido_id, condicao, inicio, fim)
        SELECT i.pessoa_id, (SELECT id FROM ref.cargo WHERE codigo = 'DEPUTADO_FEDERAL'),
               (SELECT id FROM ref.circunscricao WHERE tipo = 'BR'),
               (SELECT id FROM core.partido WHERE sigla = CASE i.valor WHEN '555' THEN 'PT' ELSE 'PL' END),
               'TITULAR', DATE '2023-02-01', DATE '2027-01-31'
        FROM core.pessoa_identificador i WHERE i.tipo = 'CAMARA_ID' AND i.valor IN ('555', '556')"""
        )
    )
    db.execute(
        text(
            """
        INSERT INTO core.mandato_situacao (mandato_id, situacao, periodo)
        SELECT id, 'EXERCICIO', daterange(DATE '2023-02-01', DATE '2027-02-01') FROM core.mandato"""
        )
    )
    db.execute(
        text(
            """
        INSERT INTO core.mandato_partido (mandato_id, partido_id, periodo)
        SELECT id, partido_id, daterange(DATE '2023-02-01', DATE '2027-02-01') FROM core.mandato"""
        )
    )
    db.commit()
    return client


def test_period_without_seat_history_is_reported_not_invented(db, client, carga_lote):
    corpo = client.get("/api/v1/parties/ippm-ranking?ano=2001").json()
    assert corpo["ranking"] == []
    assert corpo["periodo"]["aviso"] is None  # nada foi apresentado em 2001 neste cenário
    corpo = client.get("/api/v1/parties/ippm-ranking?ano=2024").json()  # há proposições, mas nenhuma cadeira registrada
    assert corpo["ranking"] == []
    assert "Sem histórico de cadeiras" in corpo["periodo"]["aviso"]


def test_ippm_only_counts_propositions_filed_in_the_selected_year(db, ranking_periodo):
    r24 = ranking_periodo.get("/api/v1/parties/ippm-ranking?ano=2024").json()["ranking"]
    r23 = ranking_periodo.get("/api/v1/parties/ippm-ranking?ano=2023").json()["ranking"]
    pt24 = next(p for p in r24 if p["sigla"] == "PT")
    pt23 = next(p for p in r23 if p["sigla"] == "PT")
    assert pt24["projetos_apresentados"] == 2  # PL 100 e PEC 101 (2024)
    assert pt23["projetos_apresentados"] == 1  # PL 90 (2023)
    assert pt24["projetos_aprovados"] == 1 and pt24["pilares"]["taxa_eficacia_pct"] == 50.0  # eficácia deixa de ser 0%


def test_fidelity_is_unavailable_instead_of_a_fake_100_when_there_are_no_votes(db, ranking_periodo):
    ranking = ranking_periodo.get("/api/v1/parties/ippm-ranking?ano=2024").json()["ranking"]
    assert all(p["pilares"]["fidelidade_partidaria_pct"] is None for p in ranking)


def test_pec_support_signatures_are_exposed_separately_in_the_ranking(db, ranking_periodo):
    ranking = ranking_periodo.get("/api/v1/parties/ippm-ranking?ano=2024").json()["ranking"]
    pl = next(p for p in ranking if p["sigla"] == "PL")
    assert pl["pilares"]["assinaturas_apoio_quorum"] == 1
    assert pl["pontuacao_bruta_ialp"] == pytest.approx(0.15)


def test_seat_days_use_the_party_history_of_the_seat(db, pg_engine):
    from app.services.party_productivity_service import calculate_party_active_seats

    eventos = [
        {
            "id": 700,
            "nome": "Dep Histórico",
            "nomeEleitoral": "Dep Histórico",
            "siglaPartido": "PT",
            "siglaUf": "SP",
            "idLegislatura": 54,
            "dataHora": "2011-02-01T00:00",
            "situacao": "Exercício",
            "condicaoEleitoral": "Titular",
            "descricaoStatus": "Entrada - Posse de Eleito Titular - Posse na Sessão Preparatória",
        },
        {
            "id": 700,
            "nome": "Dep Histórico",
            "nomeEleitoral": "Dep Histórico",
            "siglaPartido": "PL",
            "siglaUf": "SP",
            "idLegislatura": 54,
            "dataHora": "2012-07-01T00:00",
            "situacao": "Exercício",
            "condicaoEleitoral": "Titular",
            "descricaoStatus": "Alteração de partido",
        },
        {
            "id": 700,
            "nome": "Dep Histórico",
            "nomeEleitoral": "Dep Histórico",
            "siglaPartido": "PL",
            "siglaUf": "SP",
            "idLegislatura": 54,
            "dataHora": "2013-01-01T00:00",
            "situacao": "Licença",
            "condicaoEleitoral": "Titular",
            "descricaoStatus": "Saída - Afastamento com prazo determinado - Licença para Tratamento de Saúde",
        },
        {
            "id": 700,
            "nome": "Dep Histórico",
            "nomeEleitoral": "Dep Histórico",
            "siglaPartido": "PL",
            "siglaUf": "SP",
            "idLegislatura": 54,
            "dataHora": "2013-04-01T00:00",
            "situacao": "Exercício",
            "condicaoEleitoral": "Titular",
            "descricaoStatus": "Entrada - Reassunção",
        },
        {
            "id": 700,
            "nome": "Dep Histórico",
            "nomeEleitoral": "Dep Histórico",
            "siglaPartido": "PL",
            "siglaUf": "SP",
            "idLegislatura": 54,
            "dataHora": "2015-01-31T23:59",
            "situacao": "FIM_MANDATO",
            "condicaoEleitoral": "Titular",
            "descricaoStatus": "Saída - Afastamento definitivo - Término da Legislatura",
        },
    ]
    legislaturas = [{"id": 54, "dataInicio": "2011-02-01", "dataFim": "2015-01-31"}]
    camara_historico_loader.carregar_staging(pg_engine, eventos, legislaturas)
    with pg_engine.begin() as conexao:
        conexao.execute(text("SELECT etl.merge_camara_historico()"))
    db.expire_all()

    assert _rows(
        db, "SELECT situacao, lower(periodo), upper(periodo) FROM core.mandato_situacao ORDER BY lower(periodo)"
    ) == [
        ("EXERCICIO", date(2011, 2, 1), date(2013, 1, 1)),
        ("LICENCA", date(2013, 1, 1), date(2013, 4, 1)),
        ("EXERCICIO", date(2013, 4, 1), date(2015, 2, 1)),
    ]
    # em 2012 o deputado trocou de partido em 1º de julho: a cadeira passa do PT para o PL no meio do ano (366 dias)
    pt = calculate_party_active_seats("PT", "CAMARA", date(2012, 1, 1), date(2012, 12, 31), db)
    pl = calculate_party_active_seats("PL", "CAMARA", date(2012, 1, 1), date(2012, 12, 31), db)
    assert pt["cadeiras_dia_equivalentes"] == pytest.approx(182 / 366, abs=0.01)
    assert pl["cadeiras_dia_equivalentes"] == pytest.approx(184 / 366, abs=0.01)
    # durante a licença (jan a mar de 2013) a cadeira não conta para o titular
    pl13 = calculate_party_active_seats("PL", "CAMARA", date(2013, 1, 1), date(2013, 12, 31), db)
    assert pl13["cadeiras_dia_equivalentes"] == pytest.approx((365 - 90) / 365, abs=0.01)
    assert _scalar(db, "SELECT motivo_encerramento FROM core.mandato") == "CONCLUIDO"
    assert _scalar(db, "SELECT count(*) FROM core.mandato_partido") == 3  # PT; PL antes da licença; PL depois


# ── linhagem de partidos (renomeações e grafias da fonte) ────────────────────────────────────────


def test_renamed_party_points_to_the_current_one_and_is_hidden_from_the_catalog(db, client):
    db.execute(text("INSERT INTO core.partido (sigla, nome) VALUES ('MDB', 'MDB'), ('PMDB', 'PMDB'), ('XYZ', 'XYZ')"))
    assert _scalar(db, "SELECT etl.aplicar_linhagens()") == 1
    assert _rows(
        db,
        "SELECT p.sigla, c.canonico_sigla FROM core.vw_partido_canonico c JOIN core.partido p ON p.id = c.id ORDER BY p.sigla",
    ) == [
        ("MDB", "MDB"),
        ("PMDB", "MDB"),
        ("XYZ", "XYZ"),
    ]
    assert _rows(
        db,
        "SELECT o.sigla, d.sigla, s.tipo FROM core.partido_sucessao s "
        "JOIN core.partido o ON o.id = s.partido_origem_id JOIN core.partido d ON d.id = s.partido_destino_id",
    ) == [("PMDB", "MDB", "RENOMEACAO")]
    db.commit()
    assert {p["sigla"] for p in client.get("/api/v1/parties").json()} == {"MDB", "XYZ"}
    assert _scalar(db, "SELECT etl.aplicar_linhagens()") == 0  # idempotente


def test_authorship_under_the_old_acronym_counts_for_the_current_party(db, client):
    from datetime import date

    db.execute(text("INSERT INTO core.partido (sigla, nome) VALUES ('MDB', 'MDB'), ('PMDB', 'PMDB')"))
    db.execute(text("SELECT etl.aplicar_linhagens()"))
    db.execute(
        text(
            "INSERT INTO leg.proposicao (id_camara, tipo_codigo, numero, ano, titulo, data_apresentacao, status_codigo) "
            "VALUES (1, 'PL', 1, 2015, 'PL 1/2015', DATE '2015-05-01', 'EM_TRAMITACAO')"
        )
    )
    db.execute(
        text(
            "INSERT INTO leg.autoria (proposicao_id, nome_autor, tipo_codigo, partido_id) "
            "SELECT (SELECT id FROM leg.proposicao), 'Fulano', 'AUTOR_PRINCIPAL', (SELECT id FROM core.partido WHERE sigla = 'PMDB')"
        )
    )
    # a cadeira em 2015 está sob a sigla atual (MDB): o ranking precisa somar as duas
    db.execute(text("INSERT INTO core.pessoa (nome_exibicao) VALUES ('Fulano')"))
    db.execute(
        text(
            "INSERT INTO core.mandato (pessoa_id, cargo_id, circunscricao_id, partido_id, inicio, fim) "
            "SELECT (SELECT id FROM core.pessoa), (SELECT id FROM ref.cargo WHERE codigo = 'DEPUTADO_FEDERAL'), "
            "(SELECT id FROM ref.circunscricao WHERE tipo = 'BR'), (SELECT id FROM core.partido WHERE sigla = 'MDB'), "
            "DATE '2015-02-01', DATE '2019-01-31'"
        )
    )
    db.execute(
        text(
            "INSERT INTO core.mandato_situacao (mandato_id, situacao, periodo) SELECT id, 'EXERCICIO', "
            "daterange(DATE '2015-02-01', DATE '2019-02-01') FROM core.mandato"
        )
    )
    db.commit()
    ranking = client.get("/api/v1/parties/ippm-ranking?ano=2015").json()["ranking"]
    assert [(p["sigla"], p["projetos_apresentados"], p["total_cadeiras_ativas"]) for p in ranking] == [("MDB", 1, 1)]
