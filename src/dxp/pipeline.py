from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import pyarrow.parquet as pq

from dxp.files import write_csv, write_parquet
from dxp.match import rates_by_city, reconcile
from dxp.period import Period
from dxp.privacy import anonymize_row
from dxp.schema import Ato

INTERNAL_COLUMNS = {
    "gazette_id",
    "territory_id",
    "numero_contrato",
    "processo",
    "similaridade_nome",
}


class Extractor(Protocol):
    def __call__(self, text: str) -> Ato: ...

    def usage(self) -> dict: ...


class ExtractionFailed(RuntimeError):
    pass


def reconcile_atos(atos: list[dict], contracts: list[dict], extract: Callable[[str], Ato]) -> list[dict]:
    extracted = [{**ato, **extract(ato["text"]).model_dump()} for ato in atos]
    return reconcile(extracted, contracts)


def count_signed_contracts(contracts: list[dict], period: Period) -> Counter:
    return Counter(
        c["territory_id"] for c in contracts if c["data_assinatura"] and period.contains(c["data_assinatura"])
    )


def write_app_data(rows: list[dict], rates: list[dict], signed: Counter, app_data: Path) -> None:
    per_city = [{"territory_id": t, "pncp_contratos": n} for t, n in sorted(signed.items())]
    slim = [{k: v for k, v in r.items() if k not in INTERNAL_COLUMNS} for r in rows]
    write_csv(rates, app_data / "conciliacao.csv")
    write_csv(per_city, app_data / "pncp_contratos.csv", ["territory_id", "pncp_contratos"])
    write_parquet(slim, app_data / "atos.parquet", compression="zstd")


def publish_reconciliation(
    atos: Path, pncp: Path, extractor: Extractor, period: Period, app_data: Path
) -> tuple[list[dict], list[dict]]:
    contracts = pq.read_table(pncp).to_pylist()
    reconciled = reconcile_atos(pq.read_table(atos).to_pylist(), contracts, extractor)
    rows = [anonymize_row(row) for row in reconciled]
    failures = extractor.usage().get("erros", 0)
    if failures:
        raise ExtractionFailed(f"{failures} extrações falharam e virariam 'fora do escopo'")
    rates = rates_by_city(rows)
    write_app_data(rows, rates, count_signed_contracts(contracts, period), app_data)
    return rows, rates
