from types import SimpleNamespace

import anthropic
import httpx
import pytest

from dxp.extract.llm import MODEL, PROMPT, LLMExtractor, usage_report
from dxp.extract.schema import Ato

ATO = Ato(tipo="contrato", contratada_cnpj="34.075.739/0001-84", valor=10.0)


class FakeMessages:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def reply(ato=ATO, stop="end_turn", tokens=(1000, 200)):
    usage = SimpleNamespace(input_tokens=tokens[0], output_tokens=tokens[1])
    return SimpleNamespace(parsed_output=ato, stop_reason=stop, usage=usage)


def make(tmp_path, *responses):
    messages = FakeMessages(*responses)
    return LLMExtractor(SimpleNamespace(messages=messages), cache_dir=tmp_path), messages


def test_pede_saida_no_formato_do_ato(tmp_path):
    extractor, messages = make(tmp_path, reply())

    assert extractor("texto") == ATO
    request = messages.calls[0]
    assert request["model"] == MODEL
    assert request["output_format"] is Ato
    assert request["system"] == PROMPT
    assert request["messages"] == [{"role": "user", "content": "texto"}]


def test_resposta_gravada_nao_chama_a_api_de_novo(tmp_path):
    extractor, messages = make(tmp_path, reply())
    extractor("texto")

    again, _ = make(tmp_path)
    call = again.extract("texto")

    assert call.ato == ATO
    assert call.input_tokens == 1000
    assert len(messages.calls) == 1


def test_resposta_cortada_vira_erro_registrado(tmp_path):
    extractor, _ = make(tmp_path, reply(ato=None, stop="max_tokens"))

    call = extractor.extract("texto")

    assert call.ato is None
    assert call.error == "stop_reason=max_tokens"
    assert extractor("texto").tipo == "outro"


def test_erro_da_api_e_registrado_sem_derrubar_a_avaliacao(tmp_path):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    extractor, _ = make(tmp_path, anthropic.APIConnectionError(request=request))

    call = extractor.extract("texto")

    assert call.ato is None
    assert "APIConnectionError" in call.error


def test_cnpj_invalido_aparece_em_problems(tmp_path):
    extractor, _ = make(tmp_path, reply(ato=Ato(tipo="contrato", contratada_cnpj="11111111111112")))

    assert extractor.extract("texto").problems == ["CNPJ inválido: 11111111111112"]


def test_relatorio_de_custo_e_latencia(tmp_path):
    extractor, _ = make(tmp_path, reply(tokens=(1000, 200)), reply(tokens=(3000, 400)))
    extractor("a")
    extractor("b")

    report = usage_report(extractor.calls)

    assert report["chamadas"] == 2
    assert report["custo_total_usd"] == pytest.approx((4000 * 0.10 + 600 * 0.50) / 1e6)
    assert report["custo_por_documento_usd"] == pytest.approx(report["custo_total_usd"] / 2)
