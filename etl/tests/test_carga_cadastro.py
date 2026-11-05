"""
Carga no banco (Postgres de teste): idempotência, proveniência e resolução inequívoca de pessoas.

Usa o fluxo completo de `CargaCadastro.load_all` (migrações Alembic, staging por COPY e fusão em `core`/`leg`), por isso
exige o Postgres de teste (`make test-db-up`). As consultas ao staging usam `etl.tests.stg_consulta`.
"""

import json
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from etl.extractors.presidents_extractor import PresidentsExtractor  # noqa: E402
from etl.pipelines import carga_cadastro  # noqa: E402
from etl.pipelines.staging_votos import ContagemDeVotos  # noqa: E402
from etl.tests.stg_consulta import (
    Mandate,
    ParliamentaryVote,
    PartyAffiliation,
    PoliticalParty,
    Politician,
    Proposition,
)
from etl.tests.stg_consulta import Sessao as _Sessao  # noqa: E402
from etl.tests.stg_consulta import (
    VotingSession,
)


def escrever(dir_, nome, dados):
    (dir_ / nome).write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg2://test:test_pass@localhost:5433/legis_test")
    engine = create_engine(url)
    with engine.begin() as conn:
        for schema in ("api", "stg", "fin", "leg", "param", "etl", "eco", "core", "ref", "public"):
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", url)
    monkeypatch.setattr(carga_cadastro, "SessionLocal", sessionmaker(bind=engine))  # a fusão usa o banco de teste
    monkeypatch.setattr(carga_cadastro, "engine_padrao", engine)
    Sessao = lambda: _Sessao(engine)  # noqa: E731
    Sessao.engine = engine

    dados = tmp_path / "processed"
    dados.mkdir()
    escrever(dados, "presidentes_historico.json", PresidentsExtractor.get_presidents())
    escrever(
        dados,
        "deputados_camara.json",
        [
            # duplicado (como o arquivo legado) + contato real só em um dos registros
            {
                "camara_id": 1,
                "nome_eleitoral": "Eduardo Bolsonaro",
                "nome_civil": "Eduardo Nantes Bolsonaro",
                "partido_sigla": "PL",
                "uf": "SP",
                "id_legislatura": 57,
            },
            {
                "camara_id": 1,
                "nome_eleitoral": "Eduardo Bolsonaro",
                "partido_sigla": "PL",
                "uf": "SP",
                "email": "dep.eduardo@camara.leg.br",
                "gabinete_sala": "Anexo 4, Gabinete 100",
                "uf_nascimento": "RJ",
            },
            {
                "camara_id": 2,
                "nome_eleitoral": "Flávio Dino",
                "nome_civil": "Flávio Dino de Castro e Costa",
                "partido_sigla": "PSB",
                "uf": "MA",
            },
            {"camara_id": 3, "nome_eleitoral": "Dr. Flávio", "partido_sigla": "PTB", "uf": "RJ"},
            {"camara_id": 4, "nome_eleitoral": "Lula da Fonte", "partido_sigla": "PP", "uf": "PE"},
        ],
    )
    escrever(
        dados,
        "senadores_senado.json",
        [
            {
                "senado_id": 100,
                "nome_eleitoral": "Senadora Sem Datas",
                "nome_civil": "Senadora Sem Datas",
                "partido_sigla": "PSD",
                "uf": "MG",
            },
            {
                "senado_id": 101,
                "nome_eleitoral": "Senador Com Datas",
                "nome_civil": "Senador Com Datas",
                "partido_sigla": "PT",
                "uf": "BA",
                "mandato_inicio": "2019-02-01",
                "mandato_fim": "2027-01-31",
            },
        ],
    )
    escrever(
        dados,
        "filiacoes_partidarias.json",
        [
            {
                "politico_nome": "Eduardo Bolsonaro",
                "fonte": "teste",
                "camara_id": 1,
                "partido_sigla": "PSL",
                "data_filiacao": "2018-03-06",
                "data_desfiliacao": "2021-11-29",
                "is_atual": False,
                "motivo_desfiliacao": "MUDANCA_VOLUNTARIA",
            },
            {
                "politico_nome": "Eduardo Bolsonaro",
                "fonte": "teste",
                "camara_id": 1,
                "partido_sigla": "PL",
                "data_filiacao": None,
                "is_atual": True,
            },
            {"politico_nome": "Fulano Sem Id", "partido_sigla": "PL", "data_filiacao": "2020-01-01", "fonte": "teste"},
            {
                "politico_nome": "Flávio Dino",
                "camara_id": 2,
                "partido_sigla": "DEM",
                "data_filiacao": "2018-04-05",
            },  # legado: sem proveniência
        ],
    )
    return dados, Sessao


def carregar(dados, **kwargs):
    return carga_cadastro.CargaCadastro(data_dir=dados, engine=carga_cadastro.engine_padrao, **kwargs).load_all()


def test_politicos_deduplicados_e_sem_contato_inventado(ambiente):
    dados, Sessao = ambiente
    carregar(dados)
    with Sessao() as s:
        deputados = {p.camara_id: p for p in s.query(Politician).filter(Politician.camara_id.isnot(None))}
        assert len(deputados) == 4
        edu = deputados[1]
        assert edu.email == "dep.eduardo@camara.leg.br"  # vem da fonte
        assert edu.cabinet_room == "Anexo 4, Gabinete 100" and edu.birthplace_state == "RJ"
        flavio = deputados[2]
        assert flavio.email is None and flavio.cabinet_room is None and flavio.cabinet_phone is None
        assert flavio.birthplace_state is None  # UF eleitoral não é naturalidade


def test_carga_e_idempotente(ambiente):
    dados, Sessao = ambiente
    primeira = carregar(dados)
    segunda = carregar(dados)
    assert primeira == segunda


def test_filiacoes_partidos_extintos_e_data_desconhecida(ambiente):
    dados, Sessao = ambiente
    carregar(dados)
    with Sessao() as s:
        siglas = {p.acronym for p in s.query(PoliticalParty)}
        assert {"PSL", "PTB", "PL"} <= siglas  # extintos viram partidos reais, não "Sem Partido"
        edu = s.query(Politician).filter_by(camara_id=1).one()
        afs = s.query(PartyAffiliation).filter_by(politician_id=edu.id).all()
        assert len(afs) == 2
        atual = next(a for a in afs if a.is_current)
        assert atual.start_date.isoformat() == "2023-02-01"  # limite inferior de observação, não data real inventada
        assert s.query(PartyAffiliation).count() == 2  # linha sem id e com nome não único/desconhecido não vira vínculo


def test_mandatos_de_senadores_usam_datas_da_fonte(ambiente):
    dados, Sessao = ambiente
    carregar(dados)
    with Sessao() as s:
        sen_ok = s.query(Politician).filter_by(senado_id=101).one()
        m = s.query(Mandate).filter_by(politician_id=sen_ok.id).one()
        assert (m.start_date.isoformat(), m.end_date.isoformat(), m.election_year) == ("2019-02-01", "2027-01-31", 2018)
        sen_sem = s.query(Politician).filter_by(senado_id=100).one()
        m2 = s.query(Mandate).filter_by(politician_id=sen_sem.id).one()
        assert m2.end_date is None  # sem datas na fonte: não se inventa término em 2031
        dep = s.query(Politician).filter_by(camara_id=1).one()
        md = s.query(Mandate).filter_by(politician_id=dep.id).one()
        assert (md.start_date.isoformat(), md.end_date.isoformat(), md.election_year) == (
            "2023-02-01",
            "2027-01-31",
            2022,
        )


def proposicoes_e_votacoes(dados):
    escrever(
        dados,
        "proposicoes_2023.json",
        [
            {
                "camara_id": 10,
                "tipo": "PL",
                "numero": 74,
                "ano": 2023,
                "titulo": "PL 74/2023",
                "ementa": "Assunto neutro",
                "autor_nome": "Flávio Dino",
                "autor_fonte": "API",
                "autor_camara_id": None,
                "data_apresentacao": "2023-03-01",
                "url_oficial": None,
            },
            {
                "camara_id": 11,
                "tipo": "PL",
                "numero": 75,
                "ano": 2023,
                "titulo": "PL 75/2023",
                "ementa": "Assunto neutro",
                "autor_nome": "Dr. Flávio, Fulano",
                "autor_fonte": "API",
                "data_apresentacao": None,
            },
            {
                "camara_id": 12,
                "tipo": "PLP",
                "numero": 93,
                "ano": 2023,
                "titulo": "Arcabouço",
                "ementa": "arcabouço fiscal",
                "autor_nome": "Poder Executivo",
                "autor_fonte": "API",
                "iniciativa_executivo": True,
                "data_apresentacao": "2023-04-18",
            },
        ],
    )
    escrever(
        dados,
        "proposicoes_senado.json",
        [
            # mesmo tipo/número/ano de um PL da Câmara, mas é OUTRA proposição (id do Senado distinto)
            {
                "senado_id": 900,
                "tipo": "PL",
                "numero": 74,
                "ano": 2023,
                "titulo": "PL 74/2023 (Senado)",
                "ementa": "Outra coisa",
                "autor_nome": "Senador Com Datas",
                "autor_fonte": "API",
                "data_apresentacao": "2023-05-02",
            },
        ],
    )
    escrever(
        dados,
        "sessoes_votacao_2023.json",
        [
            {
                "sessao_externa_id": "S-CAM-1",
                "proposicao_camara_id": 12,
                "data_hora": "2023-05-10T19:00:00",
                "descricao": "Aprovada",
                "aprovada": True,
            },
            {"sessao_externa_id": "S-ORFA", "proposicao_camara_id": 999, "data_hora": "2023-05-10T19:00:00"},
        ],
    )
    escrever(
        dados,
        "votos_nominais_2023.json",
        [
            {"sessao_externa_id": "S-CAM-1", "deputado_camara_id": 1, "voto": "SIM", "partido_sigla": "PL"},
            {"sessao_externa_id": "S-CAM-1", "deputado_camara_id": 2, "voto": "NAO", "partido_sigla": "PSB"},
            {"sessao_externa_id": "S-CAM-1", "deputado_camara_id": 3, "voto": "ARTIGO_17"},
            {
                "sessao_externa_id": "S-CAM-1",
                "deputado_camara_id": 4,
                "voto": "OPCAO_NOVA",
            },  # antes: KeyError derrubava a carga
        ],
    )
    escrever(
        dados,
        "sessoes_votacao_senado.json",
        [
            {
                "sessao_externa_id": "SEN-1",
                "materia_sigla": "PLP",
                "materia_numero": 93,
                "materia_ano": 2023,
                "data_hora": "2023-06-01T10:00:00",
                "aprovada": True,
            },
            # matéria desconhecida: antes caía em "a primeira proposição qualquer"
            {
                "sessao_externa_id": "SEN-2",
                "materia_sigla": "PL",
                "materia_numero": 5555,
                "materia_ano": 2023,
                "data_hora": "2023-06-02T10:00:00",
            },
            {
                "sessao_externa_id": "SEN-3",
                "materia_sigla": "PLP",
                "materia_numero": 93,
                "materia_ano": 2023,
            },  # sem data
        ],
    )
    escrever(
        dados,
        "votos_nominais_senado.json",
        [
            {"sessao_externa_id": "SEN-1", "senador_id": 101, "voto": "SIM"},
            {"sessao_externa_id": "SEN-1", "senador_id": 100, "voto": "AUSENTE"},
            {"sessao_externa_id": "SEN-2", "senador_id": 101, "voto": "SIM"},
        ],
    )


def test_autoria_exata_e_senado_nao_funde_com_camara(ambiente):
    dados, Sessao = ambiente
    proposicoes_e_votacoes(dados)
    carregar(dados)
    with Sessao() as s:
        dino = s.query(Politician).filter_by(camara_id=2).one()
        drflavio = s.query(Politician).filter_by(camara_id=3).one()
        p74 = s.query(Proposition).filter_by(external_camara_id=10).one()
        assert p74.author_politician_id == dino.id  # "Flávio Dino" != "Dr. Flávio"
        p75 = s.query(Proposition).filter_by(external_camara_id=11).one()
        # "Dr. Flávio" (1 token após normalização) não pode virar autor por subconjunto de tokens; aqui é igualdade exata
        assert p75.author_politician_id == drflavio.id
        assert s.query(Proposition).filter_by(external_senado_id=900).one().id != p74.id
        assert s.query(Proposition).count() == 4  # nada foi fundido
        exec_ = s.query(Proposition).filter_by(external_camara_id=12).one()
        assert (
            exec_.author_politician_id is None
            and exec_.author_name == "Poder Executivo"
            and exec_.is_executive_initiative
        )
        # sem eixo aleatório e sem área temática inventada
        assert p74.impact_axis is None and p74.thematic_area is None


def test_votacoes_sem_proposicao_unica_sao_descartadas_e_voto_invalido_nao_derruba(ambiente):
    dados, Sessao = ambiente
    proposicoes_e_votacoes(dados)
    carregar(dados)
    with Sessao() as s:
        externos = {v.external_id for v in s.query(VotingSession)}
        assert externos == {"S-CAM-1", "SEN-1"}  # órfã, matéria desconhecida e sem data ficaram de fora
        cam = s.query(VotingSession).filter_by(external_id="S-CAM-1").one()
        assert (cam.votes_yes_count, cam.votes_no_count) == (1, 1)  # recalculado dos votos nominais
        assert s.query(ParliamentaryVote).filter_by(voting_session_id=cam.id).count() == 3  # voto "OPCAO_NOVA" ignorado
        sen = s.query(VotingSession).filter_by(external_id="SEN-1").one()
        arcabouco = s.query(Proposition).filter_by(external_camara_id=12).one()
        assert sen.proposition_id == arcabouco.id


def test_vinculo_errado_antigo_e_corrigido_na_recarga(ambiente):
    dados, Sessao = ambiente
    proposicoes_e_votacoes(dados)
    carregar(dados)
    with Sessao() as s:
        edu = s.query(Politician).filter_by(camara_id=1).one()
        p = s.query(Proposition).filter_by(external_camara_id=10).one()
        p.author_politician_id = edu.id  # vínculo errado como o do caso Eduardo Bolsonaro
        s.commit()
    carregar(dados)
    with Sessao() as s:
        dino = s.query(Politician).filter_by(camara_id=2).one()
        assert s.query(Proposition).filter_by(external_camara_id=10).one().author_politician_id == dino.id


def test_mandato_presidencial_nao_usa_vice_como_coligacao(ambiente):
    dados, Sessao = ambiente
    carregar(dados)
    with Sessao() as s:
        presidenciais = s.query(Mandate).filter(Mandate.jurisdiction_state == "BR").all()
        assert presidenciais and all(m.coalition_name is None for m in presidenciais)


def test_autoria_legada_sem_proveniencia_e_ignorada_a_menos_que_autorizada(ambiente):
    dados, Sessao = ambiente
    escrever(
        dados,
        "proposicoes_2023.json",
        [
            # como o arquivo legado: autor sorteado (round-robin) quando a API falhava, sem `autor_fonte`
            {
                "camara_id": 10,
                "tipo": "PL",
                "numero": 1,
                "ano": 2023,
                "titulo": "PL 1/2023",
                "ementa": "x",
                "autor_nome": "Flávio Dino",
                "autor_camara_id": 2,
                "data_apresentacao": "2023-03-01",
            },
            {
                "camara_id": 11,
                "tipo": "MPV",
                "numero": 2,
                "ano": 2023,
                "titulo": "MPV 2/2023",
                "ementa": "x",
                "autor_nome": "Comissão / Parlamentares",
                "iniciativa_executivo": True,
                "data_apresentacao": "2023-03-01",
            },
        ],
    )
    carregar(dados)
    with Sessao() as s:
        p1 = s.query(Proposition).filter_by(external_camara_id=10).one()
        assert p1.author_politician_id is None and p1.author_name is None
        p2 = s.query(Proposition).filter_by(external_camara_id=11).one()
        assert p2.author_name == "Poder Executivo"  # iniciativa do Executivo é fato curado, não palpite
    carregar(dados, allow_unverified=True)
    with Sessao() as s:
        dino = s.query(Politician).filter_by(camara_id=2).one()
        assert s.query(Proposition).filter_by(external_camara_id=10).one().author_politician_id == dino.id


def test_filiacoes_legadas_sem_proveniencia_sao_ignoradas(ambiente):
    dados, Sessao = ambiente
    carregar(dados)
    with Sessao() as s:
        dino = s.query(Politician).filter_by(camara_id=2).one()
        assert s.query(PartyAffiliation).filter_by(politician_id=dino.id).count() == 0
    carregar(dados, allow_unverified=True)
    with Sessao() as s:
        dino = s.query(Politician).filter_by(camara_id=2).one()
        assert s.query(PartyAffiliation).filter_by(politician_id=dino.id).count() == 1


def test_sessoes_legadas_do_senado_sem_ano_usam_materias_conhecidas(ambiente):
    dados, Sessao = ambiente
    proposicoes_e_votacoes(dados)
    escrever(
        dados,
        "sessoes_votacao_senado.json",
        [
            {
                "sessao_externa_id": "SEN-LEG",
                "materia_sigla": "PLP",
                "materia_numero": 93,
                "data_hora": "2023-06-01T10:00:00",
                "aprovada": True,
            },
        ],
    )
    escrever(dados, "votos_nominais_senado.json", [{"sessao_externa_id": "SEN-LEG", "senador_id": 101, "voto": "SIM"}])
    carregar(dados)
    with Sessao() as s:
        assert s.query(VotingSession).filter_by(external_id="SEN-LEG").count() == 1


def _execucoes(sessao, recurso, estagio="CARREGAR"):
    """As execuções do recurso (do mais antigo ao mais novo): status, estágio, erro, lidas, gravadas, rejeitadas."""
    return (
        sessao()
        .execute(
            text(
                "SELECT e.status, e.estagio, e.erro, e.linhas_lidas, e.linhas_gravadas, e.linhas_rejeitadas "
                "FROM etl.execucao e WHERE e.parametros->>'recurso' = :recurso AND e.estagio = :estagio ORDER BY e.id"
            ),
            {"recurso": recurso, "estagio": estagio},
        )
        .all()
    )


def test_fusao_do_staging_que_falha_sobe_para_a_etapa_nao_aparecer_como_ok(ambiente, monkeypatch):
    """A carga do staging já foi confirmada, mas `core`/`leg` ficaram sem ela: a esteira tem de registrar a falha."""
    dados, Sessao = ambiente

    def quebra(_sessao):
        raise RuntimeError("fusão quebrou")

    carregar(dados)  # aplica as migrações e deixa o staging pronto
    monkeypatch.setattr("app.services.staging_merge.merge_staging", quebra)
    carga = carga_cadastro.CargaCadastro(data_dir=dados, engine=Sessao.engine)
    with pytest.raises(RuntimeError, match="fusão quebrou"):
        carga._fundir_staging()
    (status, _, erro, *_) = _execucoes(Sessao, "cadastro_e_legislativo", "MERGE")[-1]
    assert (status, erro) == ("ERRO", "RuntimeError")  # só a classe da exceção vai para o banco


def test_cada_recurso_registra_a_sua_execucao_e_a_fusao_a_dela(ambiente):
    dados, Sessao = ambiente
    carregar(dados)
    for recurso in carga_cadastro.RECURSOS:
        (status, estagio, erro, lidas, gravadas, rejeitadas) = _execucoes(Sessao, recurso)[-1]
        assert (estagio, erro) == ("CARREGAR", None), recurso
        assert lidas == gravadas + rejeitadas, recurso  # as contagens de cada recurso fecham
    (status, *_) = _execucoes(Sessao, "cadastro_e_legislativo", "MERGE")[-1]
    assert status in ("OK", "COM_ALERTA")
    # a fonte, o arquivo de origem e as verificações ficam registrados
    fontes = Sessao().execute(
        text(
            "SELECT f.codigo FROM etl.execucao e JOIN etl.fonte f ON f.id = e.fonte_id "
            "WHERE e.parametros->>'recurso' = 'filiacoes'"
        )
    )
    assert {r[0] for r in fontes} == {"TSE"}
    arquivos = Sessao().execute(
        text("SELECT count(*) FROM etl.arquivo_bruto WHERE caminho LIKE '%presidentes_historico.json'")
    )
    assert arquivos.scalar() >= 1
    verificacoes = Sessao().execute(
        text(
            "SELECT count(*) FROM etl.verificacao v JOIN etl.execucao e ON e.id = v.execucao_id "
            "WHERE e.parametros->>'recurso' = 'politicos'"
        )
    )
    assert verificacoes.scalar() >= 4  # as do recurso mais a de contagens


def test_recurso_pode_ser_recarregado_sozinho_sem_mudar_o_resto(ambiente):
    dados, Sessao = ambiente
    proposicoes_e_votacoes(dados)
    carregar(dados)
    conta = text(
        "SELECT count(*) FROM etl.execucao WHERE parametros->>'recurso' IS NOT NULL"
    )  # as da carga, não as da fusão
    antes = Sessao().execute(conta).scalar()
    contagens = carga_cadastro.CargaCadastro(data_dir=dados, engine=Sessao.engine).load_all(
        recursos=["votacoes_plenario"]
    )
    depois = Sessao().execute(conta).scalar()
    assert depois == antes + 2  # só o recurso pedido e a fusão
    assert contagens["Votos Parlamentares Nominais"] == 5  # os 5 votos válidos da fixture, sem duplicar
    with pytest.raises(ValueError, match="recurso desconhecido"):
        carga_cadastro.CargaCadastro(data_dir=dados, engine=Sessao.engine).load_all(recursos=["nao_existe"])


def test_carga_registra_a_execucao_com_contagens_de_votos(ambiente):
    dados, Sessao = ambiente
    carregar(dados)
    (status, estagio, erro, lidas, gravadas, rejeitadas) = _execucoes(Sessao, "votacoes_plenario")[-1]
    assert (status, estagio, erro) == ("OK", "CARREGAR", None)
    assert (lidas, gravadas, rejeitadas) == (0, 0, 0)  # sem arquivos de votação, as contagens são zero e fecham


def test_carga_que_falha_registra_erro_so_com_a_classe_da_excecao(ambiente, monkeypatch):
    dados, Sessao = ambiente

    def explode(self, cursor):
        raise RuntimeError("detalhe sigiloso: senha=abc")

    monkeypatch.setattr(carga_cadastro.CargaCadastro, "_politicos", explode)
    with pytest.raises(RuntimeError, match="detalhe sigiloso"):  # a exceção sobe inteira; o registro guarda só a classe
        carregar(dados)
    (status, _, erro, *_) = _execucoes(Sessao, "politicos")[-1]
    assert (status, erro) == ("ERRO", "RuntimeError")


def test_contagem_de_votos_da_execucao_fecha_e_a_recarga_conta_os_ja_gravados(ambiente):
    dados, Sessao = ambiente
    proposicoes_e_votacoes(dados)
    carregar(dados)
    carregar(dados)  # a recarga não duplica no staging: os votos já gravados contam como gravados
    (status, _, _, lidas, gravadas, rejeitadas) = _execucoes(Sessao, "votacoes_plenario")[-1]
    no_staging = Sessao().execute(text("SELECT count(*) FROM stg.votos_parlamentares")).scalar()
    # 4 votos da Câmara (1 com opção desconhecida) + 3 do Senado (1 de sessão descartada, sem sessão para receber o voto)
    assert (lidas, gravadas, rejeitadas) == (7, 5, 2)
    assert no_staging == 5  # nenhum duplicado no staging, mesmo com `gravadas` contando as linhas já existentes
    assert lidas == gravadas + rejeitadas
    assert status == "COM_ALERTA"  # houve rejeitada
    motivos = (
        Sessao()
        .execute(
            text(
                "SELECT r.motivo, (r.payload->>'total')::int FROM etl.rejeito r JOIN etl.execucao e ON e.id = r.execucao_id "
                "WHERE e.id = (SELECT max(id) FROM etl.execucao WHERE parametros->>'recurso' = 'votacoes_plenario')"
            )
        )
        .all()
    )
    assert [tuple(m) for m in motivos] == [(carga_cadastro.MOTIVO_VOTO, 2)]  # o motivo e o total ficam em etl.rejeito


def test_contagem_do_historico_e_uma_execucao_propria(ambiente, monkeypatch):
    """Os votos das votações históricas têm a execução deles: lidas, gravadas e rejeitadas vêm de `ContagemDeVotos`."""
    dados, Sessao = ambiente
    proposicoes_e_votacoes(dados)
    historico = ContagemDeVotos(lidas=10, gravadas=6, rejeitadas=4).como_contadores()
    monkeypatch.setattr(carga_cadastro, "carregar_votacoes", lambda *a, **k: historico)
    carregar(dados)
    (status, _, _, lidas, gravadas, rejeitadas) = _execucoes(Sessao, "votacoes_historico")[-1]
    assert (lidas, gravadas, rejeitadas) == (10, 6, 4)
    assert status == "COM_ALERTA"
    (_, _, _, lidas, gravadas, rejeitadas) = _execucoes(Sessao, "votacoes_plenario")[-1]
    assert (lidas, gravadas, rejeitadas) == (7, 5, 2)  # o plenário não mistura com o histórico


def test_mandato_preservado_pela_fusao_aparece_no_log(ambiente, monkeypatch, caplog):
    """A 0038 poupa o mandato que algo ainda referencia: a carga avisa quantos ficaram, para não ser silencioso."""
    dados, Sessao = ambiente
    carregar(dados)
    monkeypatch.setattr("app.services.staging_merge.merge_staging", lambda _sessao: {"rejeitos": 0})
    carga = carga_cadastro.CargaCadastro(data_dir=dados, engine=Sessao.engine)

    monkeypatch.setattr(carga_cadastro.CargaCadastro, "_mandatos_preservados", staticmethod(lambda _s: 2))
    with caplog.at_level("WARNING", logger="CargaCadastro"):
        carga._fundir_staging()
    assert any("2 mandatos da fonte LEGADO" in r.message for r in caplog.records)

    caplog.clear()
    monkeypatch.setattr(carga_cadastro.CargaCadastro, "_mandatos_preservados", staticmethod(lambda _s: 0))
    with caplog.at_level("WARNING", logger="CargaCadastro"):
        carga._fundir_staging()
    assert not caplog.records


def test_consulta_de_mandatos_preservados_conta_so_o_mandato_legado_sem_vinculo(ambiente):
    dados, Sessao = ambiente
    carregar(dados)  # aplica as migrações e deixa a fusão normal: nenhum mandato poupado
    with Sessao() as s:
        assert carga_cadastro.CargaCadastro._mandatos_preservados(s) == 0
        fonte = s.execute(text("SELECT id FROM etl.fonte WHERE codigo = 'LEGADO'")).scalar_one()
        pessoa = s.execute(
            text("INSERT INTO core.pessoa (nome_exibicao) VALUES ('Zt Preservado') RETURNING id")
        ).scalar()

        def mandato(cargo, inicio, fonte_id, numero=1):
            return s.execute(
                text(
                    "INSERT INTO core.mandato (pessoa_id, cargo_id, circunscricao_id, inicio, fonte_id, numero_mandato) "
                    "VALUES (:p, (SELECT id FROM ref.cargo WHERE codigo = :c), "
                    "(SELECT id FROM ref.circunscricao WHERE tipo = 'BR'), :i, :f, :n) RETURNING id"
                ),
                {"p": pessoa, "c": cargo, "i": inicio, "f": fonte_id, "n": numero},
            ).scalar_one()

        vinculado = mandato("DEPUTADO_FEDERAL", "2003-02-01", fonte)
        solto = mandato("SENADOR", "2007-02-01", fonte)
        mandato("SENADOR", "2011-02-01", None, numero=2)  # de outra fonte (ou sem fonte): não é do LEGADO
        ligar = text(
            "INSERT INTO core.mandato_legado (legado_id, tabela, mandato_id) VALUES (gen_random_uuid(), 'mandatos', :m)"
        )
        s.execute(ligar, {"m": vinculado})
        # só o `solto`, da fonte LEGADO e sem vínculo
        assert carga_cadastro.CargaCadastro._mandatos_preservados(s) == 1
        s.execute(ligar, {"m": solto})
        assert carga_cadastro.CargaCadastro._mandatos_preservados(s) == 0  # vinculado, deixa de contar
        s.execute(text("DELETE FROM core.mandato_legado WHERE mandato_id IN (:a, :b)"), {"a": vinculado, "b": solto})
        s.execute(text("DELETE FROM core.mandato WHERE pessoa_id = :p"), {"p": pessoa})
        s.execute(text("DELETE FROM core.pessoa WHERE id = :p"), {"p": pessoa})


def test_arquivo_de_votos_so_com_um_dos_lados_deixa_a_execucao_em_alerta(ambiente):
    """Sessões sem os votos (ou o contrário): o par é ignorado e nenhuma contagem acusa; a execução não pode sair OK."""
    dados, Sessao = ambiente
    escrever(dados, "sessoes_votacao_2023.json", [])  # sem votos_nominais_2023.json
    carregar(dados)
    (status, _, erro, lidas, gravadas, rejeitadas) = _execucoes(Sessao, "votacoes_plenario")[-1]
    assert (lidas, gravadas, rejeitadas) == (0, 0, 0) and erro is None  # as contagens fecham
    assert status == "COM_ALERTA"


def test_historico_ilegivel_deixa_a_execucao_em_alerta(ambiente):
    dados, Sessao = ambiente
    (dados / "votacoes").mkdir()
    (dados / "votacoes" / "camara_2023.json.gz").write_bytes(b"isto nao e gzip")
    carregar(dados)
    (status, *_) = _execucoes(Sessao, "votacoes_historico")[-1]
    assert status == "COM_ALERTA"
