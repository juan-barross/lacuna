from pathlib import Path

import pytest

testing = pytest.importorskip("streamlit.testing.v1")
APP = Path(__file__).resolve().parents[1] / "app"


def test_painel_abre_com_os_dados_versionados():
    app = testing.AppTest.from_file(str(APP / "streamlit_app.py"), default_timeout=120).run()

    assert not app.exception
    assert app.title[0].value == "Lacuna"
    assert [m.label for m in app.metric][:2] == ["Extratos de contrato lidos", "Com par no PNCP"]


def test_busca_nos_atos_responde():
    app = testing.AppTest.from_file(str(APP / "streamlit_app.py"), default_timeout=120).run()

    app.text_input[0].input("merenda escolar").run()

    assert not app.exception
    assert any("extratos" in c.value for c in app.caption)


def test_app_de_anotacao_mostra_o_primeiro_trecho():
    app = testing.AppTest.from_file(str(APP / "anotar.py"), default_timeout=60).run()

    assert not app.exception
    assert app.radio[0].options == ["contrato", "pessoal", "outro"]
