"""Extrator de processos: enriquece a curadoria com o DataJud e só deixa passar o que o tribunal confirma."""

import json
from datetime import date

import pytest

from etl.config import PROCESSED_DATA_DIR, PROCESSOS_ARQUIVO, PROCESSOS_CURADORIA_ARQUIVO
from etl.extractors import processos_extractor as ext
from etl.pipelines.loader_helpers import cnj_digitos, cnj_valido, ler_processo, link_oficial, sob_sigilo
from etl.tests.sinteticos import CPF_A
from etl.utils.datajud_client import PROVENIENCIA_DATAJUD, DataJudClient, ErroDoDataJud

CNJ_A = "0000001-78.2020.8.26.0100"  # número sintético com dígitos verificadores corretos
CNJ_B = "0000002-46.2021.4.03.6100"
LINK = "https://exemplo.jus.br/processo/1"
LARGURA_TOTAL = {ord(c): ord(c) + 0xFEE0 for c in "0123456789"}  # dígitos de largura total (U+FF10..U+FF19)
ARABE_INDICO = {ord(c): ord(c) + 0x0660 - ord("0") for c in "0123456789"}  # U+0660..U+0669


class _ClienteFalso:
    """DataJud em memória: devolve a fonte do processo pedido; um valor que é exceção é levantado."""

    def __init__(self, base, consolidar=DataJudClient.consolidar_resumo_processo):
        self.base = base
        self.consultas = []
        self.consolidar_resumo_processo = consolidar

    def consultar_processo(self, numero):
        self.consultas.append(numero)
        achado = self.base.get(numero)
        if isinstance(achado, Exception):
            raise achado
        return achado


def _cnj_do_stf():
    """Número de processo do STF (J=1) com dígitos verificadores corretos: o DataJud não tem índice para ele."""
    corpo = "0000003" + "2020" + "1" + "00" + "0000"
    return f"0000003-{98 - int(corpo + '00') % 97:02d}.2020.1.00.0000"


def _fonte(numero, **extra):
    return {
        "numeroProcesso": numero.replace("-", "").replace(".", ""),
        "tribunal": "TJSP",
        "grau": "G1",
        "nivelSigilo": 0,
        "dataAjuizamento": "2020-03-04T00:00:00.000Z",
        "classe": {"codigo": 7, "nome": "Procedimento Comum Cível"},
        "assuntos": [{"nome": "Improbidade Administrativa"}],
        "orgaoJulgador": {"nome": "1ª Vara Cível"},
        "movimentos": [{"dataHora": "2024-05-06T10:00:00", "nome": "Conclusão"}],
        **extra,
    }


def _entrada(**campos):
    return {"nome_civil": "Ana Souza", "camara_id": 100, "numero_processo": CNJ_A, "link_comprovacao": LINK, **campos}


def _gravar(pasta, nome, conteudo):
    (pasta / nome).write_text(json.dumps(conteudo), encoding="utf-8")


def _ler(pasta, nome):
    return json.loads((pasta / nome).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "numero, esperado",
    [
        (CNJ_A, CNJ_A),
        (CNJ_B, CNJ_B),
        ("0600814-85.2022.6.00.0000", "0600814-85.2022.6.00.0000"),  # número real, confere o algoritmo
        ("0600814-86.2022.6.00.0000", None),  # dígito verificador errado
        ("06008148520226000000", None),  # sem a formatação
        ("0600814-85.2022.6.00.0000 ", "0600814-85.2022.6.00.0000"),  # espaço nas pontas é aparado
        ("0600814-85.2022.6.00.0000\n0", None),  # `$` casaria antes de uma quebra de linha; fullmatch não
        ("AIJE 0600814-85.2022.6.00.0000", None),  # texto em volta
        (CNJ_A.translate(LARGURA_TOTAL), None),  # dígitos de largura total: o CHECK do banco os recusa
        (CNJ_A.translate(ARABE_INDICO), None),  # dígitos árabe-índicos
        ("6527", None),
        (None, None),
        (6527, None),
    ],
)
def test_cnj_valido_so_aceita_o_formato_exato_ascii_com_digitos_verificadores(numero, esperado):
    assert cnj_valido(numero) == esperado


def test_enriquecer_junta_a_pessoa_da_curadoria_com_os_metadados_do_datajud():
    cliente = _ClienteFalso({CNJ_A: _fonte(CNJ_A)})
    processos, contagem = ext.enriquecer([_entrada()], cliente, hoje=date(2026, 10, 26))
    assert contagem == {}
    (p,) = processos
    assert (p["nome_civil"], p["camara_id"]) == ("Ana Souza", 100)
    assert p["numero_processo"] == CNJ_A and p["link_comprovacao"] == LINK
    assert p["classe_tpu_nome"] == "Procedimento Comum Cível" and p["assuntos_tpu"] == ["Improbidade Administrativa"]
    assert p["orgao_julgador"] == "1ª Vara Cível" and p["data_processo"] == "2020-03-04"
    assert p["ultimo_movimento"] == "Conclusão" and p["data_ultimo_movimento"] == "2024-05-06"
    assert p["fonte"] == PROVENIENCIA_DATAJUD and p["is_synthetic"] is False
    assert p["consultado_em"] == "2026-10-26"  # o andamento é o do dia da consulta
    assert "nivel_sigilo" not in p  # só serve para decidir; não vai para o arquivo
    assert cliente.consultas == [CNJ_A]
    assert ler_processo(p)[1] is None  # o que o extrator grava é exatamente o que a carga aceita


@pytest.mark.parametrize(
    "entrada, base, motivo, consultado",
    [
        (_entrada(numero_processo=CNJ_B), {}, "nao_encontrados", True),  # válido, mas o DataJud não conhece
        (_entrada(numero_processo="0000001-79.2020.8.26.0100"), {}, "invalidas", False),  # dígito verificador errado
        (_entrada(link_comprovacao=None), {}, "invalidas", False),  # sem a fonte que liga o processo à pessoa
        (_entrada(link_comprovacao="javascript:alert(1)"), {}, "invalidas", False),
        (_entrada(link_comprovacao="https://exemplo.jus.br/a b"), {}, "invalidas", False),  # espaço no link
        (_entrada(link_comprovacao="http://exemplo.jus.br/p"), {}, "invalidas", False),  # sem TLS
        (_entrada(link_comprovacao="https://exemplo.com/p"), {}, "invalidas", False),  # fonte que não é oficial
        (_entrada(numero_processo=_cnj_do_stf()), {}, "sem_cobertura", False),  # o STF não está no DataJud
        ("lixo", {}, "invalidas", False),
        (_entrada(), {CNJ_A: _fonte(CNJ_A, nivelSigilo=1)}, "sigilosos", True),
        (_entrada(), {CNJ_A: _fonte(CNJ_A, nivelSigilo="abc")}, "sigilosos", True),  # ilegível: na dúvida, não publica
        (_entrada(), {CNJ_A: _fonte(CNJ_A, nivelSigilo=True)}, "sigilosos", True),
        (_entrada(), {CNJ_A: _fonte(CNJ_B)}, "divergentes", True),  # o DataJud devolveu outro processo
        (_entrada(), {CNJ_A: _fonte(CNJ_A, classe=None)}, "sem_classe", True),
        (_entrada(), {CNJ_A: _fonte(CNJ_A, classe={"codigo": 7})}, "sem_classe", True),
        (_entrada(), {CNJ_A: _fonte(CNJ_A, classe={"nome": "  "})}, "sem_classe", True),
    ],
)
def test_processo_que_nao_se_confirma_fica_de_fora_e_e_contado(entrada, base, motivo, consultado):
    cliente = _ClienteFalso(base)
    processos, contagem = ext.enriquecer([entrada], cliente)
    assert processos == [] and contagem == {motivo: 1}
    assert bool(cliente.consultas) is consultado


@pytest.mark.parametrize("nivel", [None, 0, "0", " 0 "])
def test_sem_sigilo_informado_o_processo_entra(nivel):
    processos, contagem = ext.enriquecer([_entrada()], _ClienteFalso({CNJ_A: _fonte(CNJ_A, nivelSigilo=nivel)}))
    assert len(processos) == 1 and contagem == {}


def test_documento_malformado_nao_derruba_o_lote():
    def quebra(_origem):
        raise TypeError("documento inesperado")

    cliente = _ClienteFalso({CNJ_A: _fonte(CNJ_A), CNJ_B: _fonte(CNJ_B)}, consolidar=quebra)
    processos, contagem = ext.enriquecer([_entrada(), _entrada(numero_processo=CNJ_B)], cliente)
    assert processos == [] and contagem == {"malformados": 2}


def test_documento_com_movimento_sem_data_e_assunto_sem_nome_entra_sem_quebrar():
    fonte = _fonte(
        CNJ_A,
        movimentos=[
            {"dataHora": None, "nome": "Sem data"},
            {"dataHora": "2024-05-06T10:00:00", "nome": "Conclusão"},
            "x",
        ],
        assuntos=[{"nome": 7}, {"nome": None}, {"nome": "Improbidade"}, "x"],
    )
    (p,), contagem = ext.enriquecer([_entrada()], _ClienteFalso({CNJ_A: fonte}))
    assert contagem == {} and p["ultimo_movimento"] == "Conclusão" and p["assuntos_tpu"] == ["Improbidade"]


@pytest.mark.parametrize(
    "link",
    [
        f"https://esaj.exemplo.jus.br/cpopg/search.do?cbPesquisa=DOCPARTE&valor={CPF_A}",  # consulta por documento da parte
        f"https://exemplo.jus.br/a?doc={CPF_A[:3]}.{CPF_A[3:6]}.{CPF_A[6:9]}-{CPF_A[9:]}",
        f"https://exemplo.jus.br/a?doc={CPF_A[:3]}%2E{CPF_A[3:6]}%2E{CPF_A[6:9]}%2D{CPF_A[9:]}",  # codificado
        f"https://exemplo.jus.br/a?doc={CPF_A[:3]}%252E{CPF_A[3:6]}%252E{CPF_A[6:9]}%252D{CPF_A[9:]}",  # codificado duas vezes
        "https://usuario:senha@exemplo.jus.br/p",  # credencial embutida
        "https://exemplo.jus.br.mal.com/p",  # o domínio oficial é só um prefixo
        "https://exemplo.jus.br/a\u2003b",  # espaço Unicode: o CHECK do banco recusaria
        "https://jus.br/p",  # o sufixo sozinho
    ],
)
def test_link_com_cpf_ou_fora_de_fonte_oficial_e_recusado_inteiro(link):
    assert link_oficial(link) is None
    processos, contagem = ext.enriquecer([_entrada(link_comprovacao=link)], _ClienteFalso({CNJ_A: _fonte(CNJ_A)}))
    assert processos == [] and contagem == {"invalidas": 1}


@pytest.mark.parametrize(
    "link",
    [
        "https://www.tjsp.jus.br/processo/1",
        "https://pje.tse.jus.br/pje/ConsultaPublica/listView.seam?numero=0600814-85.2022.6.00.0000",
        "https://www.camara.leg.br/deputados/204514",
        "https://www.gov.br/pgr/pt-br/p",
        "https://www.mpf.mp.br/p",
    ],
)
def test_link_oficial_de_orgao_publico_passa(link):
    assert link_oficial(link) == link


def test_texto_do_datajud_vai_para_o_arquivo_sem_cpf():
    fonte = _fonte(
        CNJ_A,
        orgaoJulgador={"nome": f"Vara do réu {CPF_A}"},
        assuntos=[{"nome": f"Assunto {CPF_A}"}, {"nome": "Improbidade"}],
        movimentos=[{"dataHora": "2024-05-06T10:00:00", "nome": f"Juntada de petição de {CPF_A}"}],
    )
    (p,), contagem = ext.enriquecer([_entrada()], _ClienteFalso({CNJ_A: fonte}))
    assert contagem == {} and CPF_A not in json.dumps(p, ensure_ascii=False)
    assert "Improbidade" in p["assuntos_tpu"]


def test_processo_ja_publicado_que_some_do_datajud_aborta_em_vez_de_ser_retirado(tmp_path):
    _gravar(tmp_path, PROCESSOS_CURADORIA_ARQUIVO, [_entrada(), _entrada(numero_processo=CNJ_B)])
    _gravar(tmp_path, PROCESSOS_ARQUIVO, [{"numero_processo": CNJ_A}])
    with pytest.raises(ErroDoDataJud):
        ext.extrair(tmp_path, _ClienteFalso({CNJ_A: None, CNJ_B: _fonte(CNJ_B)}))
    assert _ler(tmp_path, PROCESSOS_ARQUIVO) == [{"numero_processo": CNJ_A}]  # nada foi alterado


def test_retirar_o_vinculo_publicado_e_so_pela_curadoria(tmp_path):
    _gravar(tmp_path, PROCESSOS_CURADORIA_ARQUIVO, [_entrada(numero_processo=CNJ_B)])
    _gravar(tmp_path, PROCESSOS_ARQUIVO, [{"numero_processo": CNJ_A}])
    assert ext.extrair(tmp_path, _ClienteFalso({CNJ_B: _fonte(CNJ_B)})) == {"processos": 1}
    assert [x["numero_processo"] for x in _ler(tmp_path, PROCESSOS_ARQUIVO)] == [CNJ_B]


def test_processo_nunca_visto_que_o_datajud_nao_acha_continua_so_contado(tmp_path):
    _gravar(tmp_path, PROCESSOS_CURADORIA_ARQUIVO, [_entrada()])
    _gravar(tmp_path, PROCESSOS_ARQUIVO, [{"numero_processo": CNJ_B}])
    assert ext.extrair(tmp_path, _ClienteFalso({})) == {"nao_encontrados": 1, "processos": 0}


def test_cnj_digitos_e_sob_sigilo():
    assert cnj_digitos(CNJ_A) == "00000017820208260100" and cnj_digitos(None) == ""
    assert [sob_sigilo(n) for n in (None, 0, "0", 1, "abc", True, False)] == [
        False,
        False,
        False,
        True,
        True,
        True,
        False,
    ]


def test_falha_do_datajud_conta_como_erro_e_nao_como_nao_encontrado():
    cliente = _ClienteFalso({CNJ_A: ErroDoDataJud("503"), CNJ_B: _fonte(CNJ_B)})
    processos, contagem = ext.enriquecer([_entrada(), _entrada(numero_processo=CNJ_B)], cliente)
    assert [p["numero_processo"] for p in processos] == [CNJ_B] and contagem == {"erros": 1}


def test_extrair_grava_o_arquivo_da_carga(tmp_path):
    _gravar(tmp_path, PROCESSOS_CURADORIA_ARQUIVO, [_entrada()])
    assert ext.extrair(tmp_path, _ClienteFalso({CNJ_A: _fonte(CNJ_A)})) == {"processos": 1}
    assert [x["numero_processo"] for x in _ler(tmp_path, PROCESSOS_ARQUIVO)] == [CNJ_A]


def test_falha_do_datajud_em_algum_processo_nao_grava_nada_e_o_arquivo_anterior_fica(tmp_path):
    _gravar(tmp_path, PROCESSOS_CURADORIA_ARQUIVO, [_entrada(), _entrada(numero_processo=CNJ_B)])
    _gravar(tmp_path, PROCESSOS_ARQUIVO, [{"antigo": True}])
    cliente = _ClienteFalso({CNJ_A: _fonte(CNJ_A), CNJ_B: ErroDoDataJud("429")})
    with pytest.raises(ErroDoDataJud, match="1 processo"):
        ext.extrair(tmp_path, cliente)
    assert _ler(tmp_path, PROCESSOS_ARQUIVO) == [{"antigo": True}]


def test_curadoria_esvaziada_de_proposito_grava_lista_vazia_e_retira_o_vinculo(tmp_path):
    _gravar(tmp_path, PROCESSOS_ARQUIVO, [{"antigo": True}])
    _gravar(tmp_path, PROCESSOS_CURADORIA_ARQUIVO, [])
    cliente = _ClienteFalso({})
    assert ext.extrair(tmp_path, cliente) == {"processos": 0}
    assert _ler(tmp_path, PROCESSOS_ARQUIVO) == [] and cliente.consultas == []


def test_curadoria_cujos_processos_nenhum_se_confirma_tambem_retira_o_que_nao_se_sustenta(tmp_path):
    _gravar(tmp_path, PROCESSOS_ARQUIVO, [{"antigo": True}])
    _gravar(tmp_path, PROCESSOS_CURADORIA_ARQUIVO, [_entrada()])
    assert ext.extrair(tmp_path, _ClienteFalso({})) == {"nao_encontrados": 1, "processos": 0}
    assert _ler(tmp_path, PROCESSOS_ARQUIVO) == []


@pytest.mark.parametrize("curadoria", [None, {"a": 1}, "texto"])
def test_curadoria_ausente_ou_que_nao_e_lista_nao_altera_nada(tmp_path, curadoria):
    _gravar(tmp_path, PROCESSOS_ARQUIVO, [{"antigo": True}])
    if curadoria is not None:
        _gravar(tmp_path, PROCESSOS_CURADORIA_ARQUIVO, curadoria)
    cliente = _ClienteFalso({})
    assert ext.extrair(tmp_path, cliente) == {"processos": 0}
    assert _ler(tmp_path, PROCESSOS_ARQUIVO) == [{"antigo": True}] and cliente.consultas == []


def test_extrair_sem_curadoria_nao_cria_arquivo(tmp_path):
    assert ext.extrair(tmp_path, _ClienteFalso({})) == {"processos": 0}
    assert not (tmp_path / PROCESSOS_ARQUIVO).exists()


def test_arquivos_versionados_sao_rastreaveis_e_o_gerado_acompanha_a_curadoria():
    """
    O acervo manual deixou de existir (D7): todo processo versionado tem número CNJ, link oficial, tribunal coberto pelo
    DataJud e proveniência. O gerado tem exatamente os números da curadoria: uma entrada que o DataJud não confirma sai
    da curadoria, e uma entrada nova sem `--processos` rodado é pega aqui (o deploy só olha o arquivo gerado).
    """
    curadoria = _ler(PROCESSED_DATA_DIR, PROCESSOS_CURADORIA_ARQUIVO)
    gerado = _ler(PROCESSED_DATA_DIR, PROCESSOS_ARQUIVO)
    assert isinstance(curadoria, list) and isinstance(gerado, list)
    for item in curadoria:
        assert cnj_valido(item.get("numero_processo")), item
        assert link_oficial(item.get("link_comprovacao")), item
        assert ext.cobertura_do_datajud(item["numero_processo"]), item
    numeros_da_curadoria = {item["numero_processo"] for item in curadoria}
    for item in gerado:
        lido, motivo = ler_processo(item)  # a mesma regra que a carga aplica
        assert motivo is None and lido["numero"] in numeros_da_curadoria
        assert item["link_comprovacao"] in {c["link_comprovacao"] for c in curadoria}
    assert {i["numero_processo"] for i in gerado} == numeros_da_curadoria
