from datetime import date

import httpx
import pyarrow.parquet as pq
import pytest

from dxp.qd import BASE_URL, QDClient
from dxp.qd_store import QDStore, text_status

TEXT_OK = "EXTRATO DE CONTRATO Nº 12/2025. " * 50


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


TEXTS = {
    "aaa.txt": TEXT_OK,
    "bbb.txt": "https://transparencia.exemplo.rj.gov.br/anexo.pdf",
}


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
        if name in TEXTS:
            return httpx.Response(200, text=TEXTS[name])
        return httpx.Response(404)

    http = httpx.Client(base_url=BASE_URL, transport=httpx.MockTransport(handler))
    return QDClient(http, page_size=100, sleep=lambda _: None)


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


def test_download_grava_parquet_com_todos_os_diarios(tmp_path, client):
    store = QDStore(tmp_path)

    summary = store.download(client, ["3304557"], date(2025, 10, 1), date(2025, 10, 31))

    assert summary.gazettes == 4
    assert summary.by_status == {"ok": 1, "so_link": 1, "erro": 1, "sem_txt": 1}
    table = pq.read_table(store.parquet_path).to_pylist()
    by_id = {r["gazette_id"].rsplit("_", 1)[-1]: r for r in table}
    assert by_id["aaa"]["text"] == TEXT_OK
    assert by_id["aaa"]["date"] == date(2025, 10, 1)
    assert by_id["ccc"]["text_status"] == "erro"
    assert "404" in by_id["ccc"]["error"]
    assert by_id["ddd"]["text_status"] == "sem_txt"


def test_segunda_rodada_usa_o_cache(tmp_path, client, calls):
    store = QDStore(tmp_path)
    store.download(client, ["3304557"], date(2025, 10, 1), date(2025, 10, 31))
    first = len(calls)

    summary = store.download(client, ["3304557"], date(2025, 10, 1), date(2025, 10, 31))

    assert len(calls) - first == 1
    assert summary.texts_downloaded == 0
    assert (tmp_path / "raw" / "qd" / "gazettes" / "2025-10.json").exists()


def test_arquivo_parcial_nao_conta_como_cache(tmp_path, client):
    store = QDStore(tmp_path)
    partial = tmp_path / "raw" / "qd" / "txt" / "3304557" / "3304557_2025-10-01_aaa.part"
    partial.parent.mkdir(parents=True)
    partial.write_text("EXTRATO DE CONT", encoding="utf-8")

    summary = store.download(client, ["3304557"], date(2025, 10, 1), date(2025, 10, 31))

    assert summary.by_status["ok"] == 1
    assert not partial.exists()
