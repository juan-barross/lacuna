from datetime import date

import pyarrow as pa
import pyarrow.parquet as pq

from dxp.extract.segment import build_atos, segments

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


def test_separa_um_trecho_por_extrato_de_contrato():
    found = segments(GAZETTE)

    assert len(found) == 2
    assert found[0].startswith("EXTRATO DO CONTRATO Nº 198/2025")
    assert "R$ 95.400,00" in found[0]
    assert "TERMO ADITIVO" not in found[0]


def test_ignora_sumario_frase_comum_e_trecho_sem_valor():
    assert all("....." not in s and "desacordo" not in s for s in segments(GAZETTE))
    assert not any("Sem valor informado" in s for s in segments(GAZETTE))


def test_junta_palavra_quebrada_e_linhas_vazias():
    found = segments(GAZETTE)

    assert "Sociedade de Ensino Superior Estácio" in found[1]
    assert "\n\n" not in found[0]


def test_build_atos_le_so_diarios_com_texto(tmp_path):
    source = tmp_path / "g.parquet"
    base = {
        "territory_id": "3304557",
        "territory_name": "Rio de Janeiro",
        "date": date(2025, 10, 1),
    }
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
