import pytest

from dxp.cnpj import is_valid, normalize


@pytest.mark.parametrize(
    "cnpj",
    ["28.521.748/0001-59", "28521748000159", "12.ABC.345/01DE-35", "12abc34501de35"],
)
def test_cnpj_valido(cnpj):
    assert is_valid(cnpj)


@pytest.mark.parametrize(
    "cnpj",
    [
        "28.521.748/0001-58",
        "12.ABC.345/01DE-34",
        "00.000.000/0000-00",
        "2852174800015",
        "12.ABC.345/01DE-3X",
    ],
)
def test_cnpj_invalido(cnpj):
    assert not is_valid(cnpj)


def test_normalize_tira_pontuacao_e_poe_maiuscula():
    assert normalize("12.abc.345/01de-35") == "12ABC34501DE35"
