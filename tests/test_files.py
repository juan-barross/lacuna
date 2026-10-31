import os
from datetime import date

import pyarrow.parquet as pq
import pytest

from dxp.files import (
    cached_json,
    load_env,
    path_inside,
    read_csv,
    read_jsonl,
    read_jsonl_or_empty,
    short_hash,
    write_atomic,
    write_csv,
    write_jsonl,
    write_parquet,
)

ROWS = [{"id": "a", "valor": 1.5}, {"id": "b", "valor": None}]


def test_load_env_nao_sobrescreve_variavel_existente(tmp_path, monkeypatch):
    monkeypatch.setenv("JA_EXISTE", "ambiente")
    monkeypatch.setenv("NOVA", "")
    monkeypatch.delenv("NOVA")
    env = tmp_path / ".env"
    env.write_text('# linha ignorada\nJA_EXISTE=arquivo\nNOVA="valor"\n', encoding="utf-8")

    load_env(env)

    assert (os.environ["JA_EXISTE"], os.environ["NOVA"]) == ("ambiente", "valor")


def test_load_env_sem_arquivo_nao_faz_nada(tmp_path):
    load_env(tmp_path / ".env")


def test_write_atomic_cria_pastas_e_nao_deixa_parcial(tmp_path):
    path = tmp_path / "a" / "b" / "texto.txt"

    write_atomic(path, "conteúdo")

    assert path.read_text(encoding="utf-8") == "conteúdo"
    assert not path.with_suffix(".part").exists()


def test_cached_json_busca_uma_vez_e_depois_le_do_arquivo(tmp_path):
    calls = []

    def fetch():
        calls.append(1)
        return {"cidade": "Niterói"}

    path = tmp_path / "cache" / "x.json"

    assert cached_json(path, fetch) == {"cidade": "Niterói"}
    assert cached_json(path, fetch) == {"cidade": "Niterói"}
    assert len(calls) == 1


def test_cached_json_nao_grava_quando_a_busca_falha(tmp_path):
    path = tmp_path / "x.json"

    def fetch():
        raise RuntimeError("fora do ar")

    with pytest.raises(RuntimeError):
        cached_json(path, fetch)
    assert not path.exists()


def test_csv_ida_e_volta(tmp_path):
    path = tmp_path / "out" / "linhas.csv"

    write_csv([{"id": "a", "nome": "São João"}], path)

    assert read_csv(path) == [{"id": "a", "nome": "São João"}]


def test_csv_sem_linhas_grava_so_o_cabecalho(tmp_path):
    path = tmp_path / "pncp_contratos.csv"

    write_csv([], path, ["territory_id", "pncp_contratos"])

    assert path.read_text(encoding="utf-8") == "territory_id,pncp_contratos\n"
    assert read_csv(path) == []


def test_csv_sem_linhas_e_sem_colunas_diz_o_que_faltou(tmp_path):
    with pytest.raises(ValueError, match="sem linhas e sem colunas"):
        write_csv([], tmp_path / "vazio.csv")


def test_jsonl_ida_e_volta(tmp_path):
    path = tmp_path / "dev.jsonl"

    write_jsonl(ROWS, path)

    assert read_jsonl(path) == ROWS


def test_jsonl_grava_data_como_texto(tmp_path):
    path = tmp_path / "datas.jsonl"

    write_jsonl([{"date": date(2025, 10, 1)}], path)

    assert read_jsonl(path) == [{"date": "2025-10-01"}]


def test_read_jsonl_de_arquivo_ausente_levanta_erro(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_jsonl(tmp_path / "nao_existe.jsonl")


def test_read_jsonl_or_empty_de_arquivo_ausente_devolve_lista_vazia(tmp_path):
    assert read_jsonl_or_empty(tmp_path / "nao_existe.jsonl") == []


def test_read_jsonl_or_empty_le_o_arquivo_quando_existe(tmp_path):
    path = tmp_path / "dev.jsonl"
    write_jsonl(ROWS, path)

    assert read_jsonl_or_empty(path) == ROWS


def test_write_parquet_grava_linhas_e_nao_deixa_parcial(tmp_path):
    path = tmp_path / "out" / "tabela.parquet"

    write_parquet(ROWS, path)

    assert pq.read_table(path).to_pylist() == ROWS
    assert not path.with_suffix(".part").exists()


def test_write_parquet_aceita_compressao(tmp_path):
    path = tmp_path / "tabela.parquet"

    write_parquet(ROWS, path, compression="zstd")

    assert pq.ParquetFile(path).metadata.row_group(0).column(0).compression == "ZSTD"


def test_short_hash_depende_de_todas_as_partes():
    assert short_hash("a", 1) == short_hash("a", 1)
    assert short_hash("a", 1) != short_hash("a", 2)
    assert short_hash("a", "b") != short_hash("b", "a")
    assert len(short_hash("a")) == 10


def test_path_inside_aceita_caminho_dentro_da_raiz(tmp_path):
    assert (
        path_inside(tmp_path, "txt", "3304557", "a.txt") == (tmp_path / "txt" / "3304557" / "a.txt").resolve()
    )


@pytest.mark.parametrize("part", ["..", "../fora.txt", "a/../../fora.txt"])
def test_path_inside_recusa_caminho_que_escapa_da_raiz(tmp_path, part):
    with pytest.raises(ValueError, match="fora de"):
        path_inside(tmp_path / "raiz", part)
