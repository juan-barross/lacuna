# ADR 0001: Recorte — RJ, outubro de 2025 a setembro de 2026

- **Status:** aceita
- **Data:** 2026-10-10

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
