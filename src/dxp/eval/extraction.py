import json
import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterable
from pathlib import Path

from dxp.extract.schema import FIELDS, Ato

FUZZY_FIELDS = {"objeto": 0.5, "contratada_nome": 0.8}


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^\w/]", " ", text).split())


def token_f1(a: str, b: str) -> float:
    left, right = Counter(fold(a).split()), Counter(fold(b).split())
    common = sum((left & right).values())
    if not common:
        return 0.0
    precision, recall = common / sum(right.values()), common / sum(left.values())
    return 2 * precision * recall / (precision + recall)


def same(field: str, gold, pred) -> bool:
    if field in FUZZY_FIELDS:
        return token_f1(gold, pred) >= FUZZY_FIELDS[field]
    if isinstance(gold, str):
        return fold(gold) == fold(pred)
    if isinstance(gold, float):
        return round(gold, 2) == round(pred, 2)
    return gold == pred


def load_gold(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def score(gold: Iterable[dict], extract: Callable[[str], Ato]) -> dict[str, dict[str, float]]:
    counts = {f: Counter() for f in FIELDS}
    for row in gold:
        expected = Ato.model_validate(row).model_dump()
        predicted = extract(row["text"]).model_dump()
        for field in FIELDS:
            g, p = expected[field], predicted[field]
            hit = g is not None and p is not None and same(field, g, p)
            counts[field]["tp"] += hit
            counts[field]["fp"] += p is not None and not hit
            counts[field]["fn"] += g is not None and not hit
    return {field: prf(c) for field, c in counts.items()}


def prf(c: Counter) -> dict[str, float]:
    precision = c["tp"] / (c["tp"] + c["fp"]) if c["tp"] + c["fp"] else 0.0
    recall = c["tp"] / (c["tp"] + c["fn"]) if c["tp"] + c["fn"] else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "support": c["tp"] + c["fn"]}
