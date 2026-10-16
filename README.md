# Lacuna

[![ci](https://github.com/juan-barross/lacuna/actions/workflows/ci.yml/badge.svg)](https://github.com/juan-barross/lacuna/actions/workflows/ci.yml)
[![Abrir o painel](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://lacuna.streamlit.app)

**Um em cada três extratos de contrato publicados nos diários oficiais de 13 municípios do RJ não tem registro correspondente no Portal Nacional de Contratações Públicas (PNCP).**

O Lacuna lê os diários pelo [Querido Diário](https://queridodiario.ok.org.br/), separa os extratos de contrato, extrai empresa, CNPJ, valor e data, e procura cada um entre os contratos que as prefeituras registraram no [PNCP](https://pncp.gov.br/). Um extrato sem par é tratado como **lacuna de dados**, não como irregularidade.

**[Ver o painel](https://lacuna.streamlit.app)**

[![Painel do Lacuna](docs/painel.jpg)](https://lacuna.streamlit.app)

## Resultado

Outubro de 2025 a setembro de 2026. 3.877 extratos de contrato lidos, 2.649 elegíveis (contrato com fornecedor e valor identificado) e 8.373 contratos municipais baixados do PNCP.

| | Extratos | % |
|---|---:|---:|
| Com par no PNCP | 1.676 | 63% |
| Provável (valor e data batem, nome não confirma) | 141 | 5% |
| **Sem par no PNCP** | **832** | **31%** |

Por município, com intervalo de confiança de 95% (Wilson):

| Município | Elegíveis | Com par | IC 95% |
|---|---:|---:|---|
| Quissamã | 122 | 89% | 83% a 94% |
| São José do Vale do Rio Preto | 446 | 85% | 82% a 88% |
| Saquarema | 473 | 78% | 74% a 81% |
| Macaé | 600 | 69% | 65% a 72% |
| Casimiro de Abreu | 22 | 59% | 39% a 77% |
| Armação dos Búzios | 30 | 53% | 36% a 70% |
| Cordeiro | 153 | 52% | 44% a 60% |
| Angra dos Reis | 23 | 48% | 29% a 67% |
| Niterói | 186 | 48% | 41% a 55% |
| Rio de Janeiro | 397 | 37% | 32% a 42% |
| Nova Iguaçu | 126 | 37% | 29% a 46% |
| Belford Roxo | 71 | 4% | 1% a 12% |

Belford Roxo publicou 71 extratos elegíveis no diário e registrou só 52 contratos no PNCP no mesmo período.

Outros 6 municípios (Mesquita, Miguel Pereira, Quatis, Queimados, São João de Meriti e São Pedro da Aldeia) não entram na taxa: o Querido Diário não tem o texto de nenhum diário deles, só o link para o PDF no site da prefeitura. É uma lacuna antes mesmo de chegar ao PNCP.

## Como funciona

```text
Querido Diário ──> diários (texto) ──> extratos de contrato ──> campos (regex ou LLM) ──┐
                                                                                        ├──> conciliação ──> painel
PNCP ──> órgãos municipais de cada cidade ──> contratos de cada órgão ──────────────────┘
```

1. **Ingestão** (`qd.py`, `pncp.py`): download com cache em disco, retentativa e espera quando a API limita o ritmo.
2. **Segmentação** (`segment.py`): cada extrato começa em "EXTRATO DO/DE CONTRATO" e vai até o próximo "EXTRATO".
3. **Extração** (`regex_baseline.py`, `llm.py`): regex como baseline; Claude Haiku 5.5 com saída estruturada no mesmo esquema (`schema.py`), com cache, custo por documento e latência.
4. **Conciliação** (`match.py`): mesmo município, valor a 1% e data a 60 dias; o nome da contratada (ou o CNPJ) decide entre casado e provável. Regras e motivos na [ADR 0005](docs/adr/0005-regras-de-conciliacao.md).
5. **Avaliação** (`evaluation.py`): F1 por campo contra um conjunto ouro rotulado à mão e precisão do casamento numa amostra conferida à mão.

## O que deu errado no caminho

Cada item virou um teste.

- **A taxa depende da extração.** Erros no corte do nome da contratada derrubavam o casamento: em Cordeiro o nome engolia "CONTRATO N.º 233/2025" da linha seguinte (taxa de 8% para 52% depois da correção); em Quissamã as partes vêm em "Celebrado entre o Município e a empresa X" (6% para 89%); em Macaé o nome vinha grudado em "Macaé, 07 de Outubro de 2025" (56% para 69%).
- **Valores redondos casavam por coincidência.** R$ 24.000,00 batia com contratos de outras empresas. Com os dois nomes presentes e diferentes, o par agora é descartado.
- **O CNPJ errado era o do carimbo.** O D.O.Rio repete no meio do texto a assinatura digital da gráfica municipal, com CNPJ. A segmentação tira esse cabeçalho de página.
- **APIs com armadilhas.** O Querido Diário satura o total em 10.000 resultados e devolve links `s3://` internos desde dez/2025. O PNCP não filtra contratos por município, recusa períodos acima de 365 dias, devolve 204 sem corpo quando não há resultado e bloqueia por ~27 s depois de 30 a 60 pedidos.
- **Pouca memória.** A máquina tem 4 GB. O Elasticsearch previsto saiu ([ADR 0004](docs/adr/0004-duckdb-no-lugar-do-elasticsearch.md)); a busca usa o BM25 do DuckDB.

## Limitações

- O conjunto ouro (250 trechos, `data/gold/fila.jsonl`) e a conferência dos casamentos (`data/gold/casamentos.csv`) estão preparados, mas ainda não rotulados. Até lá, a qualidade da extração e a precisão do casamento não estão medidas, e a taxa vale como estimativa.
- Só entram extratos com o cabeçalho padrão. Sumidouro, por exemplo, quase não o usa.
- Contratação temporária de pessoal (1.216 extratos, quase todos em Saquarema) fica fora, porque não vai para o PNCP.

## Como rodar

Python 3.12.

```bash
python -m venv .venv
source .venv/bin/activate        # no Windows: .venv\Scripts\activate
pip install -e ".[dev,app]"
streamlit run app/streamlit_app.py
```

O painel usa os dados já incluídos em `app/data/`. Para refazer tudo a partir das APIs (algumas horas, por causa do limite do PNCP):

```bash
dxp qd-download && dxp pncp-download
dxp atos && dxp cobertura && dxp conciliar
```

Avaliação:

```bash
dxp amostra                      # sorteia os 250 trechos do conjunto ouro
streamlit run app/anotar.py      # rotula à mão (guia em docs/guia_anotacao.md)
dxp avaliar --extrator regex     # F1 por campo no dev
dxp avaliar --extrator llm       # precisa de ANTHROPIC_API_KEY no .env
dxp precisao                     # depois de preencher data/gold/casamentos.csv
```

## Testes

```bash
pytest
```

129 testes, sem acesso à internet: respostas gravadas das APIs e um cliente falso do LLM. Um deles roda a CLI inteira de ponta a ponta num diretório temporário.

## Decisões

- [0001: recorte RJ, out/2025 a set/2026, e municípios sem texto](docs/adr/0001-recorte-estado-periodo.md)
- [0002: LLM por API contra modelo local](docs/adr/0002-escolha-do-llm.md)
- [0004: BM25 no DuckDB no lugar do Elasticsearch](docs/adr/0004-duckdb-no-lugar-do-elasticsearch.md)
- [0005: regras de conciliação](docs/adr/0005-regras-de-conciliacao.md)

## Fontes

Querido Diário (Open Knowledge Brasil) e PNCP, API de consultas. Nenhuma das duas declara licença para os dados; o repositório não redistribui o dado bruto, só contagens e os trechos de extratos usados no painel.
