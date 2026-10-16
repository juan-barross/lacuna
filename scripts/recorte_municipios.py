import csv

from dxp.cli import RECORTE, SINCE, UNTIL
from dxp.qd import QDClient

STATE = "RJ"
MIN_GAZETTES = 100


def main() -> None:
    with QDClient() as client:
        cities = sorted(
            (c for c in client.cities(level=3) if c["state_code"] == STATE),
            key=lambda c: c["territory_id"],
        )
        rows = []
        for city in cities:
            total, _ = client.search([city["territory_id"]], SINCE, UNTIL, size=0)
            rows.append(
                {
                    "territory_id": city["territory_id"],
                    "territory_name": city["territory_name"],
                    "gazettes_in_period": total,
                    "included": total >= MIN_GAZETTES,
                }
            )

    with RECORTE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    kept = sum(r["included"] for r in rows)
    print(f"{kept} de {len(rows)} municípios incluídos -> {RECORTE}")


if __name__ == "__main__":
    main()
