"""Cargas do TSE no banco (SQLite em memória): idempotência, proveniência e ausência de dados inventados."""

import json
from pathlib import Path

import pytest
from app.models import Base, CertidaoJudicial, DoacaoCampanha, Politician, StatePresidentialElectionResult
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from etl.extractors.tse_eleicoes_extractor import CAMPOS
from etl.pipelines import tse_loaders
from etl.utils.provenance import mark_official, mark_synthetic


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as s:
        yield s


@pytest.fixture
def politicos(session):
    ana = Politician(civil_name="Ana Souza Lima", electoral_name="Ana Lima", camara_id=1)
    bia = Politician(civil_name="Bia Costa", electoral_name="Bia", senado_id=7)
    d1 = Politician(civil_name="Duda Silva", electoral_name="Duda Silva")
    d2 = Politician(civil_name="Duda Silva", electoral_name="Duda S.")  # homônimo: nome ambíguo
    session.add_all([ana, bia, d1, d2])
    session.flush()
    return {"ana": ana, "bia": bia, "duda": d1}


def escrever(pasta: Path, nome: str, conteudo) -> None:
    (pasta / nome).write_text(json.dumps(conteudo, ensure_ascii=False), encoding="utf-8")


def prestacao(ano=2022, valor=100.0, **ids):
    return mark_official(
        {
            "camara_id": None,
            "senado_id": None,
            "nome_civil": "",
            "nome_eleitoral": "",
            "ano_eleicao": ano,
            "total_arrecadado": valor,
            "doadores": [
                {
                    "nome_doador": "Fulano",
                    "cpf_cnpj_doador": "***.456.789-**",
                    "valor_doado": valor,
                    "tipo_receita": "PF",
                }
            ],
            **ids,
        },
        "TSE — teste",
    )


# ----------------------------------------------------------------------------------------------------------
def test_resolver_prefere_id_oficial_e_recusa_nome_ambiguo(session, politicos):
    r = tse_loaders.PoliticoResolver(session)
    assert r.resolver({"camara_id": 1, "nome_civil": "qualquer"}) == politicos["ana"].id
    assert r.resolver({"senado_id": 7}) == politicos["bia"].id
    assert r.resolver({"nome_civil": "Bia Costa"}) == politicos["bia"].id
    assert r.resolver({"nome_civil": "Duda Silva"}) is None  # dois políticos com o mesmo nome
    assert r.resolver({"nome_civil": "Quem?"}) is None


def test_doacoes_idempotentes_e_substituem_o_conjunto_do_ano(session, politicos, tmp_path):
    escrever(tmp_path, "tse_doacoes_campanha.json", [prestacao(camara_id=1, valor=100.0)])
    assert tse_loaders.carregar_doacoes(session, tmp_path)["linhas"] == 1
    tse_loaders.carregar_doacoes(session, tmp_path)
    assert session.query(DoacaoCampanha).count() == 1

    escrever(tmp_path, "tse_doacoes_campanha.json", [prestacao(camara_id=1, valor=250.0)])
    tse_loaders.carregar_doacoes(session, tmp_path)
    linhas = session.query(DoacaoCampanha).all()
    assert [float(d.amount_donated) for d in linhas] == [250.0]
    assert linhas[0].donor_cpf_cnpj == "***.456.789-**" and linhas[0].politician_id == politicos["ana"].id


def test_doacoes_ignoram_sintetico_legado_e_politico_desconhecido(session, politicos, tmp_path):
    sintetico = mark_synthetic(prestacao(camara_id=1))
    legado = {k: v for k, v in prestacao(camara_id=1).items() if k not in ("fonte", "is_synthetic")}
    escrever(tmp_path, "tse_doacoes_campanha.json", [sintetico, legado, prestacao(camara_id=999, nome_civil="Ninguém")])
    res = tse_loaders.carregar_doacoes(session, tmp_path)
    assert res == {"linhas": 0, "prestacoes": 0, "sem_politico": 1, "ignoradas": 2}
    assert session.query(DoacaoCampanha).count() == 0


def test_doacoes_sem_arquivo_nao_apaga_nada(session, politicos, tmp_path):
    session.add(DoacaoCampanha(politician_id=politicos["ana"].id, election_year=2022, donor_name="X", amount_donated=1))
    session.flush()
    assert tse_loaders.carregar_doacoes(session, tmp_path)["linhas"] == 0
    assert session.query(DoacaoCampanha).count() == 1


def ocorrencia(**extra):
    return mark_official(
        {
            "camara_id": 1,
            "nome_civil": "",
            "nome_eleitoral": "",
            "ano_eleicao": 2010,
            "orgao": "TSE",
            "tipo_certidao": "Registro de candidatura 2010 - Deputado Federal",
            "status_ficha": "Declarada: registro indeferido",
            "detalhes": "Eleição 2010. Situação da candidatura: INAPTO.",
            "numero_processo": "123",
            **extra,
        },
        "TSE — teste",
    )


def test_certidoes_tse_inserem_e_atualizam_pela_chave_natural(session, politicos, tmp_path):
    escrever(tmp_path, "certidoes_tse.json", [ocorrencia()])
    assert tse_loaders.carregar_certidoes_tse(session, tmp_path)["inseridas"] == 1
    escrever(tmp_path, "certidoes_tse.json", [ocorrencia(detalhes="Texto novo.", numero_processo=None)])
    res = tse_loaders.carregar_certidoes_tse(session, tmp_path)
    assert res["inseridas"] == 0 and res["atualizadas"] == 1
    cert = session.query(CertidaoJudicial).one()
    assert cert.details == "Texto novo." and cert.process_number is None
    assert cert.court_agency == "TSE" and "positiva" not in cert.status.lower() and "declarada" in cert.status.lower()
    assert cert.auth_code is None and cert.issue_date is None  # nada inventado


def test_certidoes_ignoram_registro_sem_proveniencia(session, politicos, tmp_path):
    sem_fonte = {k: v for k, v in ocorrencia().items() if k not in ("fonte", "is_synthetic")}
    escrever(tmp_path, "certidoes_tse.json", [sem_fonte])
    assert tse_loaders.carregar_certidoes_tse(session, tmp_path)["ignoradas"] == 1
    assert session.query(CertidaoJudicial).count() == 0


def escrever_eleicoes(pasta: Path, **sobrescrever):
    import csv

    linha = dict(
        ano_eleicao=2022,
        mandato_id_ref="lula-2023",
        uf="MG",
        estado_nome="Minas Gerais",
        regiao="Sudeste",
        candidato_vencedor_nome="A",
        partido_vencedor_sigla="P1",
        votos_vencedor_pct="50.2",
        candidato_segundo_nome="B",
        partido_segundo_sigla="P2",
        votos_segundo_pct="49.8",
        total_votos_validos=1000,
        turno=2,
        verificado=True,
        is_synthetic=False,
        fonte="TSE",
    )
    linha.update(sobrescrever)
    with open(pasta / "eleicoes_presidenciais_uf_tse.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS)
        w.writeheader()
        w.writerow(linha)


def test_eleicoes_tse_idempotentes(session, tmp_path):
    escrever_eleicoes(tmp_path)
    assert tse_loaders.carregar_eleicoes_tse(session, tmp_path) == 1
    escrever_eleicoes(tmp_path, votos_vencedor_pct="51.0")
    assert tse_loaders.carregar_eleicoes_tse(session, tmp_path) == 1
    linha = session.query(StatePresidentialElectionResult).one()
    assert float(linha.winner_votes_pct) == 51.0 and linha.total_valid_votes == 1000 and linha.round_number == 2


def test_eleicoes_nao_verificadas_ou_ausentes_nao_sao_carregadas(session, tmp_path):
    assert tse_loaders.carregar_eleicoes_tse(session, tmp_path) == 0  # sem arquivo
    escrever_eleicoes(tmp_path, verificado=False)
    assert tse_loaders.carregar_eleicoes_tse(session, tmp_path) == 0
    assert session.query(StatePresidentialElectionResult).count() == 0


# ----------------------------------------------------------------------------------------------------------
# ligação com o DatabaseLoader
# ----------------------------------------------------------------------------------------------------------
def test_database_loader_carrega_doacoes_e_registro_do_tse_sem_flag_sintetica(session, politicos, tmp_path):
    from etl.pipelines.db_loader import DatabaseLoader

    escrever(tmp_path, "tse_doacoes_campanha.json", [prestacao(camara_id=1)])
    escrever(tmp_path, "certidoes_tse.json", [ocorrencia()])
    loader = DatabaseLoader(data_dir=tmp_path)  # allow_synthetic=False: só dados oficiais
    loader._load_certidoes_judiciais(session)
    loader._load_doacoes_campanha(session)
    assert session.query(DoacaoCampanha).count() == 1
    assert session.query(CertidaoJudicial).one().court_agency == "TSE"


def test_apuracao_do_tse_substitui_o_csv_digitado_a_mao(session, tmp_path):
    from etl.pipelines.db_loader import DatabaseLoader

    escrever_eleicoes(tmp_path, candidato_vencedor_nome="Oficial")
    (tmp_path / "resultados_eleicoes_presidenciais_uf.csv").write_text(
        "ano_eleicao,mandato_id_ref,uf,estado_nome,regiao,candidato_vencedor_nome,partido_vencedor_sigla,"
        "votos_vencedor_pct,candidato_segundo_nome,partido_segundo_sigla,votos_segundo_pct,turno,verificado\n"
        "2022,lula-2023,MG,Minas Gerais,Sudeste,Digitado,PT,99,X,PL,1,2,True\n",
        encoding="utf-8",
    )
    DatabaseLoader(data_dir=tmp_path, allow_unverified=True)._load_social_and_election_data(session)
    assert [r.winner_candidate_name for r in session.query(StatePresidentialElectionResult).all()] == ["Oficial"]


def test_loader_legado_tambem_nao_grava_cpf_no_nome_do_doador_nem_nos_detalhes_da_certidao(
    session, politicos, tmp_path
):
    registro = prestacao(camara_id=1, valor=10.0)
    registro["doadores"][0]["nome_doador"] = "MEI 111.222.333-44"
    escrever(tmp_path, "tse_doacoes_campanha.json", [registro])
    tse_loaders.carregar_doacoes(session, tmp_path)
    assert session.query(DoacaoCampanha).one().donor_name == "MEI"

    escrever(tmp_path, "certidoes_tse.json", [ocorrencia(detalhes="Réu 111.222.333-44 em processo")])
    tse_loaders.carregar_certidoes_tse(session, tmp_path)
    assert session.query(CertidaoJudicial).one().details == "Réu em processo"


def test_loader_legado_mascara_o_cpf_completo_do_doador(session, politicos, tmp_path):
    registro = prestacao(camara_id=1, valor=10.0)
    registro["doadores"][0]["cpf_cnpj_doador"] = "111.222.333-44"
    escrever(tmp_path, "tse_doacoes_campanha.json", [registro])
    tse_loaders.carregar_doacoes(session, tmp_path)
    assert session.query(DoacaoCampanha).one().donor_cpf_cnpj == "***.222.333-**"
