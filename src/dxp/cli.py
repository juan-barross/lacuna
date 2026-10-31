import argparse
import json
import logging
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from functools import partial
from pathlib import Path

import pyarrow.parquet as pq

from dxp import coverage, pncp, qd
from dxp.anonymize import anonymize_files, target_files
from dxp.evaluation import agreement, review_precision, score, write_queue, write_review
from dxp.files import load_env, read_csv, read_jsonl, write_csv
from dxp.llm import FREE_MODEL, LLMExtractor
from dxp.period import Period
from dxp.pipeline import ExtractionFailed, Extractor, publish_reconciliation
from dxp.privacy import anonymize_row
from dxp.regex_baseline import RegexExtractor, extract
from dxp.segment import build_atos

ROOT = Path(__file__).resolve().parents[2]
SCOPE_CSV = ROOT / "data" / "recorte_rj.csv"
APP_DATA = ROOT / "app" / "data"
REPORTS = ROOT / "reports"
QD_PERIOD = Period(date(2025, 10, 1), date(2026, 9, 30))
PNCP_PERIOD = Period(date(2025, 8, 1), date(2026, 10, 14))
MIN_GAZETTES = 100
EXTRACTORS: dict[str, Callable[[], Extractor]] = {
    "regex": RegexExtractor,
    "llm": LLMExtractor,
    "llm-gratis": partial(LLMExtractor, model=FREE_MODEL),
}
LLM_EXTRACTORS = [name for name in EXTRACTORS if name != "regex"]
RATE_COLUMNS = [
    "municipio",
    "elegiveis",
    "casados",
    "provaveis",
    "sem_par",
    "taxa",
    "ic_inferior",
    "ic_superior",
]


@dataclass(frozen=True)
class Option:
    flag: str
    dest: str
    choices: Sequence[str]
    default: str


@dataclass(frozen=True)
class Command:
    handler: Callable[[argparse.Namespace], None]
    help: str
    options: tuple[Option, ...] = ()


EXTRACTOR_OPTION = Option("--extrator", "extractor", list(EXTRACTORS), "regex")
LLM_EXTRACTOR_OPTION = Option("--extrator", "extractor", LLM_EXTRACTORS, "llm")
SPLIT_OPTION = Option("--split", "split", ["dev", "test"], "dev")


def build_extractor(name: str) -> Extractor:
    return EXTRACTORS[name]()


def load_scope() -> list[str]:
    return [r["territory_id"] for r in read_csv(SCOPE_CSV) if r["included"] == "True"]


def show(value) -> str:
    if isinstance(value, float):
        return f"{value:.2f}"
    return "-" if value is None else str(value)


def print_table(rows: list[dict], columns: list[str]) -> None:
    if not rows:
        print("nenhuma linha")
        return
    widths = [max(len(c), *(len(show(r[c])) for r in rows)) for c in columns]
    print("  ".join(c.ljust(w) for c, w in zip(columns, widths, strict=True)))
    for r in rows:
        print("  ".join(show(r[c]).ljust(w) for c, w in zip(columns, widths, strict=True)))


def print_fields(result: dict, columns: list[str]) -> None:
    print_table([{"campo": f, **m} for f, m in result.items()], ["campo", *columns])


def print_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2))


def write_report(name: str, payload: dict) -> None:
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / f"{date.today()}_{name}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def queue_texts(args: argparse.Namespace) -> list[str]:
    queue = read_jsonl(args.data_dir / "gold" / "fila.jsonl")
    return [r["text"] for r in queue if r["split"] == args.split]


def count_rj_gazettes(client: qd.QDClient) -> list[dict]:
    rows = []
    for city in sorted(client.cities(), key=lambda c: c["territory_id"]):
        if city["state_code"] == "RJ":
            total, _ = client.search([city["territory_id"]], QD_PERIOD, size=0)
            rows.append(
                {
                    "territory_id": city["territory_id"],
                    "territory_name": city["territory_name"],
                    "gazettes_in_period": total,
                }
            )
    return rows


def cmd_scope() -> None:
    with qd.QDClient() as client:
        rows = count_rj_gazettes(client)
    write_csv([{**r, "included": r["gazettes_in_period"] >= MIN_GAZETTES} for r in rows], SCOPE_CSV)
    print_table(rows, ["territory_name", "gazettes_in_period"])


def cmd_qd_download(args: argparse.Namespace) -> None:
    with qd.QDClient() as client:
        print(qd.download(client, load_scope(), QD_PERIOD, args.data_dir))


def cmd_pncp_download(args: argparse.Namespace) -> None:
    with pncp.PNCPClient() as client:
        print(pncp.download(client, load_scope(), PNCP_PERIOD, args.data_dir), "contratos")


def cmd_segment(args: argparse.Namespace) -> None:
    processed = args.data_dir / "processed"
    print(build_atos(processed / "qd_gazettes.parquet", processed / "atos.parquet"))


def cmd_sample(args: argparse.Namespace) -> None:
    atos = pq.read_table(args.data_dir / "processed" / "atos.parquet").to_pylist()
    rows = [anonymize_row({**ato, **extract(ato["text"]).model_dump()}) for ato in atos]
    print(write_queue(rows, args.data_dir / "gold" / "fila.jsonl"), "trechos")


def cmd_evaluate(args: argparse.Namespace) -> None:
    extractor = build_extractor(args.extractor)
    result = score(read_jsonl(args.data_dir / "gold" / f"{args.split}.jsonl"), extractor)
    print_fields(result, ["precision", "recall", "f1", "support"])
    usage = extractor.usage()
    print_json(usage)
    write_report(f"{args.extractor}_{args.split}", {"campos": result, "uso": usage})


def cmd_llm_queue(args: argparse.Namespace) -> None:
    extractor = build_extractor(args.extractor)
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(extractor, queue_texts(args)))
    print_json(extractor.usage())


def cmd_agreement(args: argparse.Namespace) -> None:
    llm = LLMExtractor()
    texts = [text for text in queue_texts(args) if llm.cache_path(text).exists()]
    result = agreement(texts, build_extractor("regex"), llm)
    print(f"regex x {llm.model} em {len(texts)} trechos do {args.split}")
    print_fields(result, ["concordancia", "n"])
    write_report(f"concordancia_{args.split}", {"trechos": len(texts), "campos": result})


def cmd_reconcile(args: argparse.Namespace) -> None:
    processed = args.data_dir / "processed"
    extractor = build_extractor(args.extractor)
    try:
        rows, rates = publish_reconciliation(
            processed / "atos.parquet", processed / "pncp_contratos.parquet", extractor, QD_PERIOD, APP_DATA
        )
    except ExtractionFailed as error:
        print_json(extractor.usage())
        raise SystemExit(f"conciliar interrompido, nada foi gravado: {error}") from error
    write_review(rows, args.data_dir / "gold" / "casamentos.csv")
    print_table(rates, RATE_COLUMNS)
    print_json(extractor.usage())


def cmd_precision(args: argparse.Namespace) -> None:
    print_json(review_precision(args.data_dir / "gold" / "casamentos.csv"))


def cmd_coverage(args: argparse.Namespace) -> None:
    rows = coverage.coverage_by_city(args.data_dir / "processed" / "qd_gazettes.parquet")
    write_csv(rows, APP_DATA / "cobertura.csv")
    print_table(rows, ["municipio", "diarios", *coverage.STATUSES, "pct_texto"])


def cmd_anonymize(args: argparse.Namespace) -> None:
    totals = anonymize_files(target_files(args.data_dir, APP_DATA))
    print_table(
        [{"marca": mark, "substituicoes": count} for mark, count in sorted(totals.items())],
        ["marca", "substituicoes"],
    )


COMMANDS = {
    "recorte": Command(lambda _: cmd_scope(), "lista os municípios do RJ e marca os que entram no recorte"),
    "qd-download": Command(cmd_qd_download, "baixa os diários do recorte"),
    "pncp-download": Command(cmd_pncp_download, "baixa os contratos municipais do PNCP"),
    "atos": Command(cmd_segment, "separa os extratos de contrato dos diários"),
    "amostra": Command(cmd_sample, "sorteia os trechos do conjunto ouro"),
    "llm-fila": Command(
        cmd_llm_queue,
        "extrai com o LLM os trechos do conjunto ouro, em paralelo",
        (LLM_EXTRACTOR_OPTION, SPLIT_OPTION),
    ),
    "avaliar": Command(cmd_evaluate, "F1 por campo contra o conjunto ouro", (EXTRACTOR_OPTION, SPLIT_OPTION)),
    "concordancia": Command(cmd_agreement, "campos em que regex e LLM dão a mesma resposta", (SPLIT_OPTION,)),
    "conciliar": Command(
        cmd_reconcile, "concilia os atos com o PNCP e grava os dados do painel", (EXTRACTOR_OPTION,)
    ),
    "precisao": Command(cmd_precision, "precisão do casamento na amostra conferida à mão"),
    "cobertura": Command(cmd_coverage, "texto disponível por município"),
    "anonimizar": Command(cmd_anonymize, "mascara dados pessoais nos arquivos versionados, no lugar"),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dxp")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("-v", "--verbose", action="store_true")
    subcommands = parser.add_subparsers(required=True)
    for name, command in COMMANDS.items():
        subparser = subcommands.add_parser(name, help=command.help)
        subparser.set_defaults(handler=command.handler)
        for option in command.options:
            subparser.add_argument(
                option.flag, dest=option.dest, choices=option.choices, default=option.default
            )
    return parser


def main(argv: list[str] | None = None) -> None:
    load_env(ROOT / ".env")
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)
    args.handler(args)


if __name__ == "__main__":
    main()
