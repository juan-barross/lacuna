from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"


def test_painel_abre_com_os_dados_versionados():
    testing = pytest.importorskip("streamlit.testing.v1")
    app = testing.AppTest.from_file(str(APP / "streamlit_app.py"), default_timeout=120).run()

    assert not app.exception
    assert app.title[0].value == "Lacuna"
    assert [m.label for m in app.metric][:2] == ["Extratos de contrato lidos", "Com par no PNCP"]


def test_busca_nos_atos_responde():
    testing = pytest.importorskip("streamlit.testing.v1")
    app = testing.AppTest.from_file(str(APP / "streamlit_app.py"), default_timeout=120).run()

    app.text_input[0].input("merenda escolar").run()

    assert not app.exception
    assert any("extratos" in c.value for c in app.caption)


def test_anotacao_converte_valor_e_data_do_formato_brasileiro(monkeypatch):
    pytest.importorskip("gradio")
    monkeypatch.syspath_prepend(str(APP))
    import anotar_gradio as anotar

    assert anotar.to_number("1.474.895,28") == "1474895.28"
    assert anotar.to_date("1/8/2025") == "2025-08-01"
    assert anotar.br_number(1474895.28) == "1.474.895,28"
    assert anotar.br_date("2025-08-01") == "01/08/2025"
