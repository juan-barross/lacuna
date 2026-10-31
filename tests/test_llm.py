import json

import httpx
import pytest
from pydantic import ValidationError

from dxp.fetch import RetryPolicy
from dxp.llm import (
    FREE_MODEL,
    MODEL,
    PROMPT,
    STRICT_SCHEMA,
    LLMExtractor,
    MissingApiKeyError,
    local_messages,
    parse_answer,
    usage_report,
)
from dxp.schema import Ato

ATO = Ato(tipo="contrato", contratada_cnpj="34.075.739/0001-84", valor=10.0)
USAGE = {"prompt_tokens": 1, "completion_tokens": 1}


def reply(
    ato: Ato | None = ATO, finish: str = "stop", tokens=(1000, 200), status: int = 200
) -> httpx.Response:
    content = ato.model_dump_json() if ato else "{}"
    body = {
        "choices": [{"message": {"content": content}, "finish_reason": finish}],
        "usage": {"prompt_tokens": tokens[0], "completion_tokens": tokens[1]},
    }
    return httpx.Response(status, json=body)


def make(tmp_path, *responses, model: str = MODEL):
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        response = responses[len(sent) - 1]
        if isinstance(response, Exception):
            raise response
        return response

    http = httpx.Client(transport=httpx.MockTransport(handler))
    retry = RetryPolicy(max_retries=1, sleep=lambda _: None)
    return LLMExtractor(http, model=model, cache_dir=tmp_path, retry=retry), sent


def test_pede_saida_no_formato_do_ato(tmp_path):
    extractor, sent = make(tmp_path, reply())

    assert extractor("texto") == ATO
    (body,) = sent
    assert body["model"] == MODEL
    assert body["messages"] == [{"role": "system", "content": PROMPT}, {"role": "user", "content": "texto"}]
    assert body["response_format"]["json_schema"]["schema"] == STRICT_SCHEMA


def test_esquema_estrito_exige_todos_os_campos():
    assert STRICT_SCHEMA["required"] == list(Ato.model_fields)
    assert STRICT_SCHEMA["additionalProperties"] is False


@pytest.mark.parametrize(
    ("model", "reasoning"),
    [(MODEL, {"effort": "low"}), (FREE_MODEL, {"enabled": False})],
)
def test_raciocinio_depende_do_modelo(tmp_path, model, reasoning):
    extractor, sent = make(tmp_path, reply(), model=model)

    extractor("texto")

    assert sent[0]["model"] == model
    assert sent[0]["reasoning"] == reasoning


def test_cada_modelo_tem_a_propria_pasta_de_cache(tmp_path):
    paid, _ = make(tmp_path)
    free, _ = make(tmp_path, model=FREE_MODEL)

    assert paid.cache_path("texto").parent != free.cache_path("texto").parent
    assert ":" not in free.cache_path("texto").parent.name


def test_resposta_gravada_nao_chama_a_api_de_novo(tmp_path):
    extractor, sent = make(tmp_path, reply())
    extractor("texto")

    again, sent_again = make(tmp_path)
    call = again.extract("texto")

    assert call.ato == ATO
    assert call.input_tokens == 1000
    assert (len(sent), len(sent_again)) == (1, 0)


def test_cache_corrompido_levanta_erro_em_vez_de_esconder(tmp_path):
    extractor, _ = make(tmp_path)
    path = extractor.cache_path("texto")
    path.parent.mkdir(parents=True)
    path.write_text("{não é json", encoding="utf-8")

    with pytest.raises(ValidationError):
        extractor.extract("texto")


def test_resposta_cortada_vira_erro_e_nao_vai_para_o_cache(tmp_path):
    extractor, sent = make(tmp_path, reply(finish="length"), reply())

    call = extractor.extract("texto")
    assert call.ato is None
    assert call.error == "finish_reason=length"
    assert call.input_tokens == 1000
    assert extractor("texto") == ATO
    assert len(sent) == 2


def test_erro_http_guarda_status_e_corpo_da_resposta(tmp_path):
    extractor, _ = make(tmp_path, httpx.Response(402, text='{"error": "créditos insuficientes"}'))

    call = extractor.extract("texto")

    assert call.ato is None
    assert call.error.startswith("HTTP 402: ")
    assert "créditos insuficientes" in call.error


def test_corpo_do_erro_http_e_cortado(tmp_path):
    extractor, _ = make(tmp_path, httpx.Response(400, text="x" * 1000))

    assert len(extractor.extract("texto").error) < 250


def test_erro_devolvido_com_status_200_aparece_no_call_error(tmp_path):
    body = {"error": {"message": "provedor indisponível", "code": 502}}
    extractor, _ = make(tmp_path, httpx.Response(200, json=body))

    call = extractor.extract("texto")

    assert call.ato is None
    assert "sem choices ou usage" in call.error
    assert "provedor indisponível" in call.error


@pytest.mark.parametrize(
    "body",
    [
        {"usage": USAGE},
        {"choices": [], "usage": USAGE},
        {"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]},
        {"choices": [{"finish_reason": "stop"}], "usage": USAGE},
    ],
)
def test_corpo_sem_choices_ou_usage_vira_erro_registrado(tmp_path, body):
    extractor, _ = make(tmp_path, httpx.Response(200, json=body))

    call = extractor.extract("texto")

    assert call.ato is None
    assert "sem choices ou usage" in call.error


def test_corpo_que_nao_e_json_vira_erro_registrado(tmp_path):
    extractor, _ = make(tmp_path, httpx.Response(200, text="<html>bad gateway</html>"))

    call = extractor.extract("texto")

    assert call.ato is None
    assert "JSONDecodeError" in call.error


def test_falha_de_rede_vira_erro_registrado(tmp_path):
    extractor, sent = make(tmp_path, httpx.ConnectError("sem rota"), httpx.ConnectError("sem rota"))

    call = extractor.extract("texto")

    assert call.ato is None
    assert "falha de rede" in call.error
    assert len(sent) == 2


def test_resposta_fora_do_esquema_guarda_os_tokens_gastos(tmp_path):
    extractor, _ = make(tmp_path, reply(ato=None, tokens=(500, 7)))

    call = extractor.extract("texto")

    assert call.ato is None
    assert "validation error for Ato" in call.error
    assert (call.input_tokens, call.output_tokens) == (500, 7)


def test_falha_registra_o_erro_em_problems(tmp_path):
    extractor, _ = make(tmp_path, httpx.Response(401, json={"error": "chave inválida"}))

    call = extractor.extract("texto")

    assert extractor.calls[0].problems == [call.error]
    assert "chave inválida" in call.error


def test_chamada_que_falha_devolve_ato_outro_e_conta_o_erro(tmp_path):
    extractor, _ = make(tmp_path, httpx.Response(500), httpx.Response(500), reply())

    assert extractor("falha") == Ato(tipo="outro")
    assert extractor("ok") == ATO
    assert extractor.usage()["erros"] == 1


def test_cnpj_invalido_aparece_em_problems(tmp_path):
    extractor, _ = make(tmp_path, reply(ato=Ato(tipo="contrato", contratada_cnpj="11111111111112")))

    assert extractor.extract("texto").problems == ["CNPJ inválido: 11111111111112"]


def test_sem_chave_da_api_falha_alto_em_vez_de_mandar_bearer_vazio(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    extractor = LLMExtractor(cache_dir=tmp_path)

    with pytest.raises(MissingApiKeyError, match="OPENROUTER_API_KEY"):
        extractor.extract("texto")
    assert extractor.calls == []


def test_sem_chave_da_api_a_resposta_gravada_ainda_funciona(tmp_path, monkeypatch):
    extractor, _ = make(tmp_path, reply())
    extractor("texto")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    offline = LLMExtractor(cache_dir=tmp_path)

    assert offline("texto") == ATO


def test_com_chave_da_api_a_sessao_leva_o_cabecalho_de_autorizacao(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-teste")
    extractor = LLMExtractor(cache_dir=tmp_path)

    assert extractor.api.http.headers["Authorization"] == "Bearer sk-teste"
    extractor.api.http.close()


def test_relatorio_de_custo(tmp_path):
    extractor, _ = make(tmp_path, reply(tokens=(1000, 200)), reply(tokens=(3000, 400)))
    extractor("a")
    extractor("b")

    report = usage_report(extractor.calls)

    assert report["chamadas"] == 2
    assert report["custo_total_usd"] == pytest.approx((4000 * 4.0 + 600 * 20.0) / 1e6)
    assert report["custo_por_documento_usd"] == pytest.approx(report["custo_total_usd"] / 2)


def test_relatorio_conta_erros_e_chamadas_com_problema(tmp_path):
    invalid_cnpj = Ato(tipo="contrato", contratada_cnpj="11111111111112")
    extractor, _ = make(tmp_path, reply(), reply(ato=invalid_cnpj), httpx.Response(401))
    for text in ("ok", "cnpj", "erro"):
        extractor(text)

    report = usage_report(extractor.calls)

    assert report["erros"] == 1
    assert report["com_problema"] == 2
    assert report["modelo"] == MODEL


def test_relatorio_do_modelo_gratis_nao_tem_custo(tmp_path):
    extractor, _ = make(tmp_path, reply(), model=FREE_MODEL)
    extractor("texto")

    assert extractor.usage()["custo_total_usd"] == 0.0
    assert extractor.usage()["modelo"] == FREE_MODEL


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


def test_limite_de_ritmo_e_retentado(tmp_path):
    extractor, sent = make(tmp_path, httpx.Response(429), reply())

    assert extractor("texto") == ATO
    assert len(sent) == 2


def test_prompt_local_traz_o_esquema_e_o_trecho():
    system, user = local_messages("EXTRATO DO CONTRATO Nº 1/2026")

    assert system["content"].startswith(PROMPT) and '"data_assinatura"' in system["content"]
    assert user == {"role": "user", "content": "EXTRATO DO CONTRATO Nº 1/2026"}


@pytest.mark.parametrize(
    "answer",
    [
        ATO.model_dump_json(),
        f"```json\n{ATO.model_dump_json()}\n```",
        f"Aqui está o resultado: {ATO.model_dump_json()} Espero ter ajudado.",
    ],
)
def test_resposta_local_ignora_texto_em_volta_do_json(answer):
    assert parse_answer(answer) == ATO


@pytest.mark.parametrize(
    "answer",
    [
        "não sei",
        "",
        '{"tipo": "contrato", "valor": ',
        '{"tipo": "aditivo"}',
        '{"valor": 10.0}',
        "} fora de ordem {",
    ],
)
def test_resposta_local_invalida_vira_none(answer):
    assert parse_answer(answer) is None
