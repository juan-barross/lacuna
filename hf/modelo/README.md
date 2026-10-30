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

Ele foi treinado para o [Lacuna](https://github.com/juan-barross/lacuna), que procura cada extrato de contrato dos diários de municípios do RJ entre os contratos registrados no PNCP. O Lacuna já tinha um extrator por regex e outro via API (Claude Opus 5.5). Este modelo testa se um modelo pequeno, ajustado com poucos exemplos e rodando de graça, chega perto do modelo grande.

## Uso

```python
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

from dxp.llm import PROMPT  # pip install git+https://github.com/juan-barross/lacuna
from dxp.schema import Ato

base = "Qwen/Qwen2.5-1.5B-Instruct"
adapter = "SEU_USUARIO_HF/lacuna-extrator-qwen2.5-1.5b-lora"
tok = AutoTokenizer.from_pretrained(adapter)
model = PeftModel.from_pretrained(AutoModelForCausalLM.from_pretrained(base, dtype=torch.float32), adapter)

texto = "EXTRATO DO CONTRATO Nº 009/2026 ..."
messages = [{"role": "system", "content": PROMPT}, {"role": "user", "content": texto}]
inputs = tok.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt", return_dict=True)
out = model.generate(**inputs, max_new_tokens=512, do_sample=False)
answer = tok.decode(out[0, inputs["input_ids"].shape[1] :], skip_special_tokens=True)
ato = Ato.model_validate_json(answer[answer.find("{") : answer.rfind("}") + 1])
```

O prompt de sistema é o mesmo `PROMPT` do extrator via API. Com outro prompt, o resultado muda.

## Dados de treino

São 289 trechos de extratos de 13 municípios do RJ, tirados dos diários indexados pelo [Querido Diário](https://queridodiario.ok.org.br/) entre 2025 e 2026: 257 contratos, 19 contratações temporárias de pessoal e 13 trechos que não são extrato de contrato (termo aditivo, termo de colaboração e afins).

**Os rótulos de treino foram escritos por um LLM (Claude) e não foram revisados à mão.** O modelo aprende a imitar esses rótulos, inclusive os erros. Ficaram fora do treino 9 trechos ambíguos e 2 que coincidiam com o conjunto ouro, um pelo mesmo texto e outro pelo mesmo contrato.

Dataset: `SEU_USUARIO_HF/lacuna-extratos`.

## Treino

QLoRA com o modelo base em NF4 e cálculo em fp16, numa GPU T4 do Colab. LoRA com r=16, alpha=32 e dropout 0,05 em todas as projeções de atenção e MLP. Foram 3 épocas com taxa de aprendizado 2e-4 e cosseno, batch efetivo de 16 e perda só na resposta. O notebook está em [`notebooks/treino_qlora.ipynb`](https://github.com/juan-barross/lacuna/blob/main/notebooks/treino_qlora.ipynb).

## Avaliação

F1 por campo no conjunto ouro do Lacuna (60 trechos de teste, rótulos revisados à mão), com a mesma função de avaliação dos outros extratores. Objeto e nome contam como acerto com sobreposição de tokens a partir de 0,5 e 0,8, e valor com arredondamento em centavos.

| Campo | Qwen2.5-1.5B sem ajuste | Este modelo | Regex |
|---|---:|---:|---:|
| tipo |  |  | 0,93 |
| número do contrato |  |  | 0,78 |
| processo |  |  | 0,82 |
| nome da contratada |  |  | 0,80 |
| CNPJ da contratada |  |  | 0,86 |
| objeto |  |  | 0,95 |
| valor |  |  | 0,91 |
| data de assinatura |  |  | 0,70 |

<!-- preencher com reports/AAAA-MM-DD_qlora_test.json depois do treino -->

No dev (40 trechos), o Claude Opus 5.5 via API teve F1 de 0,96 na data e 0,91 no nome, a US$ 0,014 por documento.

## Limitações

- Os rótulos de treino e o rascunho do conjunto ouro vieram do Claude. O conjunto ouro foi revisado à mão, mas a comparação pode favorecer modelos que escrevem como o Claude.
- Os 13 municípios do treino são os mesmos da avaliação. Em diários com outro formato, o desempenho deve cair.
- O conjunto de teste é pequeno. O CNPJ aparece em 10 a 14 trechos, e um acerto a mais ou a menos muda bastante o F1.
- Extrato sem par no PNCP indica que a informação não chegou ao portal federal. Não diz nada sobre a legalidade do contrato.
