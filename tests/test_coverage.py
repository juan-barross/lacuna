import csv

import pyarrow as pa
import pyarrow.parquet as pq

from dxp.coverage import FIELDS, coverage_by_city, write_coverage


def make_parquet(path, rows):
    pq.write_table(
        pa.Table.from_pylist(
            [{"territory_id": t, "territory_name": n, "text_status": s} for t, n, s in rows]
        ),
        path,
    )


def test_conta_status_por_municipio(tmp_path):
    path = tmp_path / "g.parquet"
    make_parquet(
        path,
        [
            ("3304128", "Quatis", "so_link"),
            ("3304128", "Quatis", "so_link"),
            ("3304557", "Rio de Janeiro", "ok"),
            ("3304557", "Rio de Janeiro", "ok"),
            ("3304557", "Rio de Janeiro", "ok"),
            ("3304557", "Rio de Janeiro", "curto"),
        ],
    )

    rows = coverage_by_city(path)

    assert [r["municipio"] for r in rows] == ["Quatis", "Rio de Janeiro"]
    quatis, rio = rows
    assert quatis["diarios"] == 2
    assert quatis["so_link"] == 2
    assert quatis["pct_texto"] == 0.0
    assert rio["ok"] == 3
    assert rio["curto"] == 1
    assert rio["pct_texto"] == 75.0


def test_grava_csv_com_todas_as_colunas(tmp_path):
    path = tmp_path / "g.parquet"
    make_parquet(path, [("3304557", "Rio de Janeiro", "ok")])
    out = tmp_path / "app" / "cobertura.csv"

    write_coverage(coverage_by_city(path), out)

    with out.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert reader.fieldnames == FIELDS
    assert rows[0]["pct_texto"] == "100.0"


def test_ordena_ignorando_acentos(tmp_path):
    path = tmp_path / "g.parquet"
    make_parquet(
        path,
        [
            ("3305703", "Sumidouro", "ok"),
            ("3305109", "São João de Meriti", "so_link"),
            ("3305505", "Saquarema", "ok"),
        ],
    )

    names = [r["municipio"] for r in coverage_by_city(path)]

    assert names == ["São João de Meriti", "Saquarema", "Sumidouro"]
