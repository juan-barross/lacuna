import sys
from pathlib import Path

import pytest

from dxp.files import write_jsonl

pytest.importorskip("gradio")

APP = Path(__file__).resolve().parents[1] / "app"


@pytest.fixture(scope="module")
def anotar():
    sys.path.insert(0, str(APP))
    try:
        import anotar_gradio
    finally:
        sys.path.remove(str(APP))
    return anotar_gradio


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.474.895,28", "1474895.28"),
        ("95,40", "95.40"),
        ("  10  ", "10"),
        ("10.5", "10.5"),
        ("", None),
        ("   ", None),
    ],
)
def test_to_number(anotar, raw, expected):
    assert anotar.to_number(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1/8/2025", "2025-08-01"),
        ("11/08/2025", "2025-08-11"),
        (" 2025-08-11 ", "2025-08-11"),
        ("", None),
    ],
)
def test_to_date(anotar, raw, expected):
    assert anotar.to_date(raw) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(1474895.28, "1.474.895,28"), (95.4, "95,40"), (0.0, "0,00"), (None, "")],
)
def test_br_number(anotar, value, expected):
    assert anotar.br_number(value) == expected


@pytest.mark.parametrize(("iso", "expected"), [("2025-08-01", "01/08/2025"), (None, ""), ("", "")])
def test_br_date(anotar, iso, expected):
    assert anotar.br_date(iso) == expected


@pytest.fixture
def gold(anotar, tmp_path, monkeypatch):
    monkeypatch.setattr(anotar, "GOLD", tmp_path)
    monkeypatch.setattr(anotar, "QUEUE", tmp_path / "fila.jsonl")
    monkeypatch.setattr(anotar, "DRAFT", tmp_path / "rascunho.jsonl")
    return tmp_path


def test_pending_sem_nenhum_rotulo_devolve_o_primeiro_da_fila(anotar, gold):
    write_jsonl([{"ato_id": "a"}, {"ato_id": "b"}], gold / "fila.jsonl")

    item, progress = anotar.pending()

    assert item == {"ato_id": "a"}
    assert progress == "**0 de 2 rotulados**"


def test_pending_pula_os_trechos_ja_rotulados(anotar, gold):
    write_jsonl([{"ato_id": "a"}, {"ato_id": "b"}], gold / "fila.jsonl")
    write_jsonl([{"ato_id": "a"}], gold / "dev.jsonl")

    item, progress = anotar.pending()

    assert item == {"ato_id": "b"}
    assert progress == "**1 de 2 rotulados**"


def test_pending_com_a_fila_ausente_levanta_erro(anotar, gold):
    with pytest.raises(FileNotFoundError):
        anotar.pending()


def test_rascunhos_ausentes_sao_lista_vazia(anotar, gold):
    assert anotar.drafts() == {}
