# Contrato — Navegação, Home, Tabelas, Modais e Gráficos

## Dono

`index-v2.html` e seus scripts/CSS locais.

## Navegação

* Existe exatamente uma `.tabs-row`.
* Ela fica imediatamente depois de `header`, antes de filtros e painéis.
* Ela permanece `sticky` no topo em desktop e mobile; no mobile rola horizontalmente e nunca muda para o rodapé.
* Abas válidas: Home, Ações, FIIs, FIAGROs, Setores e Renda Fixa.

## Home

* É a única tela com cards macro, resumo do Radar Macro e Top Picks.
* Top Picks têm um único renderizador compartilhado e um único score por item, em `.home-pick-score`.
* Top Ações: ticker, DY e P/VP quando disponível; FIIs/FIAGROs: DY e P/VP; Tesouro: taxa e prazo/vencimento.
* Nenhum detalhe de Top Pick contém “Score” ou repete o valor do badge.

## Abas analíticas

* Ações, FIIs, FIAGROs, Setores e Renda Fixa não duplicam cards, Top Picks ou resumo da Home.
* Cada aba contém somente seu título/contexto, filtros aplicáveis, tabela/gráfico próprio e detalhe sob demanda.
* Ranking e filtros de score usam exclusivamente `fundamental_score`.

## Modais e gráficos

| Modal | Aceita | Nunca aceita |
|---|---|---|
| `#detail-modal` | ações, FIIs e FIAGROs | metodologia/dados do Tesouro |
| `#td-detail-modal` | títulos do Tesouro | metodologia/dados de renda variável |
| `#focus-detail-modal` | uma série macro | score de ativo ou Tesouro |

* Cada gráfico tem instância própria; só é criado após o container ficar visível e `requestAnimationFrame()` ocorrer.
* Sem dados, renderizar mensagem explícita; canvas branco é defeito.
* Fechar/atualizar um modal destrói somente o gráfico e estado do próprio dono.

## Aceite mínimo

- [ ] Menu único no topo em desktop/mobile.
- [ ] Cards exclusivos da Home.
- [ ] Score não duplicado e P/VP zero preservado.
- [ ] Modal correto abre para cada tipo de ativo.
- [ ] Não há gráfico branco, instância duplicada ou metodologia cruzada.
