import hashlib
import json
import os
import time
from functools import cached_property
from pathlib import Path

import httpx
from pydantic import BaseModel, Field, ValidationError

from dxp.fetch import Fetcher, FetchError, RetryPolicy, new_client
from dxp.files import write_atomic
from dxp.schema import Ato
from dxp.stats import latency_summary

URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "anthropic/claude-opus-5.5"
FREE_MODEL = "nvidia/nemotron-3.5-super-vl:free"
USD_PER_MTOK = {MODEL: (4.0, 20.0), FREE_MODEL: (0.0, 0.0)}
REASONING = {MODEL: {"effort": "low"}, FREE_MODEL: {"enabled": False}}
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "llm_cache"
LLM_TIMEOUT = 180.0
LLM_RETRY = RetryPolicy(max_retries=6)
MAX_OUTPUT_TOKENS = 1500
BODY_CHARS = 200
ERROR_CHARS = 300

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


STRICT_SCHEMA = strict_schema()
SCHEMA_TEXT = json.dumps(STRICT_SCHEMA, ensure_ascii=False)
LOCAL_PROMPT = f"{PROMPT}\n\nResponda só com um JSON neste esquema:\n{SCHEMA_TEXT}"


class MissingApiKeyError(RuntimeError):
    pass


def local_messages(text: str) -> list[dict]:
    return [{"role": "system", "content": LOCAL_PROMPT}, {"role": "user", "content": text}]


def parse_answer(answer: str) -> Ato | None:
    try:
        return Ato.model_validate_json(answer[answer.find("{") : answer.rfind("}") + 1])
    except ValidationError:
        return None


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


def call_from_response(data: dict) -> Call:
    try:
        choice, usage = data["choices"][0], data["usage"]
        tokens = {"input_tokens": usage["prompt_tokens"], "output_tokens": usage["completion_tokens"]}
        finish_reason, content = choice["finish_reason"], choice["message"]["content"]
    except (KeyError, IndexError, TypeError):
        detail = data.get("error", data) if isinstance(data, dict) else data
        return Call(error=f"resposta sem choices ou usage: {str(detail)[:BODY_CHARS]}")
    if finish_reason != "stop":
        return Call(**tokens, error=f"finish_reason={finish_reason}")
    try:
        return Call(**tokens, ato=Ato.model_validate_json(content))
    except ValidationError as error:
        return Call(**tokens, error=repr(error)[:ERROR_CHARS])


class LLMExtractor:
    def __init__(
        self,
        http: httpx.Client | None = None,
        model: str = MODEL,
        cache_dir: Path = CACHE_DIR,
        retry: RetryPolicy = LLM_RETRY,
    ) -> None:
        self._http = http
        self._retry = retry
        self.model = model
        self.cache_dir = cache_dir / model.replace("/", "_").replace(":", "_")
        self.calls: list[Call] = []

    @cached_property
    def api(self) -> Fetcher:
        return Fetcher(self._http or self._open_session(), self._retry)

    def __call__(self, text: str) -> Ato:
        return self.extract(text).ato or Ato(tipo="outro")

    def usage(self) -> dict:
        return usage_report(self.calls, self.model)

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

    def _open_session(self) -> httpx.Client:
        token = os.environ.get("OPENROUTER_API_KEY")
        if not token:
            raise MissingApiKeyError("defina OPENROUTER_API_KEY no ambiente ou no .env")
        return new_client(headers={"Authorization": f"Bearer {token}"}, timeout=LLM_TIMEOUT)

    def _body(self, text: str) -> dict:
        return {
            "model": self.model,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "reasoning": REASONING[self.model],
            "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": text}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "ato", "strict": True, "schema": STRICT_SCHEMA},
            },
        }

    def _request(self, text: str) -> Call:
        api, body = self.api, self._body(text)
        start = time.perf_counter()
        call = self._post(api, body)
        call.seconds = time.perf_counter() - start
        return call

    def _post(self, api: Fetcher, body: dict) -> Call:
        try:
            data = api.post(URL, json=body).json()
        except httpx.HTTPStatusError as error:
            response = error.response
            return Call(error=f"HTTP {response.status_code}: {response.text[:BODY_CHARS]}")
        except (FetchError, httpx.HTTPError, json.JSONDecodeError) as error:
            return Call(error=repr(error)[:ERROR_CHARS])
        return call_from_response(data)


def usage_report(calls: list[Call], model: str = MODEL) -> dict:
    if not calls:
        return {}
    total = sum(c.cost(model) for c in calls)
    return {
        "modelo": model,
        "prompt": PROMPT_VERSION,
        "chamadas": len(calls),
        "erros": sum(c.error is not None for c in calls),
        "com_problema": sum(bool(c.problems) for c in calls),
        "custo_total_usd": round(total, 6),
        "custo_por_documento_usd": round(total / len(calls), 6),
        **latency_summary([c.seconds for c in calls]),
    }
