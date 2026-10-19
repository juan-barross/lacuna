from datetime import date

import pyarrow as pa
import pyarrow.parquet as pq

from dxp.evaluation import precision, write_review
from dxp.files import read_csv, write_csv
from dxp.pipeline import run
from dxp.regex_baseline import extract

RIO = "3304557"
TEXT = """EXTRATO DO CONTRATO
Contrato nº 198/2025
Data da assinatura: 11/09/2025.
Partes: PCRJ/SME e ITALIA EMPREENDIMENTOS LTDA.
Valor: R$ 95.400,00."""
CONTRACT = {
    "numero_controle": "pncp-1",
    "territory_id": RIO,
    "fornecedor_ni": "1",
    "fornecedor_nome": "ITALIA EMPREENDIMENTOS LTDA",
    "valor_global": 95400.0,
    "data_assinatura": date(2025, 9, 11),
    "data_publicacao": date(2025, 9, 12),
}


def reconcile_once(tmp_path):
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
    pq.write_table(pa.Table.from_pylist([CONTRACT, {**CONTRACT, "numero_controle": "pncp-2"}]), pncp)
    return run(atos, pncp, extract, date(2025, 9, 1), date(2025, 12, 31), tmp_path / "app")


def test_concilia_e_conta_contratos_do_pncp(tmp_path):
    rows, rates = reconcile_once(tmp_path)

    assert rows[0]["status"] == "casado"
    assert rates[0]["territory_id"] == RIO
    assert rates[0]["taxa"] == 1.0
    assert read_csv(tmp_path / "app" / "pncp_contratos.csv") == [{"territory_id": RIO, "pncp_contratos": "2"}]


def test_painel_recebe_atos_sem_colunas_internas(tmp_path):
    reconcile_once(tmp_path)

    table = pq.read_table(tmp_path / "app" / "atos.parquet")
    assert table.column("status").to_pylist() == ["casado"]
    assert "gazette_id" not in table.column_names
    assert read_csv(tmp_path / "app" / "conciliacao.csv")[0]["municipio"] == "Rio de Janeiro"


def test_conferencia_dos_casamentos(tmp_path):
    rows, _ = reconcile_once(tmp_path)
    path = tmp_path / "casamentos.csv"

    assert write_review(rows, path) == 1
    assert precision(path)["pendentes"] == 1

    write_csv([{**read_csv(path)[0], "correto": "s"}], path)

    assert precision(path) == {
        "conferidos": 1,
        "pendentes": 0,
        "precisao": 1.0,
        "ic_inferior": 0.207,
        "ic_superior": 1.0,
    }


def test_sem_casados_nao_grava_planilha(tmp_path):
    path = tmp_path / "casamentos.csv"

    assert write_review([{"status": "sem par", "ato_id": "a"}], path) == 0
    assert not path.exists()


def test_sem_contrato_no_periodo_grava_so_o_cabecalho(tmp_path):
    path = tmp_path / "pncp_contratos.csv"

    write_csv([], path, ["territory_id", "pncp_contratos"])

    assert path.read_text(encoding="utf-8") == "territory_id,pncp_contratos\n"
    assert read_csv(path) == []


def test_conferencia_ja_preenchida_nao_e_sobrescrita(tmp_path):
    rows, _ = reconcile_once(tmp_path)
    path = tmp_path / "casamentos.csv"
    write_csv([{"ato_id": "g#0", "correto": "s"}], path)

    assert write_review(rows, path) == 0
    assert read_csv(path) == [{"ato_id": "g#0", "correto": "s"}]
