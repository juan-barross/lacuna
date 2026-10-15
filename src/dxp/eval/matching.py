import csv
import random
from pathlib import Path

from dxp.eval.gold import SEED
from dxp.reconcile.match import MATCHED, wilson

REVIEW_SIZE = 100
FIELDS = [
    "ato_id",
    "municipio",
    "contratada_nome",
    "valor",
    "data_assinatura",
    "pncp_fornecedor",
    "pncp_valor",
    "pncp_numero_controle",
    "trecho",
    "correto",
]


def write_review(rows: list[dict], path: Path, size: int = REVIEW_SIZE) -> int:
    matched = sorted((r for r in rows if r["status"] == MATCHED), key=lambda r: r["ato_id"])
    sample = random.Random(SEED).sample(matched, min(size, len(matched)))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        for r in sample:
            trecho = " ".join(r["text"].split())[:400]
            writer.writerow(
                {
                    **{k: r.get(k) for k in FIELDS},
                    "municipio": r["territory_name"],
                    "trecho": trecho,
                }
            )
    return len(sample)


def precision(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        answers = [r["correto"].strip().lower() for r in csv.DictReader(f)]
    checked = [a for a in answers if a in ("s", "n")]
    hits = checked.count("s")
    low, high = wilson(hits, len(checked))
    return {
        "conferidos": len(checked),
        "pendentes": len(answers) - len(checked),
        "precisao": round(hits / len(checked), 3) if checked else None,
        "ic_inferior": round(low, 3),
        "ic_superior": round(high, 3),
    }
