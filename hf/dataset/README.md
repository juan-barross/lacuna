---
language:
- pt
license: other
task_categories:
- text-generation
tags:
- information-extraction
- public-procurement
pretty_name: Lacuna, extratos de contrato de diários oficiais do RJ
size_categories:
- n<1K
configs:
- config_name: default
  data_files:
  - split: train
    path: train.jsonl
  - split: dev
    path: dev.jsonl
  - split: test
    path: test.jsonl
---

# Lacuna: extratos de contrato de diários oficiais do RJ

Trechos de extratos de contrato publicados nos diários oficiais de 13 municípios do RJ, cada um com os campos do esquema `Ato` do [Lacuna](https://github.com/juan-barross/lacuna): tipo, número do contrato, processo, contratada, CNPJ, objeto, valor e data de assinatura.

| Split | Trechos | Rótulos |
|---|---:|---|
| train | 289 | escritos por LLM (Claude), sem revisão humana |
| dev | 40 | rascunho de LLM revisado à mão |
| test | 60 | rascunho de LLM revisado à mão |

## Campos

- `ato_id`, `territory_name`: identificador do trecho no Lacuna e município.
- `text`: o trecho do diário, como veio do Querido Diário.
- `tipo`: `contrato`, `pessoal` (contratação temporária de pessoa física) ou `outro` (não é extrato de contrato).
- `numero_contrato`, `processo`, `contratada_nome`, `objeto`: texto, como aparece no trecho.
- `contratada_cnpj`: só letras e dígitos.
- `valor`: valor total em reais (número).
- `data_assinatura`: data de assinatura em ISO (AAAA-MM-DD). Sem ela, a data do fecho. Nunca o início da vigência.
- `origem`: como o rótulo foi feito.

Campo ausente no trecho fica nulo. As regras de cada caso difícil estão no [guia de anotação](https://github.com/juan-barross/lacuna/blob/main/docs/guia_anotacao.md).

## Como foi montado

Os trechos de dev e test foram sorteados por município entre os extratos que o Lacuna separou. O treino é outra amostra de 300, sorteada por município entre os trechos de até 2.200 caracteres fora do dev e do test. Dela saíram os trechos com o mesmo texto ou o mesmo contrato (número e contratada) do dev e do test, e os 9 que o rotulador marcou como ambíguos.

## Fonte e licença

Os textos vêm de diários oficiais municipais, que são atos públicos, obtidos pela API do [Querido Diário](https://queridodiario.ok.org.br/) (Open Knowledge Brasil). A API não declara licença para os dados, por isso a licença aqui é `other`. Os trechos trazem nomes de empresas e de pessoas físicas contratadas, publicados pelas próprias prefeituras. Alguns CPFs vêm mascarados na origem, mas o nome de microempreendedores individuais costuma trazer o CPF ou a raiz do CNPJ junto.
