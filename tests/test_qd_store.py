from datetime import date

import httpx
import pyarrow.parquet as pq
import pytest

from dxp.qd import BASE_URL, QDClient, download, text_status

TEXT_OK = "EXTRATO DE CONTRATO Nº 12/2025. " * 50
TEXTS = {"aaa.txt": TEXT_OK, "bbb.txt": "https://transparencia.exemplo.rj.gov.br/anexo.pdf"}
OCTOBER = (date(2025, 10, 1), date(2025, 10, 31))


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

    http = httpx.Client(base_url=BASE_URL, transport=httpx.MockTransport(handler))
    return QDClient(http, sleep=lambda _: None)


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
    assert download(client, ["3304557"], *OCTOBER, tmp_path) == {
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
    assert by_name["ddd"]["text"] == ""


def test_segunda_rodada_usa_o_cache(tmp_path, client, calls):
    download(client, ["3304557"], *OCTOBER, tmp_path)
    first = len(calls)

    download(client, ["3304557"], *OCTOBER, tmp_path)

    assert len(calls) - first == 1
    assert (tmp_path / "raw" / "qd" / "gazettes" / "2025-10.json").exists()


def test_arquivo_parcial_nao_conta_como_cache(tmp_path, client):
    partial = tmp_path / "raw" / "qd" / "txt" / "3304557" / "3304557_2025-10-01_aaa.part"
    partial.parent.mkdir(parents=True)
    partial.write_text("EXTRATO DE CONT", encoding="utf-8")

    assert download(client, ["3304557"], *OCTOBER, tmp_path)["ok"] == 1
    assert not partial.exists()
