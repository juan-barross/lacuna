from datetime import date

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from dxp.evaluation import review_precision, write_review
from dxp.files import read_csv, write_csv
from dxp.period import Period
from dxp.pipeline import (
    ExtractionFailed,
    count_signed_contracts,
    publish_reconciliation,
    reconcile_atos,
)
from dxp.regex_baseline import RegexExtractor
from dxp.schema import Ato

RIO = "3304557"
PERIOD = Period(date(2025, 9, 1), date(2025, 12, 31))
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
ATO = {
    "ato_id": "g#0",
    "gazette_id": "g",
    "territory_id": RIO,
    "territory_name": "Rio de Janeiro",
    "date": date(2025, 10, 1),
    "url": "u",
    "text": TEXT,
}


class FailingExtractor:
    def __call__(self, text: str) -> Ato:
        return Ato(tipo="outro")

    def usage(self) -> dict:
        return {"erros": 2}


def write_inputs(tmp_path):
    atos, pncp = tmp_path / "atos.parquet", tmp_path / "pncp.parquet"
    pq.write_table(pa.Table.from_pylist([ATO]), atos)
    pq.write_table(pa.Table.from_pylist([CONTRACT, {**CONTRACT, "numero_controle": "pncp-2"}]), pncp)
    return atos, pncp


def publish(tmp_path, extractor=None):
    atos, pncp = write_inputs(tmp_path)
    return publish_reconciliation(atos, pncp, extractor or RegexExtractor(), PERIOD, tmp_path / "app")


def test_reconcile_atos_extrai_e_concilia():
    (row,) = reconcile_atos([ATO], [CONTRACT], RegexExtractor())

    assert row["status"] == "casado"
    assert row["valor"] == 95400.0
    assert row["pncp_numero_controle"] == "pncp-1"


def test_conta_contratos_assinados_no_periodo_por_cidade():
    contracts = [
        CONTRACT,
        {**CONTRACT, "numero_controle": "2", "data_assinatura": date(2025, 9, 1)},
        {**CONTRACT, "numero_controle": "3", "data_assinatura": date(2025, 12, 31)},
        {**CONTRACT, "numero_controle": "4", "data_assinatura": date(2025, 8, 31)},
        {**CONTRACT, "numero_controle": "5", "data_assinatura": date(2026, 1, 1)},
        {**CONTRACT, "numero_controle": "6", "data_assinatura": None},
        {**CONTRACT, "numero_controle": "7", "territory_id": "3303302"},
    ]

    assert count_signed_contracts(contracts, PERIOD) == {RIO: 3, "3303302": 1}


def test_concilia_e_conta_contratos_do_pncp(tmp_path):
    rows, rates = publish(tmp_path)

    assert rows[0]["status"] == "casado"
    assert rates[0]["territory_id"] == RIO
    assert rates[0]["taxa"] == 1.0
    assert read_csv(tmp_path / "app" / "pncp_contratos.csv") == [{"territory_id": RIO, "pncp_contratos": "2"}]


def test_painel_recebe_atos_sem_colunas_internas(tmp_path):
    publish(tmp_path)

    table = pq.read_table(tmp_path / "app" / "atos.parquet")
    assert table.column("status").to_pylist() == ["casado"]
    assert "gazette_id" not in table.column_names
    assert read_csv(tmp_path / "app" / "conciliacao.csv")[0]["municipio"] == "Rio de Janeiro"


def test_extracao_com_falha_nao_grava_dados_do_painel(tmp_path):
    with pytest.raises(ExtractionFailed, match="2 extrações falharam"):
        publish(tmp_path, FailingExtractor())

    assert not (tmp_path / "app").exists()


def test_conferencia_dos_casamentos(tmp_path):
    rows, _ = publish(tmp_path)
    path = tmp_path / "casamentos.csv"

    assert write_review(rows, path) == 1
    assert review_precision(path)["pendentes"] == 1

    write_csv([{**read_csv(path)[0], "correto": "s"}], path)

    assert review_precision(path) == {
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


def test_conferencia_ja_preenchida_nao_e_sobrescrita(tmp_path):
    rows, _ = publish(tmp_path)
    path = tmp_path / "casamentos.csv"
    write_csv([{"ato_id": "g#0", "correto": "s"}], path)

    assert write_review(rows, path) == 0
    assert read_csv(path) == [{"ato_id": "g#0", "correto": "s"}]
