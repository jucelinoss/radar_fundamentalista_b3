# Especificação de Testes e Qualidade de Dados

> **Status:** contrato obrigatório de qualidade.
>
> Toda feature nova ou alterada deve ter **no mínimo um teste unitário novo ou ajustado** que prove seu comportamento. Para informação financeira, uma mudança só está pronta quando as regras, dados gerados e conteúdo visível na UI passam pelos testes aplicáveis desta especificação.

## 1. Objetivo e documentos relacionados

Esta especificação define como validar cálculo, coleta, persistência, geração de `data.json` e conteúdo da interface. As regras testadas pertencem a [ANALYSIS_RULES_SPECIFICATION.md](ANALYSIS_RULES_SPECIFICATION.md); os contratos de apresentação pertencem a [UI_UX_SPECIFICATION.md](UI_UX_SPECIFICATION.md).

O propósito é impedir que:

* uma fonte externa entregue dado inválido e ele chegue ao usuário;
* um score não corresponda ao breakdown ou ao banco;
* uma alteração de UI misture metodologias ou duplique valores;
* uma correção local gere regressão em outra tela;
* uma feature seja entregue sem evidência automatizada de comportamento.

## 2. Política inegociável de testes

1. **Feature sem teste não está concluída.** Toda nova regra, função, fonte, transformação, componente, fluxo ou correção de bug exige pelo menos um teste unitário determinístico.
2. **Bug corrigido exige teste de regressão.** O teste deve falhar no comportamento defeituoso e passar com a correção.
3. **Dados financeiros falham com segurança.** Dado obrigatório inválido, fora da faixa ou sem proveniência não pode ser silenciosamente transformado em cotação/conclusão válida.
4. **Rede nunca é requisito para teste unitário.** APIs, relógio e arquivos externos devem ser mockados/isolados. Testes de integração de rede são separados e marcados como `network`.
5. **Não reduzir cobertura para “fazer passar”.** Excluir, pular ou relaxar teste existente requer justificativa documentada e aprovação explícita.
6. **O código e o teste viajam juntos.** Não aceitar PR/entrega que modifique `src/`, `index-v2.html` ou regras sem incluir os testes pertinentes.

## 3. Pirâmide e organização

| Nível | Objetivo | Ferramenta/local | Quando é obrigatório |
|---|---|---|---|
| Unitário | fórmula, normalização, estado e renderizador isolado | `pytest` em `src/tests/`; testes JS determinísticos quando extraídos | toda feature/correção |
| Contrato de dados | schema, faixas, proveniência, consistência DB → `data.json` | `pytest` em `src/tests/` | toda mudança de fonte, schema ou gerador |
| Integração | módulos, SQLite, geração e fallback | `pytest`, banco/arquivos temporários | pipeline, persistência, gerador, fontes |
| UI de contrato | DOM, conteúdo e isolamento entre telas/modais | teste estático + Playwright quando houver automação | toda mudança de UI |
| E2E | fluxos críticos no navegador | Playwright | mudanças de navegação, modal, gráfico, tema, exportação |
| Rede | disponibilidade/contrato real de fornecedores | `pytest -m network --run-network` | mudança de integração externa e execução programada |

### 3.1 Estrutura recomendada

```text
src/tests/
├── test_analyzer.py                 # Ações, FIIs e FIAGROs
├── test_tesouro_analyzer.py         # Score do Tesouro
├── test_macro_fetcher.py            # Macro, Focus, Tesouro e cache
├── test_sources.py                  # Adaptadores e fallbacks mockados
├── test_data_ranges.py               # Qualidade do banco/dados gerados
├── test_score_consistency.py         # DB, data.json, Top Picks e histórico
├── test_pipeline_integration.py      # SQLite, pipeline e generator
└── ui/                               # testes de contrato/UI, quando adicionados
    ├── test_ui_static_contract.py
    └── radar-ui.spec.ts              # Playwright, se configurado
```

Não usar dados reais mutáveis como fixture de teste unitário. Criar builders/fixtures mínimos, versionados e nomeados por cenário.

## 4. Critérios mínimos por tipo de mudança

| Alteração | Teste unitário mínimo | Validações adicionais |
|---|---|---|
| Fórmula ou threshold de score | piso, ponto intermediário, teto, `None`/inválido | breakdown soma o score; score entre 0 e 10 |
| Nova métrica financeira | cálculo com dados válidos e ausência/valor inválido | unidade, arredondamento e provenance |
| Nova fonte/fallback | resposta válida, erro HTTP, payload parcial e fallback | integração de rede marcada `network` |
| Schema/`data.json` | campos obrigatórios e tipos | DB → JSON, Top Picks → lista principal |
| Feature de UI | contrato de conteúdo/DOM isolado | fluxo E2E quando houver clique, modal, gráfico ou tema |
| Correção de bug | caso reproduzindo o defeito | cenário vizinho para não criar regressão |
| Gráfico | dados válidos, sem dados e recriação da instância | browser: canvas visível, modal/painel e claro/escuro |

## 5. Testes de regras de negócio e qualidade financeira

### 5.1 Regras de score

Cada critério de Ações, FIIs, FIAGROs e Tesouro deve ter testes para:

* valor no piso, imediatamente abaixo e imediatamente acima;
* ponto intermediário esperado;
* teto e valor acima do teto;
* ausência, `NaN`, infinito, string inválida e percentual em formato decimal/percentual quando aplicável;
* soma do score e campos de `score_breakdown`;
* classificação Premium/Bom/Regular/Alto risco nos limites `8`, `6` e `4`.

Para regras dinâmicas dependentes de Selic/Focus, o teste injeta estado macro controlado; não pode depender de `data/macro_state.json` real, data atual ou rede.

### 5.2 Sanidade do dado gerado

Após ingestão ou geração, validar banco e `data.json`:

| Campo | Critério mínimo de aceite |
|---|---|
| Identificação | ticker/nome não vazio e tipo de ativo compatível |
| Preço e valor patrimonial | finitos; preço positivo quando o ativo está ativo; ausência explícita quando indisponível |
| DY | decimal normalizado; dentro dos limites de sanidade do domínio |
| P/L, P/VP, ROE | número finito ou ausência explícita; não converter erro de fonte em zero econômico |
| Graham/Bazin | não negativos; fórmula consistente quando as entradas existirem |
| Score | finito, `0 ≤ score ≤ 10`, com breakdown do mesmo domínio |
| Histórico | datas parseáveis, sem duplicatas indevidas, ordenado; valores finitos |
| Fonte/atualização | data de coleta disponível; cache, estimativa ou demonstração identificados |
| Macro | chaves obrigatórias, Focus com lacunas explícitas, nunca expectativa sintética |
| Tesouro | título, tipo, vencimento/prazo e taxa normalizados; histórico real separado de demonstração |

Falha crítica: score fora da faixa, JSON inválido, título/ativo sem identificação, campo financeiro não finito, mismatch entre DB e JSON ou dado de demonstração apresentado como real. Essas falhas bloqueiam a publicação de `data.json`.

### 5.3 Consistência entre camadas

Testar explicitamente:

1. `score_v2` persistido no banco é o score publicado em `data.json`, inclusive quando é `0.0`.
2. `score_breakdown` soma o total publicado dentro da precisão definida.
3. Top Picks referenciam item existente na lista principal e possuem o mesmo score/ticker ou título.
4. Histórico não usa cotação ajustada por dividendos quando a regra exigir cotação histórica seca.
5. Dados de Ações, FIIs, FIAGROs e Tesouro não são cruzados por fallback ou renderização.
6. `macro_state` e títulos de Tesouro publicados pertencem à mesma execução/versão de coleta, ou declaram claramente suas datas independentes.

## 6. Testes de conteúdo e contrato da UI

Como a UI atual é HTML/CSS/JavaScript no mesmo arquivo, iniciar por testes estáticos de contrato; para comportamento real, configurar Playwright. Não considerar inspeção manual como substituta de teste automatizado.

### 6.1 Contratos estáticos obrigatórios

`test_ui_static_contract.py` (ou equivalente) deve ler `index-v2.html` e validar ao menos:

* existe exatamente uma `.tabs-row` e ela vem depois de `header` e antes de `.filters-row`/painéis;
* existem os painéis e modais previstos na especificação, com IDs únicos;
* não há bloco de metodologia do Tesouro dentro de `#detail-modal`;
* `#td-detail-modal` possui apenas elementos de detalhe do Tesouro;
* renderização de Top Picks usa um único ponto de entrada compartilhado, sem duplicação de template;
* Top Ações inclui P/VP quando disponível; score é emitido somente em `.home-pick-score`;
* cada gráfico possui chave/instância própria e rotina de destruição;
* strings `Score` não são concatenadas em `.home-pick-detail`.

### 6.2 Cenários de navegador obrigatórios

| Cenário | Asserções |
|---|---|
| Home/Top Ações | P/VP visível quando presente; um único score por item; clique abre ativo, não Tesouro |
| Top Tesouro | taxa/prazo visíveis; clique abre somente modal Tesouro |
| Modal de ativo | critérios de renda variável; ausência de texto/metodologia de Tesouro; gráfico ou estado “indisponível” |
| Modal Tesouro | cinco critérios do Tesouro; ausência de campos/metodologia de ações; gráfico ou estado “indisponível” |
| Navegação | menu no topo, uma vez, em desktop e viewport mobile; troca de aba não o move |
| Gráficos | canvas tem dimensões depois de abrir modal/painel; troca de período não cria canvas/instância duplicada; sem dados mostra mensagem |
| Tema | troca claro/escuro preserva aba, filtros e conteúdo; gráficos visíveis são recriados |
| Filtros | afetam somente tabela do domínio/aba ativa; não modificam Top Picks ou Tesouro |

Para evitar dependência da rede, o E2E deve servir `index-v2.html` com fixture de `data.json` controlada que contenha ao menos uma ação, FII, FIAGRO, título e dados macro.

## 7. Dados de teste, mocks e rastreabilidade

* Fixtures devem ser pequenas, realistas e sem informações pessoais/sigilosas.
* Todo fixture financeiro deve indicar unidade (decimal, percentual, reais, dias) e cenário econômico representado.
* Mockar chamadas HTTP, data/hora, cache e filesystem em testes unitários.
* Testes de rede usam dados reais, nunca valores exatos que variam diariamente; validar schema, finitude, tipo e presença de campos.
* Ao registrar um incidente de fonte, adicionar fixture do payload defeituoso e teste que impeça sua regressão.

## 8. Comandos e gates de entrega

### 8.1 Execução local mínima

```powershell
python -m pytest src/tests/ -v -m "not network"
python -m pytest src/tests/test_analyzer.py src/tests/test_tesouro_analyzer.py src/tests/test_macro_fetcher.py -v
python -m pytest src/tests/test_data_ranges.py src/tests/test_score_consistency.py -v
```

Executar teste de rede somente com autorização/conectividade:

```powershell
python -m pytest src/tests/test_integration_sources.py -v --run-network
```

Quando o conjunto de UI for configurado:

```powershell
python -m pytest src/tests/ui/test_ui_static_contract.py -v
npx playwright test
```

### 8.2 Gate obrigatório antes de concluir

- [ ] Pelo menos um teste unitário foi criado/alterado para cada feature ou bug tratado.
- [ ] Testes unitários relevantes passam sem rede.
- [ ] Testes de qualidade de dados e consistência DB → JSON passam quando a mudança toca dados/pipeline.
- [ ] Teste de contrato/UI e E2E relevante passam quando a mudança toca a interface.
- [ ] Nenhum teste foi removido, pulado ou enfraquecido sem justificativa.
- [ ] A documentação de análise/UI foi revisada quando seu contrato mudou.
- [ ] A entrega informa comandos executados, resultado, testes não executados e motivo.

## 9. Definição de pronto

Uma feature está pronta somente se código, teste, documentação e evidência de execução estiverem presentes. Para dados financeiros, “aparentemente correto” não é critério de aceite: a qualidade precisa ser reproduzível, automatizada e rastreável até a fonte e a regra aplicada.
