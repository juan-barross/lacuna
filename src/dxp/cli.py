import argparse
import csv
import logging
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import pyarrow.parquet as pq

from dxp.ingest.qd import QDClient
from dxp.ingest.qd_store import QDStore

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
RECORTE = DATA_DIR / "recorte_rj.csv"
SINCE = date(2025, 10, 1)
UNTIL = date(2026, 9, 30)


def load_recorte(path: Path) -> list[str]:
    with path.open(encoding="utf-8") as f:
        return [r["territory_id"] for r in csv.DictReader(f) if r["included"] == "True"]


def cmd_qd_download(args: argparse.Namespace) -> None:
    territory_ids = load_recorte(args.recorte)
    store = QDStore(args.data_dir)
    with QDClient() as client:
        summary = store.download(
            client, territory_ids, args.since, args.until, workers=args.workers
        )
    print(
        f"{summary.gazettes} diários de {len(territory_ids)} municípios "
        f"({summary.texts_downloaded} textos baixados agora) -> {store.parquet_path}"
    )
    for status, n in summary.by_status.most_common():
        print(f"  {status:8} {n}")


def cmd_qd_resumo(args: argparse.Namespace) -> None:
    table = pq.read_table(
        QDStore(args.data_dir).parquet_path, columns=["territory_name", "text_status"]
    )
    counts: dict[str, Counter] = defaultdict(Counter)
    for row in table.to_pylist():
        counts[row["territory_name"]][row["text_status"]] += 1

    statuses = ["ok", "curto", "so_link", "vazio", "sem_txt", "erro"]
    print(f"{'município':32}" + "".join(f"{s:>9}" for s in statuses) + f"{'% ok':>8}")
    for name in sorted(counts):
        c = counts[name]
        pct = 100 * c["ok"] / c.total()
        print(f"{name:32}" + "".join(f"{c[s]:>9}" for s in statuses) + f"{pct:>7.0f}%")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="dxp")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("qd-download", help="baixa os diários do recorte")
    p.add_argument("--recorte", type=Path, default=RECORTE)
    p.add_argument("--since", type=date.fromisoformat, default=SINCE)
    p.add_argument("--until", type=date.fromisoformat, default=UNTIL)
    p.add_argument("--workers", type=int, default=4, help="downloads de texto em paralelo")
    p.set_defaults(func=cmd_qd_download)

    p = sub.add_parser("qd-resumo", help="status do texto por município")
    p.set_defaults(func=cmd_qd_resumo)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args.func(args)


if __name__ == "__main__":
    main()
