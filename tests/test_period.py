from datetime import date

import pytest

from dxp.period import Period


def test_monthly_cobre_o_periodo_sem_buracos():
    assert Period(date(2025, 10, 15), date(2026, 1, 10)).monthly() == [
        Period(date(2025, 10, 15), date(2025, 10, 31)),
        Period(date(2025, 11, 1), date(2025, 11, 30)),
        Period(date(2025, 12, 1), date(2025, 12, 31)),
        Period(date(2026, 1, 1), date(2026, 1, 10)),
    ]


def test_monthly_periodo_dentro_de_um_mes():
    period = Period(date(2026, 2, 3), date(2026, 2, 20))

    assert period.monthly() == [period]


def test_monthly_fevereiro_de_ano_bissexto():
    assert Period(date(2028, 2, 1), date(2028, 3, 5)).monthly() == [
        Period(date(2028, 2, 1), date(2028, 2, 29)),
        Period(date(2028, 3, 1), date(2028, 3, 5)),
    ]


def test_yearly_divide_em_janelas_de_365_dias():
    assert Period(date(2025, 8, 1), date(2026, 10, 14)).yearly() == [
        Period(date(2025, 8, 1), date(2026, 7, 31)),
        Period(date(2026, 8, 1), date(2026, 10, 14)),
    ]


def test_yearly_periodo_curto_fica_inteiro():
    period = Period(date(2026, 1, 1), date(2026, 1, 31))

    assert period.yearly() == [period]


def test_halves_divide_ao_meio_sem_sobreposicao():
    first, second = Period(date(2025, 10, 1), date(2025, 10, 31)).halves()

    assert first == Period(date(2025, 10, 1), date(2025, 10, 16))
    assert second == Period(date(2025, 10, 17), date(2025, 10, 31))


def test_halves_de_dois_dias():
    first, second = Period(date(2025, 10, 1), date(2025, 10, 2)).halves()

    assert first == Period(date(2025, 10, 1), date(2025, 10, 1))
    assert second == Period(date(2025, 10, 2), date(2025, 10, 2))


@pytest.mark.parametrize(
    ("since", "until", "expected"),
    [(date(2025, 10, 1), date(2025, 10, 1), True), (date(2025, 10, 1), date(2025, 10, 2), False)],
)
def test_is_single_day(since, until, expected):
    assert Period(since, until).is_single_day is expected


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2025, 9, 30), False),
        (date(2025, 10, 1), True),
        (date(2025, 12, 31), True),
        (date(2026, 1, 1), False),
    ],
)
def test_contains_inclui_as_duas_pontas(day, expected):
    assert Period(date(2025, 10, 1), date(2025, 12, 31)).contains(day) is expected
