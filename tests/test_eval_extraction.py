import json

import pytest

from dxp.evaluation import load_gold, score
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


def test_load_gold(tmp_path):
    path = tmp_path / "dev.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in GOLD) + "\n", encoding="utf-8")

    assert load_gold(path) == GOLD
