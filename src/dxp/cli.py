import argparse
import csv
import json
import logging
from datetime import date
from pathlib import Path

from dxp.coverage import STATUSES, coverage_by_city, write_coverage
from dxp.eval.extraction import load_gold, score
from dxp.eval.gold import build_queue
from dxp.extract.llm import LLMExtractor, usage_report
from dxp.extract.regex_baseline import extract as regex_extract
from dxp.extract.segment import build_atos
from dxp.ingest.pncp import PNCPClient
from dxp.ingest.pncp_store import PNCPStore
from dxp.ingest.qd import QDClient
from dxp.ingest.qd_store import QDStore

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
RECORTE = DATA_DIR / "recorte_rj.csv"
APP_DATA = ROOT / "app" / "data"
SINCE = date(2025, 10, 1)
UNTIL = date(2026, 9, 30)
PNCP_SINCE = date(2025, 8, 1)
PNCP_UNTIL = date(2026, 10, 14)
REPORTS = ROOT / "reports"
EXTRACTORS = {"regex": lambda: regex_extract, "llm": lambda: LLMExtractor()}


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


def cmd_pncp_download(args: argparse.Namespace) -> None:
    territory_ids = load_recorte(args.recorte)
    store = PNCPStore(args.data_dir)
    with PNCPClient() as client:
        total = store.download(client, territory_ids, PNCP_SINCE, PNCP_UNTIL)
    print(f"{total} contratos de {len(territory_ids)} municípios -> {store.parquet_path}")


def cmd_atos(args: argparse.Namespace) -> None:
    out = args.data_dir / "processed" / "atos.parquet"
    total = build_atos(QDStore(args.data_dir).parquet_path, out)
    print(f"{total} extratos de contrato -> {out}")


def cmd_amostra(args: argparse.Namespace) -> None:
    out = args.data_dir / "gold" / "fila.jsonl"
    print(f"{build_queue(args.data_dir / 'processed' / 'atos.parquet', out)} trechos -> {out}")


def cmd_avaliar(args: argparse.Namespace) -> None:
    gold = load_gold(args.data_dir / "gold" / f"{args.split}.jsonl")
    extractor = EXTRACTORS[args.extrator]()
    result = score(gold, extractor)
    usage = usage_report(getattr(extractor, "calls", []))
    print(f"{args.extrator} no {args.split} ({len(gold)} atos)")
    print(f"{'campo':18}{'precisão':>10}{'recall':>8}{'F1':>7}{'n':>5}")
    for field, m in result.items():
        p, r, f1, n = m["precision"], m["recall"], m["f1"], m["support"]
        print(f"{field:18}{p:>10.2f}{r:>8.2f}{f1:>7.2f}{n:>5}")
    report = REPORTS / f"{date.today()}_{args.extrator}_{args.split}.json"
    report.parent.mkdir(exist_ok=True)
    for key, value in usage.items():
        print(f"  {key}: {value}")
    payload = {
        "extrator": args.extrator,
        "split": args.split,
        "n": len(gold),
        "campos": result,
        "uso": usage,
    }
    report.write_text(json.dumps(payload, indent=2), encoding="utf-8")


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

    p = sub.add_parser("pncp-download", help="baixa os contratos municipais do PNCP")
    p.add_argument("--recorte", type=Path, default=RECORTE)
    p.set_defaults(func=cmd_pncp_download)

    p = sub.add_parser("qd-resumo", help="status do texto por município")
    p.set_defaults(func=cmd_qd_resumo)

    p = sub.add_parser("atos", help="separa os extratos de contrato dos diários")
    p.set_defaults(func=cmd_atos)

    p = sub.add_parser("amostra", help="sorteia os trechos do conjunto ouro")
    p.set_defaults(func=cmd_amostra)

    p = sub.add_parser("avaliar", help="F1 por campo de um extrator contra o conjunto ouro")
    p.add_argument("--extrator", choices=EXTRACTORS, default="regex")
    p.add_argument("--split", choices=["dev", "test"], default="dev")
    p.set_defaults(func=cmd_avaliar)

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
