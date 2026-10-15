# Guia de anotação do conjunto ouro

O conjunto ouro tem 250 trechos sorteados de `data/processed/atos.parquet`, alternando entre os municípios para que nenhum formato domine. Os 100 primeiros são o **dev** e os outros 150 são o **teste**.

**O teste fica congelado.** Prompts e regras de regex só são ajustados olhando o dev. O teste roda uma vez por versão, e o resultado vai para `reports/`. Se um erro do teste mostrar uma regra nova, a regra entra no guia e é aplicada no dev, nunca corrigida direto no teste.

Para rotular:

```bash
dxp amostra
streamlit run app/anotar.py
```

O app mostra um trecho por vez e grava cada rótulo em `data/gold/dev.jsonl` ou `data/gold/test.jsonl`. Os campos começam vazios de propósito: preencher a partir da saída do regex ou do LLM puxaria o rótulo para o que o modelo já acha.

## Regra geral

Rotule o que está **escrito no trecho**. Não complete com informação de fora, nem com o que "deveria" estar lá. Se o campo não aparece, deixe vazio. Vazio é um rótulo válido e conta na avaliação: um extrator que inventa um valor onde o texto não tem perde precisão.

## Campos

**tipo**
- `contrato`: contrato com fornecedor ou prestador, pessoa jurídica ou física, fruto de licitação, dispensa ou inexigibilidade. É o tipo que deveria aparecer no PNCP.
- `pessoal`: contratação de pessoa física por tempo determinado (processo seletivo simplificado, art. 37, IX, da Constituição). Não passa pelo PNCP.
- `outro`: o trecho não é um extrato de contrato. Exemplos: termo aditivo que entrou junto, errata, apostilamento ou rescisão. Os outros campos ficam vazios.

**numero_contrato:** como está no texto, sem "nº" na frente (`195/2025-SEMED`, `06/2025`).

**processo:** número do processo administrativo, com o prefixo se houver (`CLB-OFI 2025/00583`, `14.618/2025`).

**contratada_nome:** razão social ou nome da contratada, sem o CNPJ e sem "a empresa". Corrija só quebras de linha e hifenização ("Su-perior" vira "Superior"); mantenha maiúsculas e abreviações como estão.

**contratada_cnpj:** CNPJ da **contratada**, nunca o do órgão contratante. Se o trecho só tem o CNPJ do município, o campo fica vazio. Pode ser alfanumérico.

**objeto:** o texto depois de "Objeto:", até o próximo rótulo. Tire "O presente contrato tem por objeto" quando houver.

**valor:** valor **total** do contrato, em reais, com centavos (`1474895.28`).
- Se o texto só traz valor mensal e prazo ("R$ 1.591,32 mensais por 12 meses"), anote o valor mensal e escreva "valor mensal" na observação.
- Se há valor global e valor empenhado no exercício, use o global.
- Valor só por extenso também conta.

**data_assinatura:** data em que o contrato foi assinado. Se não houver data de assinatura explícita, use a data do fecho ("Saquarema, 11 de agosto de 2025"). Não use a data de início da vigência nem a data do diário.

## Observação

Campo livre para casos que vão para a taxonomia de erros: OCR ruim, ato com várias empresas, valor só por extenso, CNPJ do órgão no lugar do da contratada, trecho cortado.
