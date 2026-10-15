import csv
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq

from dxp.text import sort_key

STATUSES = ["ok", "curto", "so_link", "vazio", "sem_txt", "erro"]
FIELDS = ["territory_id", "municipio", "diarios", *STATUSES, "pct_texto"]


def coverage_by_city(parquet_path: Path) -> list[dict]:
    table = pq.read_table(parquet_path, columns=["territory_id", "territory_name", "text_status"])
    counts: dict[tuple[str, str], Counter] = {}
    for row in table.to_pylist():
        key = (row["territory_id"], row["territory_name"])
        counts.setdefault(key, Counter())[row["text_status"]] += 1

    rows = []
    for (territory_id, name), c in sorted(counts.items(), key=lambda kv: sort_key(kv[0][1])):
        total = c.total()
        rows.append(
            {
                "territory_id": territory_id,
                "municipio": name,
                "diarios": total,
                **{s: c[s] for s in STATUSES},
                "pct_texto": round(100 * c["ok"] / total, 1),
            }
        )
    return rows


def write_coverage(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
