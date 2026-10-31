import pytest
from conftest import build_cpf

from dxp.privacy import (
    PSEUDONYM,
    anonymize_row,
    count_marks,
    is_valid_cpf,
    mask_address,
    mask_cpf,
    mask_email,
    mask_personal_data,
    mask_rg,
    pseudonym,
    pseudonymize,
)

NAME = "Maria das Dores Souza"


def format_cpf(raw: str) -> str:
    return f"{raw[:3]}.{raw[3:6]}.{raw[6:9]}-{raw[9:]}"


def break_check_digit(raw: str) -> str:
    return raw[:-1] + str((int(raw[-1]) + 1) % 10)


RAW = build_cpf("147636957")
FORMATTED = format_cpf(RAW)


def test_cpf_gerado_no_teste_e_valido():
    assert is_valid_cpf(RAW)
    assert is_valid_cpf(FORMATTED)


@pytest.mark.parametrize("candidate", ["11111111111", "123", RAW + "0"])
def test_cpf_invalido_por_repeticao_ou_tamanho(candidate):
    assert not is_valid_cpf(candidate)


@pytest.mark.parametrize("cpf", [FORMATTED, RAW])
def test_cpf_formatado_ou_cru_some(cpf):
    assert mask_cpf(f"inscrito no CPF {cpf}, residente") == "inscrito no CPF [CPF], residente"


def test_cpf_colado_ao_nome_do_mei_some():
    assert mask_cpf(f"FULANO DE TAL {RAW}") == "FULANO DE TAL [CPF]"
    assert mask_cpf(f"FULANO{RAW}") == "FULANO[CPF]"


def test_cpf_no_fim_da_frase_some():
    assert mask_cpf(f"CPF {FORMATTED}.") == "CPF [CPF]."


def test_numero_com_digito_invalido_sem_a_palavra_cpf_nao_muda():
    text = f"Nota {format_cpf(break_check_digit(RAW))} e {break_check_digit(RAW)}"

    assert mask_cpf(text) == text


@pytest.mark.parametrize(
    "cpf",
    [format_cpf(break_check_digit(RAW)), f"{RAW[:9]}\n{RAW[9:]}", f"{FORMATTED[:11]}\n{FORMATTED[11:]}"],
)
def test_cpf_depois_da_palavra_cpf_some_mesmo_com_digito_errado_ou_quebrado(cpf):
    assert mask_cpf(f"CPF sob o nº {cpf}, residente") == "CPF sob o nº [CPF], residente"


@pytest.mark.parametrize(
    "text",
    [
        "CNPJ 12.345.678/0001-95",
        "CNPJ 12345678000195",
        "Processo 2025/00012345678-90",
        f"Processo 2025/{RAW}",
        f"Processo {RAW}-1",
        "Processo 12345678901234",
        f"Contrato {RAW}7",
        f"Contrato 1{RAW}",
        f"Processo 1.{FORMATTED}",
    ],
)
def test_cnpj_processo_e_numeros_maiores_nao_mudam(text):
    assert mask_cpf(text) == text


def test_email_pessoal_some():
    text = "contato: fulano.silva@gmail.com, ciclano@Hotmail.com.br; beltrano@uol.com.br."

    assert mask_email(text) == "contato: [EMAIL], [EMAIL]; [EMAIL]."


@pytest.mark.parametrize("provider", ["yahoo", "outlook", "bol", "live", "icloud"])
def test_email_dos_outros_provedores_some(provider):
    assert mask_email(f"a@{provider}.com") == "[EMAIL]"


def test_email_institucional_fica():
    text = "licitacao@saquarema.rj.gov.br e compras@prefeitura.net"

    assert mask_email(text) == text


@pytest.mark.parametrize("prefix", ["RG nº ", "RG n° ", "RG N° ", "RG n.º ", "RG ", "RG: "])
def test_rg_some(prefix):
    assert mask_rg(f"portador do {prefix}075560912, expedido") == "portador do RG [RG], expedido"


def test_rg_com_pontos_e_digito_x():
    assert mask_rg("RG nº 12.345.678-X.") == "RG [RG]."


def test_rg_sem_numero_nao_muda():
    text = "RG nº XX.XXX.XXX-X e o RG do servidor"

    assert mask_rg(text) == text


@pytest.mark.parametrize("preposition", ["na", "no", "em"])
def test_endereco_sem_cep_nem_uf_vai_ate_a_virgula(preposition):
    text = f"residente e domiciliado {preposition} Rua das Flores 10 Centro, Saquarema"

    assert mask_address(text) == f"residente e domiciliado {preposition} [ENDERECO], Saquarema"


def test_endereco_feminino_e_quebra_de_linha():
    text = "residente e\ndomiciliada em Rua A 5; CPF"

    assert mask_address(text) == "residente e\ndomiciliada em [ENDERECO]; CPF"


def test_endereco_para_no_ponto_final_da_linha():
    assert mask_address("residente e domiciliado na Brasil.\nObjeto: x") == (
        "residente e domiciliado na [ENDERECO].\nObjeto: x"
    )


def test_endereco_vai_ate_o_ultimo_cep_ou_uf_da_frase():
    text = (
        "residente e domiciliado na Rua A, nº 9, Centro, Niterói – RJ, CEP: 24.000-000, "
        "doravante CONTRATADO.\nObjeto: RJ"
    )

    assert mask_address(text) == "residente e domiciliado na [ENDERECO], doravante CONTRATADO.\nObjeto: RJ"


def test_dois_enderecos_no_mesmo_trecho_somem():
    text = "residente e domiciliado na Rua A, 1; e residente e domiciliada na Rua B, 2"

    assert mask_address(text) == (
        "residente e domiciliado na [ENDERECO], 1; e residente e domiciliada na [ENDERECO], 2"
    )


def test_endereco_sem_a_expressao_nao_muda():
    assert mask_address("domiciliado na Rua A") == "domiciliado na Rua A"


def test_dados_pessoais_juntos():
    text = f"inscrito no CPF {FORMATTED}, RG nº 123456, residente e domiciliado na Rua A 1, a@gmail.com"

    assert mask_personal_data(text) == (
        "inscrito no CPF [CPF], RG [RG], residente e domiciliado na [ENDERECO], [EMAIL]"
    )


def test_pseudonimo_e_estavel_e_ignora_caixa_acento_e_espaco():
    assert pseudonym(NAME) == pseudonym(NAME.upper()) == pseudonym("  Maria das  Dóres Souza ")
    assert pseudonym(NAME) != pseudonym("Outra Pessoa")
    assert PSEUDONYM.fullmatch(pseudonym(NAME))


def test_pseudonimo_troca_o_nome_sem_diferenciar_caixa():
    text = "Contrata-se MARIA DAS  DORES SOUZA e maria das dores souza."

    assert pseudonymize(text, NAME) == f"Contrata-se {pseudonym(NAME)} e {pseudonym(NAME)}."


def test_pseudonimo_troca_o_nome_com_acento_ou_pontuacao_diferente():
    text = "Contrata-se MARIA DAS DÓRES, SOUZA e Maria-das-Dores Souza."

    assert pseudonymize(text, NAME) == f"Contrata-se {pseudonym(NAME)} e {pseudonym(NAME)}."


def test_pseudonimo_troca_rotulo_com_ordinal():
    label = "MARIA SOUZA, 22 ANOS ● Mº 1765"

    assert pseudonymize("Contratada MARIA SOUZA 22 ANOS Mº 1765.", label) == f"Contratada {pseudonym(label)}."


def test_pseudonimo_nao_troca_trecho_dentro_de_outra_palavra():
    assert pseudonymize("Ana Lima", "Ana") == f"{pseudonym('Ana')} Lima"
    assert pseudonymize("Anabela", "Ana") == "Anabela"


def pessoal_row(**extra):
    return {
        "ato_id": "g#1",
        "tipo": "pessoal",
        "contratada_nome": NAME,
        "text": f"Contratada {NAME.upper()}, CPF {FORMATTED}, e-mail a@gmail.com",
        "pncp_fornecedor": f"{NAME} {RAW}",
        "valor": 1500.0,
        **extra,
    }


def test_linha_mantem_texto_e_rotulo_coerentes():
    row = anonymize_row(pessoal_row())
    alias = pseudonym(NAME)

    assert row["contratada_nome"] == alias
    assert row["text"] == f"Contratada {alias}, CPF [CPF], e-mail [EMAIL]"
    assert row["pncp_fornecedor"] == alias
    assert row["valor"] == 1500.0


def test_linha_nao_muda_identificadores():
    row = pessoal_row(numero_contrato=RAW, processo=FORMATTED, url=f"http://x/{RAW}")

    cleaned = anonymize_row(row)

    assert {k: cleaned[k] for k in ("ato_id", "numero_contrato", "processo", "url")} == {
        "ato_id": "g#1",
        "numero_contrato": RAW,
        "processo": FORMATTED,
        "url": f"http://x/{RAW}",
    }


@pytest.mark.parametrize("label", [f"FULANO {RAW}", f"FULANO - CPF {FORMATTED}", "FULANO [CPF]"])
def test_linha_de_contrato_tira_o_cpf_do_rotulo_e_mascara_no_texto(label):
    row = {"tipo": "contrato", "contratada_nome": label, "text": f"FULANO {RAW}"}

    assert anonymize_row(row) == {"tipo": "contrato", "contratada_nome": "FULANO", "text": "FULANO [CPF]"}


def test_linha_sem_rotulo_usa_o_nome_conhecido():
    row = {"ato_id": "g#1", "text": f"Contratada {NAME}"}

    assert anonymize_row(row, NAME)["text"] == f"Contratada {pseudonym(NAME)}"
    assert anonymize_row(row)["text"] == f"Contratada {NAME}"


def test_nome_conhecido_vale_mesmo_se_o_rotulo_da_linha_diverge():
    row = {"tipo": "contrato", "contratada_nome": NAME, "text": f"Contratada {NAME}"}

    alias = pseudonym(NAME)

    assert anonymize_row(row, NAME) == {**row, "contratada_nome": alias, "text": f"Contratada {alias}"}


@pytest.mark.parametrize("name", [None, "", "   ", "..."])
def test_linha_pessoal_sem_nome_so_mascara(name):
    row = {"tipo": "pessoal", "contratada_nome": name, "text": f"CPF {RAW}"}

    assert anonymize_row(row) == {**row, "text": "CPF [CPF]"}


def test_anonimizar_duas_vezes_da_o_mesmo_resultado():
    once = anonymize_row(pessoal_row())

    assert anonymize_row(once) == once
    assert anonymize_row(once, NAME) == once


def test_contagem_de_marcas():
    rows = [anonymize_row(pessoal_row()), {"n": 3, "text": "RG [RG] [ENDERECO] [CPF]"}]

    assert count_marks(rows) == {"PESSOA": 3, "CPF": 2, "EMAIL": 1, "RG": 1, "ENDERECO": 1}
