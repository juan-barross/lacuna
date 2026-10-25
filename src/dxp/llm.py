import hashlib
import os
import statistics
import time
from functools import cached_property
from pathlib import Path

import httpx
from pydantic import BaseModel, Field, ValidationError

from dxp.fetch import Fetcher, FetchError
from dxp.files import write_atomic
from dxp.schema import Ato

URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "anthropic/claude-opus-5.5"
USD_PER_MTOK = {"anthropic/claude-opus-5.5": (4.0, 20.0)}
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "llm_cache"

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


def strict_schema() -> dict:
    schema = Ato.model_json_schema()
    return {**schema, "required": list(schema["properties"]), "additionalProperties": False}


class Call(BaseModel):
    ato: Ato | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    error: str | None = None
    problems: list[str] = Field(default_factory=list, exclude=True)

    def cost(self, model: str = MODEL) -> float:
        price_in, price_out = USD_PER_MTOK[model]
        return (self.input_tokens * price_in + self.output_tokens * price_out) / 1_000_000


class LLMExtractor:
    def __init__(self, http: httpx.Client | None = None, model=MODEL, cache_dir: Path = CACHE_DIR, **retry):
        self._http, self._retry = http, {"max_retries": 6, **retry}
        self.model = model
        self.cache_dir = cache_dir / model.replace("/", "_")
        self.calls: list[Call] = []

    @cached_property
    def api(self) -> Fetcher:
        token = os.environ.get("OPENROUTER_API_KEY", "")
        http = self._http or httpx.Client(headers={"Authorization": f"Bearer {token}"}, timeout=180)
        return Fetcher(URL, http, **self._retry)

    def __call__(self, text: str) -> Ato:
        return self.extract(text).ato or Ato(tipo="outro")

    def cache_path(self, text: str) -> Path:
        key = hashlib.sha256(f"{self.model}\n{PROMPT_VERSION}\n{text}".encode()).hexdigest()
        return self.cache_dir / f"{key}.json"

    def extract(self, text: str) -> Call:
        path = self.cache_path(text)
        if path.exists():
            call = Call.model_validate_json(path.read_text(encoding="utf-8"))
        else:
            call = self._request(text)
            if call.error is None:
                write_atomic(path, call.model_dump_json())
        call.problems = call.ato.problems() if call.ato else [call.error]
        self.calls.append(call)
        return call

    def _request(self, text: str) -> Call:
        body = {
            "model": self.model,
            "max_tokens": 1500,
            "reasoning": {"effort": "low"},
            "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": text}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "ato", "strict": True, "schema": strict_schema()},
            },
        }
        start = time.perf_counter()
        try:
            data = self.api.post(URL, json=body).json()
            choice, usage = data["choices"][0], data["usage"]
            tokens = {"input_tokens": usage["prompt_tokens"], "output_tokens": usage["completion_tokens"]}
            if choice["finish_reason"] != "stop":
                return Call(
                    **tokens,
                    seconds=time.perf_counter() - start,
                    error=f"finish_reason={choice['finish_reason']}",
                )
            ato = Ato.model_validate_json(choice["message"]["content"])
        except (FetchError, httpx.HTTPError, KeyError, ValidationError) as error:
            return Call(seconds=time.perf_counter() - start, error=repr(error)[:300])
        return Call(ato=ato, **tokens, seconds=time.perf_counter() - start)


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
