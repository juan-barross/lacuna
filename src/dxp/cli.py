import argparse
import csv
import logging
from datetime import date
from pathlib import Path

from dxp.coverage import STATUSES, coverage_by_city, write_coverage
from dxp.ingest.qd import QDClient
from dxp.ingest.qd_store import QDStore

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
RECORTE = DATA_DIR / "recorte_rj.csv"
APP_DATA = ROOT / "app" / "data"
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
    rows = coverage_by_city(QDStore(args.data_dir).parquet_path)
    print(f"{'município':32}" + "".join(f"{s:>9}" for s in STATUSES) + f"{'% ok':>8}")
    for r in rows:
        counts = "".join(f"{r[s]:>9}" for s in STATUSES)
        print(f"{r['municipio']:32}{counts}{r['pct_texto']:>7.0f}%")


def cmd_cobertura(args: argparse.Namespace) -> None:
    rows = coverage_by_city(QDStore(args.data_dir).parquet_path)
    write_coverage(rows, args.out)
    print(f"{len(rows)} municípios -> {args.out}")


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

    p = sub.add_parser("cobertura", help="exporta a cobertura usada pelo painel")
    p.add_argument("--out", type=Path, default=APP_DATA / "cobertura.csv")
    p.set_defaults(func=cmd_cobertura)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args.func(args)


if __name__ == "__main__":
    main()
