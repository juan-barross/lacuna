import re
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

HEADER = re.compile(r"^[ \t]*EXTRATO\s+D[OE]\s+CONTRATO\b(?![^\n]*\.{4})", re.M)
NEXT_HEADER = re.compile(r"^[ \t]*EXTRATO\b", re.M)
MAX_CHARS = 3000
COLUMNS = ["gazette_id", "territory_id", "territory_name", "date", "url"]

SCHEMA = pa.schema(
    [
        ("ato_id", pa.string()),
        ("gazette_id", pa.string()),
        ("territory_id", pa.string()),
        ("territory_name", pa.string()),
        ("date", pa.date32()),
        ("url", pa.string()),
        ("text", pa.string()),
    ]
)


PAGE_NOISE = re.compile(
    r"^.*(?:Assinado Digitalmente por|Diário Oficial do Município|D\.O\.RIO|Ano [XLVI]+ •).*\n?",
    re.M,
)


def clean(text: str) -> str:
    text = PAGE_NOISE.sub("", text)
    text = re.sub(r"-\n(?=[a-zà-ú])", "", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def segments(text: str) -> list[str]:
    out = []
    for match in HEADER.finditer(text):
        nxt = NEXT_HEADER.search(text, match.end())
        end = min(nxt.start() if nxt else len(text), match.start() + MAX_CHARS)
        segment = clean(text[match.start() : end])
        if "R$" in segment:
            out.append(segment)
    return out


def build_atos(gazettes: Path, out: Path) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    source = pq.ParquetFile(gazettes)
    with pq.ParquetWriter(out, SCHEMA) as writer:
        for batch in source.iter_batches(batch_size=100, columns=[*COLUMNS, "text", "text_status"]):
            rows = [
                {"ato_id": f"{g['gazette_id']}#{i}", **{c: g[c] for c in COLUMNS}, "text": seg}
                for g in batch.to_pylist()
                if g["text_status"] == "ok"
                for i, seg in enumerate(segments(g["text"]))
            ]
            writer.write_table(pa.Table.from_pylist(rows, schema=SCHEMA))
            total += len(rows)
    return total
