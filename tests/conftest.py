import pytest

from dxp.privacy import check_digit


def build_cpf(base: str) -> str:
    digits = [int(c) for c in base]
    digits.append(check_digit(digits))
    digits.append(check_digit(digits))
    return "".join(map(str, digits))


@pytest.fixture
def cpf() -> str:
    return build_cpf("147636957")
