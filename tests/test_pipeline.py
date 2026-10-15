import csv
from datetime import date

import pyarrow as pa
import pyarrow.parquet as pq

from dxp.eval.matching import precision, write_review
from dxp.extract.regex_baseline import extract
from dxp.reconcile.pipeline import run, write_outputs

RIO = "3304557"
TEXT = """EXTRATO DO CONTRATO
Contrato nº 198/2025
Data da assinatura: 11/09/2025.
Partes: PCRJ/SME e ITALIA EMPREENDIMENTOS LTDA.
Valor: R$ 95.400,00."""


def setup(tmp_path):
    atos, pncp = tmp_path / "atos.parquet", tmp_path / "pncp.parquet"
    ato = {
        "ato_id": "g#0",
        "gazette_id": "g",
        "territory_id": RIO,
        "territory_name": "Rio de Janeiro",
        "date": date(2025, 10, 1),
        "url": "u",
        "text": TEXT,
    }
    pq.write_table(pa.Table.from_pylist([ato]), atos)
    contract = {
        "numero_controle": "pncp-1",
        "territory_id": RIO,
        "fornecedor_ni": "1",
        "fornecedor_nome": "ITALIA EMPREENDIMENTOS LTDA",
        "valor_global": 95400.0,
        "data_assinatura": date(2025, 9, 11),
        "data_publicacao": date(2025, 9, 12),
    }
    pq.write_table(
        pa.Table.from_pylist([contract, {**contract, "numero_controle": "pncp-2"}]), pncp
    )
    return run(atos, pncp, extract, date(2025, 9, 1), date(2025, 12, 31))


def test_run_concilia_e_conta_contratos_do_pncp(tmp_path):
    rows, rates, pncp = setup(tmp_path)

    assert rows[0]["status"] == "casado"
    assert rates[0]["territory_id"] == RIO
    assert rates[0]["taxa"] == 1.0
    assert pncp == [{"territory_id": RIO, "pncp_contratos": 2}]


def test_saidas_do_painel(tmp_path):
    rows, rates, pncp = setup(tmp_path)

    write_outputs(rows, rates, pncp, tmp_path / "app")

    table = pq.read_table(tmp_path / "app" / "atos.parquet")
    assert table.column("status").to_pylist() == ["casado"]
    assert (tmp_path / "app" / "conciliacao.csv").read_text("utf-8").startswith("territory_id,")


def test_conferencia_dos_casamentos(tmp_path):
    rows, _, _ = setup(tmp_path)
    path = tmp_path / "casamentos.csv"

    assert write_review(rows, path) == 1
    assert precision(path)["pendentes"] == 1

    with path.open(encoding="utf-8") as f:
        sample = list(csv.DictReader(f))
    sample[0]["correto"] = "s"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(sample[0]))
        writer.writeheader()
        writer.writerows(sample)

    assert precision(path)["precisao"] == 1.0
