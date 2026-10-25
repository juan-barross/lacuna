import random
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from itertools import chain, zip_longest
from pathlib import Path

from dxp.files import read_csv, write_csv, write_jsonl
from dxp.match import MATCHED, wilson
from dxp.schema import FIELDS, Ato
from dxp.text import fold, token_f1

SEED = 2026
FUZZY_FIELDS = {"objeto": 0.5, "contratada_nome": 0.8}


def stratified(rows: list[dict], size: int, seed: int = SEED) -> list[dict]:
    rng = random.Random(seed)
    by_city = defaultdict(list)
    for row in sorted(rows, key=lambda r: r["ato_id"]):
        by_city[row["territory_name"]].append(row)
    for group in by_city.values():
        rng.shuffle(group)
    round_robin = chain.from_iterable(zip_longest(*by_city.values()))
    return [row for row in round_robin if row is not None][:size]


def write_queue(rows: list[dict], path: Path, size: int = 250, dev_size: int = 100) -> int:
    keep = ("ato_id", "territory_name", "date", "text")
    queue = [
        {**{k: r[k] for k in keep}, "split": "dev" if i < dev_size else "test"}
        for i, r in enumerate(stratified(rows, size))
    ]
    write_jsonl(queue, path)
    return len(queue)


def same(field: str, gold, pred) -> bool:
    if field in FUZZY_FIELDS:
        return token_f1(gold, pred) >= FUZZY_FIELDS[field]
    if isinstance(gold, str):
        return fold(gold) == fold(pred)
    if isinstance(gold, float):
        return round(gold, 2) == round(pred, 2)
    return gold == pred


def prf(c: Counter) -> dict[str, float]:
    precision = c["tp"] / (c["tp"] + c["fp"]) if c["tp"] + c["fp"] else 0.0
    recall = c["tp"] / (c["tp"] + c["fn"]) if c["tp"] + c["fn"] else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "support": c["tp"] + c["fn"]}


def score(gold: Iterable[dict], extract: Callable[[str], Ato]) -> dict[str, dict[str, float]]:
    counts = {f: Counter() for f in FIELDS}
    for row in gold:
        expected, predicted = (
            Ato.model_validate(row).model_dump(),
            extract(row["text"]).model_dump(),
        )
        for field in FIELDS:
            g, p = expected[field], predicted[field]
            hit = g is not None and p is not None and same(field, g, p)
            counts[field].update(tp=hit, fp=p is not None and not hit, fn=g is not None and not hit)
    return {field: prf(c) for field, c in counts.items()}


def agreement(texts: Iterable[str], first: Callable[[str], Ato], second: Callable[[str], Ato]) -> dict:
    counts = {f: Counter() for f in FIELDS}
    for text in texts:
        a, b = first(text).model_dump(), second(text).model_dump()
        for field in FIELDS:
            if a[field] is None and b[field] is None:
                continue
            both = a[field] is not None and b[field] is not None
            counts[field].update(n=1, iguais=both and same(field, a[field], b[field]))
    return {
        field: {"concordancia": round(c["iguais"] / c["n"], 3) if c["n"] else None, "n": c["n"]}
        for field, c in counts.items()
    }


def write_review(rows: list[dict], path: Path, size: int = 100) -> int:
    if path.exists():
        return 0
    matched = sorted((r for r in rows if r["status"] == MATCHED), key=lambda r: r["ato_id"])
    sample = random.Random(SEED).sample(matched, min(size, len(matched)))
    keep = (
        "ato_id",
        "contratada_nome",
        "valor",
        "data_assinatura",
        "pncp_fornecedor",
        "pncp_valor",
    )
    review = [
        {
            "municipio": r["territory_name"],
            **{k: r[k] for k in keep},
            "trecho": " ".join(r["text"].split())[:400],
            "correto": "",
        }
        for r in sample
    ]
    if review:
        write_csv(review, path)
    return len(review)


def precision(path: Path) -> dict:
    answers = [r["correto"].strip().lower() for r in read_csv(path)]
    checked = [a for a in answers if a in ("s", "n")]
    hits = checked.count("s")
    low, high = wilson(hits, len(checked))
    return {
        "conferidos": len(checked),
        "pendentes": len(answers) - len(checked),
        "precisao": round(hits / len(checked), 3) if checked else None,
        "ic_inferior": round(low, 3),
        "ic_superior": round(high, 3),
    }
