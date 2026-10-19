# ADR 0005: Regras de conciliação entre o diário e o PNCP

- Status: aceita
- Data: 2026-10-15

## Contexto

Um extrato no diário e um contrato no PNCP não compartilham identificador. O número do contrato no diário (`198/2025`) raramente aparece igual no PNCP (`numeroContratoEmpenho`), e metade dos extratos nem traz o CNPJ da contratada. O casamento precisa usar o que os dois lados têm em comum: município, valor, data e o nome do fornecedor.

## Decisão

Um contrato do PNCP é candidato para um extrato quando:

- é de um órgão municipal do mesmo município (descoberto pela rota de contratações, `esferaId = "M"`);
- o valor global difere no máximo 1% (ou R$ 1, o que for maior);
- a data de assinatura está a até 60 dias da data de assinatura do extrato (ou da data do diário, quando o extrato não traz a de assinatura).

Entre os candidatos, o extrato é:

- casado, se o CNPJ da contratada bate ou se o nome tem similaridade de tokens a partir de 0,6;
- provável, se o extrato não traz nome nem CNPJ, ou se o nome fica entre 0,3 e 0,6;
- sem par, se não há candidato, ou se os dois nomes existem e a similaridade fica abaixo de 0,3.

Contratação temporária de pessoa física ("pessoal") e extrato sem valor ficam fora da taxa.

A taxa por município é casados dividido por elegíveis (casados, prováveis e sem par), com intervalo de Wilson de 95%.

## Por quê

- Valor e data reduzem os candidatos a poucos, e o nome da contratada decide entre eles. Na primeira versão, um par só por valor e data contava como provável mesmo com nomes diferentes, e valores redondos (R$ 24.000,00) casavam com contratos de outras empresas: Cordeiro tinha 89 prováveis. Com nomes presentes e diferentes, o par agora é descartado.
- 1% de tolerância cobre arredondamento e a diferença entre valor inicial e global, sem abrir para contratos diferentes.
- 60 dias cobre a defasagem entre assinatura, publicação no diário e registro no PNCP. A Lei 14.133 (art. 94) dá até 20 dias úteis para a divulgação no PNCP, ou 10 nas contratações diretas, e na prática há atraso.
- Prováveis não entram na taxa principal. Contá-los como casados aumentaria a taxa com pares que ninguém confirmou. Eles aparecem separados no painel.
- Wilson em vez do intervalo normal, porque vários municípios têm poucas dezenas de extratos e taxas perto de 0% ou 100%.

## Consequências

- A taxa depende da extração: um nome mal extraído vira "provável" ou "sem par". Corrigir a leitura do nome levou a taxa de Cordeiro de 8% para 52%, a de Macaé de 56% para 69% e a de Quissamã de 6% para 89%. Por isso a extração tem avaliação própria contra o conjunto ouro.
- Um contrato do PNCP pode casar com dois extratos (republicação, errata). Isso não muda a taxa do lado do diário, que é a medida do projeto.
- A precisão do casamento é medida à mão numa amostra de 100 casados (`dxp precisao`).
