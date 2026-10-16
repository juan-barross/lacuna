from collections import Counter
from datetime import date

from dxp.evaluation import stratified, write_queue
from dxp.files import read_jsonl

ROWS = [{"ato_id": f"s{i:02d}", "territory_name": "Saquarema"} for i in range(50)] + [
    {"ato_id": f"q{i}", "territory_name": "Quatis"} for i in range(2)
]


def test_amostra_alterna_municipios():
    sample = stratified(ROWS, 6)

    assert Counter(r["territory_name"] for r in sample) == {"Saquarema": 4, "Quatis": 2}
    assert [r["territory_name"] for r in sample[:4]] == ["Quatis", "Saquarema"] * 2


def test_amostra_nao_depende_da_ordem_de_entrada():
    assert stratified(ROWS, 10) == stratified(list(reversed(ROWS)), 10)


def test_amostra_pede_mais_do_que_existe():
    assert len(stratified(ROWS, 500)) == len(ROWS)


def test_fila_separa_dev_e_teste(tmp_path):
    rows = [{**r, "date": date(2025, 10, 1), "text": "x"} for r in ROWS]
    out = tmp_path / "fila.jsonl"

    assert write_queue(rows, out, size=10, dev_size=4) == 10
    queue = read_jsonl(out)
    assert Counter(r["split"] for r in queue) == {"dev": 4, "test": 6}
    assert queue[0]["date"] == "2025-10-01"
