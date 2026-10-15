import hashlib
import json
import statistics
import time
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

import anthropic

from dxp.extract.schema import Ato

MODEL = "claude-haiku-5-5"
USD_PER_MTOK = {"claude-haiku-5-5": (0.10, 0.50)}
CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "llm_cache"

PROMPT = """Você extrai dados de extratos de contrato publicados em diários oficiais municipais.

Use só o que está escrito no trecho. Quando um campo não aparece, deixe-o nulo; não deduza.

- tipo: "contrato" para contrato com fornecedor ou prestador; "pessoal" para contratação de \
pessoa física por tempo determinado (processo seletivo simplificado); "outro" quando o trecho \
não é um extrato de contrato (termo aditivo, errata, rescisão).
- contratada_cnpj: CNPJ da contratada, nunca o do município ou do órgão contratante. \
Pode ter letras.
- contratada_nome: razão social ou nome, sem o CNPJ e sem "a empresa".
- objeto: o texto do objeto, sem "o presente contrato tem por objeto".
- valor: valor total em reais. Se houver valor global e valor empenhado, use o global. \
Valor só por extenso também conta.
- data_assinatura: data de assinatura; sem ela, a data do fecho ("Cidade, 11 de agosto de 2025"). \
Nunca a data de início da vigência."""

PROMPT_VERSION = hashlib.sha256(PROMPT.encode()).hexdigest()[:8]


@dataclass
class Call:
    ato: Ato | None
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    error: str | None = None
    problems: list[str] = field(default_factory=list)

    def cost(self, model: str = MODEL) -> float:
        price_in, price_out = USD_PER_MTOK[model]
        return (self.input_tokens * price_in + self.output_tokens * price_out) / 1_000_000

    def to_json(self) -> str:
        ato = self.ato.model_dump(mode="json") if self.ato else None
        usage = {"input_tokens": self.input_tokens, "output_tokens": self.output_tokens}
        return json.dumps({"ato": ato, **usage, "seconds": self.seconds, "error": self.error})

    @classmethod
    def from_json(cls, raw: str) -> "Call":
        data = json.loads(raw)
        ato = Ato.model_validate(data.pop("ato")) if data["ato"] else data.pop("ato")
        return cls(ato=ato, **data)


class LLMExtractor:
    def __init__(self, client=None, model: str = MODEL, cache_dir: Path = CACHE_DIR) -> None:
        self._client = client
        self.model = model
        self.cache_dir = cache_dir / model
        self.calls: list[Call] = []

    @cached_property
    def client(self):
        return self._client or anthropic.Anthropic()

    def __call__(self, text: str) -> Ato:
        return self.extract(text).ato or Ato(tipo="outro")

    def extract(self, text: str) -> Call:
        key = hashlib.sha256(f"{self.model}\n{PROMPT_VERSION}\n{text}".encode()).hexdigest()
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            call = Call.from_json(path.read_text(encoding="utf-8"))
        else:
            call = self._request(text)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(call.to_json(), encoding="utf-8")
        call.problems = call.ato.problems() if call.ato else [call.error]
        self.calls.append(call)
        return call

    def _request(self, text: str) -> Call:
        start = time.perf_counter()
        try:
            response = self.client.messages.parse(
                model=self.model,
                max_tokens=4000,
                system=PROMPT,
                messages=[{"role": "user", "content": text}],
                output_format=Ato,
            )
        except anthropic.APIError as error:
            return Call(ato=None, seconds=time.perf_counter() - start, error=repr(error))
        finished = response.stop_reason == "end_turn"
        return Call(
            ato=response.parsed_output if finished else None,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            seconds=time.perf_counter() - start,
            error=None if finished else f"stop_reason={response.stop_reason}",
        )


def usage_report(calls: list[Call], model: str = MODEL) -> dict:
    if not calls:
        return {}
    latencies = sorted(c.seconds for c in calls)
    total = sum(c.cost(model) for c in calls)
    return {
        "modelo": model,
        "prompt": PROMPT_VERSION,
        "chamadas": len(calls),
        "erros": sum(c.error is not None for c in calls),
        "com_problema": sum(bool(c.problems) for c in calls),
        "custo_total_usd": round(total, 6),
        "custo_por_documento_usd": round(total / len(calls), 6),
        "latencia_p50_s": round(statistics.median(latencies), 2),
        "latencia_p95_s": round(latencies[int(0.95 * (len(latencies) - 1))], 2),
    }
