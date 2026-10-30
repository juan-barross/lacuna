---
title: Lacuna Extrator
emoji: 📄
colorFrom: gray
colorTo: green
sdk: gradio
sdk_version: 5.50.0
python_version: "3.12"
app_file: app.py
license: mit
short_description: Extrai campos de extratos de contrato de diários oficiais
---

Demonstração do extrator ajustado com QLoRA do [Lacuna](https://github.com/juan-barross/lacuna). O app recebe um extrato de contrato publicado em diário oficial municipal e devolve tipo, número, processo, contratada, CNPJ, objeto, valor e data de assinatura, lado a lado com o extrator por regex do projeto.

O adaptador é lido da variável `ADAPTER` (Settings → Variables). O modelo roda em CPU, por isso cada extração leva de 30 s a 1 min.
