import json
import re
import runpy
from datetime import date

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from dxp import cli
from dxp.files import read_csv, read_jsonl, write_csv, write_jsonl
from dxp.period import Period
from dxp.schema import Ato

RIO = "3304557"
TEXT = """EXTRATO DO CONTRATO Nº 198/2025
Data da assinatura: 11/09/2025.
Partes: PCRJ/SME e ITALIA EMPREENDIMENTOS LTDA.
Objeto: Aquisição de condicionadores de ar.
Valor: R$ 95.400,00."""
VERSIONED_SCOPE = cli.SCOPE_CSV
GOLD_ROW = {
    "text": TEXT,
    "tipo": "contrato",
    "contratada_nome": "ITALIA EMPREENDIMENTOS LTDA",
    "valor": 95400.0,
}


class FakeLLM:
    model = "fake/modelo"

    def __init__(self, failures: int = 0, cached: set[str] | None = None) -> None:
        self.seen: list[str] = []
        self.failures = failures
        self.cached = cached or set()

    def __call__(self, text: str) -> Ato:
        self.seen.append(text)
        return Ato(tipo="contrato", valor=95400.0)

    def usage(self) -> dict:
        return {"modelo": self.model, "chamadas": len(self.seen), "erros": self.failures}

    def cache_path(self, text: str):
        return FakeCacheEntry(text in self.cached)


class FakeCacheEntry:
    def __init__(self, exists: bool) -> None:
        self._exists = exists

    def exists(self) -> bool:
        return self._exists


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "load_env", lambda _: None)
    monkeypatch.setattr(cli, "APP_DATA", tmp_path / "app")
    monkeypatch.setattr(cli, "REPORTS", tmp_path / "reports")
    monkeypatch.setattr(cli, "SCOPE_CSV", tmp_path / "recorte.csv")


@pytest.fixture
def data_dir(tmp_path):
    gazette = {
        "gazette_id": "g",
        "territory_id": RIO,
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
        "territory_id": RIO,
        "fornecedor_ni": "1",
        "fornecedor_nome": "ITALIA EMPREENDIMENTOS LTDA",
        "valor_global": 95400.0,
        "data_assinatura": date(2025, 9, 11),
        "data_publicacao": date(2025, 9, 12),
    }
    pq.write_table(pa.Table.from_pylist([contract]), processed / "pncp_contratos.parquet")
    return tmp_path / "data"


@pytest.fixture
def atos_file(data_dir):
    processed = data_dir / "processed"
    cli.build_atos(processed / "qd_gazettes.parquet", processed / "atos.parquet")
    return processed / "atos.parquet"


@pytest.fixture
def queue_file(data_dir):
    rows = [
        {"ato_id": "a", "territory_name": "Rio", "date": "2025-10-01", "text": "texto dev", "split": "dev"},
        {"ato_id": "b", "territory_name": "Rio", "date": "2025-10-01", "text": "texto test", "split": "test"},
    ]
    write_jsonl(rows, data_dir / "gold" / "fila.jsonl")
    return rows


def dxp(data_dir, *args):
    cli.main(["--data-dir", str(data_dir), *args])


def stdout_json(capsys) -> dict:
    out = capsys.readouterr().out
    return json.loads(out[out.index("{") :])


def test_recorte_versionado_traz_municipios_validos(monkeypatch):
    monkeypatch.setattr(cli, "SCOPE_CSV", VERSIONED_SCOPE)
    ids = cli.load_scope()

    assert len(ids) == len(set(ids)) > 0
    assert all(re.fullmatch(r"\d{7}", territory_id) for territory_id in ids)
    assert RIO in ids


def test_load_scope_le_so_os_municipios_incluidos(tmp_path):
    write_csv(
        [
            {"territory_id": "1111111", "included": True},
            {"territory_id": "2222222", "included": False},
            {"territory_id": "3333333", "included": True},
        ],
        cli.SCOPE_CSV,
    )

    assert cli.load_scope() == ["1111111", "3333333"]


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


def test_print_table_sem_linhas_diz_que_nao_ha_nada(capsys):
    cli.print_table([], ["municipio", "taxa"])

    assert capsys.readouterr().out == "nenhuma linha\n"


def test_atos_separa_os_extratos_dos_diarios(data_dir, capsys):
    dxp(data_dir, "atos")

    assert capsys.readouterr().out.strip() == "1"
    assert pq.read_table(data_dir / "processed" / "atos.parquet").num_rows == 1


def test_amostra_grava_a_fila_do_conjunto_ouro(data_dir, atos_file, capsys):
    dxp(data_dir, "amostra")

    assert capsys.readouterr().out.strip() == "1 trechos"
    (row,) = read_jsonl(data_dir / "gold" / "fila.jsonl")
    assert (row["split"], row["territory_name"]) == ("dev", "Rio de Janeiro")


def test_cobertura_grava_csv_e_imprime_a_tabela(data_dir, tmp_path, capsys):
    dxp(data_dir, "cobertura")

    (row,) = read_csv(tmp_path / "app" / "cobertura.csv")
    assert (row["municipio"], row["pct_texto"]) == ("Rio de Janeiro", "100.0")
    assert "Rio de Janeiro" in capsys.readouterr().out


def test_conciliar_grava_dados_do_painel_e_a_planilha_de_conferencia(data_dir, atos_file, tmp_path, capsys):
    dxp(data_dir, "conciliar")

    assert read_csv(tmp_path / "app" / "conciliacao.csv")[0]["taxa"] == "1.0"
    assert read_csv(data_dir / "gold" / "casamentos.csv")[0]["correto"] == ""
    assert "Rio de Janeiro" in capsys.readouterr().out


def test_conciliar_com_extracoes_falhas_sai_com_erro_e_nao_grava_nada(
    data_dir, atos_file, tmp_path, monkeypatch, capsys
):
    monkeypatch.setitem(cli.EXTRACTORS, "llm", lambda: FakeLLM(failures=3))

    with pytest.raises(SystemExit, match="3 extrações falharam"):
        dxp(data_dir, "conciliar", "--extrator", "llm")

    assert stdout_json(capsys)["erros"] == 3
    assert not (tmp_path / "app").exists()
    assert not (data_dir / "gold" / "casamentos.csv").exists()


def test_conciliar_com_llm_imprime_o_uso(data_dir, atos_file, monkeypatch, capsys):
    llm = FakeLLM()
    monkeypatch.setitem(cli.EXTRACTORS, "llm", lambda: llm)

    dxp(data_dir, "conciliar", "--extrator", "llm")

    assert stdout_json(capsys) == {"modelo": "fake/modelo", "chamadas": 1, "erros": 0}


def test_avaliar_grava_relatorio_com_o_f1_por_campo(data_dir, tmp_path):
    write_jsonl([GOLD_ROW], data_dir / "gold" / "dev.jsonl")

    dxp(data_dir, "avaliar", "--extrator", "regex")

    (path,) = (tmp_path / "reports").glob("*_regex_dev.json")
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["campos"]["valor"]["f1"] == 1.0
    assert report["campos"]["tipo"]["support"] == 1
    assert report["uso"] == {}


def test_avaliar_usa_o_split_pedido(data_dir, tmp_path):
    write_jsonl([GOLD_ROW], data_dir / "gold" / "test.jsonl")

    dxp(data_dir, "avaliar", "--split", "test")

    assert len(list((tmp_path / "reports").glob("*_regex_test.json"))) == 1


def test_avaliar_com_llm_guarda_o_uso_no_relatorio(data_dir, tmp_path, monkeypatch):
    write_jsonl([GOLD_ROW], data_dir / "gold" / "dev.jsonl")
    monkeypatch.setitem(cli.EXTRACTORS, "llm-gratis", lambda: FakeLLM())

    dxp(data_dir, "avaliar", "--extrator", "llm-gratis")

    (path,) = (tmp_path / "reports").glob("*_llm-gratis_dev.json")
    assert json.loads(path.read_text(encoding="utf-8"))["uso"]["chamadas"] == 1


def test_avaliar_sem_conjunto_ouro_falha_com_arquivo_ausente(data_dir):
    with pytest.raises(FileNotFoundError):
        dxp(data_dir, "avaliar")


def test_llm_fila_extrai_so_os_trechos_do_split(data_dir, queue_file, monkeypatch, capsys):
    llm = FakeLLM()
    monkeypatch.setitem(cli.EXTRACTORS, "llm", lambda: llm)

    dxp(data_dir, "llm-fila", "--split", "test")

    assert llm.seen == ["texto test"]
    assert stdout_json(capsys)["chamadas"] == 1


def test_llm_fila_nao_aceita_extrator_regex(data_dir):
    with pytest.raises(SystemExit):
        dxp(data_dir, "llm-fila", "--extrator", "regex")


def test_concordancia_compara_so_os_trechos_com_resposta_gravada(data_dir, queue_file, tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "LLMExtractor", lambda: FakeLLM(cached={"texto dev"}))

    dxp(data_dir, "concordancia", "--split", "dev")

    (path,) = (tmp_path / "reports").glob("*_concordancia_dev.json")
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["trechos"] == 1
    assert set(report["campos"]) == set(Ato.model_fields)


def test_precisao_imprime_json_com_o_resultado_da_conferencia(data_dir, capsys):
    write_csv(
        [{"ato_id": "a", "correto": "s"}, {"ato_id": "b", "correto": "n"}, {"ato_id": "c", "correto": ""}],
        data_dir / "gold" / "casamentos.csv",
    )

    dxp(data_dir, "precisao")

    result = stdout_json(capsys)
    assert (result["conferidos"], result["pendentes"], result["precisao"]) == (2, 1, 0.5)


class FakeQDClient:
    def __init__(self) -> None:
        self.searched: list[tuple[list[str], Period, int | None]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def cities(self) -> list[dict]:
        return [
            {"territory_id": "3304557", "territory_name": "Rio de Janeiro", "state_code": "RJ"},
            {"territory_id": "3302700", "territory_name": "Macaé", "state_code": "RJ"},
            {"territory_id": "3550308", "territory_name": "São Paulo", "state_code": "SP"},
        ]

    def search(self, territory_ids, period, *, size=None):
        self.searched.append((territory_ids, period, size))
        return (500 if territory_ids == ["3304557"] else 10), []


def test_recorte_marca_os_municipios_com_diarios_suficientes(tmp_path, monkeypatch, capsys):
    client = FakeQDClient()
    monkeypatch.setattr(cli.qd, "QDClient", lambda: client)

    cli.main(["recorte"])

    rows = read_csv(tmp_path / "recorte.csv")
    assert [(r["territory_id"], r["gazettes_in_period"], r["included"]) for r in rows] == [
        ("3302700", "10", "False"),
        ("3304557", "500", "True"),
    ]
    assert {size for _, _, size in client.searched} == {0}
    assert {period for _, period, _ in client.searched} == {cli.QD_PERIOD}
    assert "Rio de Janeiro" in capsys.readouterr().out


def test_qd_download_usa_o_recorte_e_o_periodo_dos_diarios(data_dir, tmp_path, monkeypatch, capsys):
    write_csv([{"territory_id": RIO, "included": True}], tmp_path / "recorte.csv")
    calls = []
    monkeypatch.setattr(cli.qd, "QDClient", FakeQDClient)
    monkeypatch.setattr(cli.qd, "download", lambda *args: calls.append(args) or {"ok": 1})

    dxp(data_dir, "qd-download")

    ((_, territory_ids, period, target),) = calls
    assert (territory_ids, period, target) == ([RIO], cli.QD_PERIOD, data_dir)
    assert capsys.readouterr().out.strip() == "{'ok': 1}"


def test_pncp_download_usa_o_recorte_e_o_periodo_do_pncp(data_dir, tmp_path, monkeypatch, capsys):
    write_csv([{"territory_id": RIO, "included": True}], tmp_path / "recorte.csv")
    calls = []
    monkeypatch.setattr(cli.pncp, "PNCPClient", FakeQDClient)
    monkeypatch.setattr(cli.pncp, "download", lambda *args: calls.append(args) or 7)

    dxp(data_dir, "pncp-download")

    ((_, territory_ids, period, target),) = calls
    assert (territory_ids, period, target) == ([RIO], cli.PNCP_PERIOD, data_dir)
    assert capsys.readouterr().out.strip() == "7 contratos"


def test_comando_desconhecido_sai_com_erro():
    with pytest.raises(SystemExit):
        cli.main(["nao-existe"])


def test_extrator_desconhecido_sai_com_erro(data_dir):
    with pytest.raises(SystemExit):
        dxp(data_dir, "avaliar", "--extrator", "gpt")


def test_todo_comando_tem_ajuda():
    parser = cli.build_parser()

    for name in cli.COMMANDS:
        with pytest.raises(SystemExit) as exit_info:
            parser.parse_args([name, "--help"])
        assert exit_info.value.code == 0


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
def test_modulo_executavel_roda_a_linha_de_comando(monkeypatch):
    monkeypatch.setattr("sys.argv", ["dxp", "--help"])

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("dxp.cli", run_name="__main__")

    assert exit_info.value.code == 0


def test_main_carrega_o_env_do_projeto(monkeypatch, data_dir):
    loaded = []
    monkeypatch.setattr(cli, "load_env", loaded.append)

    dxp(data_dir, "cobertura")

    assert loaded == [cli.ROOT / ".env"]
