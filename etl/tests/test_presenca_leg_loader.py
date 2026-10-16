from datetime import date

import pytest

from etl.extractors.camara_presenca_eventos_extractor import caminho_do_arquivo
from etl.pipelines.presenca_leg_loader import (
    QUORUM_ABERTURA,
    presencas_por_dia,
    sessoes_deliberativas,
    verificar_arquivos,
)

CAB_EVENTOS = '"id";"uri";"urlDocumentoPauta";"dataHoraInicio";"dataHoraFim";"situacao";"descricao";"descricaoTipo";"localExterno";"localCamara.nome";"localCamara.predio";"localCamara.sala";"localCamara.andar"\n'
CAB_PRESENCA = '"idEvento";"uriEvento";"dataHoraInicio";"idDeputado";"uriDeputado"\n'


def _evento(id_, data, tipo, local):
    return f'"{id_}";"";"";"{data}";"";"Encerrada";"";"{tipo}";"";"{local}";"";"";""\n'


def _gravar(raw, ano, eventos, presencas):
    for recurso, conteudo in (
        ("eventos", CAB_EVENTOS + "".join(eventos)),
        ("eventosPresencaDeputados", CAB_PRESENCA + "".join(presencas)),
    ):
        caminho = caminho_do_arquivo(raw, recurso, ano)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(conteudo, encoding="utf-8-sig")


def test_sessoes_deliberativas_ignora_comissao_e_sessao_nao_deliberativa(tmp_path):
    _gravar(
        tmp_path,
        2010,
        [
            _evento(1, "2010-04-13T15:10:00", "Sessão Deliberativa", "Plenário da Câmara dos Deputados"),
            _evento(2, "2010-04-13T10:00:00", "Reunião Deliberativa", "Anexo II, Plenário 01"),
            _evento(3, "2010-04-14T10:00:00", "Sessão Não Deliberativa Solene", "Plenário da Câmara dos Deputados"),
            _evento(4, "2003-04-15T10:00:00", "Sessão Deliberativa", ""),
        ],
        [],
    )
    assert sessoes_deliberativas(tmp_path, 2010) == {1: date(2010, 4, 13), 4: date(2003, 4, 15)}


def test_sessao_sem_quorum_nao_conta_como_realizada(tmp_path):
    cheia = [f'"1";"";"2010-04-13T15:10:00";"{d}";""\n' for d in range(QUORUM_ABERTURA)]
    vazia = [f'"2";"";"2010-04-14T15:10:00";"{d}";""\n' for d in range(QUORUM_ABERTURA - 1)]
    _gravar(
        tmp_path,
        2010,
        [
            _evento(1, "2010-04-13T15:10:00", "Sessão Deliberativa", "Plenário da Câmara dos Deputados"),
            _evento(2, "2010-04-14T15:10:00", "Sessão Deliberativa", "Plenário da Câmara dos Deputados"),
        ],
        cheia + vazia,
    )
    presencas, dias = presencas_por_dia(tmp_path, 2010)
    assert dias == {date(2010, 4, 13)}
    assert len(presencas) == QUORUM_ABERTURA and (0, date(2010, 4, 13)) in presencas


def test_ano_sem_arquivos_nao_gera_dados(tmp_path):
    assert presencas_por_dia(tmp_path, 1999) == (set(), set())


def test_presenca_em_sessao_sem_quorum_conta_quando_o_dia_foi_realizado(tmp_path):
    """Dois turnos no mesmo dia: quem esteve só na sessão sem quórum não deve receber falta inferida."""
    cheia = [f'"1";"";"2010-04-13T15:10:00";"{d}";""\n' for d in range(QUORUM_ABERTURA)]
    vazia = [f'"2";"";"2010-04-13T21:00:00";"{d}";""\n' for d in (900, 901)]
    _gravar(
        tmp_path,
        2010,
        [
            _evento(1, "2010-04-13T15:10:00", "Sessão Deliberativa", "Plenário da Câmara dos Deputados"),
            _evento(2, "2010-04-13T21:00:00", "Sessão Deliberativa", "Plenário da Câmara dos Deputados"),
        ],
        cheia + vazia,
    )
    presencas, dias = presencas_por_dia(tmp_path, 2010)
    dia = date(2010, 4, 13)
    assert dias == {dia}
    assert {(900, dia), (901, dia)} <= presencas and len(presencas) == QUORUM_ABERTURA + 2


def test_sessao_sem_quorum_sozinha_no_dia_nao_gera_presenca(tmp_path):
    vazia = [f'"2";"";"2010-04-14T15:10:00";"{d}";""\n' for d in range(3)]
    _gravar(
        tmp_path,
        2010,
        [_evento(2, "2010-04-14T15:10:00", "Sessão Deliberativa", "Plenário da Câmara dos Deputados")],
        vazia,
    )
    assert presencas_por_dia(tmp_path, 2010) == (set(), set())


def test_presenca_em_reuniao_de_comissao_nao_conta(tmp_path):
    cheia = [f'"1";"";"2010-04-13T15:10:00";"{d}";""\n' for d in range(QUORUM_ABERTURA)]
    comissao = ['"2";"";"2010-04-13T10:00:00";"999";""\n']
    _gravar(
        tmp_path,
        2010,
        [
            _evento(1, "2010-04-13T15:10:00", "Sessão Deliberativa", "Plenário da Câmara dos Deputados"),
            _evento(2, "2010-04-13T10:00:00", "Reunião Deliberativa", "Anexo II, Plenário 01"),
        ],
        cheia + comissao,
    )
    presencas, _ = presencas_por_dia(tmp_path, 2010)
    assert 999 not in {deputado for deputado, _ in presencas}


def test_linhas_invalidas_sao_puladas_sem_abortar(tmp_path, caplog):
    cheia = [f'"1";"";"2010-04-13T15:10:00";"{d}";""\n' for d in range(QUORUM_ABERTURA)]
    ruins = ['"1";"";"2010-04-13T15:10:00";"";""\n', '"x";"";"2010-04-13T15:10:00";"7";""\n']
    _gravar(
        tmp_path,
        2010,
        [
            _evento(1, "2010-04-13T15:10:00", "Sessão Deliberativa", "Plenário da Câmara dos Deputados"),
            _evento(5, "", "Sessão Deliberativa", "Plenário da Câmara dos Deputados"),  # data vazia
            _evento("abc", "2010-04-15T15:10:00", "Sessão Deliberativa", "Plenário da Câmara dos Deputados"),  # id ruim
        ],
        cheia + ruins,
    )
    with caplog.at_level("WARNING"):
        presencas, dias = presencas_por_dia(tmp_path, 2010)
    assert dias == {date(2010, 4, 13)} and len(presencas) == QUORUM_ABERTURA
    assert "inválid" in caplog.text


def test_verificar_arquivos_recusa_ano_sem_arquivo(tmp_path):
    _gravar(tmp_path, 2010, [], [])
    verificar_arquivos(tmp_path, [2010])  # completo: não levanta
    with pytest.raises(FileNotFoundError, match="eventos-2011.csv"):
        verificar_arquivos(tmp_path, [2010, 2011])
