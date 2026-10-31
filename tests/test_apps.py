from pathlib import Path

import pytest

from dxp.files import read_csv

testing = pytest.importorskip("streamlit.testing.v1")

APP = Path(__file__).resolve().parents[1] / "app"
APP_DATA = APP / "data"
STATUS_LABELS = {"conciliado", "sem texto", "sem elegíveis"}


def open_painel():
    return testing.AppTest.from_file(str(APP / "streamlit_app.py"), default_timeout=120).run()


def extract_count(painel) -> int:
    (caption,) = [c.value for c in painel.caption if c.value.endswith(" extratos")]
    return int(caption.split()[0])


@pytest.fixture(scope="module")
def painel():
    return open_painel()


def expected_status(city: dict, rates: dict[str, dict]) -> str:
    if float(city["pct_texto"]) == 0:
        return "sem texto"
    rate = rates.get(city["territory_id"])
    return "conciliado" if rate and int(rate["elegiveis"]) > 0 else "sem elegíveis"


def test_painel_abre_com_os_dados_versionados(painel):
    assert not painel.exception
    assert painel.title[0].value == "Lacuna"


def test_painel_mostra_as_quatro_metricas(painel):
    assert [m.label for m in painel.metric] == [
        "Extratos de contrato lidos",
        "Com par no PNCP",
        "Sem par no PNCP",
        "Municípios sem texto no diário",
    ]


def test_painel_tem_as_tres_abas(painel):
    assert [tab.label for tab in painel.tabs] == ["Conciliação", "Atos", "Cobertura do diário"]


def test_tabela_de_municipios_rotula_a_situacao_de_cada_cidade(painel):
    table = painel.dataframe[0].value
    rates = {r["territory_id"]: r for r in read_csv(APP_DATA / "conciliacao.csv")}
    cities = {c["municipio"]: c for c in read_csv(APP_DATA / "cobertura.csv")}

    assert set(table["situacao"]) <= STATUS_LABELS
    assert dict(zip(table["municipio"], table["situacao"], strict=True)) == {
        name: expected_status(city, rates) for name, city in cities.items()
    }


def test_tabela_de_municipios_mostra_traco_onde_falta_contagem(painel):
    table = painel.dataframe[0].value
    with_contracts = {r["territory_id"] for r in read_csv(APP_DATA / "pncp_contratos.csv")}
    cities = {c["municipio"]: c["territory_id"] for c in read_csv(APP_DATA / "cobertura.csv")}

    without_contracts = {name for name, territory_id in cities.items() if territory_id not in with_contracts}

    assert set(table.loc[table["pncp_contratos"] == "—", "municipio"]) == without_contracts


@pytest.mark.slow
def test_busca_nos_atos_filtra_pelos_termos():
    painel = open_painel()
    before = extract_count(painel)

    painel.text_input[0].input("merenda escolar").run()

    assert not painel.exception
    assert 0 < extract_count(painel) < before


@pytest.mark.slow
def test_busca_limita_o_tamanho_da_consulta():
    assert open_painel().text_input[0].max_chars == 200
