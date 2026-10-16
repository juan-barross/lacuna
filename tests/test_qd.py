import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from dxp.fetch import FetchError
from dxp.qd import BASE_URL, Gazette, QDClient, month_windows

FIXTURES = Path(__file__).parent / "fixtures" / "qd"
QUATIS = "3304128"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_client(handler) -> QDClient:
    http = httpx.Client(base_url=BASE_URL, transport=httpx.MockTransport(handler))
    return QDClient(http, page_size=2, sleep=lambda _: None)


def paged_handler(items: list[dict], calls: list[httpx.Request]):

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        size = int(request.url.params["size"])
        offset = int(request.url.params["offset"])
        return httpx.Response(
            200, json={"total_gazettes": len(items), "gazettes": items[offset : offset + size]}
        )

    return handler


def test_month_windows_cobre_o_periodo_sem_buracos():
    windows = month_windows(date(2025, 10, 15), date(2026, 1, 10))
    assert windows == [
        (date(2025, 10, 15), date(2025, 10, 31)),
        (date(2025, 11, 1), date(2025, 11, 30)),
        (date(2025, 12, 1), date(2025, 12, 31)),
        (date(2026, 1, 1), date(2026, 1, 10)),
    ]


def test_month_windows_periodo_dentro_de_um_mes():
    assert month_windows(date(2026, 2, 3), date(2026, 2, 20)) == [(date(2026, 2, 3), date(2026, 2, 20))]


def test_gazette_aceita_item_da_api():
    item = {
        "territory_id": "3304557",
        "date": "2025-10-01",
        "scraped_at": "2025-10-02T06:24:50.886086",
        "url": "https://data.queridodiario.ok.org.br/3304557/2025-10-01/abc.pdf",
        "territory_name": "Rio de Janeiro",
        "state_code": "RJ",
        "excerpts": [],
        "edition": "136",
        "is_extra_edition": False,
        "txt_url": "https://data.queridodiario.ok.org.br/3304557/2025-10-01/abc.txt",
    }
    g = Gazette.model_validate(item)
    assert g.date == date(2025, 10, 1)
    assert g.territory_id == "3304557"
    assert g.gazette_id == "3304557_2025-10-01_abc"


def test_gazette_sem_txt_url():
    g = Gazette.model_validate(
        {
            "territory_id": "3304557",
            "date": "2025-10-01",
            "scraped_at": "2025-10-02T06:24:50",
            "url": "https://data.queridodiario.ok.org.br/3304557/2025-10-01/abc.pdf",
            "territory_name": "Rio de Janeiro",
            "state_code": "RJ",
            "txt_url": None,
        }
    )
    assert g.txt_url is None
    assert g.excerpts == []


def test_search_envia_parametros_e_le_a_resposta():
    fixture = load_fixture("gazettes_quatis_2025-10-01_10.json")
    calls: list[httpx.Request] = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=fixture)

    client = make_client(handler)
    total, gazettes = client.search([QUATIS, "3304557"], date(2025, 10, 1), date(2025, 10, 10))

    assert total == 6
    assert [g.date.day for g in gazettes] == [1, 2, 3, 8, 9, 10]
    params = calls[0].url.params
    assert params.get_list("territory_ids") == [QUATIS, "3304557"]
    assert params["published_since"] == "2025-10-01"
    assert params["sort_by"] == "ascending_date"
    assert "querystring" not in params


def test_iter_gazettes_pagina_por_offset():
    items = load_fixture("gazettes_quatis_2025-10-01_10.json")["gazettes"]
    calls: list[httpx.Request] = []
    client = make_client(paged_handler(items, calls))

    gazettes = list(client.iter_gazettes([QUATIS], date(2025, 10, 1), date(2025, 10, 10)))

    assert len(gazettes) == 6
    assert [int(c.url.params["offset"]) for c in calls] == [0, 2, 4]


def test_iter_gazettes_uma_chamada_por_mes():
    calls: list[httpx.Request] = []
    client = make_client(paged_handler([], calls))

    list(client.iter_gazettes([QUATIS], date(2025, 10, 1), date(2025, 12, 31)))

    windows = [(c.url.params["published_since"], c.url.params["published_until"]) for c in calls]
    assert windows == [
        ("2025-10-01", "2025-10-31"),
        ("2025-11-01", "2025-11-30"),
        ("2025-12-01", "2025-12-31"),
    ]


def test_iter_gazettes_remove_repetidos():
    item = load_fixture("gazettes_quatis_2025-10-01_10.json")["gazettes"][0]
    client = make_client(paged_handler([item, item, item], []))

    gazettes = list(client.iter_gazettes([QUATIS], date(2025, 10, 1), date(2025, 10, 10)))

    assert len(gazettes) == 1


def test_janela_no_teto_e_dividida_ao_meio():
    calls: list[httpx.Request] = []

    def handler(request):
        calls.append(request)
        since = request.url.params["published_since"]
        until = request.url.params["published_until"]
        total = 10_000 if (since, until) == ("2025-10-01", "2025-10-31") else 0
        return httpx.Response(200, json={"total_gazettes": total, "gazettes": []})

    list(make_client(handler).iter_gazettes([QUATIS], date(2025, 10, 1), date(2025, 10, 31)))

    windows = [(c.url.params["published_since"], c.url.params["published_until"]) for c in calls]
    assert windows == [
        ("2025-10-01", "2025-10-31"),
        ("2025-10-01", "2025-10-16"),
        ("2025-10-17", "2025-10-31"),
    ]


def test_dia_unico_no_teto_levanta_erro():
    def handler(request):
        return httpx.Response(200, json={"total_gazettes": 10_000, "gazettes": []})

    with pytest.raises(FetchError, match="único dia"):
        list(make_client(handler).iter_gazettes([QUATIS], date(2025, 10, 1), date(2025, 10, 1)))


def test_retenta_em_503():
    responses = iter([httpx.Response(503), httpx.Response(200, json={"cities": []})])
    client = make_client(lambda request: next(responses))

    assert client.cities() == []


def test_desiste_depois_das_retentativas():
    calls: list[httpx.Request] = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503)

    with pytest.raises(FetchError, match="503"):
        make_client(handler).cities()
    assert len(calls) == 4


def test_nao_retenta_erro_do_cliente():
    calls: list[httpx.Request] = []

    def handler(request):
        calls.append(request)
        return httpx.Response(422)

    with pytest.raises(httpx.HTTPStatusError):
        make_client(handler).cities()
    assert len(calls) == 1


def test_gazette_troca_endereco_interno_do_s3_pelo_publico():
    path = "3302858/2025-12-02/600522b9f67b2b33122562555e3af4af613b2f67"
    g = Gazette.model_validate(
        {
            "territory_id": "3302858",
            "territory_name": "Mesquita",
            "state_code": "RJ",
            "date": "2025-12-02",
            "scraped_at": "2025-12-03T06:00:00",
            "url": f"s3://okbr-qd-migration//{path}.pdf",
            "txt_url": f"s3://okbr-qd-migration//{path}.txt",
        }
    )
    assert g.txt_url == f"https://data.queridodiario.ok.org.br/{path}.txt"
    assert g.gazette_id == "3302858_2025-12-02_600522b9f67b2b33122562555e3af4af613b2f67"


def test_nao_retenta_protocolo_invalido():
    calls: list[httpx.Request] = []

    def handler(request):
        calls.append(request)
        raise httpx.UnsupportedProtocol("s3://")

    with pytest.raises(FetchError, match="falha de rede"):
        make_client(handler).cities()
    assert len(calls) == 1


def test_espera_mais_quando_a_api_limita_o_ritmo():
    waits: list[float] = []
    responses = iter([httpx.Response(429), httpx.Response(200, json={"cities": []})])
    http = httpx.Client(base_url=BASE_URL, transport=httpx.MockTransport(lambda r: next(responses)))

    QDClient(http, sleep=waits.append).cities()

    assert waits == [30.0]


def test_respeita_retry_after_quando_a_api_manda():
    waits: list[float] = []
    responses = iter(
        [httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200, json={"cities": []})]
    )
    http = httpx.Client(base_url=BASE_URL, transport=httpx.MockTransport(lambda r: next(responses)))

    QDClient(http, sleep=waits.append).cities()

    assert waits == [7.0]
