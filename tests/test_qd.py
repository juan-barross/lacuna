from datetime import date

from dxp.ingest.qd import Gazette, month_windows


def test_month_windows_cobre_o_periodo_sem_buracos():
    windows = month_windows(date(2025, 10, 15), date(2026, 1, 10))
    assert windows == [
        (date(2025, 10, 15), date(2025, 10, 31)),
        (date(2025, 11, 1), date(2025, 11, 30)),
        (date(2025, 12, 1), date(2025, 12, 31)),
        (date(2026, 1, 1), date(2026, 1, 10)),
    ]


def test_month_windows_periodo_dentro_de_um_mes():
    assert month_windows(date(2026, 2, 3), date(2026, 2, 20)) == [
        (date(2026, 2, 3), date(2026, 2, 20))
    ]


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
