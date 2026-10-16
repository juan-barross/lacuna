from datetime import date

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from dxp import cli
from dxp.files import read_csv, read_jsonl, write_csv, write_jsonl

TEXT = """EXTRATO DO CONTRATO Nº 198/2025
Data da assinatura: 11/09/2025.
Partes: PCRJ/SME e ITALIA EMPREENDIMENTOS LTDA.
Objeto: Aquisição de condicionadores de ar.
Valor: R$ 95.400,00."""


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "APP_DATA", tmp_path / "app")
    monkeypatch.setattr(cli, "REPORTS", tmp_path / "reports")
    gazette = {
        "gazette_id": "g",
        "territory_id": "3304557",
        "territory_name": "Rio de Janeiro",
        "date": date(2025, 10, 1),
        "url": "u",
        "text": TEXT,
        "text_status": "ok",
    }
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    pq.write_table(pa.Table.from_pylist([gazette]), processed / "qd_gazettes.parquet")
    contract = {
        "numero_controle": "pncp-1",
        "territory_id": "3304557",
        "fornecedor_ni": "1",
        "fornecedor_nome": "ITALIA EMPREENDIMENTOS LTDA",
        "valor_global": 95400.0,
        "data_assinatura": date(2025, 9, 11),
        "data_publicacao": date(2025, 9, 12),
    }
    pq.write_table(pa.Table.from_pylist([contract]), processed / "pncp_contratos.parquet")
    return tmp_path / "data"


def dxp(data_dir, *args):
    cli.main(["--data-dir", str(data_dir), *args])


def test_recorte_versionado_tem_19_municipios():
    ids = cli.load_recorte()
    assert len(ids) == 19
    assert "3304557" in ids
    assert "3302700" not in ids


@pytest.mark.parametrize(("value", "shown"), [(0.5, "0.50"), (None, "-"), (3, "3"), ("Rio", "Rio")])
def test_show(value, shown):
    assert cli.show(value) == shown


def test_print_table_alinha_colunas(capsys):
    cli.print_table(
        [{"municipio": "Rio", "taxa": 0.5}, {"municipio": "Niterói", "taxa": None}], ["municipio", "taxa"]
    )

    header, *lines = capsys.readouterr().out.splitlines()
    assert header.split() == ["municipio", "taxa"]
    assert lines == ["Rio        0.50", "Niterói    -   "]


def test_pipeline_completo_pela_linha_de_comando(data_dir, tmp_path, capsys):
    dxp(data_dir, "atos")
    dxp(data_dir, "amostra")
    dxp(data_dir, "cobertura")
    dxp(data_dir, "conciliar")

    assert pq.read_table(data_dir / "processed" / "atos.parquet").num_rows == 1
    assert read_jsonl(data_dir / "gold" / "fila.jsonl")[0]["split"] == "dev"
    assert read_csv(tmp_path / "app" / "cobertura.csv")[0]["pct_texto"] == "100.0"
    assert read_csv(tmp_path / "app" / "conciliacao.csv")[0]["taxa"] == "1.0"
    assert read_csv(data_dir / "gold" / "casamentos.csv")[0]["correto"] == ""
    assert "Rio de Janeiro" in capsys.readouterr().out


def test_avaliar_grava_relatorio(data_dir, tmp_path):
    gold = {
        "text": TEXT,
        "tipo": "contrato",
        "contratada_nome": "ITALIA EMPREENDIMENTOS LTDA",
        "valor": 95400.0,
    }
    write_jsonl([gold], data_dir / "gold" / "dev.jsonl")

    dxp(data_dir, "avaliar", "--extrator", "regex")

    (report,) = (tmp_path / "reports").glob("*_regex_dev.json")
    assert '"f1": 1.0' in report.read_text(encoding="utf-8")


def test_precisao_le_a_planilha_conferida(data_dir, capsys):
    write_csv(
        [{"ato_id": "a", "correto": "s"}, {"ato_id": "b", "correto": "n"}],
        data_dir / "gold" / "casamentos.csv",
    )

    dxp(data_dir, "precisao")

    assert "'precisao': 0.5" in capsys.readouterr().out


def test_comando_desconhecido_sai_com_erro():
    with pytest.raises(SystemExit):
        cli.main(["nao-existe"])
