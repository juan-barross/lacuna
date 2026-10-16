import json
from pathlib import Path

import streamlit as st
from pydantic import ValidationError

from dxp.schema import Ato

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "data" / "gold"
QUEUE = GOLD / "fila.jsonl"
TEXT_FIELDS = ["numero_contrato", "processo", "contratada_nome", "contratada_cnpj", "objeto"]


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def to_number(raw: str) -> str | None:
    raw = raw.strip()
    return raw.replace(".", "").replace(",", ".") if "," in raw else raw or None


st.set_page_config(page_title="Anotação", layout="wide")

queue = read(QUEUE)
if not queue:
    st.error("Rode `dxp amostra` antes de anotar.")
    st.stop()

done = {r["ato_id"] for split in ("dev", "test") for r in read(GOLD / f"{split}.jsonl")}
pending = [r for r in queue if r["ato_id"] not in done]
st.progress(len(done) / len(queue), text=f"{len(done)} de {len(queue)} rotulados")
if not pending:
    st.success("Tudo rotulado.")
    st.stop()

item = pending[0]
left, right = st.columns([3, 2])
left.caption(f"{item['territory_name']} · {item['date']} · {item['split']} · {item['ato_id']}")
left.text(item["text"])
with left.expander("Guia de anotação"):
    st.markdown((ROOT / "docs" / "guia_anotacao.md").read_text(encoding="utf-8"))

with right.form("rotulo", clear_on_submit=True):
    tipo = st.radio("tipo", ["contrato", "pessoal", "outro"], horizontal=True)
    texts = {field: st.text_input(field) for field in TEXT_FIELDS}
    valor = st.text_input("valor total em reais")
    assinatura = st.text_input("data_assinatura (AAAA-MM-DD)")
    observacao = st.text_input("observação")
    if st.form_submit_button("Salvar e ir para o próximo", type="primary"):
        label = {
            "tipo": tipo,
            **{k: v.strip() or None for k, v in texts.items()},
            "valor": to_number(valor),
            "data_assinatura": assinatura.strip() or None,
        }
        try:
            ato = Ato.model_validate(label)
        except ValidationError as error:
            st.error(error)
            st.stop()
        row = {
            "ato_id": item["ato_id"],
            "territory_name": item["territory_name"],
            "text": item["text"],
            **ato.model_dump(mode="json"),
            "observacao": observacao.strip() or None,
        }
        with (GOLD / f"{item['split']}.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        st.rerun()
