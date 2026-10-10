# ADR 0002: LLM da extração — um modelo por API e um local

- **Status:** aceita
- **Data:** 2026-10-10

## Contexto

A extração precisa transformar um trecho de diário (texto de OCR, muitas vezes quebrado) num registro estruturado: tipo de ato, processo, modalidade, objeto, CNPJ e razão social da contratada, valor, datas. O regex resolve parte disso (CNPJ, valores, datas em formato fixo), mas falha em valor por extenso, ato com várias empresas e CNPJ do órgão misturado com o da contratada.

São alguns milhares de diários. Custo por documento e latência entram no resultado do projeto, não são detalhe.

## Decisão

Rodar e comparar dois modelos com o mesmo prompt e o mesmo esquema Pydantic:

1. **Por API:** Claude Haiku 5.5 (`claude-haiku-5-5`), com saída estruturada.
2. **Local:** um modelo aberto servido pelo Ollama, escolhido na semana 4 entre os que cabem na máquina disponível.

O regex continua como baseline e como primeira passada: o LLM só é chamado nos trechos que a busca BM25 trouxe como candidatos a ato de contratação.

## Por quê

- Um modelo pequeno da família Haiku tem custo baixo por chamada e suporta saída estruturada, o que reduz resposta fora do esquema.
- O modelo local mostra quanto se perde (ou não) sem pagar API e sem mandar o texto para fora. Essa comparação vira uma linha da tabela de resultados.
- Fixar o ID do modelo no código evita que o número mude porque o fornecedor atualizou um alias.

## Consequências

- Todo resultado em `reports/` registra o ID exato do modelo, o prompt (hash) e a data.
- A CI usa respostas gravadas do LLM; a API só é chamada à mão.
- Trocar de modelo exige rodar a avaliação no dev de novo antes de tocar no teste.
- Preço por token não fica fixado aqui: o custo é calculado a partir do uso devolvido pela API e da tabela de preços vigente na data da rodada.
