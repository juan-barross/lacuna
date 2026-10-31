import json

import httpx
import pytest

from dxp.fetch import USER_AGENT, Fetcher, FetchError, RetryPolicy, new_client

URL = "https://api.exemplo.org/dados"


class Server:
    def __init__(self, *responses: httpx.Response | Exception) -> None:
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []
        self.waits: list[float] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def fetcher(self, max_retries: int = 3) -> Fetcher:
        http = httpx.Client(transport=httpx.MockTransport(self.handle))
        return Fetcher(http, RetryPolicy(max_retries=max_retries, sleep=self.waits.append))


def test_resposta_ok_volta_sem_espera():
    server = Server(httpx.Response(200, json={"ok": True}))

    assert server.fetcher().get(URL).json() == {"ok": True}
    assert server.waits == []


def test_503_e_retentado_com_espera_dobrando():
    server = Server(httpx.Response(503), httpx.Response(502), httpx.Response(200, text="ok"))

    assert server.fetcher().get(URL).text == "ok"
    assert server.waits == [2.0, 4.0]


def test_desiste_depois_do_limite_de_tentativas():
    server = Server(*[httpx.Response(503) for _ in range(3)])

    with pytest.raises(FetchError, match="503 após 3 tentativas"):
        server.fetcher(max_retries=2).get(URL)
    assert len(server.requests) == 3
    assert server.waits == [2.0, 4.0]


def test_max_retries_zero_tenta_uma_vez():
    server = Server(httpx.Response(503))

    with pytest.raises(FetchError, match="após 1 tentativas"):
        server.fetcher(max_retries=0).get(URL)
    assert server.waits == []


@pytest.mark.parametrize("status", [400, 401, 404, 422])
def test_erro_do_cliente_nao_e_retentado(status):
    server = Server(httpx.Response(status))

    with pytest.raises(httpx.HTTPStatusError) as raised:
        server.fetcher().get(URL)
    assert raised.value.response.status_code == status
    assert len(server.requests) == 1
    assert server.waits == []


def test_429_sem_retry_after_espera_o_padrao():
    server = Server(httpx.Response(429), httpx.Response(200))

    server.fetcher().get(URL)

    assert server.waits == [30.0]


def test_429_com_retry_after_espera_o_que_a_api_pediu():
    server = Server(httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200))

    server.fetcher().get(URL)

    assert server.waits == [7.0]


def test_erro_de_rede_e_retentado():
    server = Server(
        httpx.ConnectError("sem rota"), httpx.ReadTimeout("lento"), httpx.Response(200, text="ok")
    )

    assert server.fetcher().get(URL).text == "ok"
    assert server.waits == [2.0, 4.0]


def test_erro_de_rede_persistente_vira_fetch_error():
    server = Server(*[httpx.ConnectError("sem rota") for _ in range(2)])

    with pytest.raises(FetchError, match="falha de rede em .*sem rota") as raised:
        server.fetcher(max_retries=1).get(URL)
    assert isinstance(raised.value.__cause__, httpx.ConnectError)
    assert len(server.requests) == 2


def test_erro_que_nao_e_transitorio_nao_e_retentado():
    server = Server(httpx.UnsupportedProtocol("s3://"))

    with pytest.raises(FetchError, match="falha de rede"):
        server.fetcher().get(URL)
    assert len(server.requests) == 1


def test_post_envia_o_corpo_json_em_todas_as_tentativas():
    server = Server(httpx.Response(503), httpx.Response(200))

    server.fetcher().post(URL, json={"a": 1})

    assert [json.loads(r.content) for r in server.requests] == [{"a": 1}, {"a": 1}]
    assert {r.method for r in server.requests} == {"POST"}


def test_get_envia_os_parametros():
    server = Server(httpx.Response(200))

    server.fetcher().get(URL, params={"pagina": 2})

    assert server.requests[0].url.params["pagina"] == "2"


def test_fecha_o_cliente_ao_sair_do_with():
    server = Server()
    http = httpx.Client(transport=httpx.MockTransport(server.handle))

    with Fetcher(http):
        pass

    assert http.is_closed


def test_cliente_novo_identifica_o_projeto_e_aceita_cabecalhos():
    client = new_client("https://api.exemplo.org", headers={"Authorization": "Bearer x"}, timeout=5)

    assert client.headers["User-Agent"] == USER_AGENT
    assert client.headers["Authorization"] == "Bearer x"
    assert client.timeout.read == 5
    assert str(client.base_url) == "https://api.exemplo.org"
