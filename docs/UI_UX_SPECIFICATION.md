# Especificação de UI/UX — Radar Fundamentalista B3

> **Status:** contrato obrigatório de interface.
>
> Este documento é a fonte de verdade para qualquer alteração em [`index-v2.html`](../index-v2.html). Regras de análise, fórmulas, limites, dados e fontes pertencem exclusivamente a [ANALYSIS_RULES_SPECIFICATION.md](ANALYSIS_RULES_SPECIFICATION.md). Antes de editar a interface, a pessoa ou IA responsável deve ler as seções **Arquitetura**, **Contrato da tela afetada** e **Checklist de regressão**. Se o pedido contradisser este documento, deve-se esclarecer a decisão antes de alterar o código.

## 1. Objetivo e princípios inegociáveis

O Radar Fundamentalista B3 deve permitir comparar ativos e títulos de forma estável, legível e confiável. A interface não pode mudar de estrutura, semântica ou conteúdo incidentalmente quando uma feature isolada é ajustada.

### 1.1 Invariantes globais

1. **Navegação sempre no topo.** A barra `.tabs-row` aparece uma única vez, imediatamente após `header`, antes de busca, filtros, cards, tabelas e painéis. Ela é fixa/sticky no topo da área de navegação e nunca é duplicada, movida para o rodapé ou renderizada dentro de um painel.
2. **Uma responsabilidade por componente.** Cada modal, card, tabela, gráfico e renderizador possui uma única família de dados e uma única responsabilidade visual.
3. **Uma origem para cada dado visível.** O mesmo campo não pode ser calculado ou montado em mais de um lugar. Renderizadores diferentes reutilizam formatadores e contratos comuns.
4. **Sem vazamento entre domínios.** Ações/FIIs/FIAGROs, Tesouro Direto e Focus possuem estado, texto metodológico, seletores e gráficos independentes.
5. **Nenhuma alteração sem regressão dirigida.** Alterar uma feature exige validar sua tela, seus componentes compartilhados e as telas declaradamente dependentes nesta especificação.
6. **Estado explícito.** Dados da aplicação, aba ativa, filtros, modal aberto e instâncias de gráfico devem ter dono definido; não podem depender de sobras do DOM ou de uma variável temporária de outra feature.
7. **Fato e hipótese nunca se confundem.** Score fundamental e histórico representam dados observados; o Radar Macro representa expectativas condicionais e nunca altera score, indicadores, ranking, filtro ou recomendação.
8. **Cards são exclusivos da Home.** Cards de macro, Top Picks e resumo de cenário existem apenas em `#panel-home`. As abas analíticas usam título, filtros, tabelas, gráficos e detalhes — nunca cópias dos cards da Home.

### 1.2 Regra de coesão e acoplamento

| Unidade | Pode conhecer | Não pode conhecer |
|---|---|---|
| Navegação | IDs das abas e aba ativa | Dados, scores, gráficos ou regras de filtros |
| Top Picks | Contrato resumido de seu ativo e ação de abertura | Metodologia de score ou markup de modal |
| Tabela de ativos | Lista do domínio, filtros e ação de abertura | Estado de Tesouro/Focus ou canvas de modal |
| Modal de renda variável | Um ativo `stock`, `fii` ou `fiagro` e seu histórico | Critérios, textos e estado do Tesouro |
| Modal do Tesouro | Um título do Tesouro e seu histórico | Dados, metodologia ou breakdown de renda variável |
| Modal Focus | Uma série macro e projeções Focus | Ativos, score de ativos ou Tesouro |
| Gerenciador de gráficos | Canvas, dados e opções já preparados pelo dono | Regras de negócio ou decisão de qual modal abrir |

**Proibido:** copiar um bloco de Top Picks para outra tela, reutilizar um modal para outro domínio, preencher um modal por seletor genérico sem validar o tipo, ou usar uma função de score de outro domínio “por conveniência”. Quando houver UI semelhante, reutilize apenas um componente/formatador com contrato explícito; não a lógica de negócio alheia.

## 2. Arquitetura da aplicação e dados

A aplicação é uma SPA estática em `index-v2.html`. Carrega `data.json` no `DOMContentLoaded` por `loadDashboardData()` e guarda a resposta somente em `window.dashboardData` (ou store equivalente único). `generator.py` produz os dados a partir do SQLite.

### 2.1 Domínios de dados

| Domínio | Chave em `data.json` | Consumidores autorizados |
|---|---|---|
| Ações | `stocks`, `unique_sectors`, `sectors_summary` | Home (resumo), Ações, Setores, modal de renda variável |
| FIIs | `fiis` | Home (resumo), FIIs, modal de renda variável |
| FIAGROs | `fiagros` | Home (resumo), FIAGROs, modal de renda variável |
| Renda fixa | `tesouro_direto` | Home (resumo), Renda Fixa, modal do Tesouro |
| Macroeconomia | `macro_state` | Home, Renda Fixa, modal Focus |
| Metadados | `timestamp` | Cabeçalho/rodapé de atualização |

`home` pode conter listas pré-selecionadas, mas nunca deve introduzir formato incompatível com os domínios acima. Todo item de Top Pick deve ser normalizado antes de renderizar.

### 2.2 Contratos de apresentação

* **Score de ativos e Tesouro:** valor numérico de `0` a `10`, exibido com duas casas em Top Picks e conforme a tabela/modal definir. A escala e os thresholds são únicos em `getScoreRangeClass()`.
* **P/VP:** usar somente `pb_ratio` normalizado; `0` é valor válido, portanto não pode ser removido por uma checagem de verdade (`if (pb)`). Quando indisponível, mostrar `—` ou omitir o segmento conforme o contrato do componente.
* **Percentuais:** campos numéricos fracionários são formatados no limite de apresentação (`0.1325` → `13,25%`). O dado bruto nunca é multiplicado duas vezes.
* **Texto e HTML:** nomes, tickers, setores e dados externos devem ser escapados antes de entrar em `innerHTML` ou, preferencialmente, inseridos via `textContent`.

## 3. Casca da aplicação e navegação

### 3.1 Ordem obrigatória do DOM

```text
.app / .container
├── header
├── .tabs-row                    ← única navegação principal
├── .filters-row                 ← contextual; pode ficar oculto
├── #panel-home
├── #panel-stocks
├── #panel-fiis
├── #panel-fiagros
├── #panel-sectors
├── #panel-rendafixa
└── overlays de modal             ← fora dos painéis, ao fim do container/body
```

`.tabs-row` deve usar `position: sticky; top: 0` (ou posição fixa equivalente definida uma vez), `z-index` acima do conteúdo e abaixo dos modais. Em telas pequenas, permanece no mesmo lugar e rola horizontalmente; não é reposicionada para baixo. O `header` não pode ser recriado em mudança de aba.

### 3.2 Abas e painéis

| Aba | Painel | Conteúdo próprio | Dependências compartilhadas permitidas |
|---|---|---|---|
| Home | `#panel-home` | macro e Top Picks | dados normalizados e abertura de modal |
| Ações | `#panel-stocks` | tabela e filtros de ações | filtros globais, modal de renda variável |
| FIIs | `#panel-fiis` | tabela de FIIs | busca e score, modal de renda variável |
| FIAGROs | `#panel-fiagros` | tabela de FIAGROs | busca e score, modal de renda variável |
| Setores | `#panel-sectors` | agregação por setor | dados de ações; modal setorial próprio, se existir |
| Renda Fixa | `#panel-rendafixa` | macro, Tesouro e ETTJ | modal Focus e modal Tesouro |

`switchTab(tabId)` somente pode: validar a aba, trocar o painel visível, atualizar a classe ativa da aba, ajustar a visibilidade dos filtros e iniciar/redimensionar gráficos pertencentes ao painel recém-visível. Não pode renderizar Top Picks, abrir modais ou recalcular scores.

### 3.3 Filtros

* Busca e faixa de score são filtros contextuais às tabelas de ativos e não alteram Top Picks, macro, Tesouro ou Focus.
* Índice e setor existem somente em **Ações**; devem estar ocultos e desabilitados nas demais abas.
* Cada filtro possui fonte, predicado e alvo declarados. `filterTable()` não lê nem altera linhas de tabela que não pertençam à aba ativa.
* Ao trocar de aba, o valor do filtro pode ser preservado para retorno, mas sua aplicação só ocorre no domínio compatível.

### 3.4 Arquitetura de informação e hierarquia de UX

A navegação tem seis escolhas, dentro do limite cognitivo recomendado: **Home, Ações, FIIs, FIAGROs, Setores e Renda Fixa**. Ela é o único ponto de troca de contexto. A interface não deve tentar repetir o painel executivo em cada aba.

```text
Topo permanente
├── Marca, data de atualização, tema e exportação
└── Navegação: Home | Ações | FIIs | FIAGROs | Setores | Renda Fixa

Home — síntese e orientação
├── Cards macro e resumo do cenário-base
└── Top Picks por classe

Abas analíticas — investigação
├── Título da seção + contexto breve
├── Filtros aplicáveis
├── Tabela ou gráfico próprio da classe
└── Detalhe sob demanda no modal
```

O topo permanece `sticky` durante a rolagem, sem salto de layout: `header` e `.tabs-row` formam uma única região de navegação com altura reservada. Em mobile, a mesma região permanece no topo; as abas rolam horizontalmente, sem quebrar em duas linhas e sem ser movidas para a parte inferior.

### 3.5 Regras de apresentação de scores e Radar Macro

| Elemento | Pode mostrar | Rótulo obrigatório | Não pode fazer |
|---|---|---|---|
| Tabela/ranking padrão | `fundamental_score` | `Score fundamental` ou `Score atual` | usar qualquer sinal do Radar Macro como ordenação |
| Histórico do ativo | score e métricas da data observada | data do ponto e “histórico” | recalcular passado com Focus de hoje |
| Radar Macro | sinais, hipóteses, exposições, confiança e contribuições | `Radar macro — expectativa, não fato`, cenário e data Focus | parecer score, fato observado ou recomendação |

Cor nunca pode ser o único sinal: usar texto `Pode favorecer`, `Misto`, `Pode pressionar` e ícone/descrição, além da cor. Em confiança baixa, exibir “Radar indisponível” e quais dados faltam; não mostrar `0` como se fosse neutralidade.

## 4. Contrato visual e de conteúdo por tela

### 4.1 Home

Ordem: indicadores macro → Top Picks. A Home não contém tabela completa, metodologia extensa nem gráfico de detalhe permanente.

#### Cards macro e cenário-base

Exibir Selic Meta, IPCA acumulado em 12 meses e Câmbio Comercial. Cada card contém valor atual, tendência/projeção resumida e ação clara para abrir o modal Focus correspondente. O clique não pode abrir modal de Tesouro nem modal de ativo.

Após os três cards, a Home pode exibir **um único resumo do Radar Macro**, não uma cópia de cards em outras telas. Ele informa: data do Focus, direção esperada de juros, inflação, crescimento, estado da curva, confiança e link “Ver hipóteses e premissas”. Não contém nota, score composto por ativo, ordenação de Top Picks nem linguagem prescritiva como “compre” ou “oportunidade garantida”.

#### Top Picks

Há quatro cards: **Top Ações**, **Top FIIs**, **Top FIAGROs** e **Top Tesouro Direto**. Um item é uma linha clicável com três áreas: identificação, detalhe secundário e score. O score aparece **uma única vez**, exclusivamente em `.home-pick-score`, dentro do próprio card. Nenhum texto de detalhe pode conter `Score`, `score` ou repetir seu valor.

| Card | Identificação | Detalhe permitido (na ordem indicada) | Ação |
|---|---|---|---|
| Top Ações | ticker | `DY xx,xx% · P/VP x,xx` | abre modal de renda variável como `stock` |
| Top FIIs | ticker | `DY xx,xx% · P/VP x,xx` | abre modal de renda variável como `fii` |
| Top FIAGROs | ticker | `DY xx,xx% · P/VP x,xx` | abre modal de renda variável como `fiagro` |
| Top Tesouro | nome do título | `xx,xx% a.a. · vencimento/prazo` | abre exclusivamente o modal do Tesouro |

O **P/VP é obrigatório no Top Ações quando existir em `pb_ratio`**. Se não existir, somente esse segmento é omitido; o score não entra em seu lugar. A mesma função `renderTopPicks(container, normalizedItems)` deve atender toda ocorrência visual de Top Picks; não manter um renderizador paralelo para Home e outro para Renda Fixa.

Top Picks pertencem exclusivamente à Home. Nenhuma aba analítica — inclusive Renda Fixa — pode conter cópia, variação ou “atalho relacionado” desses cards. A navegação para a análise detalhada acontece pela aba no topo ou pelo clique no item da própria Home.

### 4.2 Ações

Apresenta exclusivamente a triagem de ações: título/descrição curta, busca, filtros de índice/setor/score, contador, tabela e exportação contextual. A tabela mostra ticker, nome, badges de índice, P/L, P/VP, DY, ROE, valores de referência e score fundamental conforme os dados disponíveis. O score de uma linha aparece uma vez na coluna de score; não deve ser repetido em outra célula ou texto de ajuda.

P/VP, P/L, DY, ROE, Graham e Bazin são apresentados com o estado semântico definido pelas regras de negócio vigentes; a interface não recalcula nem redefine limites. Abrir uma linha sempre chama o modal de renda variável com tipo `stock`.

### 4.3 FIIs e FIAGROs

Cada aba apresenta somente título/descrição curta, tabela do respectivo domínio, busca e filtro de score. Não exibir filtro de índice/setor de ações nem cards da Home. Abertura de linha chama o modal de renda variável com o tipo correto (`fii` ou `fiagro`), preservando o contrato visual compartilhado, mas usando apenas critérios do domínio selecionado.

### 4.4 Setores

Exibe a agregação de ações por setor — score médio, DY médio, P/L e demais medidas agregadas disponíveis. Não reaproveita score individual como se fosse score setorial. Um eventual detalhe setorial abre apenas `#sector-detail-modal`, sem acessar o modal de ativo nem o modal do Tesouro.

### 4.5 Renda Fixa

Ordem: título/descrição curta → resumo macro textual → curva ETTJ → tabela Tesouro Direto. A aba não renderiza cards da Home, Top Picks ou qualquer variação desses componentes.

* Cards macro abrem somente o modal Focus.
* A curva ETTJ é renderizada somente quando a aba estiver visível e houver dados válidos.
* A tabela do Tesouro mostra título, tipo, taxa, vencimento, score e classificação. Clicar em uma linha abre somente `#td-detail-modal`.
* A metodologia do Tesouro não é conteúdo da tabela, de Top Picks de ações, do modal de ações, nem de qualquer outro modal. Se houver botão “Como calculamos”, ele abre um painel/ajuda de **Renda Fixa** explicitamente nomeado.
* A curva e os textos devem informar quando são aproximação de cenário; não apresentar projeção como taxa negociável.

## 5. Componentes compartilhados

### 5.1 Tabelas

* A primeira coluna identificadora é sticky, opaca e fica acima das células comuns, mas abaixo de menus e modais.
* Ticker: `white-space: nowrap`. Nome: quebra controlada, sem ampliar indevidamente a coluna.
* A rolagem horizontal fica em um único wrapper de tabela. Tooltips não podem ser cortados por esse wrapper.
* Estados obrigatórios: carregando, vazio após filtros, dados indisponíveis e erro de carregamento. Nunca deixar tabela ou gráfico simplesmente em branco.

### 5.2 Score

O componente de score (`ScoreBadge`/`score-pill`) recebe somente `{ score, scale, className }`. Ele não decide critérios, não altera dados e não produz texto explicativo fora de seu próprio elemento. A faixa de cor é única: premium `≥ 8`, bom `≥ 6`, alerta `≥ 4`, risco `< 4`.

`MacroRadar` é componente diferente e recebe `{ signals, hypotheses, exposures, confidence, scenarioName, asOf, sources }`. Ele só é renderizado no detalhe do ativo ou em uma visão explícita de hipóteses; nunca dentro de `.home-pick-detail`, do badge de ranking padrão ou como substituto de `ScoreBadge`.

### 5.3 Tooltips, botões e acessibilidade

Tooltips são anexados ao `body` e posicionados por `getBoundingClientRect()`, para não serem cortados por `overflow`. Todo item clicável possui nome acessível, foco visível, ativação por teclado e alvo de toque mínimo de 44 px em dispositivos touch. Modal fecha por botão, `Escape` e clique no backdrop; foco retorna ao elemento que o abriu.

## 6. Modais: contratos totalmente isolados

Todos os modais ficam fora dos painéis e possuem identificador, estado, dados e ciclo de vida próprios. Abrir um modal deve fechar ou limpar somente seu próprio estado; o fechamento não pode destruir gráfico, dados ou elementos de outro modal.

| Modal | ID | Entrada válida | Conteúdo permitido | Gráfico permitido |
|---|---|---|---|---|
| Ativo | `#detail-modal` | ativo + tipo `stock`/`fii`/`fiagro` | fundamentais, score breakdown e metodologia do ativo | histórico do ativo |
| Tesouro | `#td-detail-modal` | um título de `tesouro_direto` | taxa, PU, vencimento e score breakdown do Tesouro | taxa, PU ou score histórico do título |
| Focus | `#focus-detail-modal` | indicador macro | série realizada e projeções Focus | tendência do indicador macro |
| Setor | `#sector-detail-modal` | setor agregado | métricas e composição setorial | somente gráfico setorial, se existir |

### 6.1 Modal de ativo — `#detail-modal`

Aceita apenas ações, FIIs e FIAGROs. A metodologia, os labels do breakdown, os comparativos e as séries vêm do tipo recebido. **É proibido** exibir “Scorecard de Renda Fixa”, critérios de prêmio real, alíquota de IR, indexador ou qualquer texto do Tesouro neste modal. O select de indicador contém somente séries que existam para o ativo; opções sem dado devem ficar desabilitadas ou exibir estado indisponível.

Após o scorecard fundamental e antes do gráfico, pode haver uma seção recolhível **“Radar macro — hipóteses futuras”**. A ordem obrigatória é: score fundamental atual → cenário Base → cenário Adverso → cenário Favorável. Cada cenário mostra até três itens no formato “sinal → hipótese condicional → exposição do ativo”, além de confiança, data do Focus e fontes. Não mostra nota, ajuste de score ou score composto; o score histórico fica em gráfico separado e não é alterado. A seção inicia recolhida para preservar foco na análise fundamental e reduzir carga cognitiva.

### 6.2 Modal do Tesouro — `#td-detail-modal`

Aceita somente item de `tesouro_direto`. É o único local de detalhe que pode exibir score e metodologia de renda fixa: prêmio real, prazo, IR, proteção inflacionária, liquidez ou demais critérios oficiais. Nunca recebe ticker de ação/FII/FIAGRO e nunca reaproveita `score_breakdown` de renda variável.

O Radar do título apresenta sua sensibilidade de duration e a taxa/curva relevante. A mensagem deve dizer “hipótese de cenário” e distinguir claramente taxa contratada, taxa de mercado atual e projeção Focus, sem mudar o score do título.

### 6.3 Modal Focus — `#focus-detail-modal`

Exibe histórico realizado e projeção Focus do indicador selecionado, com linhas visualmente distintas. Não contém score de ativos ou Tesouro, nem usa o estado de gráficos de outro modal.

## 7. Gráficos: contrato contra canvas em branco

Cada gráfico possui uma chave de propriedade única: `assetDetailChart`, `treasuryDetailChart`, `focusDetailChart`, `ettjChart` ou equivalente. Não usar uma instância genérica que possa ser reutilizada por dois domínios.

### 7.1 Ciclo obrigatório

1. Validar dados: labels e valores finitos, com ao menos dois pontos para linha histórica.
2. Tornar painel/modal visível.
3. Aguardar `requestAnimationFrame()`; confirmar `canvas.isConnected`, `offsetWidth > 0` e `offsetHeight > 0`.
4. Destruir apenas a instância pertencente à mesma chave, se existir.
5. Criar o Chart.js com o canvas visível.
6. Em troca de indicador/período, repetir da etapa 1; não criar uma segunda instância sobre o mesmo canvas.
7. Em fechamento do modal ou desmontagem do painel, destruir a instância do dono e atribuir `null`.

### 7.2 Estados de gráfico

| Condição | Resultado obrigatório |
|---|---|
| Dados válidos | gráfico renderizado e responsivo |
| Sem histórico suficiente | mensagem no container: “Histórico ainda indisponível para este indicador.” |
| Dados inválidos/erro | mensagem de erro recuperável e opção de tentar novamente, quando aplicável |
| Painel oculto | não instanciar Chart.js |
| Tema alterado | recriar apenas gráficos visíveis, após destruir a instância correspondente |

Um canvas em branco é defeito: não pode ser tratado como estado vazio. Antes de concluir uma alteração que toque gráficos, verificar visualmente cada gráfico afetado em tema claro e escuro.

## 8. Tema, responsividade e exportação

Tema claro/escuro usa tokens CSS centralizados e persiste em `localStorage` com a chave `theme`. A troca de tema não pode mover navegação, modificar filtros, alterar a aba ativa ou mudar conteúdo de cards; apenas atualiza tokens e gráficos visíveis.

No mobile: a navegação continua no topo com rolagem horizontal, tabelas permanecem roláveis dentro do wrapper e modais ocupam a largura útil sem cortar controles. Nenhum recurso essencial deve depender apenas de hover.

Exportação é contextual à aba ativa. CSV usa linhas visíveis da tabela ativa; JSON exporta a fonte de dados; PDF aplica alterações temporárias e deve sempre restaurar classes, largura, overflow, cabeçalho temporário e posição de rolagem, inclusive em erro.

## 9. Protocolo obrigatório para mudanças futuras

### 9.1 Antes de editar

1. Identificar o recurso solicitado e seu dono na tabela de coesão.
2. Listar os contratos desta seção e as telas dependentes.
3. Inspecionar se já há componente/formatador equivalente. Reutilizar o contrato; não duplicar renderização.
4. Declarar o escopo de alteração. Qualquer mudança em outro domínio exige justificativa explícita e validação extra.

### 9.2 Durante a edição

* Alterar somente o módulo, selector e estado do recurso dono.
* Manter markup estrutural da casca, sobretudo a posição única de `.tabs-row`.
* Não editar texto de metodologia de outro domínio.
* Não ampliar seletores CSS/JS globais se um seletor do componente resolve o caso.
* Para um novo recurso, registrar aqui: dono, dados aceitos, estados, ações permitidas, dependências e critérios de aceitação antes de codificar.

### 9.3 Após a edição: matriz mínima de regressão

| Mudança em | Validar obrigatoriamente |
|---|---|
| Top Picks | Home, qualquer atalho aprovado, P/VP de Ações, score único no card, abertura correta dos quatro tipos |
| Navegação/layout | desktop e mobile; todas as abas; menu uma vez e sempre no topo |
| Modal de ativo | Ação, FII e FIAGRO; metodologia sem Tesouro; gráfico e fechamento |
| Modal Tesouro | tabela e Top Tesouro; metodologia somente do Tesouro; gráfico e fechamento |
| Focus/ETTJ | Home, Renda Fixa, estado sem dados, claro/escuro |
| Score/formatadores | Top Picks, tabelas e modais dos domínios afetados |
| Tema/exportação | aba ativa preservada, gráficos visíveis, restauração de estilos |

## 10. Checklist de aceite para IA e desenvolvimento

Marcar todos os itens antes de entregar uma alteração de UI.

### Estrutura e isolamento

- [ ] `.tabs-row` existe uma única vez, está após `header` e antes de filtros/painéis, inclusive no mobile.
- [ ] A mudança está limitada ao dono do recurso; nenhum modal, tela ou domínio não relacionado foi alterado sem motivo documentado.
- [ ] Não há novo renderizador duplicado para a mesma informação.
- [ ] Dados de Ações/FIIs/FIAGROs, Tesouro e Focus não foram cruzados fora dos consumidores autorizados.
- [ ] Cards macro, Top Picks e resumo de cenário estão somente na Home; abas analíticas não os duplicam.

### Conteúdo e score

- [ ] Top Ações mostra DY e P/VP (sem setor); não mostra score no detalhe.
- [ ] Top FIIs/FIAGROs mostram DY e P/VP quando disponível; não mostram score no detalhe.
- [ ] Todo item de Top Pick mostra score somente uma vez, em `.home-pick-score` dentro de seu card.
- [ ] P/VP `0` e campos ausentes são tratados corretamente, sem falsos ocultamentos ou `undefined`.
- [ ] Score aparece apenas no local previsto de cada componente, sem duplicação em cards, tabelas ou textos auxiliares.
- [ ] Score fundamental e histórico permanecem separados do Radar Macro, que contém data, fonte e confiança quando aplicável.
- [ ] Ranking padrão continua ordenado por score fundamental; o Radar Macro não altera score, indicadores, filtros, Top Picks, ranking ou recomendação.

### Modais e gráficos

- [ ] O modal de ativo não exibe metodologia ou critérios do Tesouro.
- [ ] O modal do Tesouro não exibe dados/metodologia de renda variável.
- [ ] Cada abertura de modal usa dados do tipo validado e limpa o estado anterior do próprio modal.
- [ ] Todo gráfico é criado somente com canvas visível, dados válidos e após `requestAnimationFrame()`.
- [ ] Instâncias Chart.js são destruídas na atualização/fechamento do respectivo dono; não há canvas em branco.
- [ ] Estados de histórico ausente e erro exibem mensagem clara.

### Experiência e qualidade

- [ ] Busca, filtros, exportação e teclado continuam funcionando na tela afetada.
- [ ] Tema claro/escuro e viewport mobile foram verificados quando a mudança toca layout ou gráficos.
- [ ] Sem erros no console, sem `undefined` visível e sem sobreposição/corte de conteúdo.
- [ ] A evidência de validação informa quais telas e cenários da matriz foram exercitados.

---

Esta especificação prevalece sobre conveniência de implementação. Se uma mudança aparentemente pequena exigir copiar UI, compartilhar estado entre domínios ou alterar uma tela não relacionada, a implementação deve ser redesenhada até respeitar alta coesão, baixo acoplamento e os contratos acima.
