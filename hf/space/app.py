import json
import os
import time
from pathlib import Path

import gradio as gr
import torch
from peft import PeftModel
from pydantic import ValidationError
from transformers import AutoModelForCausalLM, AutoTokenizer

from dxp.llm import PROMPT
from dxp.regex_baseline import extract as regex_extract
from dxp.schema import FIELDS, Ato

BASE = "Qwen/Qwen2.5-1.5B-Instruct"
ADAPTER = os.environ.get("ADAPTER", "SEU_USUARIO_HF/lacuna-extrator-qwen2.5-1.5b-lora")
EXAMPLES = json.loads((Path(__file__).parent / "exemplos.json").read_text(encoding="utf-8"))

tok = AutoTokenizer.from_pretrained(ADAPTER)
model = PeftModel.from_pretrained(
    AutoModelForCausalLM.from_pretrained(BASE, dtype=torch.float32), ADAPTER
).eval()


def lora_extract(text: str) -> tuple[Ato | None, str]:
    messages = [{"role": "system", "content": PROMPT}, {"role": "user", "content": text}]
    inputs = tok.apply_chat_template(
        messages, add_generation_prompt=True, return_tensors="pt", return_dict=True
    )
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=512, do_sample=False, pad_token_id=tok.eos_token_id)
    answer = tok.decode(out[0, inputs["input_ids"].shape[1] :], skip_special_tokens=True)
    start, end = answer.find("{"), answer.rfind("}")
    try:
        return Ato.model_validate_json(answer[start : end + 1]), answer
    except ValidationError:
        return None, answer


def compare(text: str):
    text = text.strip()
    if not text:
        return [], "", "Cole um extrato de contrato."
    start = time.perf_counter()
    lora, raw = lora_extract(text)
    seconds = time.perf_counter() - start
    regex = regex_extract(text).model_dump(mode="json")
    tuned = lora.model_dump(mode="json") if lora else {}
    rows = [[f, tuned.get(f), regex.get(f)] for f in FIELDS]
    status = f"Modelo ajustado: {seconds:.1f} s na CPU."
    if lora is None:
        status += " A saída não era um JSON válido do esquema."
    elif lora.problems():
        status += " Avisos: " + "; ".join(lora.problems())
    return rows, raw, status


with gr.Blocks(title="Lacuna: extrator de contratos") as demo:
    gr.Markdown(
        "# Lacuna: extrator de extratos de contrato\n"
        f"Qwen2.5-1.5B-Instruct ajustado com QLoRA (`{ADAPTER}`) ao lado do extrator por regex do "
        "[Lacuna](https://github.com/juan-barross/lacuna). Cole um extrato de contrato de diário "
        "oficial municipal. Roda em CPU gratuita, então a resposta leva de 30 s a 1 min."
    )
    text = gr.Textbox(label="Extrato", lines=10)
    button = gr.Button("Extrair", variant="primary")
    status = gr.Markdown()
    table = gr.Dataframe(headers=["campo", "modelo ajustado", "regex"], wrap=True)
    with gr.Accordion("Saída bruta do modelo", open=False):
        raw = gr.Code(language="json")
    gr.Examples(EXAMPLES, inputs=text)
    button.click(compare, text, [table, raw, status])

if __name__ == "__main__":
    demo.launch()
