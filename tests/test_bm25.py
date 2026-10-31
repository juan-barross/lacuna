from concurrent.futures import ThreadPoolExecutor

import pyarrow as pa
import pytest

from dxp.bm25 import BM25

ATOS = pa.table(
    {
        "ato_id": ["a", "b", "c"],
        "text": [
            "Aquisição de gêneros alimentícios para a merenda escolar",
            "Locação de veículos para a Secretaria de Saúde",
            "Fornecimento de MERENDAS e alimentação escolar",
        ],
    }
)


def test_busca_com_stemmer_e_sem_acento():
    found = [ato_id for ato_id, _ in BM25(ATOS).search("merenda escolar")]

    assert set(found) == {"a", "c"}


def test_sem_resultado():
    assert BM25(ATOS).search("pavimentação") == []


def test_limita_o_numero_de_resultados():
    assert len(BM25(ATOS).search("para", k=1)) == 1


def test_empate_de_pontuacao_sai_na_ordem_do_ato_id():
    same_text = "Locação de veículos"
    atos = pa.table({"ato_id": ["z", "m", "a"], "text": [same_text] * 3})

    assert [ato_id for ato_id, _ in BM25(atos).search("veículos")] == ["a", "m", "z"]


def test_ato_id_repetido_e_recusado_antes_de_indexar():
    atos = pa.table({"ato_id": ["a", "a"], "text": ["um", "dois"]})

    with pytest.raises(ValueError, match="ato_id repetido"):
        BM25(atos)


def test_ignora_colunas_alem_de_ato_id_e_texto():
    atos = ATOS.append_column("territory_name", pa.array(["Rio", "Rio", "Rio"]))

    assert {ato_id for ato_id, _ in BM25(atos).search("merenda")} == {"a", "c"}


def test_buscas_em_paralelo_usam_cursores_proprios():
    index = BM25(ATOS)

    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(index.search, ["merenda", "veículos", "merenda", "saúde"] * 8))

    assert {frozenset(ato_id for ato_id, _ in r) for r in results} == {frozenset("ac"), frozenset("b")}
