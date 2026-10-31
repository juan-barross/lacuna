from datetime import date

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from dxp.segment import MAX_CHARS, build_atos, segments

GAZETTE = """SUMÁRIO
EXTRATO DE CONTRATO ................................................. 18
Não será publicado extrato de contrato que esteja em desacordo com a resolução.
EXTRATO DO CONTRATO Nº 198/2025
Partes: PCRJ/SME e ITALIA EMPREENDIMENTOS LTDA.

Objeto: Aquisição de condicionadores de ar.
Valor: R$ 95.400,00.
EXTRATO DE TERMO ADITIVO
Termo Aditivo nº 59/2025. Valor: R$ 10,00.
EXTRATO DE CONTRATO
Contratada: Sociedade de Ensino Su-
perior Estácio de Sá LTDA. Valor do Contrato: R$ 1.474.895,28.
EXTRATO DE CONTRATO Nº 7/2025
Sem valor informado.
"""


def first_lines(found: list[str]) -> list[str]:
    return [segment.splitlines()[0] for segment in found]


def test_separa_um_trecho_por_extrato_de_contrato_com_valor():
    assert first_lines(segments(GAZETTE)) == ["EXTRATO DO CONTRATO Nº 198/2025", "EXTRATO DE CONTRATO"]


def test_trecho_vai_do_cabecalho_ate_o_proximo_extrato():
    first = segments(GAZETTE)[0]

    assert first.endswith("Valor: R$ 95.400,00.")
    assert "Objeto: Aquisição de condicionadores de ar." in first


def test_termo_aditivo_nao_entra_no_trecho_do_contrato_anterior():
    assert [s for s in segments(GAZETTE) if "TERMO ADITIVO" in s] == []


def test_linha_do_sumario_com_pontilhado_nao_abre_trecho():
    assert [s for s in segments(GAZETTE) if "....." in s] == []


def test_frase_comum_sobre_extrato_de_contrato_nao_abre_trecho():
    text = "Não será publicado extrato de contrato em desacordo. Valor: R$ 1,00."

    assert segments(text) == []


def test_trecho_sem_valor_em_reais_e_descartado():
    assert segments("EXTRATO DE CONTRATO Nº 7/2025\nSem valor informado.\n") == []


def test_remove_linhas_vazias_dentro_do_trecho():
    first = segments(GAZETTE)[0]

    assert first.splitlines() == [
        "EXTRATO DO CONTRATO Nº 198/2025",
        "Partes: PCRJ/SME e ITALIA EMPREENDIMENTOS LTDA.",
        "Objeto: Aquisição de condicionadores de ar.",
        "Valor: R$ 95.400,00.",
    ]


def test_junta_palavra_quebrada_por_hifen_no_fim_da_linha():
    assert "Sociedade de Ensino Superior Estácio" in segments(GAZETTE)[1]


@pytest.mark.parametrize(
    "broken",
    [
        "representa-\ndo",
        "representa- \ndo",
        "representa-\n\n  do",
        "representa- \n\n  do",
    ],
)
def test_junta_hifen_mesmo_com_espaco_ou_linha_em_branco_no_meio(broken):
    text = f"EXTRATO DO CONTRATO\n{broken} pela SECRETARIA. Valor: R$ 1,00."

    assert "representado pela" in segments(text)[0]


def test_mantem_hifen_antes_de_maiuscula():
    text = "EXTRATO DO CONTRATO\nPCRJ-\nSME. Valor: R$ 1,00."

    assert "PCRJ-\nSME" in segments(text)[0]


def test_tira_carimbo_de_assinatura_do_meio_do_ato():
    text = (
        "EXTRATO DO CONTRATO\nPartes: PCRJ e X LTDA.\n"
        "Assinado Digitalmente por EMPRESA MUNICIPAL DE ARTES GRÁFICAS S/A - 68.697.333/0001-55\n"
        "Valor: R$ 1,00."
    )

    assert segments(text) == ["EXTRATO DO CONTRATO\nPartes: PCRJ e X LTDA.\nValor: R$ 1,00."]


def test_tira_cabecalho_de_pagina_do_meio_do_ato():
    text = (
        "EXTRATO DO CONTRATO\nPartes: PCRJ e X LTDA.\n"
        "Diário Oficial do Município do Rio de Janeiro\nValor: R$ 1,00."
    )

    assert segments(text) == ["EXTRATO DO CONTRATO\nPartes: PCRJ e X LTDA.\nValor: R$ 1,00."]


def test_trecho_longo_e_cortado_no_limite():
    text = "EXTRATO DO CONTRATO\nValor: R$ 1,00. " + "x " * 5000

    assert len(segments(text)[0]) <= MAX_CHARS


def test_build_atos_le_so_diarios_com_texto(tmp_path):
    source = tmp_path / "g.parquet"
    base = {"territory_id": "3304557", "territory_name": "Rio de Janeiro", "date": date(2025, 10, 1)}
    pq.write_table(
        pa.Table.from_pylist(
            [
                {**base, "gazette_id": "a", "url": "u", "text": GAZETTE, "text_status": "ok"},
                {**base, "gazette_id": "b", "url": "u", "text": GAZETTE, "text_status": "curto"},
            ]
        ),
        source,
    )
    out = tmp_path / "atos.parquet"

    assert build_atos(source, out) == 2
    assert pq.read_table(out).column("ato_id").to_pylist() == ["a#0", "a#1"]
