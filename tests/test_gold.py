import json
from collections import Counter
from datetime import date

import pyarrow as pa
import pyarrow.parquet as pq

from dxp.eval.gold import build_queue, stratified

ROWS = [{"ato_id": f"s{i}", "territory_name": "Saquarema"} for i in range(50)] + [
    {"ato_id": f"q{i}", "territory_name": "Quatis"} for i in range(2)
]


def test_amostra_alterna_municipios():
    sample = stratified(ROWS, 6)

    assert Counter(r["territory_name"] for r in sample) == {"Saquarema": 4, "Quatis": 2}
    assert [r["territory_name"] for r in sample[:4]] == ["Saquarema", "Quatis"] * 2


def test_amostra_e_reprodutivel():
    assert stratified(ROWS, 10) == stratified(ROWS, 10)


def test_fila_separa_dev_e_teste(tmp_path):
    atos = tmp_path / "atos.parquet"
    rows = [{**r, "date": date(2025, 10, 1), "text": "x"} for r in ROWS]
    pq.write_table(pa.Table.from_pylist(rows), atos)
    out = tmp_path / "fila.jsonl"

    assert build_queue(atos, out, size=10, dev_size=4) == 10
    queue = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert Counter(r["split"] for r in queue) == {"dev": 4, "test": 6}
    assert queue[0]["date"] == "2025-10-01"
