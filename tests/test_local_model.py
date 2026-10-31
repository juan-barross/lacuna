import numpy as np
import pytest

from dxp.llm import local_messages
from dxp.local_model import LocalExtractor
from dxp.schema import Ato

ATO = Ato(tipo="contrato", valor=10.0)
PROMPT_TOKENS = 5


class Encoded(dict):
    device = None

    def to(self, device):
        self.device = device
        return self


class FakeTokenizer:
    eos_token_id = 7

    def __init__(self, answers):
        self.answers = iter(answers)
        self.templates = []
        self.decoded = []

    def apply_chat_template(self, messages, **options):
        self.templates.append((messages, options))
        return Encoded(input_ids=np.zeros((1, PROMPT_TOKENS), dtype=int))

    def decode(self, tokens, skip_special_tokens):
        self.decoded.append((tokens.tolist(), skip_special_tokens))
        return next(self.answers)


class FakeModel:
    device = "cpu"

    def __init__(self):
        self.generate_calls = []

    def generate(self, **kwargs):
        self.generate_calls.append(kwargs)
        return np.arange(PROMPT_TOKENS + 3).reshape(1, -1)


def extractor_with(*answers):
    tokenizer, model = FakeTokenizer(answers), FakeModel()
    return LocalExtractor(tokenizer, model), tokenizer, model


def test_pede_ao_modelo_so_a_resposta_depois_do_prompt():
    extractor, tokenizer, model = extractor_with(ATO.model_dump_json())

    answer = extractor.extract("EXTRATO")

    assert answer.ato == ATO
    assert tokenizer.decoded == [([5, 6, 7], True)]
    messages, options = tokenizer.templates[0]
    assert messages == local_messages("EXTRATO")
    assert options["add_generation_prompt"] is True
    (call,) = model.generate_calls
    assert (call["max_new_tokens"], call["do_sample"], call["pad_token_id"]) == (512, False, 7)


def test_devolve_a_saida_bruta_e_o_tempo():
    extractor, _, _ = extractor_with("```json\n" + ATO.model_dump_json() + "\n```")

    answer = extractor.extract("EXTRATO")

    assert answer.raw_output.startswith("```json")
    assert answer.seconds >= 0.0


def test_saida_invalida_vira_ato_none_sem_derrubar():
    extractor, _, _ = extractor_with("não sei")

    assert extractor.extract("EXTRATO").ato is None


def test_extract_nao_guarda_historico():
    extractor, _, _ = extractor_with(ATO.model_dump_json())

    extractor.extract("EXTRATO")

    assert extractor.answers == []


def test_chamada_devolve_ato_ou_outro_e_guarda_historico():
    extractor, _, _ = extractor_with(ATO.model_dump_json(), "lixo")

    assert extractor("a") == ATO
    assert extractor("b") == Ato(tipo="outro")
    assert len(extractor.answers) == 2


def test_uso_conta_erros_e_resume_a_latencia():
    extractor, _, _ = extractor_with(ATO.model_dump_json(), "lixo", ATO.model_dump_json())
    for text in "abc":
        extractor(text)

    usage = extractor.usage("Qwen + LoRA")

    assert usage["modelo"] == "Qwen + LoRA"
    assert (usage["chamadas"], usage["erros"], usage["custo_total_usd"]) == (3, 1, 0.0)
    assert usage["latencia_p50_s"] <= usage["latencia_p95_s"]


def test_uso_sem_chamadas_e_vazio():
    extractor, _, _ = extractor_with()

    assert extractor.usage("x") == {}


@pytest.mark.parametrize("limit", [64, 1024])
def test_limite_de_tokens_novos_e_configuravel(limit):
    tokenizer, model = FakeTokenizer([ATO.model_dump_json()]), FakeModel()

    LocalExtractor(tokenizer, model, max_new_tokens=limit).extract("EXTRATO")

    assert model.generate_calls[0]["max_new_tokens"] == limit
