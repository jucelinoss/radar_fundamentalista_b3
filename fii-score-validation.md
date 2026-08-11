# Validação do score experimental de FIIs

## Objetivo

Comparar o score atual com uma versão experimental que prioriza renda sustentável, sem alterar produção.

## Tarefas

- [x] Definir pesos: renda 5, risco observável 3 e valuation 2.
- [x] Gerar SQLite de teste com todos os FIIs atuais e o histórico do BCRI11 como baseline.
- [x] Medir amplitude, variação mensal e quedas de renda de 6 meses.
- [x] Validar com testes unitários e executar o script em modo experimental.

## Critério de validação

O experimento deve ser reproduzível, manter o score de produção intacto e identificar separadamente cortes persistentes de renda de 15% em seis meses.
