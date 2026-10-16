from collections import Counter
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from dxp.files import write_csv
from dxp.match import rates_by_city, reconcile
from dxp.schema import Ato

INTERNAL_COLUMNS = {
    "gazette_id",
    "territory_id",
    "numero_contrato",
    "processo",
    "similaridade_nome",
}


def run(
    atos: Path, pncp: Path, extract: Callable[[str], Ato], since: date, until: date, app_data: Path
):
    contracts = pq.read_table(pncp).to_pylist()
    rows = reconcile(
        [{**r, **extract(r["text"]).model_dump()} for r in pq.read_table(atos).to_pylist()],
        contracts,
    )
    city_ids = {r["territory_name"]: r["territory_id"] for r in rows}
    rates = [{"territory_id": city_ids[r["municipio"]], **r} for r in rates_by_city(rows)]
    signed = Counter(
        c["territory_id"]
        for c in contracts
        if c["data_assinatura"] and since <= c["data_assinatura"] <= until
    )

    write_csv(rates, app_data / "conciliacao.csv")
    write_csv(
        [{"territory_id": t, "pncp_contratos": n} for t, n in sorted(signed.items())],
        app_data / "pncp_contratos.csv",
    )
    slim = [{k: v for k, v in r.items() if k not in INTERNAL_COLUMNS} for r in rows]
    pq.write_table(pa.Table.from_pylist(slim), app_data / "atos.parquet", compression="zstd")
    return rows, rates
