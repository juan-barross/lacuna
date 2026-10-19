import json
import os

import httpx
import pytest

from dxp.files import load_env
from dxp.llm import MODEL, PROMPT, LLMExtractor, strict_schema, usage_report
from dxp.schema import Ato

ATO = Ato(tipo="contrato", contratada_cnpj="34.075.739/0001-84", valor=10.0)


def reply(
    ato: Ato | None = ATO, finish: str = "stop", tokens=(1000, 200), status: int = 200
) -> httpx.Response:
    content = ato.model_dump_json() if ato else "{}"
    body = {
        "choices": [{"message": {"content": content}, "finish_reason": finish}],
        "usage": {"prompt_tokens": tokens[0], "completion_tokens": tokens[1]},
    }
    return httpx.Response(status, json=body)


def make(tmp_path, *responses):
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        response = responses[len(sent) - 1]
        if isinstance(response, Exception):
            raise response
        return response

    return LLMExtractor(httpx.Client(transport=httpx.MockTransport(handler)), cache_dir=tmp_path), sent


def test_pede_saida_no_formato_do_ato(tmp_path):
    extractor, sent = make(tmp_path, reply())

    assert extractor("texto") == ATO
    (body,) = sent
    assert body["model"] == MODEL
    assert body["messages"] == [{"role": "system", "content": PROMPT}, {"role": "user", "content": "texto"}]
    assert body["response_format"]["json_schema"]["schema"] == strict_schema()


def test_esquema_estrito_exige_todos_os_campos():
    schema = strict_schema()

    assert schema["required"] == list(Ato.model_fields)
    assert schema["additionalProperties"] is False


def test_resposta_gravada_nao_chama_a_api_de_novo(tmp_path):
    extractor, sent = make(tmp_path, reply())
    extractor("texto")

    again, sent_again = make(tmp_path)
    call = again.extract("texto")

    assert call.ato == ATO
    assert call.input_tokens == 1000
    assert (len(sent), len(sent_again)) == (1, 0)


def test_resposta_cortada_vira_erro_e_nao_vai_para_o_cache(tmp_path):
    extractor, sent = make(tmp_path, reply(finish="length"), reply())

    call = extractor.extract("texto")
    assert call.ato is None
    assert call.error == "finish_reason=length"
    assert extractor("texto") == ATO
    assert len(sent) == 2


@pytest.mark.parametrize(
    "response",
    [httpx.Response(401, json={"error": "chave inválida"}), httpx.ConnectError("sem rede"), reply(ato=None)],
)
def test_falha_vira_erro_registrado_sem_derrubar_a_avaliacao(tmp_path, response):
    extractor, _ = make(tmp_path, response)

    call = extractor.extract("texto")

    assert call.ato is None
    assert call.error
    assert extractor.calls[0].problems == [call.error]


def test_cnpj_invalido_aparece_em_problems(tmp_path):
    extractor, _ = make(tmp_path, reply(ato=Ato(tipo="contrato", contratada_cnpj="11111111111112")))

    assert extractor.extract("texto").problems == ["CNPJ inválido: 11111111111112"]


def test_relatorio_de_custo(tmp_path):
    extractor, _ = make(tmp_path, reply(tokens=(1000, 200)), reply(tokens=(3000, 400)))
    extractor("a")
    extractor("b")

    report = usage_report(extractor.calls)

    assert report["chamadas"] == 2
    assert report["custo_total_usd"] == pytest.approx((4000 * 4.0 + 600 * 20.0) / 1e6)
    assert report["custo_por_documento_usd"] == pytest.approx(report["custo_total_usd"] / 2)


def test_relatorio_vazio_sem_chamadas():
    assert usage_report([]) == {}


def test_p50_e_p95_da_latencia(tmp_path):
    extractor, _ = make(tmp_path, *[reply() for _ in range(20)])
    for i in range(20):
        extractor(f"texto {i}")
    for i, call in enumerate(extractor.calls):
        call.seconds = 10.0 if i >= 18 else 1.0

    report = usage_report(extractor.calls)

    assert (report["latencia_p50_s"], report["latencia_p95_s"]) == (1.0, 10.0)


def test_prompt_novo_invalida_o_cache(tmp_path, monkeypatch):
    extractor, sent = make(tmp_path, reply(), reply())
    extractor("texto")
    monkeypatch.setattr("dxp.llm.PROMPT_VERSION", "outro")

    extractor("texto")

    assert len(sent) == 2


def test_load_env_nao_sobrescreve_variavel_existente(tmp_path, monkeypatch):
    monkeypatch.setenv("JA_EXISTE", "ambiente")
    monkeypatch.delenv("NOVA", raising=False)
    env = tmp_path / ".env"
    env.write_text('# linha ignorada\nJA_EXISTE=arquivo\nNOVA="valor"\n', encoding="utf-8")

    load_env(env)

    assert (os.environ["JA_EXISTE"], os.environ["NOVA"]) == ("ambiente", "valor")
