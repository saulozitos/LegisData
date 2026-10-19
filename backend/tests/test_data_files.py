import pytest
from app.core.data_files import FIRST_SERIES_YEAR, mandate_year_range


@pytest.mark.parametrize(
    "mandate,last_year,expected",
    [
        # fim exclusivo: um mandato que termina em 01/01/AAAA não inclui AAAA
        ({"data_inicio": "2019-01-01", "data_fim": "2023-01-01"}, 2026, (2019, 2022)),
        ({"data_inicio": "2003-01-01", "data_fim": "2011-01-01"}, 2026, (2003, 2010)),
        ({"data_inicio": "2010-01-01", "data_fim": "2014-12-31"}, 2026, (2010, 2014)),
        # sem data de fim: até o último ano da série
        ({"data_inicio": "2023-01-01", "data_fim": None}, 2026, (2023, 2026)),
        # série anterior ao início dos dados é recortada em min_year
        ({"data_inicio": "1992-10-02", "data_fim": "1999-01-01"}, 2026, (1995, 1998)),
    ],
)
def test_mandate_year_range(mandate, last_year, expected):
    assert mandate_year_range(mandate, last_year, FIRST_SERIES_YEAR) == expected


def test_mandate_year_range_never_inverts():
    first, last = mandate_year_range({"data_inicio": "2030-01-01", "data_fim": None}, 2026)
    assert (first, last) == (2030, 2030)
