# ADR 0004: Busca BM25 no DuckDB no lugar do Elasticsearch

- **Status:** aceita, substitui a [ADR 0003](0003-elasticsearch-alem-da-busca-do-qd.md)
- **Data:** 2026-10-15

## Contexto

A ADR 0003 previa um Elasticsearch local para indexar o texto dos diários. Na prática, a máquina de desenvolvimento tem 4 GB de RAM, e um nó do Elasticsearch pede pelo menos 1 a 2 GB só de heap. Com o texto completo (cerca de 220 MB em Parquet), o índice e o sistema disputando memória, o ambiente fica instável.

Também ficou claro que a busca não precisa rodar sobre o diário inteiro. A segmentação por cabeçalho ("EXTRATO DO CONTRATO", "EXTRATO DE CONTRATO") já separa os atos de contratação, e são cerca de 3.900 trechos, com mediana de 900 caracteres. É um corpus pequeno.

## Decisão

Indexar só os trechos segmentados, com a extensão `fts` do DuckDB: BM25, stemmer de português e acentos removidos. O índice fica num arquivo `.duckdb` em `data/processed/`, sem servidor.

## Por quê

- Cabe na máquina: o índice dos trechos ocupa poucos MB.
- O motivo principal da ADR 0003 continua valendo: o índice é nosso, então a busca pode ser medida (recall@10, MRR) sem depender da configuração da API do QD.
- O mesmo arquivo serve para a conciliação (SQL) e para o painel.

## Consequências

- Perde-se a busca vetorial e híbrida pronta do Elasticsearch. Se a comparação BM25 contra embeddings entrar no projeto, os vetores ficam numa coluna do DuckDB e a similaridade é calculada em SQL.
- A busca cobre só os trechos que a segmentação achou. Um ato com cabeçalho fora do padrão não aparece; a contagem por município no painel deixa isso visível (Sumidouro, por exemplo, quase não usa esse cabeçalho).
