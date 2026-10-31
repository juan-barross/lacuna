from datetime import date

import httpx
import pyarrow.parquet as pq
import pytest

from dxp.fetch import FetchError, RetryPolicy
from dxp.period import Period
from dxp.qd import (
    BASE_URL,
    Gazette,
    QDClient,
    build_row,
    download,
    listing_path,
    status_of,
    text_path,
    text_status,
)

TEXT_OK = "EXTRATO DE CONTRATO Nº 12/2025. " * 50
TEXTS = {"aaa.txt": TEXT_OK, "bbb.txt": "https://transparencia.exemplo.rj.gov.br/anexo.pdf"}
OCTOBER = Period(date(2025, 10, 1), date(2025, 10, 31))


def gazette(day: int, name: str, txt: bool = True) -> dict:
    url = f"https://data.queridodiario.ok.org.br/3304557/2025-10-{day:02d}/{name}"
    return {
        "territory_id": "3304557",
        "territory_name": "Rio de Janeiro",
        "state_code": "RJ",
        "date": f"2025-10-{day:02d}",
        "scraped_at": "2025-10-02T06:00:00",
        "url": url + ".pdf",
        "txt_url": url + ".txt" if txt else None,
    }


def make_client(handler) -> QDClient:
    http = httpx.Client(base_url=BASE_URL, transport=httpx.MockTransport(handler))
    return QDClient(http, retry=RetryPolicy(sleep=lambda _: None))


@pytest.fixture
def calls():
    return []


@pytest.fixture
def client(calls):
    items = [gazette(1, "aaa"), gazette(2, "bbb"), gazette(3, "ccc"), gazette(6, "ddd", txt=False)]

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/gazettes":
            return httpx.Response(200, json={"total_gazettes": len(items), "gazettes": items})
        name = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, text=TEXTS[name]) if name in TEXTS else httpx.Response(404)

    return make_client(handler)


@pytest.mark.parametrize(
    ("text", "status"),
    [
        ("", "vazio"),
        ("  \n\t ", "vazio"),
        ("\nhttps://transparencia.quatis.rj.gov.br/x/anexo.pdf\n", "so_link"),
        ("ESCALA DE SERVIÇO SOMENTE NA VERSÃO HTML", "curto"),
        (TEXT_OK, "ok"),
    ],
)
def test_text_status(text, status):
    assert text_status(text) == status


@pytest.mark.parametrize(
    ("txt", "error", "text", "status"),
    [
        (True, "boom", "", "erro"),
        (False, None, "", "sem_txt"),
        (True, None, TEXT_OK, "ok"),
        (True, None, "", "vazio"),
    ],
)
def test_status_of(txt, error, text, status):
    assert status_of(Gazette.model_validate(gazette(1, "aaa", txt=txt)), error, text) == status


def test_download_grava_parquet_com_todos_os_diarios(tmp_path, client):
    assert download(client, ["3304557"], OCTOBER, tmp_path) == {
        "ok": 1,
        "so_link": 1,
        "erro": 1,
        "sem_txt": 1,
    }

    rows = pq.read_table(tmp_path / "processed" / "qd_gazettes.parquet").to_pylist()
    by_name = {r["gazette_id"].rsplit("_", 1)[-1]: r for r in rows}
    assert by_name["aaa"]["text"] == TEXT_OK
    assert by_name["aaa"]["date"] == date(2025, 10, 1)
    assert "404" in by_name["ccc"]["error"]
    assert by_name["ccc"]["text_status"] == "erro"
    assert by_name["ddd"]["text"] == ""
    assert by_name["ddd"]["text_status"] == "sem_txt"


def test_segunda_rodada_usa_o_cache(tmp_path, client, calls):
    download(client, ["3304557"], OCTOBER, tmp_path)
    first = len(calls)

    download(client, ["3304557"], OCTOBER, tmp_path)

    assert len(calls) - first == 1
    assert list((tmp_path / "raw" / "qd" / "gazettes").glob("2025-10_*.json"))


def test_cache_da_listagem_depende_das_cidades_e_do_periodo(tmp_path):
    raw = tmp_path / "raw"
    october = Period(date(2025, 10, 1), date(2025, 10, 31))
    paths = {
        listing_path(raw, ["3304557"], october),
        listing_path(raw, ["3304557", "3304128"], october),
        listing_path(raw, ["3304557"], Period(date(2025, 10, 1), date(2025, 10, 15))),
    }

    assert len(paths) == 3
    assert listing_path(raw, ["3304128", "3304557"], october) == listing_path(
        raw, ["3304557", "3304128"], october
    )


def test_outra_lista_de_cidades_nao_reaproveita_o_cache(tmp_path, client, calls):
    download(client, ["3304557"], OCTOBER, tmp_path)
    listings = [c for c in calls if c.url.path == "/gazettes"]

    download(client, ["3304557", "3304128"], OCTOBER, tmp_path)

    assert len([c for c in calls if c.url.path == "/gazettes"]) == len(listings) + 1


def test_listagem_incompleta_nao_e_gravada_no_cache(tmp_path):
    def handler(request):
        page = [gazette(1, "aaa")] if request.url.params["offset"] == "0" else []
        return httpx.Response(200, json={"total_gazettes": 2, "gazettes": page})

    with pytest.raises(FetchError, match="informou 2 diários, vieram 1"):
        download(make_client(handler), ["3304557"], OCTOBER, tmp_path)
    assert not (tmp_path / "raw" / "qd" / "gazettes").exists()


def test_arquivo_parcial_nao_conta_como_cache(tmp_path, client):
    partial = tmp_path / "raw" / "qd" / "txt" / "3304557" / "3304557_2025-10-01_aaa.part"
    partial.parent.mkdir(parents=True)
    partial.write_text("EXTRATO DE CONT", encoding="utf-8")

    assert download(client, ["3304557"], OCTOBER, tmp_path)["ok"] == 1
    assert not partial.exists()


def test_falha_de_download_fica_no_parquet_com_o_tipo_do_erro(tmp_path, client):
    download(client, ["3304557"], OCTOBER, tmp_path)

    rows = pq.read_table(tmp_path / "processed" / "qd_gazettes.parquet").to_pylist()
    (failed,) = [r for r in rows if r["text_status"] == "erro"]
    assert failed["error"].startswith("HTTPStatusError(")


def test_texto_gravado_fica_dentro_da_pasta_do_municipio(tmp_path):
    raw = tmp_path / "raw"
    path = text_path(raw, Gazette.model_validate(gazette(1, "aaa")))

    assert path == (raw / "txt" / "3304557" / "3304557_2025-10-01_aaa.txt").resolve()


def test_build_row_sem_erro_le_o_texto_gravado(tmp_path):
    raw = tmp_path / "raw"
    g = Gazette.model_validate(gazette(1, "aaa"))
    path = text_path(raw, g)
    path.parent.mkdir(parents=True)
    path.write_text(TEXT_OK, encoding="utf-8")

    row = build_row(raw, g, None)

    assert (row["text"], row["text_status"], row["error"]) == (TEXT_OK, "ok", None)
    assert row["gazette_id"] == g.gazette_id
