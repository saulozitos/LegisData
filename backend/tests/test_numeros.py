"""Conversões numéricas compartilhadas: zero é valor, só None é ausência."""

from app.core.numeros import opt_float, pct


def test_opt_float_preserva_zero_e_none():
    assert opt_float(0) == 0.0 and opt_float(None) is None and opt_float("1.5") == 1.5


def test_pct_arredonda_uma_casa_e_protege_total_zero_ou_negativo():
    assert pct(1, 3) == 33.3 and pct(0, 10) == 0.0 and pct(5, 0) == 0.0
    assert pct(5, -10) == 0.0  # percentual sobre base negativa não faz sentido
