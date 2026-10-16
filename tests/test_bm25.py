import pyarrow as pa

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
