"""Conversões numéricas compartilhadas: zero é valor, só None é ausência."""

from app.core.numeros import opt_float, pct


def test_opt_float_preserva_zero_e_none():
    assert opt_float(0) == 0.0 and opt_float(None) is None and opt_float("1.5") == 1.5


def test_pct_arredonda_uma_casa_e_protege_total_zero_ou_negativo():
    assert pct(1, 3) == 33.3 and pct(0, 10) == 0.0 and pct(5, 0) == 0.0
    assert pct(5, -10) == 0.0  # percentual sobre base negativa não faz sentido


def test_brl_formata_em_reais_no_padrao_brasileiro():
    from app.core.numeros import brl

    assert brl(0) == "R$ 0,00"
    assert brl(1234.5) == "R$ 1.234,50"
    assert brl(1234567.891) == "R$ 1.234.567,89"
    assert brl(-10.5) == "R$ -10,50"


def test_o_engine_nao_copia_os_parametros_para_as_mensagens_de_erro():
    from app.core.database import engine

    assert engine.hide_parameters is True
