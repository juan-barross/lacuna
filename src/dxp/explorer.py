from collections.abc import Iterable

from dxp.evaluation import same, score
from dxp.regex_baseline import extract as regex_extract
from dxp.schema import FIELDS, Ato

EXTRACTORS = {"qlora": "Qwen2.5-1.5B + QLoRA", "base": "Qwen2.5-1.5B sem ajuste", "regex": "Regex"}
MODELS = ("qlora", "base")


def hit(field: str, gold: object, predicted: object) -> bool:
    if gold is None or predicted is None:
        return gold is predicted
    return same(field, gold, predicted)


def parse(answer: dict | None) -> Ato | None:
    return Ato.model_validate(answer) if answer else None


def answers(row: dict, prediction: dict) -> dict[str, Ato | None]:
    return {**{name: parse(prediction[name]) for name in MODELS}, "regex": regex_extract(row["text"])}


def field_hits(gold: dict, ato: Ato | None) -> dict[str, bool]:
    predicted = ato.model_dump() if ato else dict.fromkeys(FIELDS)
    return {field: hit(field, gold[field], predicted[field]) for field in FIELDS}


def document(row: dict, prediction: dict) -> dict:
    gold = Ato.model_validate(row)
    extracted = answers(row, prediction)
    return {
        "id": row["ato_id"],
        "municipio": row["territory_name"],
        "texto": row["text"],
        "ouro": gold.model_dump(mode="json"),
        "respostas": {name: ato.model_dump(mode="json") if ato else None for name, ato in extracted.items()},
        "acertos": {name: field_hits(gold.model_dump(), ato) for name, ato in extracted.items()},
    }


def f1_by_extractor(rows: list[dict], predictions: dict[str, dict]) -> dict[str, dict[str, float]]:
    by_text = {row["text"]: answers(row, predictions[row["ato_id"]]) for row in rows}

    def f1(name: str) -> dict[str, float]:
        fields = score(rows, lambda text: by_text[text][name] or Ato(tipo="outro"))
        return {field: round(metrics["f1"], 2) for field, metrics in fields.items()}

    return {name: f1(name) for name in EXTRACTORS}


def explorer_data(rows: Iterable[dict], predictions: Iterable[dict]) -> dict:
    rows = list(rows)
    by_id = {prediction["ato_id"]: prediction for prediction in predictions}
    return {
        "extratores": EXTRACTORS,
        "campos": FIELDS,
        "f1": f1_by_extractor(rows, by_id),
        "documentos": [document(row, by_id[row["ato_id"]]) for row in rows],
    }
