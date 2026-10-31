from datetime import date

import pytest

from dxp.match import rates_by_city, reconcile

RIO = "3304557"
SIGNED = date(2025, 9, 11)


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
        "data_assinatura": SIGNED,
    }
    return {**base, **kw}


def contract(**kw) -> dict:
    base = {
        "numero_controle": "pncp-1",
        "territory_id": RIO,
        "fornecedor_ni": "34075739000184",
        "fornecedor_nome": "ITALIA EMPREENDIMENTOS LTDA",
        "valor_global": 95400.0,
        "data_assinatura": SIGNED,
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
        status(ato(contratada_nome="ITALIA EMP", contratada_cnpj="34075739000184"), [contract()]) == "casado"
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


def test_nomes_diferentes_nao_viram_provavel():
    assert status(ato(contratada_nome="WENDELL DO VALE SOUZA"), [contract()]) == "sem par"


def test_usa_data_do_diario_quando_falta_assinatura():
    assert status(ato(data_assinatura=None), [contract()]) == "casado"


def test_contrato_do_pncp_sem_assinatura_usa_a_data_de_publicacao():
    other = contract(data_assinatura=None, data_publicacao=SIGNED)

    assert status(ato(), [other]) == "casado"


@pytest.mark.parametrize(
    ("value", "contract_value", "expected"),
    [
        (100000.0, 101000.0, "casado"),
        (100000.0, 99000.0, "casado"),
        (100000.0, 101100.0, "sem par"),
        (100000.0, 98900.0, "sem par"),
        (50.0, 51.0, "casado"),
        (50.0, 51.01, "sem par"),
        (50.0, 49.0, "casado"),
        (50.0, 48.99, "sem par"),
    ],
)
def test_tolerancia_de_um_por_cento_com_piso_de_um_real(value, contract_value, expected):
    assert status(ato(valor=value), [contract(valor_global=contract_value)]) == expected


@pytest.mark.parametrize(
    ("days", "expected"),
    [(0, "casado"), (60, "casado"), (-60, "casado"), (61, "sem par"), (-61, "sem par")],
)
def test_janela_de_sessenta_dias(days, expected):
    other = contract(data_assinatura=date.fromordinal(SIGNED.toordinal() + days))

    assert status(ato(), [other]) == expected


@pytest.mark.parametrize("value", [None, 0, 0.0])
def test_ato_sem_valor_nao_entra_na_taxa(value):
    assert status(ato(valor=value), [contract()]) == "sem valor"


@pytest.mark.parametrize("value", [None, 0, 0.0])
def test_contrato_do_pncp_sem_valor_nao_casa(value):
    assert status(ato(), [contract(valor_global=value)]) == "sem par"


def test_pessoal_e_outro_ficam_fora_do_escopo():
    assert [status(ato(tipo=tipo), [contract()]) for tipo in ("pessoal", "outro")] == ["fora do escopo"] * 2


@pytest.mark.parametrize("order", [1, -1])
def test_com_dois_candidatos_vence_o_nome_mais_parecido(order):
    close = contract(numero_controle="parecido", fornecedor_nome="ITALIA LTDA", fornecedor_ni="1")
    exact = contract(numero_controle="exato", fornecedor_ni="2")

    row = reconcile([ato()], [close, exact][::order])[0]

    assert (row["status"], row["pncp_numero_controle"]) == ("casado", "exato")


def test_casado_por_cnpj_vence_provavel():
    probable = contract(numero_controle="provavel", fornecedor_nome="ITALIA", fornecedor_ni="1")
    matched = contract(numero_controle="casado", fornecedor_ni="34075739000184")

    row = reconcile([ato(contratada_cnpj="34075739000184")], [probable, matched])[0]

    assert row["pncp_numero_controle"] == "casado"


def test_empate_total_fica_com_o_primeiro_candidato_na_ordem_do_valor():
    higher = contract(numero_controle="maior", valor_global=95500.0)
    lower = contract(numero_controle="menor", valor_global=95300.0)

    row = reconcile([ato(contratada_nome=None)], [higher, lower])[0]

    assert (row["status"], row["pncp_numero_controle"]) == ("provável", "menor")


def test_toda_linha_tem_as_colunas_do_pncp_mesmo_sem_par():
    unmatched, matched = reconcile([ato(valor=1.0), ato()], [contract()])

    assert unmatched.keys() == matched.keys()
    assert unmatched["pncp_fornecedor"] is None


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


def test_cidade_sem_elegiveis_tem_taxa_vazia():
    rows = reconcile([ato(tipo="pessoal"), ato(valor=None)], [contract()])

    (city,) = rates_by_city(rows)

    assert (city["atos"], city["elegiveis"], city["casados"]) == (2, 0, 0)
    assert city["taxa"] is None
    assert (city["ic_inferior"], city["ic_superior"]) == (0.0, 0.0)
    assert (city["fora_do_escopo"], city["sem_valor"]) == (1, 1)


def test_taxas_agrupam_por_codigo_do_municipio_e_ordenam_pelo_nome_sem_acento():
    rows = reconcile(
        [
            ato(territory_id="3305109", territory_name="São João de Meriti"),
            ato(territory_id="3305505", territory_name="Saquarema"),
            ato(territory_id="3305505", territory_name="Saquarema"),
            ato(),
        ],
        [],
    )

    rates = rates_by_city(rows)

    assert [(r["territory_id"], r["municipio"], r["atos"]) for r in rates] == [
        (RIO, "Rio de Janeiro", 1),
        ("3305109", "São João de Meriti", 1),
        ("3305505", "Saquarema", 2),
    ]


def test_municipios_com_o_mesmo_nome_e_codigos_diferentes_ficam_separados():
    rows = reconcile([ato(territory_id="1111111"), ato(territory_id="2222222")], [])

    assert sorted(r["territory_id"] for r in rates_by_city(rows)) == ["1111111", "2222222"]
