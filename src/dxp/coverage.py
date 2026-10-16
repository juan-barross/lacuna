from collections import Counter, defaultdict
from pathlib import Path

import pyarrow.parquet as pq

from dxp.text import sort_key

STATUSES = ["ok", "curto", "so_link", "vazio", "sem_txt", "erro"]


def coverage_by_city(gazettes: Path) -> list[dict]:
    counts = defaultdict(Counter)
    for r in pq.read_table(
        gazettes, columns=["territory_id", "territory_name", "text_status"]
    ).to_pylist():
        counts[r["territory_id"], r["territory_name"]][r["text_status"]] += 1
    return [
        {
            "territory_id": territory_id,
            "municipio": name,
            "diarios": c.total(),
            **{s: c[s] for s in STATUSES},
            "pct_texto": round(100 * c["ok"] / c.total(), 1),
        }
        for (territory_id, name), c in sorted(counts.items(), key=lambda kv: sort_key(kv[0][1]))
    ]
