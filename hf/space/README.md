---
title: Lacuna Extrator
emoji: 📄
colorFrom: blue
colorTo: gray
sdk: static
app_file: index.html
license: mit
models:
- juan1211/lacuna-extrator-qwen2.5-1.5b-lora
datasets:
- juan1211/lacuna-extratos
short_description: O que cada extrator leu em contratos de diários oficiais
---

Explorador do conjunto de teste do [Lacuna](https://github.com/juan-barross/lacuna): para cada extrato de contrato, a resposta revisada à mão ao lado do que leram o Qwen2.5-1.5B ajustado com QLoRA, o mesmo modelo sem ajuste e o extrator por regex. As respostas foram geradas uma vez numa T4 e gravadas em `dados.json` pelo comando `dxp explorador`, então o Space é estático e não dorme.
