from datetime import date

import pytest
from pydantic import ValidationError

from dxp.schema import Ato


def test_cnpj_vira_so_letras_e_digitos():
    assert Ato(tipo="contrato", contratada_cnpj="12.abc.345/01de-35").contratada_cnpj == "12ABC34501DE35"


def test_ato_valido_nao_tem_problemas():
    assert Ato(tipo="contrato", contratada_cnpj="28.521.748/0001-59", valor=10.0).problems() == []


@pytest.mark.parametrize(
    ("ato", "problem"),
    [
        (Ato(tipo="contrato", contratada_cnpj="11111111111112"), "CNPJ inválido: 11111111111112"),
        (Ato(tipo="contrato", valor=0.0), "valor não positivo: 0.0"),
    ],
)
def test_problemas_sao_registrados(ato, problem):
    assert ato.problems() == [problem]


def test_data_em_texto_iso_vira_date():
    assert Ato(tipo="contrato", data_assinatura="2025-09-11").data_assinatura == date(2025, 9, 11)


def test_tipo_fora_da_lista_e_recusado():
    with pytest.raises(ValidationError):
        Ato(tipo="aditivo")
