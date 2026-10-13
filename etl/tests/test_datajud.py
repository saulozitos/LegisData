"""Testes para a integração oficial com a API do DataJud (CNJ)."""

from unittest.mock import MagicMock

import pytest
from app.models.base import Base
from app.models.politician import ProcessoJudicial
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from etl.extractors.processos_loader import populate_processos_judiciais
from etl.utils.datajud_client import DataJudClient, deduzir_aliases_datajud, parse_cnj_parts


@pytest.fixture
def sessao():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, autoflush=False)() as s:
        yield s


def test_parse_cnj_parts_formatado():
    res = parse_cnj_parts("0600814-85.2022.6.00.0000")
    assert res is not None
    assert res["sequencial"] == "0600814"
    assert res["digito"] == "85"
    assert res["ano"] == "2022"
    assert res["segmento"] == "6"
    assert res["tribunal"] == "00"
    assert res["origem"] == "0000"
    assert res["limpo"] == "06008148520226000000"
    assert res["formatado"] == "0600814-85.2022.6.00.0000"


def test_parse_cnj_parts_limpo():
    res = parse_cnj_parts("06008148520226000000")
    assert res is not None
    assert res["limpo"] == "06008148520226000000"
    assert res["formatado"] == "0600814-85.2022.6.00.0000"


def test_parse_cnj_parts_invalido():
    assert parse_cnj_parts("123") is None
    assert parse_cnj_parts("Inq 4878 / DF") is None


def test_deduzir_aliases_datajud():
    # TSE
    p_tse = parse_cnj_parts("0600814-85.2022.6.00.0000")
    assert "api_publica_tse" in deduzir_aliases_datajud(p_tse)

    # TRE-PR
    p_tre = parse_cnj_parts("0604176-51.2022.6.16.0000")
    assert "api_publica_tre-pr" in deduzir_aliases_datajud(p_tre)

    # TRF-1
    p_trf1 = parse_cnj_parts("1026137-89.2019.4.01.3400")
    assert "api_publica_trf1" in deduzir_aliases_datajud(p_trf1)

    # STJ
    p_stj = parse_cnj_parts("0000001-00.2020.3.00.0000")
    assert "api_publica_stj" in deduzir_aliases_datajud(p_stj)


def test_consolidar_resumo_processo():
    sample_source = {
        "numeroProcesso": "06008148520226000000",
        "tribunal": "TSE",
        "grau": "SUP",
        "dataAjuizamento": "2022-08-19T14:30:55.000Z",
        "classe": {"codigo": 11527, "nome": "Ação de Investigação Judicial Eleitoral"},
        "assuntos": [{"codigo": 11682, "nome": "Abuso de Poder"}],
        "orgaoJulgador": {"codigo": 100, "nome": "Plenário do TSE"},
        "movimentos": [
            {"dataHora": "2023-06-30T12:00:00.000Z", "nome": "Julgamento de Mérito - Procedência"},
            {"dataHora": "2022-08-20T10:00:00.000Z", "nome": "Distribuição"},
        ],
    }
    summary = DataJudClient.consolidar_resumo_processo(sample_source)
    assert summary["numero_processo"] == "06008148520226000000"
    assert summary["tribunal"] == "TSE"
    assert summary["classe_tpu_nome"] == "Ação de Investigação Judicial Eleitoral"
    assert "Abuso de Poder" in summary["classe_assunto"]
    assert summary["data_processo"] == "2022-08-19"
    assert summary["total_movimentacoes"] == 2
    assert summary["ultimo_movimento"] == "Julgamento de Mérito - Procedência"
    assert summary["is_synthetic"] is False


def test_populate_processos_com_datajud_mock(sessao):
    from etl.tests.test_scripts_and_legal import politico

    politico(sessao, "Jair Bolsonaro", "Jair Messias Bolsonaro")
    sessao.commit()

    mock_client = MagicMock(spec=DataJudClient)
    mock_client.consultar_processo.side_effect = lambda num: (
        {
            "numeroProcesso": num,
            "tribunal": "TSE",
            "grau": "SUP",
            "dataAjuizamento": "2022-08-19",
            "classe": {"codigo": 11527, "nome": "AIJE"},
            "assuntos": [{"nome": "Abuso"}],
            "orgaoJulgador": {"nome": "TSE"},
            "movimentos": [{"dataHora": "2023-06-30", "nome": "Julgado"}],
        }
        if "0600814" in str(num)
        else None
    )

    mock_client.consolidar_resumo_processo.side_effect = DataJudClient.consolidar_resumo_processo

    inseridos = populate_processos_judiciais(sessao, use_datajud=True, allow_unverified=False, client=mock_client)
    assert inseridos == 1
    procs = sessao.query(ProcessoJudicial).all()
    assert len(procs) == 1
    assert "0600814" in procs[0].process_number
    assert "CNJ / DataJud" in procs[0].court_agency
