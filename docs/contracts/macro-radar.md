# Contrato — Radar Macro Informativo

## Finalidade

Expor ao usuário expectativas e riscos futuros como hipóteses verificáveis, sem contaminar a análise fundamentalista.

## Dados permitidos

Focus, Selic, IPCA, PIB, câmbio, curva de juros e sinais de crédito, desde que cada item tenha fonte, data de referência e confiança.

## Formato público por observação

```text
sinal → hipótese condicional → exposição do ativo → confirmação necessária → confiança → fonte/data
```

Exemplo: “Focus indica queda da Selic; se a taxa longa também cair, o título prefixado longo tende a ser mais sensível à marcação a mercado; confirmar curva longa; confiança média; Focus de DD/MM/AAAA.”

## Regras

1. O Radar Macro não possui score, nota, ajuste de score ou score composto.
2. Não altera `fundamental_score`, indicadores, breakdown, filtros, ranking, Top Picks, CSV ou recomendação.
3. Não reescreve histórico com expectativas atuais.
4. Sem dado suficiente, mostra `indisponível` e os dados ausentes; não mostra neutralidade artificial.
5. Linguagem obrigatória é condicional: “pode favorecer”, “pode pressionar”, “se”, “depende de”. Proibido: “vai subir”, “compre”, “garantido”.

## Cobertura mínima por classe

| Classe | Fatores a contextualizar |
|---|---|
| Ações | juros reais, crescimento, inflação, câmbio, alavancagem e setor |
| FII tijolo | cap rate, ocupação, inflação, contratos e alavancagem |
| FII papel | CDI, spread, duration, indexador, inadimplência e concentração |
| FIAGRO | crédito, indexador, garantias, LTV, cadeia agro, commodity e câmbio |
| Tesouro | duration, taxa contratada, taxa de mercado, curva e risco de inflação |

## Local de exibição

Home: um resumo global. Modal do ativo/título: seção recolhível “Radar macro — hipóteses futuras”. Tabelas e Top Picks: não exibem Radar Macro.

## Aceite mínimo

- [ ] Cada observação contém fonte, data, confiança e condição de confirmação.
- [ ] Nenhum valor macro altera a análise fundamentalista.
- [ ] Há teste que prova o isolamento entre Radar Macro e score/ranking.
