from collections import Counter
from collections.abc import Callable
from functools import partial
from pathlib import Path

import pyarrow.parquet as pq

from dxp.files import read_csv, read_jsonl, write_csv, write_jsonl, write_parquet
from dxp.privacy import PERSON_TYPE, anonymize_row, count_marks

READERS: dict[str, Callable[[Path], list[dict]]] = {
    ".jsonl": read_jsonl,
    ".csv": read_csv,
    ".parquet": lambda path: pq.read_table(path).to_pylist(),
}
WRITERS: dict[str, Callable[[list[dict], Path], None]] = {
    ".jsonl": write_jsonl,
    ".csv": write_csv,
    ".parquet": partial(write_parquet, compression="zstd"),
}


def target_files(data_dir: Path, app_data: Path) -> list[Path]:
    gold, training = data_dir / "gold", data_dir / "treino"
    candidates = [*sorted(gold.glob("*.jsonl")), gold / "casamentos.csv", *sorted(training.glob("*.jsonl"))]
    return [path for path in [*candidates, app_data / "atos.parquet"] if path.exists()]


def person_names(tables: list[list[dict]]) -> dict[str, str]:
    return {
        row["ato_id"]: row["contratada_nome"]
        for rows in tables
        for row in rows
        if row.get("tipo") == PERSON_TYPE and row.get("contratada_nome")
    }


def anonymize_file(path: Path, names: dict[str, str], rows: list[dict]) -> Counter:
    cleaned = [anonymize_row(row, names.get(row.get("ato_id"))) for row in rows]
    WRITERS[path.suffix](cleaned, path)
    return count_marks(cleaned) - count_marks(rows)


def anonymize_files(paths: list[Path]) -> Counter:
    tables = {path: READERS[path.suffix](path) for path in paths}
    names = person_names(list(tables.values()))
    totals = Counter()
    for path, rows in tables.items():
        totals += anonymize_file(path, names, rows)
    return totals
