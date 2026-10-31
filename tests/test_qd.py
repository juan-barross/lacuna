import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from dxp.fetch import FetchError, RetryPolicy
from dxp.period import Period
from dxp.qd import BASE_URL, Gazette, QDClient

FIXTURES = Path(__file__).parent / "fixtures" / "qd"
QUATIS = "3304128"
OCTOBER = Period(date(2025, 10, 1), date(2025, 10, 10))
HASH = "600522b9f67b2b33122562555e3af4af613b2f67"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_client(handler) -> QDClient:
    http = httpx.Client(base_url=BASE_URL, transport=httpx.MockTransport(handler))
    return QDClient(http, page_size=2, retry=RetryPolicy(sleep=lambda _: None))


def paged_handler(items: list[dict], calls: list[httpx.Request], total: int | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        size = int(request.url.params["size"])
        offset = int(request.url.params["offset"])
        body = {
            "total_gazettes": len(items) if total is None else total,
            "gazettes": items[offset : offset + size],
        }
        return httpx.Response(200, json=body)

    return handler


def item(**overrides) -> dict:
    base = {
        "territory_id": "3302858",
        "territory_name": "Mesquita",
        "state_code": "RJ",
        "date": "2025-12-02",
        "scraped_at": "2025-12-03T06:00:00",
        "url": f"https://data.queridodiario.ok.org.br/3302858/2025-12-02/{HASH}.pdf",
        "txt_url": f"https://data.queridodiario.ok.org.br/3302858/2025-12-02/{HASH}.txt",
    }
    return {**base, **overrides}


def windows_of(calls: list[httpx.Request]) -> list[tuple[str, str]]:
    return [(c.url.params["published_since"], c.url.params["published_until"]) for c in calls]


def test_gazette_aceita_item_da_api():
    g = Gazette.model_validate(
        item(territory_id="3304557", date="2025-10-01", url="https://x.org/3304557/2025-10-01/abc.pdf")
    )

    assert g.date == date(2025, 10, 1)
    assert g.territory_id == "3304557"
    assert g.gazette_id == "3304557_2025-10-01_abc"


def test_gazette_troca_endereco_interno_do_s3_pelo_publico():
    path = f"3302858/2025-12-02/{HASH}"
    g = Gazette.model_validate(
        item(url=f"s3://okbr-qd-migration//{path}.pdf", txt_url=f"s3://okbr-qd-migration//{path}.txt")
    )

    assert g.txt_url == f"https://data.queridodiario.ok.org.br/{path}.txt"
    assert g.gazette_id == f"3302858_2025-12-02_{HASH}"


@pytest.mark.parametrize("territory_id", ["", "330285", "33028588", "../3302858", "3302858/x", "330285a"])
def test_gazette_recusa_territory_id_que_nao_e_codigo_ibge(territory_id):
    with pytest.raises(ValueError, match="territory_id"):
        Gazette.model_validate(item(territory_id=territory_id))


@pytest.mark.parametrize("name", ["..", "a b", "x%2Fy", "é"])
def test_gazette_recusa_hash_de_arquivo_com_caracteres_de_caminho(name):
    with pytest.raises(ValueError, match="hash do arquivo"):
        Gazette.model_validate(
            item(url=f"https://data.queridodiario.ok.org.br/3302858/2025-12-02/{name}.pdf")
        )


def test_search_envia_parametros_e_le_a_resposta():
    fixture = load_fixture("gazettes_quatis_2025-10-01_10.json")
    calls: list[httpx.Request] = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=fixture)

    total, gazettes = make_client(handler).search([QUATIS, "3304557"], OCTOBER)

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

    gazettes = list(client.iter_gazettes([QUATIS], OCTOBER))

    assert len(gazettes) == 6
    assert [int(c.url.params["offset"]) for c in calls] == [0, 2, 4]


def test_iter_gazettes_uma_chamada_por_mes():
    calls: list[httpx.Request] = []
    client = make_client(paged_handler([], calls))

    list(client.iter_gazettes([QUATIS], Period(date(2025, 10, 1), date(2025, 12, 31))))

    assert windows_of(calls) == [
        ("2025-10-01", "2025-10-31"),
        ("2025-11-01", "2025-11-30"),
        ("2025-12-01", "2025-12-31"),
    ]


def test_iter_gazettes_remove_repetidos():
    first = load_fixture("gazettes_quatis_2025-10-01_10.json")["gazettes"][0]
    client = make_client(paged_handler([first, first, first], []))

    assert len(list(client.iter_gazettes([QUATIS], OCTOBER))) == 1


def test_janela_no_teto_e_dividida_ao_meio():
    calls: list[httpx.Request] = []

    def handler(request):
        calls.append(request)
        window = (request.url.params["published_since"], request.url.params["published_until"])
        total = 10_000 if window == ("2025-10-01", "2025-10-31") else 0
        return httpx.Response(200, json={"total_gazettes": total, "gazettes": []})

    list(make_client(handler).iter_gazettes([QUATIS], Period(date(2025, 10, 1), date(2025, 10, 31))))

    assert windows_of(calls) == [
        ("2025-10-01", "2025-10-31"),
        ("2025-10-01", "2025-10-16"),
        ("2025-10-17", "2025-10-31"),
    ]


def test_dia_unico_no_teto_levanta_erro():
    def handler(request):
        return httpx.Response(200, json={"total_gazettes": 10_000, "gazettes": []})

    day = Period(date(2025, 10, 1), date(2025, 10, 1))
    with pytest.raises(FetchError, match="único dia"):
        list(make_client(handler).iter_gazettes([QUATIS], day))


def test_listagem_incompleta_levanta_erro_em_vez_de_virar_cache_parcial():
    items = load_fixture("gazettes_quatis_2025-10-01_10.json")["gazettes"]
    client = make_client(paged_handler(items[:3], [], total=6))

    with pytest.raises(FetchError, match="informou 6 diários, vieram 3"):
        client.listing([QUATIS], OCTOBER)


def test_cities_le_a_lista_da_api():
    client = make_client(lambda request: httpx.Response(200, json={"cities": [{"territory_id": QUATIS}]}))

    assert client.cities() == [{"territory_id": QUATIS}]


def test_fetch_text_sem_txt_url_levanta_erro():
    gazette = Gazette.model_validate(item(txt_url=None))

    with pytest.raises(FetchError, match="não tem txt_url"):
        make_client(lambda request: httpx.Response(200)).fetch_text(gazette)
