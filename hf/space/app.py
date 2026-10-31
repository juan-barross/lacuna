import json
import os
import sys
from pathlib import Path

import gradio as gr
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

from dxp.local_model import LocalAnswer, LocalExtractor
from dxp.regex_baseline import extract as regex_extract
from dxp.schema import FIELDS

BASE = "Qwen/Qwen2.5-1.5B-Instruct"
ADAPTER = os.environ.get("ADAPTER") or sys.exit("defina a variável ADAPTER com o repositório do adaptador")
MAX_CHARS = 4000
QUEUE_SIZE = 8
EXAMPLES = json.loads((Path(__file__).parent / "exemplos.json").read_text(encoding="utf-8"))

tokenizer = AutoTokenizer.from_pretrained(ADAPTER)
base_model = AutoModelForCausalLM.from_pretrained(BASE, dtype=torch.float32)
tuned_model = PeftModel.from_pretrained(base_model, ADAPTER).merge_and_unload().eval()
extractor = LocalExtractor(tokenizer, tuned_model)


def status_message(answer: LocalAnswer) -> str:
    message = f"Modelo ajustado: {answer.seconds:.1f} s na CPU."
    if answer.ato is None:
        return message + " A saída não era um JSON válido do esquema."
    problems = answer.ato.problems()
    return message + (" Avisos: " + "; ".join(problems) if problems else "")


def compare(excerpt: str):
    excerpt = excerpt.strip()[:MAX_CHARS]
    if not excerpt:
        return [], "", "Cole um extrato de contrato."
    answer = extractor.extract(excerpt)
    regex = regex_extract(excerpt).model_dump(mode="json")
    tuned = answer.ato.model_dump(mode="json") if answer.ato else {}
    rows = [[field, tuned.get(field), regex.get(field)] for field in FIELDS]
    return rows, answer.raw_output, status_message(answer)


with gr.Blocks(title="Lacuna: extrator de contratos") as demo:
    gr.Markdown(
        "# Lacuna: extrator de extratos de contrato\n"
        f"Qwen2.5-1.5B-Instruct ajustado com QLoRA (`{ADAPTER}`) ao lado do extrator por regex do "
        "[Lacuna](https://github.com/juan-barross/lacuna). Cole um extrato de contrato de diário "
        "oficial municipal. Roda em CPU gratuita, então a resposta leva de 30 s a 1 min."
    )
    excerpt_box = gr.Textbox(label="Extrato", lines=10, max_length=MAX_CHARS)
    extract_button = gr.Button("Extrair", variant="primary")
    status_box = gr.Markdown()
    fields_table = gr.Dataframe(headers=["campo", "modelo ajustado", "regex"], wrap=True)
    with gr.Accordion("Saída bruta do modelo", open=False):
        raw_output_box = gr.Code(language="json")
    gr.Examples(EXAMPLES, inputs=excerpt_box)
    extract_button.click(compare, excerpt_box, [fields_table, raw_output_box, status_box], api_name=False)

demo.queue(max_size=QUEUE_SIZE, default_concurrency_limit=1)

if __name__ == "__main__":
    demo.launch()
