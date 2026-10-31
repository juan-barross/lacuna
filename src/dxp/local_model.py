import time
from dataclasses import dataclass

from dxp.llm import local_messages, parse_answer
from dxp.schema import Ato
from dxp.stats import latency_summary

MAX_NEW_TOKENS = 512


@dataclass(frozen=True)
class LocalAnswer:
    ato: Ato | None
    raw_output: str
    seconds: float


class LocalExtractor:
    def __init__(self, tokenizer, model, max_new_tokens: int = MAX_NEW_TOKENS) -> None:
        self.tokenizer = tokenizer
        self.model = model
        self.max_new_tokens = max_new_tokens
        self.answers: list[LocalAnswer] = []

    def __call__(self, text: str) -> Ato:
        answer = self.extract(text)
        self.answers.append(answer)
        return answer.ato or Ato(tipo="outro")

    def extract(self, text: str) -> LocalAnswer:
        inputs = self.tokenizer.apply_chat_template(
            local_messages(text), add_generation_prompt=True, return_tensors="pt", return_dict=True
        ).to(self.model.device)
        start = time.perf_counter()
        generated = self.model.generate(
            **inputs,
            max_new_tokens=self.max_new_tokens,
            do_sample=False,
            use_cache=True,
            pad_token_id=self.tokenizer.eos_token_id,
        )
        seconds = time.perf_counter() - start
        prompt_length = inputs["input_ids"].shape[1]
        raw_output = self.tokenizer.decode(generated[0, prompt_length:], skip_special_tokens=True)
        return LocalAnswer(parse_answer(raw_output), raw_output, seconds)

    def usage(self, model_name: str) -> dict:
        if not self.answers:
            return {}
        return {
            "modelo": model_name,
            "chamadas": len(self.answers),
            "erros": sum(answer.ato is None for answer in self.answers),
            "custo_total_usd": 0.0,
            **latency_summary([answer.seconds for answer in self.answers]),
        }
