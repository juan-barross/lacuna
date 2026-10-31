import re

TERRITORY_ID = re.compile(r"\d{7}")
ALPHANUMERIC_ID = re.compile(r"[0-9A-Za-z]+")


def checked_id(pattern: re.Pattern[str], value: str, what: str) -> str:
    if not pattern.fullmatch(value):
        raise ValueError(f"{what} inválido: {value!r}")
    return value
