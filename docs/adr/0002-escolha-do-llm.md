# ADR 0002: Claude Opus 5.5 pelo OpenRouter na extração

- Status: aceita (revista em 2026-10-19)
- Data: 2026-10-10

## Contexto

A extração transforma um extrato de diário, em geral texto de OCR quebrado, num registro com tipo de ato, processo, objeto, CNPJ e nome da contratada, valor e data de assinatura. O regex resolve o que tem formato fixo (CNPJ, valores em R$, datas numéricas) e erra quando o rótulo muda de um município para outro, quando o valor vem por extenso ou quando o nome da contratada não tem rótulo.

A primeira versão desta ADR previa o Claude Haiku pela API da Anthropic e um modelo aberto rodando no Ollama. O modelo local saiu: a máquina de desenvolvimento tem 4 GB de RAM, que não comportam um modelo útil junto com o resto do pipeline.

## Decisão

Comparar dois extratores com o mesmo esquema (`Ato`, em `schema.py`):

1. o baseline de regex (`regex_baseline.py`);
2. o Claude Opus 5.5 (`anthropic/claude-opus-5.5`) pelo OpenRouter, com `response_format` em JSON Schema estrito gerado do próprio `Ato` e raciocínio em esforço baixo.

## Por quê

O OpenRouter dá acesso ao modelo com uma chave só e devolve o uso de tokens em cada resposta, o que basta para medir custo por documento. A saída estruturada com esquema estrito elimina respostas fora do formato, e a validação pelo Pydantic e pelo dígito do CNPJ pega o que o esquema não pega.

O esforço baixo de raciocínio mantém o custo perto de US$ 0,012 por extrato, medido nos 85 trechos do dev já processados. Extrair um campo de um parágrafo não pede raciocínio longo.

## Consequências

- Cada resposta fica em `data/llm_cache/` por hash de modelo, prompt e texto. A CI avalia com essas respostas e não precisa de chave.
- Mudar o prompt muda o hash e invalida o cache. Uma nova rodada no dev vem antes de qualquer rodada no teste.
- O OpenRouter reserva crédito pelo `max_tokens` de cada pedido. Com o saldo baixo, pedidos em paralelo voltam com 402; por isso `max_tokens` fica em 1.500 e o `llm-fila` usa duas chamadas por vez.
- O custo é calculado pelos tokens de cada resposta e pela tabela de preço em `llm.py`. Se o preço mudar, a tabela muda junto.
