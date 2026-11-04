"""Catálogo de verificações de carga: funções puras, sem banco."""

from datetime import date

from etl.utils import verificacoes as v


def test_contagem_fecha_quando_tudo_foi_gravado_ou_rejeitado():
    assert v.contagem_fecha("c", 10, 8, 2).passou
    falha = v.contagem_fecha("c", 10, 8, 1)
    assert not falha.passou and falha.detalhe["diferenca"] == -1  # obtido - esperado: falta uma linha
    assert v.contagem_fecha("c", 10, 8, 3).detalhe["diferenca"] == 1  # sobra uma


def test_contagem_desconhecida_nao_passa_nem_vira_zero():
    for medidas in [(None, 1, 0), (1, None, 0), (1, 1, None)]:
        resultado = v.contagem_fecha("c", *medidas)
        assert not resultado.passou and resultado.detalhe["motivo"] == "contagem desconhecida"
    assert v.contagem_fecha("c", 0, 0, 0).passou  # zero medido é diferente de desconhecido


def test_total_informado_pela_fonte_tem_de_bater():
    assert v.total_confere("t", 513, 513).passou
    falha = v.total_confere("t", 513, 510)
    assert not falha.passou and falha.detalhe["diferenca"] == -3
    assert not v.total_confere("t", None, 5).passou and not v.total_confere("t", 5, None).passou


def test_cobertura_minima_e_esperado_zero():
    assert v.cobertura_minima("k", 95, 100, 0.9).passou
    assert not v.cobertura_minima("k", 89, 100, 0.9).passou
    assert v.cobertura_minima("k", 0, 0).passou  # nada esperado, nada obtido
    assert not v.cobertura_minima("k", 3, 0).passou  # veio o que ninguém esperava
    assert v.cobertura_minima("k", 90, 100, 0.9).passou  # no limite exato conta


def test_cobertura_desconhecida_nao_passa_nem_vira_zero():
    for medidas in [(None, 10), (0, None), (None, None)]:
        resultado = v.cobertura_minima("k", *medidas)
        assert not resultado.passou and resultado.detalhe["motivo"] == "medida desconhecida"


def test_diferenca_tem_o_mesmo_sinal_em_todas_as_verificacoes():
    """Obtido - esperado: negativo é falta, positivo é sobra, em contagem_fecha e em total_confere."""
    assert v.contagem_fecha("c", 10, 7, 0).detalhe["diferenca"] < 0 > v.total_confere("t", 10, 7).detalhe["diferenca"]
    assert v.contagem_fecha("c", 10, 12, 0).detalhe["diferenca"] > 0 < v.total_confere("t", 10, 12).detalhe["diferenca"]


def test_sem_nulos_e_sem_duplicatas():
    assert v.sem_nulos("n", "partido", 0).passou and not v.sem_nulos("n", "partido", 2).passou
    assert v.sem_duplicatas("d", [1, 2, 3]).passou
    repetido = v.sem_duplicatas("d", [("a", 1), ("a", 1), ("b", 2)])
    assert not repetido.passou and repetido.detalhe["repetidas"] == 1 and repetido.detalhe["amostra"] == ["('a', 1)"]


def test_duplicatas_guardam_so_uma_amostra():
    resultado = v.sem_duplicatas("d", [chave for i in range(50) for chave in (i, i)])
    assert resultado.detalhe["repetidas"] == 50 and len(resultado.detalhe["amostra"]) == v.AMOSTRA_DO_DETALHE


def test_janela_comeca_em_1995_e_data_ausente_nao_reprova():
    assert v.JANELA_INICIAL == date(1995, 1, 1)
    assert v.dentro_da_janela("j", [date(1995, 1, 1), date(2024, 5, 1), None]).passou
    falha = v.dentro_da_janela("j", [date(1994, 12, 31), date(2000, 1, 1), None])
    assert not falha.passou
    assert falha.detalhe["anteriores"] == 1 and falha.detalhe["desconhecidas"] == 1 and falha.detalhe["total"] == 3
    assert falha.detalhe["amostra"] == ["1994-12-31"]


def test_detalhe_e_serializavel_em_json():
    import json

    for resultado in [
        v.contagem_fecha("c", 1, 1, 0),
        v.sem_duplicatas("d", [1, 1]),
        v.dentro_da_janela("j", [date(1990, 1, 1), None]),
        v.cobertura_minima("k", 1, 3),
    ]:
        json.dumps(resultado.detalhe)  # vai para a coluna jsonb de etl.verificacao
