"""A contagem de votos de uma carga (`ContagemDeVotos`); a cópia dos votos para as planas está em `test_planas_votacoes`."""

import pytest

from etl.pipelines.staging_votos import ContagemDeVotos


def test_contagem_de_votos_soma_campo_a_campo():
    assert ContagemDeVotos(10, 8, 2) + ContagemDeVotos(5, 5, 0, 1) == ContagemDeVotos(15, 13, 2, 1)
    assert ContagemDeVotos() == ContagemDeVotos(0, 0, 0, 0)


def test_contagem_de_votos_vai_e_volta_pelos_contadores_do_resumo():
    contagem = ContagemDeVotos(lidas=10, gravadas=7, rejeitadas=3, arquivos_ignorados=2)
    contadores = contagem.como_contadores()
    assert contadores == {"votos_lidos": 10, "votos_gravados": 7, "votos_descartados": 3, "arquivos_ignorados": 2}
    assert ContagemDeVotos.de_contadores(contadores) == contagem
    with pytest.raises(KeyError):  # chave que falta não vira zero em silêncio
        ContagemDeVotos.de_contadores({"votos_lidos": 1})
