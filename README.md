# Lacuna

[![ci](https://github.com/juan-barross/lacuna/actions/workflows/ci.yml/badge.svg)](https://github.com/juan-barross/lacuna/actions/workflows/ci.yml)
[![Abrir o painel](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://lacuna.streamlit.app)

Prefeituras publicam seus contratos no diário oficial e deveriam registrá-los também no [Portal Nacional de Contratações Públicas (PNCP)](https://pncp.gov.br/). O Lacuna lê os diários de municípios do RJ pelo [Querido Diário](https://queridodiario.ok.org.br/), extrai os atos de contratação e confere quais deles aparecem no PNCP.

Um ato sem par no PNCP é tratado como **lacuna de dados**, não como irregularidade.

**[Ver o painel](https://lacuna.streamlit.app)**

[![Painel do Lacuna](docs/painel.jpg)](https://lacuna.streamlit.app)

## O que já deu para medir

Foram 4.585 diários de 19 municípios, de outubro de 2025 a setembro de 2026. Em 6 desses municípios o Querido Diário não tem o texto de nenhum diário do período, só o link para o PDF no site da prefeitura. Nos outros 13, entre 98% e 100% dos diários têm texto.

Antes mesmo de chegar ao PNCP já existe uma lacuna: em um terço dos municípios cobertos, os atos publicados não podem ser lidos por máquina. Detalhes na [ADR 0001](docs/adr/0001-recorte-estado-periodo.md).

## Andamento

- [x] Recorte e ingestão do Querido Diário, com cache e status do texto de cada diário
- [x] Painel com a cobertura por município
- [ ] Cliente do PNCP e guia de anotação
- [ ] Conjunto ouro rotulado à mão e baseline com regex
- [ ] Extração com LLM, com F1 por campo, custo e latência
- [ ] Conciliação com o PNCP e taxa por município com intervalo de confiança

## Como rodar

Python 3.12.

```bash
python -m venv .venv
source .venv/bin/activate        # no Windows: .venv\Scripts\activate
pip install -e ".[dev,app]"
```

Painel local, com os dados já incluídos no repositório:

```bash
streamlit run app/streamlit_app.py
```

Baixar os diários de novo (uns 15 minutos, cerca de 900 MB em `data/`):

```bash
dxp -v qd-download
dxp qd-resumo
dxp cobertura
```

`qd-download` grava `data/processed/qd_gazettes.parquet`, uma linha por diário. A coluna `text_status` diz se o texto é utilizável (`ok`) ou por que não é (`so_link`, `curto`, `vazio`, `sem_txt`, `erro`). `cobertura` gera o `app/data/cobertura.csv` que o painel lê.

## Testes

```bash
pytest
```

Os testes não acessam a internet: usam respostas gravadas da API em `tests/fixtures/`.

## Problemas que apareceram nas APIs

- O campo `total_gazettes` do Querido Diário para em 10.000 e um `offset` acima disso devolve erro 500. O download é feito mês a mês, e uma janela que bate no teto é dividida ao meio.
- A API responde 403 ao User-Agent padrão do `urllib`.
- Desde dezembro de 2025, parte dos links de texto vem como `s3://okbr-qd-migration//...`, que não é acessível. O mesmo arquivo está em `data.queridodiario.ok.org.br`, e o cliente faz a troca.
- O servidor de arquivos às vezes fecha a conexão no meio do download. O cliente tenta de novo e só grava o arquivo quando ele chega inteiro.

## Decisões

- [0001: recorte RJ, out/2025 a set/2026](docs/adr/0001-recorte-estado-periodo.md)
- [0002: LLM por API contra modelo local](docs/adr/0002-escolha-do-llm.md)
- [0003: índice próprio no Elasticsearch](docs/adr/0003-elasticsearch-alem-da-busca-do-qd.md)

## Fontes

- Querido Diário, Open Knowledge Brasil: `https://api.queridodiario.org.br`
- PNCP, API de consultas: `https://pncp.gov.br/api/consulta`

Nenhuma das duas APIs declara licença para os dados. O repositório não redistribui o dado bruto; o código baixa direto das fontes e só as contagens agregadas ficam versionadas.
