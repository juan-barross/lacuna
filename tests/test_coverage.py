import pyarrow as pa
import pyarrow.parquet as pq

from dxp.coverage import STATUSES, coverage_by_city
from dxp.files import read_csv, write_csv


def coverage(tmp_path, rows):
    path = tmp_path / "g.parquet"
    columns = ["territory_id", "territory_name", "text_status"]
    pq.write_table(pa.Table.from_pylist([dict(zip(columns, r, strict=True)) for r in rows]), path)
    return coverage_by_city(path)


def test_conta_status_por_municipio(tmp_path):
    rows = coverage(
        tmp_path,
        [
            ("3304128", "Quatis", "so_link"),
            ("3304128", "Quatis", "so_link"),
            ("3304557", "Rio de Janeiro", "ok"),
            ("3304557", "Rio de Janeiro", "ok"),
            ("3304557", "Rio de Janeiro", "ok"),
            ("3304557", "Rio de Janeiro", "curto"),
        ],
    )

    quatis, rio = rows
    assert quatis["diarios"] == 2
    assert quatis["so_link"] == 2
    assert quatis["pct_texto"] == 0.0
    assert rio["ok"] == 3
    assert rio["curto"] == 1
    assert rio["pct_texto"] == 75.0


def test_todos_os_status_aparecem_mesmo_zerados(tmp_path):
    (row,) = coverage(tmp_path, [("3304557", "Rio de Janeiro", "ok")])

    assert all(row[s] == 0 for s in STATUSES if s != "ok")


def test_ordena_ignorando_acentos(tmp_path):
    rows = coverage(
        tmp_path,
        [
            ("3305703", "Sumidouro", "ok"),
            ("3305109", "São João de Meriti", "so_link"),
            ("3305505", "Saquarema", "ok"),
        ],
    )

    assert [r["municipio"] for r in rows] == ["São João de Meriti", "Saquarema", "Sumidouro"]


def test_csv_ida_e_volta(tmp_path):
    rows = coverage(tmp_path, [("3304557", "Rio de Janeiro", "ok")])
    write_csv(rows, tmp_path / "app" / "cobertura.csv")

    (saved,) = read_csv(tmp_path / "app" / "cobertura.csv")
    assert saved["municipio"] == "Rio de Janeiro"
    assert saved["pct_texto"] == "100.0"
