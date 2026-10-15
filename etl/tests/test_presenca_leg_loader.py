from datetime import date

from etl.extractors.camara_presenca_eventos_extractor import caminho_do_arquivo
from etl.pipelines.presenca_leg_loader import QUORUM_ABERTURA, presencas_por_dia, sessoes_deliberativas

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
