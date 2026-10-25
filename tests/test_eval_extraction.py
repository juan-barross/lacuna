import pytest

from dxp.evaluation import agreement, prf, same, score
from dxp.files import read_jsonl, write_jsonl
from dxp.schema import Ato
from dxp.text import fold, token_f1

GOLD = [
    {
        "text": "A",
        "tipo": "contrato",
        "contratada_nome": "JMP Distribuidora em Geral Ltda",
        "contratada_cnpj": "34.075.739/0001-84",
        "objeto": "Aquisição de gêneros alimentícios para o CAPS",
        "valor": 3306.88,
        "data_assinatura": "2026-07-01",
    },
    {"text": "B", "tipo": "pessoal", "valor": 1591.32},
]


def fake_extractor(text: str) -> Ato:
    if text == "A":
        return Ato(
            tipo="contrato",
            contratada_nome="JMP DISTRIBUIDORA EM GERAL LTDA.",
            contratada_cnpj="34075739000184",
            objeto="aquisição de gêneros alimentícios",
            valor=3306.88,
            numero_contrato="305/2026",
        )
    return Ato(tipo="contrato", valor=1591.30)


def test_fold_ignora_acento_caixa_e_pontuacao():
    assert fold("JMP Distribuidora, LTDA.") == fold("jmp distribuidora ltda")


def test_token_f1():
    assert token_f1("a b c d", "a b") == pytest.approx(2 / 3)
    assert token_f1("a", "b") == 0.0
    assert token_f1("", "a") == 0.0


@pytest.mark.parametrize(
    ("field", "gold", "pred", "expected"),
    [
        ("valor", 10.0, 10.004, True),
        ("valor", 10.0, 10.01, False),
        ("numero_contrato", "195/2025", "195/2025.", True),
        ("contratada_nome", "Italia Empreendimentos Ltda", "ITALIA EMPREENDIMENTOS", True),
        ("contratada_nome", "Italia Empreendimentos Ltda", "ITALIA", False),
    ],
)
def test_same(field, gold, pred, expected):
    assert same(field, gold, pred) is expected


def test_prf_sem_nada_e_zero():
    assert prf({"tp": 0, "fp": 0, "fn": 0}) == {
        "precision": 0.0,
        "recall": 0.0,
        "f1": 0.0,
        "support": 0,
    }


def test_score_por_campo():
    result = score(GOLD, fake_extractor)

    assert result["contratada_cnpj"] == {"precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 1}
    assert result["contratada_nome"]["f1"] == 1.0
    assert result["objeto"]["f1"] == 1.0
    assert result["valor"]["precision"] == 0.5
    assert result["valor"]["recall"] == 0.5
    assert result["tipo"]["f1"] == 0.5
    assert result["numero_contrato"]["precision"] == 0.0
    assert result["data_assinatura"]["recall"] == 0.0


def test_jsonl_ida_e_volta(tmp_path):
    path = tmp_path / "dev.jsonl"
    write_jsonl(GOLD, path)

    assert read_jsonl(path) == GOLD
    assert read_jsonl(tmp_path / "nao_existe.jsonl") == []


def test_concordancia_ignora_campo_vazio_nos_dois():
    first = {"A": Ato(tipo="contrato", valor=10.0, objeto="obra"), "B": Ato(tipo="pessoal")}
    second = {"A": Ato(tipo="contrato", valor=10.0), "B": Ato(tipo="contrato")}

    result = agreement(["A", "B"], first.get, second.get)

    assert result["tipo"] == {"concordancia": 0.5, "n": 2}
    assert result["valor"] == {"concordancia": 1.0, "n": 1}
    assert result["objeto"] == {"concordancia": 0.0, "n": 1}
    assert result["processo"] == {"concordancia": None, "n": 0}
