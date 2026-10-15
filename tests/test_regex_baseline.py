from datetime import date

import pytest

from dxp.extract.regex_baseline import brl, extract, parse_date

SAQUAREMA = """EXTRATO DO CONTRATO
N° 102/2025
Processo Administrativo nº 14.618/2025
Objeto: Parceria entre universidades e o Município de Saquarema.
Contratante: Município de Saquarema.
Contratada: Sociedade de Ensino Superior Estácio de Sá LTDA, CNPJ n° 34.075.739/0001-84.
Prazo de Vigência: 12 meses.
Valor do Contrato: R$ 1.474.895,28.
Saquarema, 11 de agosto de 2025."""

MACAE = """EXTRATO DO CONTRATO
I – Espécie: CONTRATO DE FORNECIMENTO DE MATERIAL Nº 195/2025-SEMED
– PROCESSO ADMINISTRATIVO Nº 600.655/2024.
II – Objeto: FORNECIMENTO DE MOBILIÁRIOS PARA AS UNIDADES ESCOLARES.
VI – Valor do Contrato: R$ 13.151,10.
VII – Valor empenhado no exercício: R$ 13.151,10.
IX – Data da assinatura: 27/10/2025.
X – Partes: MUNICÍPIO DE MACAÉ e SANTANA WERNECK COMERCIAL LTDA. Macaé, 27 de outubro 2025."""

SAO_JOSE = """EXTRATO DO CONTRATO Nº 305/2026
INSTRUMENTO: Processo administrativo nº 7947/2026; PARTES: MUNICÍPIO DE SÃO JOSÉ DO VALE
DO RIO PRETO e a empresa JMP DISTRIBUIDORA EM GERAL LTDA; OBJETO: Aquisição de gêneros
alimentícios; VALOR: R$ 3.306,88; DATA DE ASSINATURA: 01 de julho de 2026."""

PESSOAL = """EXTRATO DE CONTRATO ADMINISTRATIVO Nº .1253/2025
Processo Seletivo Simplificado nº 001/2025.
Contratante: Município de Saquarema, CNPJ nº 32.147.670/0001-21.
Contratado: Yasmin Sousa e Silva Vitorino, CPF nº XXX.XXX.117-21.
Remuneração Mensal: R$ 1.591,32."""


def test_saquarema_com_rotulos_em_linhas():
    ato = extract(SAQUAREMA)

    assert ato.tipo == "contrato"
    assert ato.numero_contrato == "102/2025"
    assert ato.processo == "14.618/2025"
    assert ato.contratada_nome == "Sociedade de Ensino Superior Estácio de Sá LTDA"
    assert ato.contratada_cnpj == "34075739000184"
    assert ato.valor == 1474895.28
    assert ato.data_assinatura == date(2025, 8, 11)


def test_macae_com_numeral_romano_antes_do_rotulo():
    ato = extract(MACAE)

    assert ato.objeto == "FORNECIMENTO DE MOBILIÁRIOS PARA AS UNIDADES ESCOLARES"
    assert ato.contratada_nome == "SANTANA WERNECK COMERCIAL LTDA"
    assert ato.processo == "600.655/2024"
    assert ato.valor == 13151.10
    assert ato.data_assinatura == date(2025, 10, 27)


def test_partes_na_mesma_linha_separadas_por_ponto_e_virgula():
    ato = extract(SAO_JOSE)

    assert ato.contratada_nome == "JMP DISTRIBUIDORA EM GERAL LTDA"
    assert ato.objeto == "Aquisição de gêneros alimentícios"
    assert ato.contratada_cnpj is None
    assert ato.data_assinatura == date(2026, 7, 1)


def test_contratacao_temporaria_de_pessoa_fisica():
    ato = extract(PESSOAL)

    assert ato.tipo == "pessoal"
    assert ato.contratada_cnpj is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("em 05/03/2026", date(2026, 3, 5)),
        ("aos 15 de setembro de 2025", date(2025, 9, 15)),
        ("1º de abril de 2026", date(2026, 4, 1)),
        ("31/02/2026 e depois 01/03/2026", date(2026, 3, 1)),
        ("sem data", None),
    ],
)
def test_parse_date(text, expected):
    assert parse_date(text) == expected


def test_brl():
    assert brl("1.474.895,28") == 1474895.28
