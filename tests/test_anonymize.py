import pyarrow as pa
import pyarrow.parquet as pq

from dxp.anonymize import anonymize_files, person_names, target_files
from dxp.files import read_csv, read_jsonl, write_csv, write_jsonl
from dxp.privacy import pseudonym

NAME = "João Carlos Pereira"


def labeled(cpf: str) -> dict:
    return {
        "ato_id": "a#1",
        "tipo": "pessoal",
        "contratada_nome": NAME,
        "text": f"Contratado {NAME.upper()}, CPF {cpf}",
    }


def unlabeled() -> dict:
    return {"ato_id": "a#1", "text": f"Contratado {NAME}"}


def test_alvos_sao_so_os_arquivos_que_existem(tmp_path):
    gold, training, app = tmp_path / "gold", tmp_path / "treino", tmp_path / "app"
    for path in (gold / "dev.jsonl", training / "amostra.jsonl", app / "atos.parquet"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    assert target_files(tmp_path, app) == [
        gold / "dev.jsonl",
        training / "amostra.jsonl",
        app / "atos.parquet",
    ]


def test_nomes_vem_so_das_linhas_pessoais_com_nome():
    tables = [
        [labeled("x"), {"ato_id": "b", "tipo": "contrato", "contratada_nome": "ACME"}],
        [{"ato_id": "c", "tipo": "pessoal", "contratada_nome": None}, {"ato_id": "d", "text": "t"}],
    ]

    assert person_names(tables) == {"a#1": NAME}


def test_reescreve_cada_formato_no_lugar_e_conta_por_tipo(tmp_path, cpf):
    jsonl, csv_file, parquet = tmp_path / "dev.jsonl", tmp_path / "casamentos.csv", tmp_path / "atos.parquet"
    write_jsonl([unlabeled()], jsonl)
    write_csv([{"ato_id": "a#1", "contratada_nome": NAME, "trecho": cpf}], csv_file)
    pq.write_table(pa.Table.from_pylist([labeled(cpf)]), parquet)

    totals = anonymize_files([jsonl, csv_file, parquet])

    alias = pseudonym(NAME)
    assert read_jsonl(jsonl) == [{"ato_id": "a#1", "text": f"Contratado {alias}"}]
    assert read_csv(csv_file) == [{"ato_id": "a#1", "contratada_nome": alias, "trecho": "[CPF]"}]
    (row,) = pq.read_table(parquet).to_pylist()
    assert (row["contratada_nome"], row["text"]) == (alias, f"Contratado {alias}, CPF [CPF]")
    assert totals == {"CPF": 2, "PESSOA": 4}


def test_segunda_passada_nao_muda_nada(tmp_path, cpf):
    path = tmp_path / "dev.jsonl"
    write_jsonl([labeled(cpf)], path)
    anonymize_files([path])
    once = path.read_bytes()

    assert anonymize_files([path]) == {}
    assert path.read_bytes() == once
