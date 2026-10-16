import csv
from collections import Counter
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from dxp.match import rates_by_city, reconcile
from dxp.schema import Ato

APP_COLUMNS = [
    "ato_id",
    "territory_name",
    "date",
    "url",
    "text",
    "tipo",
    "contratada_nome",
    "contratada_cnpj",
    "objeto",
    "valor",
    "data_assinatura",
    "status",
    "pncp_numero_controle",
    "pncp_fornecedor",
    "pncp_valor",
]


def extracted(atos: Path, extract: Callable[[str], Ato]) -> list[dict]:
    return [{**row, **extract(row["text"]).model_dump()} for row in pq.read_table(atos).to_pylist()]


def pncp_per_city(contracts: list[dict], since: date, until: date) -> list[dict]:
    signed = Counter(
        c["territory_id"]
        for c in contracts
        if c["data_assinatura"] and since <= c["data_assinatura"] <= until
    )
    return [{"territory_id": t, "pncp_contratos": n} for t, n in sorted(signed.items())]


def run(atos: Path, pncp: Path, extract: Callable[[str], Ato], since: date, until: date):
    contracts = pq.read_table(pncp).to_pylist()
    rows = reconcile(extracted(atos, extract), contracts)
    ids = {r["territory_name"]: r["territory_id"] for r in rows}
    rates = [{"territory_id": ids[r["municipio"]], **r} for r in rates_by_city(rows)]
    return rows, rates, pncp_per_city(contracts, since, until)


def write_csv(rows: list[dict], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_outputs(rows: list[dict], rates: list[dict], pncp: list[dict], app_data: Path) -> None:
    app_data.mkdir(parents=True, exist_ok=True)
    write_csv(rates, app_data / "conciliacao.csv")
    write_csv(pncp, app_data / "pncp_contratos.csv")
    table = pa.Table.from_pylist([{c: r.get(c) for c in APP_COLUMNS} for r in rows])
    pq.write_table(table, app_data / "atos.parquet", compression="zstd")
