# ADR 0003: Índice próprio no Elasticsearch, além da busca da API do QD

- Status: substituída pela [ADR 0004](0004-duckdb-no-lugar-do-elasticsearch.md)
- Data: 2026-10-10

## Contexto

A API do Querido Diário já tem busca (`/gazettes?querystring=...`) sobre um índice OpenSearch. Ela devolve metadados do diário e alguns trechos destacados, com tamanho e quantidade configuráveis.

O projeto precisa de mais do que isso: dividir cada diário em trechos com município, data e página; buscar candidatos a ato de contratação; e **medir a busca** (recall@10, MRR) comparando BM25, embeddings e híbrido.

## Decisão

Usar a API do QD só para **descobrir e baixar** os diários (metadados e `txt_url`). A busca do projeto roda num Elasticsearch 8 local, nó único em Docker, com o analisador `brazilian`, sobre o texto completo dividido em trechos.

## Por quê

- Avaliação: não dá para medir recall@10 de um índice que não controlamos. A configuração do índice do QD (analisador, campos, ranking) pode mudar sem aviso e mudaria o número.
- Granularidade: os trechos da API são destaques ao redor do termo buscado, não unidades estáveis. O conjunto ouro precisa de trechos com identificador fixo.
- Variações de busca: BM25 com analisador `brazilian`, busca vetorial e híbrida só são comparáveis no mesmo índice.
- Carga na API: o QD é um serviço público mantido por uma ONG. Baixar cada diário uma vez e consultar localmente é mais educado do que repetir milhares de buscas remotas a cada ajuste.
- Já tenho experiência com Elasticsearch, o que reduz o risco da parte que não é o foco do projeto.

## Consequências

- O `docker-compose.yml` sobe o Elasticsearch para desenvolvimento; a CI usa fixtures e não depende dele para os testes de unidade.
- O índice é derivado: pode ser apagado e reconstruído a partir de `data/processed/`.
- O painel publicado não consulta o Elasticsearch; usa resultados pré-calculados.
