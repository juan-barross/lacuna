---
base_model: Qwen/Qwen2.5-1.5B-Instruct
library_name: peft
license: apache-2.0
language:
- pt
pipeline_tag: text-generation
tags:
- lora
- qlora
- information-extraction
- structured-output
- public-procurement
---

# Lacuna: extrator de extratos de contrato (Qwen2.5-1.5B + QLoRA)

Adaptador LoRA que faz o Qwen2.5-1.5B-Instruct ler um extrato de contrato publicado em diário oficial municipal e devolver um JSON com tipo, número do contrato, processo, contratada, CNPJ, objeto, valor e data de assinatura.

Ele foi treinado para o [Lacuna](https://github.com/juan-barross/lacuna), que procura cada extrato de contrato dos diários de municípios do RJ entre os contratos registrados no PNCP. O Lacuna já tinha um extrator por regex e outro via API (Claude Opus 5.5). Este adaptador mede o quanto um modelo pequeno, ajustado com poucos exemplos e rodando de graça, chega perto do modelo grande.

## Uso

O código usa o prompt e o esquema do Lacuna (`pip install git+https://github.com/juan-barross/lacuna`).

```python
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

from dxp.llm import local_messages, parse_answer

base = "Qwen/Qwen2.5-1.5B-Instruct"
adapter = "juan1211/lacuna-extrator-qwen2.5-1.5b-lora"
tok = AutoTokenizer.from_pretrained(adapter)
model = PeftModel.from_pretrained(AutoModelForCausalLM.from_pretrained(base, dtype=torch.float32), adapter)

texto = "EXTRATO DO CONTRATO Nº 009/2026 ..."
inputs = tok.apply_chat_template(
    local_messages(texto), add_generation_prompt=True, return_tensors="pt", return_dict=True
)
out = model.generate(**inputs, max_new_tokens=512, do_sample=False)
answer = tok.decode(out[0, inputs["input_ids"].shape[1] :], skip_special_tokens=True)
ato = parse_answer(answer)
```

O prompt de sistema é o `LOCAL_PROMPT` do Lacuna: o `PROMPT` do extrator via API mais o esquema JSON do `Ato`. Com outro prompt, o resultado muda.

## Dados de treino

São 289 trechos de extratos de 13 municípios do RJ, tirados dos diários indexados pelo [Querido Diário](https://queridodiario.ok.org.br/) entre 2025 e 2026: 257 contratos, 19 contratações temporárias de pessoal e 13 trechos que não são extrato de contrato (termo aditivo, termo de colaboração e afins).

Os rótulos de treino foram escritos por um LLM (Claude) e não foram revisados à mão. O modelo aprende a imitar esses rótulos, inclusive os erros. Ficaram fora do treino 9 trechos ambíguos e 2 que coincidiam com o conjunto ouro, um pelo mesmo texto e outro pelo mesmo contrato.

Dataset: `juan1211/lacuna-extratos`.

## Treino

QLoRA com o modelo base em NF4 e cálculo em fp16, numa GPU T4 do Colab. LoRA com r=16, alpha=32 e dropout 0,05 em todas as projeções de atenção e MLP. Foram 3 épocas com taxa de aprendizado 2e-4 e cosseno, batch efetivo de 16 e perda só na resposta. O treino levou 17,7 min e terminou com perda de 0,008. Versões: torch 2.11, transformers 5.21, peft 0.21.2, trl 1.17.1 e bitsandbytes 0.50.2. O notebook está em [`notebooks/treino_qlora.ipynb`](https://github.com/juan-barross/lacuna/blob/main/notebooks/treino_qlora.ipynb).

## Avaliação

F1 por campo no conjunto ouro do Lacuna (60 trechos de teste, rótulos revisados à mão), com a mesma função de avaliação dos outros extratores. Objeto e nome contam como acerto com sobreposição de tokens a partir de 0,5 e 0,8, e valor com arredondamento em centavos.

| Campo | Qwen2.5-1.5B sem ajuste | Este modelo | Regex |
|---|---:|---:|---:|
| tipo |  | 0,98 | 0,93 |
| número do contrato |  | 0,93 | 0,78 |
| processo |  | 0,97 | 0,82 |
| nome da contratada |  | 0,93 | 0,80 |
| CNPJ da contratada |  | 1,00 | 0,86 |
| objeto |  | 0,97 | 0,95 |
| valor |  | 0,99 | 0,91 |
| data de assinatura |  | 0,92 | 0,70 |

As colunas do modelo foram medidas na T4 do Colab com a base em 4 bits, como no treino. Nenhuma das 100 respostas saiu fora do JSON, e a latência foi de 18 s por trecho (p95 de 28 s). O Space roda a base em fp32, e a diferença não foi medida.

No dev (40 trechos), este modelo teve F1 de 0,88 na data, 0,86 no nome e 0,91 no número do contrato. O Claude Opus 5.5 via API teve 0,96, 0,91 e 0,89, a US$ 0,014 por documento, medido antes da anonimização dos dados.

## Limitações

- Os rótulos de treino e o rascunho do conjunto ouro vieram do Claude. O conjunto ouro foi revisado à mão, mas a comparação pode favorecer modelos que escrevem como o Claude.
- Os 13 municípios do treino são os mesmos da avaliação. Em diários com outro formato, o desempenho deve cair.
- Treino e avaliação usam os dados anonimizados: nas contratações temporárias o nome virou `Pessoa XXXXXX`. Com o nome e o CPF reais, o modelo pode errar mais o tipo e o nome desses casos.
- Treino e ouro foram separados por texto e por contrato, não por diário. Dez trechos do ouro têm no treino um trecho do mesmo diário, com cabeçalho e rodapé parecidos.
- O conjunto de teste é pequeno. O CNPJ aparece em 10 a 14 trechos, e um acerto a mais ou a menos muda bastante o F1.
- Extrato sem par no PNCP indica que a informação não chegou ao portal federal. Não diz nada sobre a legalidade do contrato.
