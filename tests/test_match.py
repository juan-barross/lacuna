from datetime import date

import pytest

from dxp.match import rates_by_city, reconcile, wilson

RIO = "3304557"


def ato(**kw) -> dict:
    base = {
        "ato_id": "a",
        "territory_id": RIO,
        "territory_name": "Rio de Janeiro",
        "date": date(2025, 10, 10),
        "tipo": "contrato",
        "contratada_nome": "ITALIA EMPREENDIMENTOS LTDA",
        "contratada_cnpj": None,
        "valor": 95400.0,
        "data_assinatura": date(2025, 9, 11),
    }
    return {**base, **kw}


def contract(**kw) -> dict:
    base = {
        "numero_controle": "pncp-1",
        "territory_id": RIO,
        "fornecedor_ni": "34075739000184",
        "fornecedor_nome": "ITALIA EMPREENDIMENTOS LTDA",
        "valor_global": 95400.0,
        "data_assinatura": date(2025, 9, 11),
        "data_publicacao": date(2025, 9, 20),
    }
    return {**base, **kw}


def status(a: dict, contracts: list[dict]) -> str:
    return reconcile([a], contracts)[0]["status"]


def test_casa_por_valor_data_e_nome():
    row = reconcile([ato()], [contract()])[0]

    assert row["status"] == "casado"
    assert row["pncp_numero_controle"] == "pncp-1"


def test_casa_por_cnpj_mesmo_com_nome_diferente():
    assert (
        status(ato(contratada_nome="ITALIA EMP", contratada_cnpj="34075739000184"), [contract()])
        == "casado"
    )


def test_provavel_quando_so_valor_e_data_batem():
    assert status(ato(contratada_nome=None), [contract()]) == "provável"


@pytest.mark.parametrize(
    "other",
    [
        contract(valor_global=100000.0),
        contract(data_assinatura=date(2026, 3, 1)),
        contract(territory_id="3303302"),
    ],
)
def test_sem_par_fora_da_tolerancia(other):
    assert status(ato(), [other]) == "sem par"


def test_tolerancia_de_um_por_cento_no_valor():
    assert status(ato(), [contract(valor_global=95400.0 * 1.009)]) == "casado"


def test_usa_data_do_diario_quando_falta_assinatura():
    assert status(ato(data_assinatura=None), [contract()]) == "casado"


def test_pessoal_e_sem_valor_ficam_fora_da_taxa():
    rows = reconcile(
        [ato(), ato(tipo="pessoal"), ato(valor=None), ato(valor=1.0)],
        [contract()],
    )
    city = rates_by_city(rows)[0]

    assert [r["status"] for r in rows] == ["casado", "fora do escopo", "sem valor", "sem par"]
    assert city["elegiveis"] == 2
    assert city["taxa"] == 0.5
    assert city["ic_inferior"] < 0.5 < city["ic_superior"]


def test_wilson():
    low, high = wilson(50, 100)

    assert low == pytest.approx(0.404, abs=1e-3)
    assert high == pytest.approx(0.596, abs=1e-3)
    assert wilson(0, 0) == (0.0, 0.0)


def test_nomes_diferentes_nao_viram_provavel():
    assert status(ato(contratada_nome="WENDELL DO VALE SOUZA"), [contract()]) == "sem par"
