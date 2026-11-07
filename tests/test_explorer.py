from dxp.explorer import explorer_data, hit
from dxp.schema import FIELDS

ROW = {
    "ato_id": "3300000_2026-08-13_abc#0",
    "territory_name": "Cidade Teste",
    "text": "EXTRATO DE CONTRATO Nº 012/2026\nPROCESSO nº 1.563/2026\nOBJETO: seguro da frota de veículos\n"
    "VALOR: R$ 12.500,00\nDATA DA ASSINATURA: 10/08/2026",
    "tipo": "contrato",
    "numero_contrato": "012/2026",
    "processo": "1.563/2026",
    "contratada_nome": None,
    "contratada_cnpj": None,
    "objeto": "seguro da frota de veículos",
    "valor": 12500.0,
    "data_assinatura": "2026-08-10",
}
GOLD = {field: ROW[field] for field in FIELDS}


def prediction(qlora, base=None):
    return {"ato_id": ROW["ato_id"], "qlora": qlora, "base": base}


def test_campo_vazio_so_acerta_quando_o_ouro_tambem_e_vazio():
    assert hit("contratada_nome", None, None)
    assert not hit("contratada_nome", None, "Empresa X")
    assert not hit("contratada_nome", "Empresa X", None)


def test_objeto_aceita_texto_parecido_como_na_avaliacao():
    assert hit("objeto", "seguro da frota de veículos", "seguro da frota de veiculos municipais")


def test_resposta_fora_do_esquema_fica_vazia_e_erra_os_campos_preenchidos():
    (doc,) = explorer_data([ROW], [prediction(GOLD)])["documentos"]

    assert doc["respostas"]["base"] is None
    assert not doc["acertos"]["base"]["valor"]
    assert all(doc["acertos"]["qlora"].values())


def test_f1_do_extrator_que_acerta_tudo_e_um():
    data = explorer_data([ROW], [prediction(GOLD, base=GOLD | {"valor": 1.0})])

    assert data["f1"]["qlora"]["valor"] == 1.0
    assert data["f1"]["base"]["valor"] == 0.0
    assert set(data["f1"]) == {"qlora", "base", "regex"}
