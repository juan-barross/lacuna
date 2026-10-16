import re

SHAPE = re.compile(r"[0-9A-Z]{12}[0-9]{2}")
WEIGHTS = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]


def normalize(raw: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", raw).upper()


def check_digit(base: str) -> str:
    total = sum((ord(c) - ord("0")) * w for c, w in zip(base, WEIGHTS[-len(base) :], strict=True))
    rest = total % 11
    return "0" if rest < 2 else str(11 - rest)


def is_valid(raw: str) -> bool:
    cnpj = normalize(raw)
    if not SHAPE.fullmatch(cnpj) or len(set(cnpj)) == 1:
        return False
    return cnpj[12:] == check_digit(cnpj[:12]) + check_digit(cnpj[:13])
