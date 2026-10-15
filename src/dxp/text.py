import re
import unicodedata
from collections import Counter


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def sort_key(name: str) -> str:
    return strip_accents(name.casefold())


def fold(text: str) -> str:
    return " ".join(re.sub(r"[^\w/]", " ", sort_key(text)).split())


def token_f1(a: str, b: str) -> float:
    left, right = Counter(fold(a).split()), Counter(fold(b).split())
    common = sum((left & right).values())
    if not common:
        return 0.0
    precision, recall = common / sum(right.values()), common / sum(left.values())
    return 2 * precision * recall / (precision + recall)
