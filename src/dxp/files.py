import csv
import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def load_env(path: Path) -> None:
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and not key.lstrip().startswith("#"):
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def short_hash(*parts: object) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:10]


def path_inside(root: Path, *parts: str) -> Path:
    resolved_root = root.resolve()
    path = Path(os.path.normpath(resolved_root.joinpath(*parts)))
    if not path.is_relative_to(resolved_root):
        raise ValueError(f"{path} fica fora de {root}")
    return path


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    partial.write_text(text, encoding="utf-8")
    partial.replace(path)


def cached_json(path: Path, fetch: Callable[[], object]):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    data = fetch()
    write_atomic(path, json.dumps(data, ensure_ascii=False))
    return data


def write_csv(rows: list[dict], path: Path, columns: list[str] | None = None) -> None:
    if not rows and not columns:
        raise ValueError(f"sem linhas e sem colunas para gravar em {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns or list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_jsonl(rows: list[dict], path: Path) -> None:
    write_atomic(path, "".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in rows))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def read_jsonl_or_empty(path: Path) -> list[dict]:
    return read_jsonl(path) if path.exists() else []


def write_parquet(rows: list[dict], path: Path, *, compression: str = "snappy") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    pq.write_table(pa.Table.from_pylist(rows), partial, compression=compression)
    partial.replace(path)
