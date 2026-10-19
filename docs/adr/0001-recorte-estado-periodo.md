# ADR 0001: Recorte no RJ, outubro de 2025 a setembro de 2026

- Status: aceita
- Data: 2026-10-10

## Contexto

O projeto precisa de um recorte pequeno o bastante para rotular à mão e grande o bastante para que a taxa de conciliação por município tenha intervalo de confiança útil. O Querido Diário (QD) cobre só parte dos municípios brasileiros, e a cobertura dentro de um estado é desigual: alguns municípios têm o diário completo, outros têm poucas edições ou nenhuma no período.

Em 2026-10-10, a rota `/cities?levels=3` listava 510 municípios com nível 3 de cobertura, sendo 26 no RJ. Contagem de diários publicados entre 2025-10-01 e 2026-09-30, por município, em `data/recorte_rj.csv`.

## Decisão

- **Estado:** Rio de Janeiro.
- **Período:** 12 meses fechados, de 2025-10-01 a 2026-09-30.
- **Municípios:** os do RJ com nível 3 no QD e **pelo menos 100 diários no período** (cerca de dois por semana). Ficam 19 de 26.

Excluídos e motivo (número de diários no período):

| Município | Diários |
|---|---|
| Arraial do Cabo | 0 |
| São João da Barra | 0 |
| Varre-Sai | 0 |
| Cabo Frio | 5 |
| Iguaba Grande | 11 |
| Nova Friburgo | 26 |
| Maricá | 72 |

A lista é gerada por `scripts/recorte_municipios.py` e fica versionada.

## Por quê

- O RJ tem cobertura suficiente (26 municípios em nível 3, sétimo estado em número) e inclui a capital, com volume alto de contratações.
- Um município com poucos diários no período provavelmente tem cobertura parcial no QD. Incluí-lo faria uma falha de coleta parecer lacuna no PNCP.
- Doze meses fechados evitam efeito de sazonalidade (fim de ano e início de gestão) e dão margem para a janela de datas da conciliação.

## Consequências

- O resultado vale para esses 19 municípios, não para o RJ inteiro. O README precisa dizer isso.
- O corte de 100 é arbitrário. Maricá (72) fica perto do limite; se o número de atos por município ficar baixo, revisitar o corte é a primeira opção.
- A cobertura do QD muda com o tempo. Rodar o script de novo pode dar outra lista; a versionada é a que vale para os resultados.

## Revisão de 2026-10-12: municípios sem texto

Depois de baixar o período inteiro (4.585 diários), apareceu um problema que a contagem de diários não mostrava: em 6 dos 19 municípios o `.txt` do QD não tem o texto do diário, só o link para o PDF no site da prefeitura. Acontece nos 12 meses.

| Município | Diários | Com texto |
|---|---|---|
| Mesquita | 226 | 0 |
| Miguel Pereira | 246 | 0 |
| Quatis | 227 | 0 |
| Queimados | 244 | 0 |
| São João de Meriti | 215 | 0 |
| São Pedro da Aldeia | 174 | 0 |

Nos outros 13, entre 98% e 100% dos diários têm texto. Os que não têm são avisos curtos, como "somente na versão HTML" no Rio.

**Decisão:** a extração e a conciliação usam só os diários com `text_status = "ok"`, o que na prática deixa 13 municípios. Os 6 sem texto continuam no download, no painel e no README, marcados como sem texto disponível no QD.

**Por quê:** tirar o texto dos PDFs das prefeituras exigiria um raspador por site e OCR, um projeto à parte. Manter esses municípios visíveis mostra que a falta de texto também é uma lacuna de dados.

**Consequência:** os resultados de conciliação valem para 13 municípios. Se o QD passar a ter o texto desses 6, basta baixar de novo; nada no código depende da lista.
