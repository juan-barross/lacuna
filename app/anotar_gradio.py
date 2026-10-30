import json
import re
from pathlib import Path

import gradio as gr
from pydantic import ValidationError

from dxp.files import read_jsonl
from dxp.schema import Ato

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "data" / "gold"
QUEUE = GOLD / "fila.jsonl"
DRAFT = GOLD / "rascunho.jsonl"
GUIDE = (ROOT / "docs" / "guia_anotacao.md").read_text(encoding="utf-8")
TEXT_FIELDS = ["numero_contrato", "processo", "contratada_nome", "contratada_cnpj", "objeto"]
BLANK = ["contrato", *[""] * (len(TEXT_FIELDS) + 3)]


def drafts() -> dict[str, dict]:
    return {r["ato_id"]: r for r in read_jsonl(DRAFT)}


def br_number(value: float | None) -> str:
    return "" if value is None else f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def br_date(iso: str | None) -> str:
    return "" if not iso else f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"


def to_number(raw: str) -> str | None:
    raw = raw.strip()
    return raw.replace(".", "").replace(",", ".") if "," in raw else raw or None


def to_date(raw: str) -> str | None:
    raw = raw.strip()
    if match := re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw):
        day, month, year = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    return raw or None


def pending() -> tuple[dict | None, str]:
    queue = read_jsonl(QUEUE)
    done = {r["ato_id"] for split in ("dev", "test") for r in read_jsonl(GOLD / f"{split}.jsonl")}
    rest = [r for r in queue if r["ato_id"] not in done]
    progress = f"**{len(done)} de {len(queue)} rotulados**"
    return (rest[0] if rest else None), progress


def show():
    item, progress = pending()
    if item is None:
        return [None, progress, "Tudo rotulado.", "", *BLANK]
    caption = f"{item['territory_name']} · {item['date']} · {item['split']} · `{item['ato_id']}`"
    draft = drafts().get(item["ato_id"])
    if draft is None:
        return [item, progress, caption, item["text"], *BLANK]
    note = draft.get("observacao") or ""
    if "CONFERIR" in note:
        caption += "\n\n**Rascunho marcado para conferir.**"
    return [
        item,
        progress,
        caption,
        item["text"],
        draft["tipo"],
        *[draft.get(field) or "" for field in TEXT_FIELDS],
        br_number(draft.get("valor")),
        br_date(draft.get("data_assinatura")),
        note,
    ]


def save(item, tipo, *values):
    if item is None:
        raise gr.Error("Não há trecho pendente.")
    texts, (valor, assinatura, observacao) = values[: len(TEXT_FIELDS)], values[len(TEXT_FIELDS) :]
    label = {
        "tipo": tipo,
        **{k: v.strip() or None for k, v in zip(TEXT_FIELDS, texts, strict=True)},
        "valor": to_number(valor),
        "data_assinatura": to_date(assinatura),
    }
    try:
        ato = Ato.model_validate(label)
    except ValidationError as error:
        raise gr.Error(str(error)) from error
    for problem in ato.problems():
        gr.Warning(f"Salvo com aviso: {problem}")
    row = {
        "ato_id": item["ato_id"],
        "territory_name": item["territory_name"],
        "text": item["text"],
        **ato.model_dump(mode="json"),
        "observacao": observacao.strip() or None,
        "origem": "rascunho_llm_revisado" if item["ato_id"] in drafts() else "manual",
    }
    with (GOLD / f"{item['split']}.jsonl").open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return [item["split"], *show()]


def undo(last_split):
    if last_split is None:
        gr.Info("Nada para desfazer nesta sessão.")
        return [None, *show()]
    path = GOLD / f"{last_split}.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("".join(line + "\n" for line in lines[:-1]), encoding="utf-8", newline="\n")
    gr.Info("Último rótulo desfeito. O trecho voltou para a fila.")
    return [None, *show()]


with gr.Blocks(title="Anotação · Lacuna") as demo:
    item_state = gr.State()
    last_split = gr.State()
    progress = gr.Markdown()
    with gr.Row():
        with gr.Column(scale=3):
            caption = gr.Markdown()
            text = gr.Textbox(
                label="Trecho", lines=28, max_lines=40, interactive=False, show_copy_button=True
            )
            with gr.Accordion("Guia de anotação", open=False):
                gr.Markdown(GUIDE)
        with gr.Column(scale=2):
            tipo = gr.Radio(["contrato", "pessoal", "outro"], value="contrato", label="tipo")
            texts = [gr.Textbox(label=field) for field in TEXT_FIELDS]
            valor = gr.Textbox(label="valor total em reais", placeholder="1.474.895,28")
            assinatura = gr.Textbox(label="data de assinatura", placeholder="11/08/2025 ou 2025-08-11")
            observacao = gr.Textbox(label="observação")
            with gr.Row():
                salvar = gr.Button("Salvar e ir para o próximo", variant="primary")
                desfazer = gr.Button("Desfazer o último")

    fields = [tipo, *texts, valor, assinatura, observacao]
    view = [item_state, progress, caption, text, *fields]
    demo.load(show, outputs=view)
    salvar.click(save, inputs=[item_state, *fields], outputs=[last_split, *view])
    desfazer.click(undo, inputs=[last_split], outputs=[last_split, *view])


if __name__ == "__main__":
    demo.launch(inbrowser=True)
