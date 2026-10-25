import argparse
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import pyarrow.parquet as pq

from dxp import coverage, pncp, qd
from dxp.evaluation import agreement, precision, score, write_queue, write_review
from dxp.files import load_env, read_csv, read_jsonl, write_csv
from dxp.llm import LLMExtractor, usage_report
from dxp.pipeline import run
from dxp.regex_baseline import extract as regex_extract
from dxp.segment import build_atos

ROOT = Path(__file__).resolve().parents[2]
RECORTE = ROOT / "data" / "recorte_rj.csv"
APP_DATA = ROOT / "app" / "data"
REPORTS = ROOT / "reports"
SINCE, UNTIL = date(2025, 10, 1), date(2026, 9, 30)
PNCP_SINCE, PNCP_UNTIL = date(2025, 8, 1), date(2026, 10, 14)
MIN_GAZETTES = 100
EXTRACTORS = {"regex": lambda: regex_extract, "llm": LLMExtractor}


def load_recorte(path: Path = RECORTE) -> list[str]:
    return [r["territory_id"] for r in read_csv(path) if r["included"] == "True"]


def show(value) -> str:
    if isinstance(value, float):
        return f"{value:.2f}"
    return "-" if value is None else str(value)


def print_table(rows: list[dict], columns: list[str]) -> None:
    widths = [max(len(c), *(len(show(r[c])) for r in rows)) for c in columns]
    print("  ".join(c.ljust(w) for c, w in zip(columns, widths, strict=True)))
    for r in rows:
        print("  ".join(show(r[c]).ljust(w) for c, w in zip(columns, widths, strict=True)))


def recorte(args) -> None:
    rows = []
    with qd.QDClient() as client:
        for city in sorted(client.cities(), key=lambda c: c["territory_id"]):
            if city["state_code"] == "RJ":
                total, _ = client.search([city["territory_id"]], SINCE, UNTIL, size=0)
                name, territory_id = city["territory_name"], city["territory_id"]
                rows.append(
                    {
                        "territory_id": territory_id,
                        "territory_name": name,
                        "gazettes_in_period": total,
                    }
                )
    write_csv([{**r, "included": r["gazettes_in_period"] >= MIN_GAZETTES} for r in rows], RECORTE)
    print_table(rows, ["territory_name", "gazettes_in_period"])


def qd_download(args) -> None:
    with qd.QDClient() as client:
        print(qd.download(client, load_recorte(), SINCE, UNTIL, args.data_dir))


def pncp_download(args) -> None:
    with pncp.PNCPClient() as client:
        print(
            pncp.download(client, load_recorte(), PNCP_SINCE, PNCP_UNTIL, args.data_dir),
            "contratos",
        )


def atos(args) -> None:
    print(
        build_atos(
            args.data_dir / "processed" / "qd_gazettes.parquet",
            args.data_dir / "processed" / "atos.parquet",
        )
    )


def amostra(args) -> None:
    rows = pq.read_table(args.data_dir / "processed" / "atos.parquet").to_pylist()
    print(write_queue(rows, args.data_dir / "gold" / "fila.jsonl"), "trechos")


def avaliar(args) -> None:
    extractor = EXTRACTORS[args.extrator]()
    result = score(read_jsonl(args.data_dir / "gold" / f"{args.split}.jsonl"), extractor)
    print_table(
        [{"campo": f, **m} for f, m in result.items()],
        ["campo", "precision", "recall", "f1", "support"],
    )
    usage = usage_report(getattr(extractor, "calls", []))
    print(json.dumps(usage, indent=2))
    report = REPORTS / f"{date.today()}_{args.extrator}_{args.split}.json"
    report.parent.mkdir(exist_ok=True)
    report.write_text(json.dumps({"campos": result, "uso": usage}, indent=2), encoding="utf-8")


def llm_fila(args) -> None:
    extractor = LLMExtractor()
    queue = read_jsonl(args.data_dir / "gold" / "fila.jsonl")
    texts = [row["text"] for row in queue if row["split"] == args.split]
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(extractor.extract, texts))
    print(json.dumps(usage_report(extractor.calls), indent=2))


def concordancia(args) -> None:
    llm = LLMExtractor()
    queue = read_jsonl(args.data_dir / "gold" / "fila.jsonl")
    texts = [r["text"] for r in queue if r["split"] == args.split and llm.cache_path(r["text"]).exists()]
    result = agreement(texts, regex_extract, llm)
    print(f"regex x {llm.model} em {len(texts)} trechos do {args.split}")
    print_table([{"campo": f, **m} for f, m in result.items()], ["campo", "concordancia", "n"])
    report = REPORTS / f"{date.today()}_concordancia_{args.split}.json"
    report.parent.mkdir(exist_ok=True)
    report.write_text(json.dumps({"trechos": len(texts), "campos": result}, indent=2), encoding="utf-8")


def conciliar(args) -> None:
    processed = args.data_dir / "processed"
    rows, rates = run(
        processed / "atos.parquet",
        processed / "pncp_contratos.parquet",
        EXTRACTORS[args.extrator](),
        SINCE,
        UNTIL,
        APP_DATA,
    )
    write_review(rows, args.data_dir / "gold" / "casamentos.csv")
    print_table(
        rates,
        [
            "municipio",
            "elegiveis",
            "casados",
            "provaveis",
            "sem_par",
            "taxa",
            "ic_inferior",
            "ic_superior",
        ],
    )


def precisao(args) -> None:
    print(precision(args.data_dir / "gold" / "casamentos.csv"))


def cobertura(args) -> None:
    rows = coverage.coverage_by_city(args.data_dir / "processed" / "qd_gazettes.parquet")
    write_csv(rows, APP_DATA / "cobertura.csv")
    print_table(rows, ["municipio", "diarios", *coverage.STATUSES, "pct_texto"])


COMMANDS = {
    "recorte": (recorte, "lista os municípios do RJ e marca os que entram no recorte"),
    "qd-download": (qd_download, "baixa os diários do recorte"),
    "pncp-download": (pncp_download, "baixa os contratos municipais do PNCP"),
    "atos": (atos, "separa os extratos de contrato dos diários"),
    "amostra": (amostra, "sorteia os trechos do conjunto ouro"),
    "llm-fila": (llm_fila, "extrai com o LLM os trechos do conjunto ouro, em paralelo"),
    "avaliar": (avaliar, "F1 por campo contra o conjunto ouro"),
    "concordancia": (concordancia, "campos em que regex e LLM dão a mesma resposta"),
    "conciliar": (conciliar, "concilia os atos com o PNCP e grava os dados do painel"),
    "precisao": (precisao, "precisão do casamento na amostra conferida à mão"),
    "cobertura": (cobertura, "texto disponível por município"),
}


def main(argv: list[str] | None = None) -> None:
    load_env(ROOT / ".env")
    parser = argparse.ArgumentParser(prog="dxp")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(required=True)
    for name, (func, help_text) in COMMANDS.items():
        command = sub.add_parser(name, help=help_text)
        command.set_defaults(func=func)
        if name in ("avaliar", "conciliar"):
            command.add_argument("--extrator", choices=EXTRACTORS, default="regex")
        if name in ("avaliar", "llm-fila", "concordancia"):
            command.add_argument("--split", choices=["dev", "test"], default="dev")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)
    args.func(args)


if __name__ == "__main__":
    main()
