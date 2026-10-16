import json
from datetime import date
from pathlib import Path

import httpx
import pyarrow.parquet as pq

from dxp.pncp import BASE_URL, PNCPClient, download, flatten, windows

CONTRATO = json.loads(
    (Path(__file__).parent / "fixtures" / "pncp" / "contrato_niteroi.json").read_text("utf-8")
)
NITEROI = "3303302"
PREFEITURA = "28521748000159"
SINCE, UNTIL = date(2025, 8, 1), date(2026, 10, 14)


def page(data: list, remaining: int = 0) -> httpx.Response:
    return httpx.Response(200, json={"data": data, "paginasRestantes": remaining})


def org(cnpj: str, esfera: str) -> dict:
    return {"orgaoEntidade": {"cnpj": cnpj, "razaoSocial": cnpj, "esferaId": esfera}}


def make_client(handler) -> PNCPClient:
    http = httpx.Client(base_url=BASE_URL, transport=httpx.MockTransport(handler))
    return PNCPClient(http, sleep=lambda _: None)


def test_contratos_segue_as_paginas():
    calls = []

    def handler(request):
        calls.append(request.url.params)
        return page([CONTRATO], remaining=1 if request.url.params["pagina"] == "1" else 0)

    contracts = make_client(handler).contracts(PREFEITURA, SINCE, UNTIL)

    assert len(contracts) == 4
    assert [c["pagina"] for c in calls] == ["1", "2", "1", "2"]
    assert [c["dataInicial"] for c in calls[::2]] == ["20250801", "20260801"]
    assert calls[0]["tamanhoPagina"] == "500"


def test_204_e_lista_vazia():
    client = make_client(lambda request: httpx.Response(204))

    assert client.contracts(PREFEITURA, SINCE, UNTIL) == []


def test_orgaos_municipais_ignora_federais():
    def handler(request):
        if request.url.params["codigoModalidadeContratacao"] != "8":
            return httpx.Response(204)
        return page([org(PREFEITURA, "M"), org("00394502000144", "F"), org(PREFEITURA, "M")])

    agencies = make_client(handler).municipal_agencies(NITEROI, SINCE, UNTIL)

    assert list(agencies) == [PREFEITURA]


def test_flatten_contrato_real():
    row = flatten(CONTRATO, NITEROI)

    assert row["numero_controle"] == "28521748000159-2-000075/2025"
    assert row["fornecedor_ni"] == "52281385000106"
    assert row["valor_global"] == 6613.0
    assert row["data_assinatura"] == date(2025, 9, 29)
    assert row["territory_id"] == NITEROI


def test_download_grava_parquet_e_usa_cache(tmp_path):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/contratacoes/publicacao"):
            return page([org(PREFEITURA, "M")])
        return page([CONTRATO, CONTRATO])

    client = make_client(handler)

    assert download(client, [NITEROI], SINCE, UNTIL, tmp_path) == 1
    first = len(calls)
    assert download(client, [NITEROI], SINCE, UNTIL, tmp_path) == 1
    assert len(calls) == first
    assert pq.read_table(tmp_path / "processed" / "pncp_contratos.parquet").num_rows == 1


def test_janelas_de_no_maximo_365_dias():
    assert windows(SINCE, UNTIL) == [
        (date(2025, 8, 1), date(2026, 7, 31)),
        (date(2026, 8, 1), date(2026, 10, 14)),
    ]
