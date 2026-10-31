import pytest

from dxp.ids import ALPHANUMERIC_ID, TERRITORY_ID, checked_id


@pytest.mark.parametrize(
    ("pattern", "value"), [(TERRITORY_ID, "3304557"), (ALPHANUMERIC_ID, "28521748000159")]
)
def test_aceita_identificador_valido(pattern, value):
    assert checked_id(pattern, value, "id") == value


@pytest.mark.parametrize(
    ("pattern", "value"),
    [
        (TERRITORY_ID, "330455"),
        (TERRITORY_ID, "33045577"),
        (TERRITORY_ID, "../etc"),
        (TERRITORY_ID, "3304557\n"),
        (ALPHANUMERIC_ID, ""),
        (ALPHANUMERIC_ID, "../x"),
        (ALPHANUMERIC_ID, "a/b"),
    ],
)
def test_recusa_identificador_que_vira_caminho(pattern, value):
    with pytest.raises(ValueError, match="inválido"):
        checked_id(pattern, value, "id")
