import json
import random
from collections import defaultdict
from itertools import chain, zip_longest
from pathlib import Path

import pyarrow.parquet as pq

SEED = 2026
SIZE = 250
DEV_SIZE = 100


def stratified(rows: list[dict], size: int, seed: int = SEED) -> list[dict]:
    rng = random.Random(seed)
    by_city = defaultdict(list)
    for row in rows:
        by_city[row["territory_name"]].append(row)
    for group in by_city.values():
        rng.shuffle(group)
    round_robin = chain.from_iterable(zip_longest(*by_city.values()))
    return [row for row in round_robin if row is not None][:size]


def build_queue(atos: Path, out: Path, size: int = SIZE, dev_size: int = DEV_SIZE) -> int:
    columns = ["ato_id", "territory_name", "date", "text"]
    rows = sorted(pq.read_table(atos, columns=columns).to_pylist(), key=lambda r: r["ato_id"])
    sample = stratified(rows, size)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for i, row in enumerate(sample):
            row = {
                **row,
                "date": row["date"].isoformat(),
                "split": "dev" if i < dev_size else "test",
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(sample)
