"""Gera data/recorte_rj.csv: municípios do RJ cobertos pelo Querido Diário e quantos
diários cada um publicou no período do projeto.

Critério de inclusão (ADR 0001): pelo menos MIN_GAZETTES diários no período.

    python scripts/recorte_municipios.py
"""

import csv
from pathlib import Path

import httpx

BASE_URL = "https://api.queridodiario.org.br"
STATE = "RJ"
SINCE = "2025-10-01"
UNTIL = "2026-09-30"
MIN_GAZETTES = 100
OUT = Path(__file__).resolve().parents[1] / "data" / "recorte_rj.csv"


def main() -> None:
    with httpx.Client(
        base_url=BASE_URL, headers={"User-Agent": "diario-x-pncp/0.1"}, timeout=30
    ) as http:
        cities = http.get("/cities", params={"levels": 3}).raise_for_status().json()["cities"]
        cities = sorted(
            (c for c in cities if c["state_code"] == STATE), key=lambda c: c["territory_id"]
        )

        rows = []
        for city in cities:
            resp = http.get(
                "/gazettes",
                params={
                    "territory_ids": city["territory_id"],
                    "published_since": SINCE,
                    "published_until": UNTIL,
                    "size": 0,
                },
            ).raise_for_status()
            total = resp.json()["total_gazettes"]
            rows.append(
                {
                    "territory_id": city["territory_id"],
                    "territory_name": city["territory_name"],
                    "gazettes_in_period": total,
                    "included": total >= MIN_GAZETTES,
                }
            )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    kept = sum(r["included"] for r in rows)
    print(f"{kept} de {len(rows)} municípios incluídos -> {OUT}")


if __name__ == "__main__":
    main()
