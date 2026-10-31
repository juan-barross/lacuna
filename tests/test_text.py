import pytest

from dxp.text import fold, sort_key, token_f1


def test_fold_ignora_acento_caixa_e_pontuacao():
    assert fold("JMP Distribuidora, LTDA.") == fold("jmp distribuidora ltda")


def test_sort_key_ignora_acento_e_caixa():
    assert sorted(["Sumidouro", "São João", "Saquarema"], key=sort_key) == [
        "São João",
        "Saquarema",
        "Sumidouro",
    ]


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("a b c d", "a b", pytest.approx(2 / 3)),
        ("a b", "a b", 1.0),
        ("a", "b", 0.0),
        ("", "a", 0.0),
        ("a", "", 0.0),
        ("Italia LTDA", "ITALIA ltda.", 1.0),
    ],
)
def test_token_f1(left, right, expected):
    assert token_f1(left, right) == expected
