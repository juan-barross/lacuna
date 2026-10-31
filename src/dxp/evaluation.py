import random
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from itertools import chain, zip_longest
from pathlib import Path

from dxp.files import read_csv, write_csv, write_jsonl
from dxp.match import MATCHED
from dxp.schema import FIELDS, Ato
from dxp.stats import wilson
from dxp.text import fold, token_f1

SEED = 2026
FUZZY_FIELDS = {"objeto": 0.5, "contratada_nome": 0.8}
QUEUE_FIELDS = ("ato_id", "territory_name", "date", "text")
REVIEW_FIELDS = ("ato_id", "contratada_nome", "valor", "data_assinatura", "pncp_fornecedor", "pncp_valor")


def stratified(rows: list[dict], size: int, seed: int = SEED) -> list[dict]:
    rng = random.Random(seed)
    by_city = defaultdict(list)
    for row in sorted(rows, key=lambda r: r["ato_id"]):
        by_city[row["territory_name"]].append(row)
    for group in by_city.values():
        rng.shuffle(group)
    round_robin = chain.from_iterable(zip_longest(*by_city.values()))
    return [row for row in round_robin if row is not None][:size]


def write_queue(rows: list[dict], path: Path, size: int = 100, dev_size: int = 40) -> int:
    queue = [
        {**{k: r[k] for k in QUEUE_FIELDS}, "split": "dev" if i < dev_size else "test"}
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


def precision_recall_f1(counts: Counter) -> dict[str, float]:
    precision = counts["tp"] / (counts["tp"] + counts["fp"]) if counts["tp"] + counts["fp"] else 0.0
    recall = counts["tp"] / (counts["tp"] + counts["fn"]) if counts["tp"] + counts["fn"] else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "support": counts["tp"] + counts["fn"]}


def count_fields(
    pairs: Iterable[tuple[dict, dict]], update: Callable[[Counter, str, object, object], None]
) -> dict[str, Counter]:
    counts = {field: Counter() for field in FIELDS}
    for first, second in pairs:
        for field in FIELDS:
            update(counts[field], field, first[field], second[field])
    return counts


def count_hits(counts: Counter, field: str, gold: object, predicted: object) -> None:
    hit = gold is not None and predicted is not None and same(field, gold, predicted)
    counts.update(tp=hit, fp=predicted is not None and not hit, fn=gold is not None and not hit)


def count_agreement(counts: Counter, field: str, first: object, second: object) -> None:
    if first is None and second is None:
        return
    both_present = first is not None and second is not None
    counts.update(n=1, iguais=both_present and same(field, first, second))


def score(gold: Iterable[dict], extract: Callable[[str], Ato]) -> dict[str, dict[str, float]]:
    pairs = ((Ato.model_validate(row).model_dump(), extract(row["text"]).model_dump()) for row in gold)
    return {field: precision_recall_f1(c) for field, c in count_fields(pairs, count_hits).items()}


def agreement(texts: Iterable[str], first: Callable[[str], Ato], second: Callable[[str], Ato]) -> dict:
    pairs = ((first(text).model_dump(), second(text).model_dump()) for text in texts)
    return {
        field: {"concordancia": round(c["iguais"] / c["n"], 3) if c["n"] else None, "n": c["n"]}
        for field, c in count_fields(pairs, count_agreement).items()
    }


def write_review(rows: list[dict], path: Path, size: int = 100) -> int:
    if path.exists():
        return 0
    matched = sorted((r for r in rows if r["status"] == MATCHED), key=lambda r: r["ato_id"])
    if not matched:
        return 0
    sample = random.Random(SEED).sample(matched, min(size, len(matched)))
    review = [
        {
            "municipio": r["territory_name"],
            **{k: r[k] for k in REVIEW_FIELDS},
            "trecho": " ".join(r["text"].split())[:400],
            "correto": "",
        }
        for r in sample
    ]
    write_csv(review, path)
    return len(review)


def review_precision(path: Path) -> dict:
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
