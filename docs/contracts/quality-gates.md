# Contrato — Qualidade e Entrega

## Regra de teste

Toda feature, regra, correção, fonte, transformação ou componente novo/alterado exige no mínimo um teste unitário determinístico. Bug corrigido exige teste de regressão.

## Gates por mudança

| Mudança | Obrigatório |
|---|---|
| cálculo, dado ou fonte | testes unitários + qualidade/consistência DB → JSON |
| UI | teste de contrato estático + E2E quando houver interação crítica |
| modal/gráfico | dados, ausência de dados, abertura, atualização e fechamento |
| Radar Macro | prova de que não altera score, indicador, filtro, ranking ou Top Pick |

## Comando mínimo

```powershell
python -m pytest src/tests/ -v -m "not network"
```

## Bloqueadores de entrega

* score fora de 0–10, JSON inválido, dado financeiro não finito ou mismatch DB → JSON;
* alteração sem teste correspondente;
* UI que duplique navegação/cards, misture domínios ou deixe gráfico em branco;
* Radar Macro que modifique qualquer resultado fundamental.

## Relatório final obrigatório

1. Contrato(s) lido(s).
2. Arquivos modificados.
3. Testes criados/alterados.
4. Comandos e resultados.
5. Pendências, riscos e dados indisponíveis.
