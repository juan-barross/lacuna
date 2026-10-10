# diario-x-pncp

Cruza os atos de contratação publicados nos diários oficiais municipais (via [Querido Diário](https://queridodiario.ok.org.br/)) com os contratos registrados no [Portal Nacional de Contratações Públicas (PNCP)](https://pncp.gov.br/) e mede, por município, quantos atos não têm registro correspondente no portal federal.

Um ato sem par no PNCP é tratado aqui como **lacuna de dados**, não como irregularidade.

> Em construção. Pronto até agora: recorte e ingestão do Querido Diário.

## Recorte

19 municípios do RJ, de 2025-10-01 a 2026-09-30. Critério e municípios excluídos em [ADR 0001](docs/adr/0001-recorte-estado-periodo.md); lista em [`data/recorte_rj.csv`](data/recorte_rj.csv).

## Como rodar

Requer Python 3.12.

```bash
python -m venv .venv
source .venv/bin/activate        # no Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Baixar os diários do recorte (texto completo, com cache em `data/raw/`):

```bash
dxp -v qd-download
dxp qd-resumo                    # status do texto por município
```

O resultado fica em `data/processed/qd_gazettes.parquet`, uma linha por diário. A coluna `text_status` diz se o texto é utilizável (`ok`) ou por que não é (`so_link`, `curto`, `vazio`, `sem_txt`, `erro`).

## Testes

```bash
pytest
```

Os testes não acessam a internet: usam respostas gravadas da API em `tests/fixtures/`.

## Decisões

- [0001: recorte RJ, out/2025 a set/2026](docs/adr/0001-recorte-estado-periodo.md)
- [0002: LLM por API contra modelo local](docs/adr/0002-escolha-do-llm.md)
- [0003: índice próprio no Elasticsearch](docs/adr/0003-elasticsearch-alem-da-busca-do-qd.md)

## Fontes

- Querido Diário, Open Knowledge Brasil: `https://api.queridodiario.org.br`
- PNCP, API de consultas: `https://pncp.gov.br/api/consulta`

Nenhuma das duas APIs declara licença para os dados. O repositório não redistribui o dado bruto; o código baixa direto das fontes.
