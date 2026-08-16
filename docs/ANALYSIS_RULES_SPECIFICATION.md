# Especificação de Regras de Análise e Dados

> **Status:** fonte de verdade das regras de negócio do Radar Fundamentalista B3.
>
> Este documento define **o que** é coletado, **de onde**, **como** é normalizado e **como** é analisado. Não define layout, componentes, modais ou comportamento visual: esses contratos pertencem a [UI_UX_SPECIFICATION.md](UI_UX_SPECIFICATION.md).

## 1. Escopo, responsabilidade e hierarquia

O Radar classifica ações, FIIs, FIAGROs, títulos do Tesouro Direto e o cenário macroeconômico. O score é um instrumento quantitativo de triagem e comparação, não uma recomendação individual de investimento nem promessa de rentabilidade.

| Assunto | Documento dono | Implementação de referência |
|---|---|---|
| Dados, fórmulas, critérios, scores e fontes | este documento | `src/analyzer.py`, `src/tesouro_analyzer.py`, `src/macro_fetcher.py`, `src/sources.py` |
| Estrutura de telas, cards, tabelas, modais e gráficos | [UI_UX_SPECIFICATION.md](UI_UX_SPECIFICATION.md) | `index-v2.html` |
| Pipeline e componentes do sistema | [ARCHITECTURE.md](ARCHITECTURE.md) | `src/pipeline.py`, `src/generator.py` |

Em caso de conflito, a implementação testada prevalece até que código e documentação sejam corrigidos na mesma mudança. Não duplicar fórmulas de negócio no documento de UI.

## 2. Governança de dados

### 2.1 Fontes autorizadas e prioridade

| Domínio | Fonte primária | Uso | Fallback e regra |
|---|---|---|---|
| Ações, FIIs e FIAGROs | Yahoo Finance via `yfinance` | preços, fundamentos, proventos, histórico e metadados | `brapi.dev`, quando configurada/disponível; registrar indisponibilidade, nunca inventar dados |
| Selic Over | Banco Central do Brasil — SGS série 11 | taxa efetiva corrente | último cache válido; se não houver, fallback técnico explícito de 14% somente para manter o cálculo operacional |
| Selic Meta | Banco Central do Brasil — SGS série 432 | meta definida pelo Copom e histórico | cache; estimativa técnica somente quando a API e o cache falharem, marcada como estimada |
| Focus | Banco Central do Brasil — Expectativas de Mercado (OData) | medianas anuais de IPCA, Selic, câmbio e PIB | lacuna explícita quando indisponível; não criar expectativas sintéticas |
| IPCA realizado | IBGE/SIDRA | IPCA em 12 meses e acumulado no ano | último cache válido |
| Câmbio realizado | Banco Central do Brasil — SGS série 1 | PTAX/dólar de venda histórico | último cache válido |
| Tesouro Direto | Tesouro Transparente (CSV oficial de preço e taxa) | títulos, taxas, preços e histórico | endpoints públicos do Tesouro Direto; por último, dados de demonstração identificáveis e nunca apresentados como cotação corrente |
| Curva ETTJ | Selic atual + Focus | aproximação de vértices 1, 3, 5 e 10 anos | não chamar de curva de mercado/intraday; para isso seria necessária fonte B3/broker licenciada |

As URLs, credenciais e detalhes de transporte ficam no código. A fonte apresentada à pessoa usuária deve indicar nome, data/hora de coleta e, quando aplicável, se é estimativa, cache ou demonstração.

### 2.2 Qualidade, normalização e indisponibilidade

1. Todo número é convertido para valor finito antes do cálculo. `NaN`, infinito, texto inválido e ausência viram `None`, não zero silencioso.
2. Percentuais são normalizados para decimal interno: `9,48%` → `0,0948`. A camada de apresentação é a única que converte novamente para percentuais legíveis.
3. Dividend yield usa, preferencialmente, dividendos efetivamente distribuídos nos últimos 365 dias divididos pelo preço atual; o campo estático do provedor é fallback.
4. Limites de sanidade bloqueiam valores evidentemente corrompidos: DY máximo de 30% para ações/FIAGROs, 25% para FIIs, DY médio de três anos máximo de 50% e dividendos por cota até R$ 100. O evento deve ser registrado.
5. Dado ausente zera somente o critério que depende dele, salvo critério cuja regra determine nota neutra. Não preencher lacunas com média, último valor ou dado de outro ativo.
6. Cache macro tem TTL de 24 horas. Histórico macro usa o último cache válido se a fonte falhar; expectativas Focus sem fonte permanecem vazias.

### 2.3 Saída mínima por domínio

Cada ativo/título entregue a `data.json` deve conter identificador, data de atualização, valores brutos normalizados, score total e `score_breakdown`. O breakdown deve declarar `label`, `score`, `max`, `desc` e `tip`, todos do mesmo domínio do registro.

## 3. Convenções comuns de score

* Escala oficial: **0,00 a 10,00**, duas casas decimais, sem arredondar critérios antes do cálculo final além do previsto no motor.
* Faixas de classificação: Premium `≥ 8`, Bom `≥ 6 e < 8`, Regular `≥ 4 e < 6`, Alto risco `< 4`.
* Score alto ordena a triagem; não substitui análise de liquidez, governança, concentração, risco de crédito, tributação individual ou adequação ao prazo do investidor.
* Todas as fórmulas aplicam limite (`clamp`) na faixa de seu critério. A soma não pode exceder 10.

## 4. Análise de ações

### 4.1 Entradas e medidas auxiliares

| Medida | Definição usada |
|---|---|
| DY médio de 3 anos | média anual de dividendos/proventos sobre o preço atual, calculada da série disponível |
| P/L médio de 5 anos | preço atual dividido pela média de LPA/resultado do período disponível |
| P/VP | preço por ação dividido pelo valor patrimonial por ação |
| ROE | retorno sobre patrimônio líquido corrente |
| Preço Graham | `√(22,5 × LPA × VPA)`; inaplicável para LPA ou VPA não positivos |
| Preço Bazin | dividendos anuais por ação divididos por 6%; indicador de apoio, não critério atual do score contínuo |
| PEG | usado somente para setores de tecnologia/serviços de comunicação, quando disponível |

### 4.2 Score-base: cinco critérios contínuos de até 2 pontos (v2.6 Gaussiano / Sigmoide)

A partir da versão v2.6, o Radar Fundamentalista B3 adota uma modelagem contínua baseada em **Distribuições Gaussianas Assimétricas (*Split Normal*)** e **Curvas Sigmoides Logísticas**, eliminando degraus artificiais e efeitos penhasco (*cliff edges*) onde pequenas variações de centavos causavam perdas de até 2,0 pontos:

* **Função Gaussiana Assimétrica:**
  $$\text{Score}_{\text{gauss}}(x; \mu, \sigma_{\text{esq}}, \sigma_{\text{dir}}) = 2,0 \cdot \exp\left( - \frac{(x - \mu)^2}{2 \sigma^2} \right), \quad \text{onde } \sigma = \begin{cases} \sigma_{\text{esq}}, & \text{se } x < \mu \\ \sigma_{\text{dir}}, & \text{se } x \ge \mu \end{cases}$$
* **Função Sigmoide Logística:**
  $$\text{Score}_{\text{sigm}}(x; x_0, k) = \frac{2,0}{1 + \exp\left(-k \cdot (x - x_0)\right)}$$

| Critério | Função / Parâmetros | Racional e Literatura de Apoio |
|---|---|---|
| **DY médio 3 anos** | Gaussiana Assimétrica<br>Centro $\mu = \max(9,5\%, \text{meta} + 1,5\%)$<br>$\sigma_{\text{esq}} = 3,5\%$, $\sigma_{\text{dir}} = 5,5\%$ | **Décio Bazin / Luiz Barsi:** Piso a partir de 6,0% líquido. Sweet spot em 9,5%–12,0%. Decai suavemente após 16% para conter o risco de *Dividend Traps* (distribuição atípica ou queima de caixa). |
| **P/L médio 5 anos** | Gaussiana Assimétrica<br>Centro $\mu = \min(6,5; \text{teto} \times 0,8)$<br>$\sigma_{\text{esq}} = 2,0$, $\sigma_{\text{dir}} = 4,0$ | **Alexandre Póvoa / Benjamin Graham:** Centro em 6,5x (múltiplo histórico de valor da B3). Penaliza tanto múltiplos esticados (> 15x) quanto picos de lucros atípicos/cíclicos (< 3,5x). |
| **P/VP (Preço / V.P.)** | Gaussiana Assimétrica<br>Centro $\mu = 0,80$<br>$\sigma_{\text{esq}} = 0,25$, $\sigma_{\text{dir}} = 0,45$ | **Benjamin Graham / Luiz Barsi:** Centro em 0,80 (*Deep Value* com margem de segurança). Transição contínua sem cortes abruptos: 0,40 → 0,55 pts; 0,65–0,95 → 1,85–2,00 pts; 1,20 → 1,35 pts. |
| **ROE** | Sigmoide Logística<br>Inflexão $x_0 = 12,0\%$, $k = 22,0$ | **Aswath Damodaran / José Roberto Securato:** Ponto de inflexão em 12% (custo de oportunidade de capital no Brasil). Satura assintoticamente até 2,0 pts para ROEs elevados (> 20%). |
| **Margem de Segurança** | Sigmoide Logística<br>Margem $= (\text{Justo} - \text{Preço}) / \text{Preço}$<br>Inflexão $x_0 = 0,0$, $k = 4,0$ | **Benjamin Graham / Peter Lynch:** No preço justo de Graham: 1,0 pt. Margens amplas de desconto (+50%) convergem para 1,96 pts. Para Tech/Comunicação, aplica $1 - \text{PEG}$. |

### 4.2.1 Fundamentação Teórica e Literatura de Referência

O modelo quantitativo do Radar Fundamentalista B3 é construído sobre o cruzamento de referências internacionais e nacionais consagradas:

1. **Benjamin Graham & David Dodd (*Security Analysis*, 1934 e *The Intelligent Investor*, 1949):**
   * *Margem de Segurança:* Preço Justo de Graham $V = \sqrt{22,5 \times \text{LPA} \times \text{VPA}}$.
   * Teto combinado de múltiplos: $\text{P/L} \times \text{P/VP} \le 22,5$.
2. **Décio Bazin (*Faça Fortuna com Ações*, 1992):**
   * Exigência de Yield mínimo de 6% ao ano em dinheiro e $\text{Preço Teto} = \text{Dividendo Médio} / 0,06$.
   * Eliminação de empresas excessivamente endividadas e foco em dividendos semestrais consistentes.
3. **Luiz Barsi Filho (*O Rei dos Dividendos*, 2022):**
   * Filosofia BESST e acumulação em ações de valor com $\text{P/VP} \le 0,80$ e dividendos perenes.
4. **Alexandre Póvoa (*Valuation: Como Avaliar Empresas e Escolher as Melhores Ações*):**
   * Desconto estrutural da bolsa brasileira: P/L médio histórico entre 6,0x e 8,5x.
   * ROE exigido acima do custo de capital próprio ($K_e > 14\%$) para criação real de valor.
5. **Prof. Aswath Damodaran (*Investment Valuation*, NYU Stern):**
   * Teoria de que $\text{P/VP} = (\text{ROE} - g) / (K_e - g)$. O desconto de P/VP só é atrativo se acompanhado de ROE saudável; caso contrário, é uma armadilha de valor (*Value Trap*).
6. **Prof. Arthur Vieira de Moraes (*Fundos de Investimento Imobiliário*, B3 Educação):**
   * Distinção fundamental entre FII de Tijolo (Cap Rate vs NTN-B, P/VP 0,85–0,95) e FII de Papel (marcação a mercado de CRIs, onde P/VP < 0,80 reflete risco de calote e não pechincha).
7. **Joel Greenblatt (*The Little Book That Still Beats the Market*, 2005):**
   * *Magic Formula:* Combinação balanceada de barganha (baixo múltiplo) e alta eficiência de capital (alto ROE/ROIC).
8. **Howard Marks (*The Most Important Thing*, 2011):**
   * Assimetria do risco de crédito: em títulos de dívida (CRIs/CRAs), o ganho é limitado ao cupom e a perda pode ser de 100%, justificando travas estritas de P/VP e DY em FIIs e FIAGROs.

### 4.3 Solvência e regra macro legada

Após a soma do score-base, a implementação atual aplica somente às ações:

* liquidez corrente `< 1,0`: `−1,50` ponto;
* cobertura de juros (`EBIT / despesa financeira`) `< 1,0`: `−1,00` ponto.

O indicador Dívida Líquida/EBITDA é suporte informativo; alvo visual de referência `≤ 3x`, sem peso direto no score.

> **Regra legada — não usar em nova implementação:** a implementação v3 também adiciona `+0,50` quando o DY médio supera a Selic. Essa regra deve ser retirada na migração para a camada de cenários do capítulo 9. Ela não mede Equity Risk Premium (ERP): DY é apenas renda distribuída, pode subir porque o preço caiu ou porque o payout é insustentável, e já é componente do score-base. Enquanto o código ainda a contiver, o breakdown deve identificá-la como `legada` e nunca chamá-la de ERP positivo.

## 5. Análise de FIIs (v2.6 Gaussiano / Sigmoide)

FIIs utilizam três critérios contínuos calibrados para somar 10 pontos. O modelo equilibra desconto patrimonial, sustentabilidade de renda e estabilidade semestral de proventos através de distribuições Gaussianas e Sigmoides:

| Critério | Peso máximo | Função / Parâmetros | Regra e Racional |
|---|---:|---|---|
| **P/VP (Valor Patrimonial)** | 3,5 | Gaussiana Assimétrica<br>Centro $\mu = 0,95$<br>$\sigma_{\text{esq}} = 0,18$, $\sigma_{\text{dir}} = 0,14$ | *Sweet Spot* em 0,95 (leve desconto com margem de segurança). Elimina degraus em 0,60 e 0,70: 0,60 → 0,53 pts (distress severo); 0,80 → 2,47 pts; 0,95 → 3,50 pts; 1,05 → 2,71 pts; 1,15 → 1,25 pts. |
| **Dividend Yield** | 4,0 | Gaussiana Assimétrica<br>Centro $\mu = 11,5\%$ (0,115)<br>$\sigma_{\text{esq}} = 2,5\%$, $\sigma_{\text{dir}} = 3,5\%$ | Sweet spot em 10,5%–12,5% (renda perene). Sobe suavemente a partir de 6,5% e decai suavemente acima de 15,5% para conter o risco de *Yield Traps* e queima de patrimônio. |
| **Consistência de Proventos** | 2,5 | Sigmoide Logística<br>Inflexão $x_0 = 85,0\%$, $k = 15,0$ | Compara a renda dos últimos 6 meses com o semestre anterior. Fundos com retenção $\ge 95\%$ atingem 2,26–2,50 pts. Quedas severas (< 70%) derrubam a nota suavemente. Sem histórico: 1,5 pts neutro. |

## 6. Análise de FIAGROs (v2.6 Gaussiano / Sigmoide)

FIAGROs compartilham a estrutura contínua dos FIIs, calibrada com o prêmio de risco de crédito do agronegócio:

| Critério | Peso máximo | Função / Parâmetros | Regra e Racional |
|---|---:|---|---|
| **P/VP (Valor Patrimonial)** | 3,5 | Gaussiana Assimétrica<br>Centro $\mu = 0,95$<br>$\sigma_{\text{esq}} = 0,18$, $\sigma_{\text{dir}} = 0,14$ | Mesma modelagem dos FIIs: valoriza negociação no valor justo e protege contra CRAs estressados com descontos anômalos. |
| **Dividend Yield Agro** | 4,0 | Gaussiana Assimétrica<br>Centro $\mu = 13,5\%$ (0,135)<br>$\sigma_{\text{esq}} = 3,0\%$, $\sigma_{\text{dir}} = 4,0\%$ | Sweet spot em 12,5%–15,5% (incorporando o spread de risco agro sobre o CDI). Decaimento suave acima de 17,5% contra risco de inadimplência em produtores. |
| **Consistência de Proventos** | 2,5 | Sigmoide Logística<br>Inflexão $x_0 = 85,0\%$, $k = 15,0$ | Mesma modelagem dos FIIs: premia previsibilidade e pune histórico de cortes nos dividendos. Sem histórico: 1,5 pts neutro. |

## 7. Análise do Tesouro Direto (v2.6 Sigmoide e Percentil Contínuo)

O Tesouro Direto avalia a atratividade do ponto de entrada e o timing na curva de juros em uma escala contínua de 0 a 10 pontos calibrada para comparabilidade interclasses de alocação de ativos (*Asset Allocation*):

| Critério | Peso máximo | Função / Modelagem | Regra e Racional |
|---|---:|---|---|
| **Taxa Real / Entrada** | 5,0 (6,0 Selic) | Sigmoide Logística<br>Inflexão $x_0 = 5,5\%$, $k = 110,0$<br>(LFT: $x_0 = 0,0\%$, $k = 1500$) | IPCA+ usa a taxa real contratada (atualizada pelo VNA); Prefixado usa a taxa real esperada descontando o IPCA Focus. Inflexão em 5,5% a.a. Taxas elevadas (>6,8% a.a.) aproximam-se do teto de 5,0 pts. |
| **Taxa vs. Histórico Próprio** | 3,0 | Percentil Empírico (CDF) | Compara a taxa atual com a série histórica diária de negociação do Tesouro Transparente (STN). Percentis elevados (ex: 95%–99%) pontuam 2,8–3,0 pts. |
| **Potencial de MTM** | 1,0 | Duration Efetiva × $\Delta\text{Selic}_{\text{Focus}}$ | Avalia ganho de capital por fechamento da curva quando o Focus projeta queda da Selic. |
| **Taxa vs. Pares do Grupo** | 0,5 | Percentil no Grupo Homogêneo | Compara a taxa dentro de seu cluster homogêneo (sem misturar títulos com e sem cupom). |
| **Eficiência Tributária IR** | 0,5 | Regressiva por Prazo | Alíquota regressiva de IR: > 720 dias pontua 0,5 pt (alíquota mínima de 15%). |

Títulos são ordenados por score decrescente. `score_breakdown` do Tesouro é produzido somente por `src/tesouro_analyzer.py` e não pode ser exibido ou reutilizado para ativos de renda variável.

## 8. Análise macroeconômica

### 8.1 Estado macro canônico

`data/macro_state.json` concentra dados coletados diariamente: `CURRENT_SELIC`, `SELIC_META`, projeções `FOCUS_SELIC`, `FOCUS_IPCA`, `FOCUS_CAMBIO`, `FOCUS_PIB`, tendência semanal de IPCA, `ETTJ_CURVE`, títulos do Tesouro e históricos de Selic, IPCA e câmbio. `generator.py` apenas o propaga a `data.json`.

### 8.2 Métricas e interpretação

| Métrica | Fonte | Regra de cálculo/uso |
|---|---|---|
| Selic Over | SGS 11 | taxa efetiva corrente; ancora limites dinâmicos de Ações, FIIs e FIAGROs |
| Selic Meta | SGS 432 | decisão de política monetária e histórico de referência |
| Focus | BCB Expectativas | medianas anuais para ano corrente e três seguintes; IPCA semanal gera tendência `alta`, `baixa` ou `estável` |
| IPCA | IBGE/SIDRA | realizado em 12 meses e no ano; não confundir com expectativa Focus |
| Câmbio | SGS 1 | histórico de dólar de venda; expectativa vem do Focus |
| ETTJ aproximada | Selic + Focus | vértices 1/3/5/10 anos por spreads de prazo. É cenário indicativo, não cotação de DI Futuro |

A tendência do IPCA compara observações semanais do Focus: diferença acima de 0,01 p.p. indica `alta`, abaixo de −0,01 p.p. indica `baixa`; ausência ou variação menor indica `estável`.

## 9. Camada de cenários macroeconômicos e visão prospectiva

### 9.1 Decisão metodológica

**Status: proposta aprovada para implementação futura; ainda não substitui o score publicado.**

O score fundamental (0–10) mede qualidade, preço e risco do ativo a partir de seus dados próprios. A camada macro mede a **compatibilidade condicional** do ativo com o cenário esperado. Elas não podem ser somadas em uma única nota sem validação histórica: uma empresa ruim não se torna boa apenas porque os juros devem cair, e uma empresa boa não deixa de sê-lo porque o cenário piorou.

Por isso, o sistema deve publicar dois resultados independentes:

| Resultado | Pergunta respondida | Escala e uso |
|---|---|---|
| `fundamental_score` | “Qual é a qualidade/atratividade intrínseca observada hoje?” | 0–10; ranking principal e série histórica; usa somente dados realizados/atuais |
| `macro_radar` | “Quais expectativas e riscos futuros merecem atenção neste ativo?” | sinais e hipóteses com direção/confiança; **não é score, filtro, ranking ou recomendação** |

Essa separação evita dupla contagem de DY, P/L ou P/VP e torna a incerteza explícita. O Focus é mediana de expectativas de participantes de mercado, não projeção do BCB e não garantia de trajetória futura. [Banco Central — Expectativas de Mercado](https://www.bcb.gov.br/controleinflacao/expectativasmercado)

### 9.2 Sinais prospectivos mínimos

Cada sinal deve ter valor, data de coleta, histórico de revisões, fonte e nível de confiança. Sem série de revisões ou sem dado de mercado adequado, o sinal é `indisponível`, e não neutro.

| Sinal | Cálculo inicial | Interpretação | Fonte exigida |
|---|---|---|---|
| Impulso de juros nominais | `Selic atual − Focus Selic do próximo horizonte` | positivo = consenso de queda de juros | BCB SGS + Focus |
| Taxa real ex-ante curta | `(1 + Selic)/(1 + IPCA Focus 12m) − 1` | mede custo de oportunidade real, não DY | BCB SGS + Focus |
| Revisão de inflação | mediana Focus IPCA atual menos a de 4 semanas atrás, em p.p. | positiva = inflação esperada piorando | histórico Focus, não apenas ponto atual |
| Revisão de crescimento | mediana Focus PIB atual menos a de 4 semanas atrás, em p.p. | positiva = atividade esperada melhorando | histórico Focus |
| Estresse cambial | variação percentual da projeção Focus de câmbio em 4 semanas e seu desvio contra média móvel | positivo = deterioração cambial esperada | histórico Focus/PTAX |
| Curva de juros | variação das taxas nominais e reais por prazo | separa queda de Selic de fechamento/abertura da curva longa | **mercado observável**: DI futuro/B3 e curva real ANBIMA ou fonte licenciada equivalente |

Não usar nível fixo de câmbio (por exemplo R$ 5,50) como sinal permanente: ele envelhece e ignora o regime de preço. Não inferir marcação a mercado de títulos longos somente pela Selic/Focus; o preço responde à taxa exigida no vértice correspondente da curva, que pode subir mesmo se a Selic esperada cair.

### 9.3 Como estruturar o Radar, sem falsa precisão

Cada sinal disponível recebe direção qualitativa (`pode favorecer`, `misto`, `pode pressionar`) e confiança (`alta`, `média`, `baixa`), usando limiares versionados e calibrados em histórico brasileiro. Não somar sinais, não normalizá-los em uma nota e não calcular qualquer score de cenário.

* A confiança é `alta` apenas quando pelo menos juros, inflação, crescimento e curva observável existem e foram atualizados; `média` sem curva; `baixa` com duas ou mais lacunas.
* A primeira implementação deve publicar somente o conjunto de sinais, contribuições e confiança. Não calcular, exibir ou ordenar por score composto.
* O score fundamental histórico nunca é reescrito com a expectativa conhecida hoje. Cada observação histórica usa apenas dados e expectativas disponíveis naquela data, evitando viés de antecipação.

### 9.3.1 Invariantes de isolamento

O `macro_radar` é um artefato de contexto. É expressamente proibido que ele:

* altere `fundamental_score`, qualquer critério do breakdown, P/L, P/VP, DY, ROE, Graham, Bazin, preço justo ou score do Tesouro;
* determine a faixa/cor do score, filtro de score, ordenação de tabela, Top Pick, exportação CSV ou ranking;
* reclassifique um ativo como bom/ruim, compre/venda ou recomendado/não recomendado;
* preencha dados ausentes com expectativa ou transforme expectativa em dado histórico.

O `macro_radar` pode somente acrescentar observações com o formato: **sinal → hipótese condicional → exposição do ativo → confiança → fonte/data**. Exemplo: “Focus indica queda de Selic; se a taxa longa também cair, título prefixado longo tem maior sensibilidade de marcação a mercado; confiança média.”

### 9.4 Sensibilidade por classe de ativo

| Classe | Queda ordenada de juros reais / inflação ancorada | Crescimento revisado para cima | Inflação/câmbio piorando | Crédito/risco que limita a leitura |
|---|---|---|---|---|
| Ações de longa duração (crescimento, tecnologia, utilities reguladas) | em geral favorável à taxa de desconto e valuation | depende da demanda do setor | tende a ser adverso se elevar taxa de desconto | alavancagem, geração de caixa e duration do lucro devem confirmar |
| Ações cíclicas/domésticas | favorável se reduzir custo de capital | em geral favorável | adverso via custo, demanda e juros | margem, dívida e poder de preço |
| Financeiras | **ambíguo**: pode comprimir margem financeira, mas melhorar inadimplência e atividade | usualmente favorável à originação | pode elevar custo de risco e funding | não atribuir bônus setorial automático; usar NIM, custo de risco e capital do emissor |
| Exportadoras/commodities | efeito de juros domésticos secundário | depende do ciclo global e commodity | câmbio fraco pode elevar receita em reais, mas insumos/dívida podem anular | moeda da receita, hedge, endividamento e preço da commodity |
| FII de tijolo | pode favorecer cap rates, valor de imóveis e P/VP | favorece ocupação/reajustes em alguns segmentos | tende a elevar cap rates e custo de capital | vacância, contratos, indexador, concentração e alavancagem |
| FII de papel | queda de CDI pode reduzir renda de CRIs pós-fixados; preço depende de spread de crédito e duration | efeito indireto via crédito | pode aumentar default/spread e reduzir valor | indexador, duration, LTV, rating, concentração e inadimplência |
| FIAGRO | semelhante a crédito estruturado: CDI menor pode reduzir renda pós-fixada; spread e risco agrícola dominam | melhora seletiva, conforme cadeia agro | pode pressionar custos, crédito e devedores | commodity, clima, garantias, LTV, concentração, indexador e crédito |
| Tesouro Selic | pouco exposto à marcação; referência de liquidez | neutro | defensivo em incerteza de inflação | prazo e objetivo do investidor |
| Tesouro Prefixado/IPCA+ curto | ganho/perda moderado conforme taxa do vértice | secundário | inflação/curva abrindo é adverso | prazo e taxa real/nominal travada |
| Tesouro Prefixado/IPCA+ longo | favorecido somente se **taxa do vértice longo cair**; maior duration amplia efeito | secundário | vulnerável a inflação, prêmio fiscal e abertura da curva | duration, taxa de entrada e objetivo até vencimento |

As relações acima são hipóteses econômicas condicionais, não causalidade garantida. Para FIIs e FIAGROs, classificar por “tijolo/papel”, indexador e duration antes de qualquer sinal macro; para ações, classificar por setor e exposição econômica antes de aplicar sensibilidades.

### 9.5 Cenários operacionais e conduta analítica

| Cenário | Sinais | Leitura por classe | Como usar no Radar |
|---|---|---|---|
| Desinflação ordenada | juros e inflação esperados caem; curva longa estável/caindo; PIB estável | tende a ajudar duration longa, tijolo e ativos domésticos de qualidade; Tesouro longo só se o vértice longo confirmar | publicar hipótese e fatores de confirmação no Radar; não mudar score ou ranking |
| Queda de juros com crescimento fraco | juros caem, PIB revisado para baixo | pode ajudar valuation, mas pressionar lucros, ocupação e crédito | exigir qualidade de balanço e caixa; evitar interpretar múltiplo baixo como sinal isolado |
| Reaceleração com inflação ancorada | PIB sobe, inflação estável, curva controlada | favorável a cíclicas e crédito saudável; efeito heterogêneo em growth | priorizar métricas operacionais do setor, não apenas direção da Selic |
| Estagflação/abertura de curva | inflação e câmbio pioram, PIB cai, taxa longa sobe | adverso para duration, crédito frágil e tijolo alavancado; pós-fixados ganham papel defensivo | reduzir confiança do cenário e destacar riscos de liquidez/crédito |
| Desinflação com estresse de crédito | inflação cai, mas spreads/default sobem | taxa menor não compensa risco de crédito em papel/FIAGRO ou empresas frágeis | sobrepor sinal de crédito; não premiar DY alto |

### 9.6 Substituição da regra “DY maior que Selic”

O termo ERP deve ser reservado para retorno esperado de ações menos taxa livre de risco; ele não pode ser calculado como `DY − Selic`. A substituição ocorre em duas etapas:

1. **Agora:** remover o bônus automático de `+0,50` do score fundamental e preservar DY apenas em seu critério próprio. Exibir, se necessário, `spread de renda distribuída = DY − Selic` como métrica descritiva, sem chamá-la de ERP e sem pontuação.
2. **Depois, com dados e backtest:** um `equity_expected_return_proxy` pode compor o `macro_radar` como hipótese, por earnings yield normalizado/cash-flow yield, crescimento sustentável, risco de alavancagem e prêmio de risco de mercado. Ele deve ser apresentado como faixa, premissas e confiança, nunca como score ou previsão certa.

### 9.7 Dados, implementação e validação antes de ativar

Para ativar o `macro_radar`, adicionar dados que hoje não são suficientes no pipeline:

* histórico semanal de revisões Focus para Selic, IPCA, PIB e câmbio;
* curva nominal por prazo e curva real por prazo de fonte de mercado observável;
* classificação versionada dos ativos (setor, duração econômica, exposição a câmbio, tipo de FII/FIAGRO, indexador e duration de carteira);
* para crédito: rating, LTV, concentração, inadimplência e spread, quando houver fonte confiável;
* data de referência de cada input, para evitar viés de antecipação.

Critérios de aceite:

1. cada sinal tem teste de unidade para limite positivo, neutro, negativo e dado ausente;
2. cada classe tem teste de sensibilidade e explicação gerada;
3. um backtest walk-forward compara o ranking fundamental isolado contra fundamental + filtro macro, com custos e períodos fora da amostra;
4. a nova camada só pode explicar e alertar; não pode filtrar, ordenar, compor ou substituir o score fundamental, mesmo após backtest, sem nova decisão explícita e validação humana;
5. resultados, hipótese, período, viés de sobrevivência e limitações são publicados junto ao backtest.

## 10. Mudança de regra e critérios de aceite

Qualquer mudança de regra deve, na mesma entrega:

1. atualizar este documento e o código dono;
2. registrar fonte, fórmula, unidade, limites, fallbacks e domínios afetados;
3. criar ou ajustar teste unitário para piso, ponto intermediário, teto, dado ausente e valor inválido;
4. validar que o `score_breakdown` corresponde ao score final;
5. regenerar/validar `data.json` e garantir que a UI apenas apresenta o resultado, sem recalcular metodologia;
6. revisar [UI_UX_SPECIFICATION.md](UI_UX_SPECIFICATION.md) apenas se o contrato de dado ou apresentação também mudar.

### Checklist de análise

- [ ] A fonte usada é autorizada e sua condição (atual, cache, estimada ou demonstração) está registrada.
- [ ] Nenhuma lacuna foi preenchida com dado sintético quando a regra exige ausência explícita.
- [ ] A fórmula e os limites são exclusivos do domínio correto.
- [ ] O score está entre 0 e 10 e o breakdown soma o total esperado.
- [ ] A alteração não mudou UI, filtros, modal ou gráficos sem revisão do documento de UI.

---

Histórico: [SCORE_RULES.md](SCORE_RULES.md) permanece apenas como ponte de compatibilidade. O material histórico em `docs/v3/` não é especificação vigente.
