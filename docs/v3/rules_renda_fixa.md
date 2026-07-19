# **Regras de Ingestão e Análise Macroeconômica — Scorecard & Alocação**

**Radar Fundamentalista B3**  
**Versão do documento:** 3.0  
**Última atualização:** 2026-07-16
**Módulo:** Macro, Câmbio, Renda Fixa e Curva de Juros  

---

## **1. Estrutura do Pipeline de Dados Macro (`macro_fetcher.py`)**

O sistema deixa de ser um analisador estático e passa a rodar de forma **forward-looking (preditiva)**. Os insumos macroeconômicos diários alimentam o dicionário global `CURRENT_MACRO_STATE` para calibrar os limites dinâmicos de ações, FIIs, FIAGROs e precificar títulos públicos.

### **1.1 Fontes e Ingestão de Dados**
*   **Taxa Selic Over/Meta:** Capturada diariamente via API do Sistema Gerenciador de Séries Temporais (SGS) do Banco Central do Brasil (Série 11).
*   **Consenso do Mercado (Boletim Focus):** Consulta semanal à API de Expectativas de Mercado do Banco Central. São extraídas as medianas agregadas para o IPCA, PIB, Câmbio e Selic para o ano corrente e os três anos subsequentes.
*   **Estrutura a Termo (Curva de Juros DI):** Coleta das taxas dos contratos de DI Futuro (vértices de 1 ano, 3 anos, 5 anos e 10 anos) para mapear a inclinação da curva.
*   **Preços do Tesouro Direto:** Ingestão diária das taxas de compra (*Yield*) e preços de liquidação de todos os títulos públicos federais vigentes através do portal de dados abertos do Tesouro Nacional.

---

## **2. Regras de Ajuste Dinâmico no Motor de Renda Variável (`analyzer.py`)**

As variáveis macro alteram em tempo real os limites do Scorecard 0-10 de ações e fundos, criando um modelo anticrágil adaptado ao custo de oportunidade do país.

### **2.1 Ações: Ajuste por Custo de Oportunidade**
*   **Teto Dinâmico de P/L:** O limite fixo de P/L $\le$ 15 é substituído pela taxa de desconto de longo prazo.  
    $$\text{PE\_MAX} = \min\left(15.0, \frac{1.2}{\text{CURRENT\_SELIC}}\right)$$
*   **Yield Mínimo Adaptativo:** A exigência de Dividend Yield base (Bazin) acompanha os juros:  
    $$\text{DY\_STOCK\_TARGET} = \max(0.06, \text{CURRENT\_SELIC} \times 0.6)$$

### **2.2 FIIs & FIAGROs: Trava de Risco Baseada em Spread**
Para evitar que fundos saudáveis percam nota injustamente em cenários de juros altos (v2.5), os tetos de segurança (*High Yield* predador) tornam-se elásticos:
*   **Teto Máximo para FIIs:** $\text{DY\_FII\_MAX} = \text{CURRENT\_SELIC} + 0.04$
*   **Teto Máximo para FIAGROs:** $\text{DY\_FIAGRO\_MAX} = \text{CURRENT\_SELIC} + 0.06$
*   *Comportamento:* Se o yield real do ativo ultrapassar esses limites indexados, o critério é zerado por risco de crédito excessivo.

---

## **3. Score de Atratividade do Dia — Tesouro Direto (0 a 10)**

O score classifica a oportunidade de compra observável no dia. Ele usa somente taxa, prazo, pares comparáveis e tributação; projeções Focus permanecem como contexto no painel macro e **não atribuem pontos**.

### **3.1 Universo e grupos comparáveis**

Os títulos são comparados por indexador e fluxo de pagamento:

* IPCA+ sem cupom e IPCA+ com juros semestrais;
* Prefixado sem cupom e Prefixado com juros semestrais;
* Selic e IGP-M+;
* RendA+ e Educa+, cada qual em seu grupo de planejamento.

O ranking geral de **Oportunidades do Dia** inclui Selic, Prefixados, IPCA+ e IGP-M+. RendA+ e Educa+ recebem `planning_rank` próprio e não disputam o Top 5 geral, pois foram estruturados para fluxo de renda/educação e não para comparação tática com títulos bullet.

### **3.2 Composição da nota**

| Critério | Peso | Regra |
| --- | ---: | --- |
| Taxa vs. histórico | 4,0 | Percentil da taxa de compra na série do próprio título. Taxa no percentil 79 é igual ou maior que 79% das observações disponíveis. |
| Taxa vs. pares | 2,0 | Percentil da taxa entre títulos do mesmo grupo. Não compara taxa nominal Prefixada diretamente com taxa real IPCA+. |
| Potencial técnico de marcação a mercado | 2,0 | Combina posição histórica alta da taxa com prazo até o vencimento. É sensibilidade técnica, não projeção de queda de juros nem promessa de ganho. |
| IR se mantido até o vencimento | 2,0 | Referência da alíquota regressiva, assumindo compra no dia e resgate no vencimento. |

### **3.3 Tributação e interpretação**

O IR incide sobre o rendimento e depende do prazo efetivo entre liquidação da compra e resgate: até 180 dias (22,5%), 181–360 dias (20%), 361–720 dias (17,5%) e acima de 720 dias (15%). A nota usa os dias até o vencimento apenas para a hipótese explícita de manter o título até essa data. Em venda antecipada ou em cupons, a alíquota real pode ser diferente.

### **3.4 Histórico de atratividade**

Cada ponto do gráfico é recalculado com a taxa observada, o prazo restante e as observações disponíveis até aquela data. A série não reutiliza o cenário macro atual para pontuar o passado.

---

## **4. Arquitetura Gráfica e Apresentação Visual (v3.0)**

### **4.1 Painel do Tesouro Direto (`#td-detail-modal`)**
*   **Dimensões do Modal:** Configurado com `max-width: 650px` para compatibilidade com múltiplos dispositivos e ausência de barra de rolagem lateral.
*   **Seletor Dropdown de Gráficos:** Substitui múltiplos gráficos lado a lado por um seletor dinâmico (`#td-chart-type`), alternando entre **Taxa Histórica**, **PU Histórico** e **Atratividade Histórica**.
*   **Plugin `valueLabels`:** Rótulos numéricos dinâmicos desenhados diretamente na linha do gráfico nos extremos e nos picos/vales locais. O indicador de atratividade é formatado com precisão de 1 casa decimal (ex: `7.5`), enquanto o Y-axis para taxas e PUs possui `grace: '20%'` para evitar corte visual.

### **4.2 Expectativas de Mercado do Boletim Focus**
*   **Linha Contínua Segmentada:** Exibe uma trajetória contínua no gráfico de linhas unindo o **Histórico (Realizado)** (anos $T-5$ a $T-1$) com as **Projeções Futuras** ($T$ a $T+3$) para garantir o equilíbrio visual ideal (proporção 5x4).
*   **Diferenciação por Cor:** O segmento histórico utiliza tons sóbrios e escuros, e o de projeção utiliza a paleta original vibrante. Os dois segmentos encontram-se no ano corrente $T$ sem quebras.
*   **Legenda e Tabelas Expandidas:** Habilita a legenda informativa do gráfico ("Histórico" vs "Projeção"). A tabela no final do modal possui 9 linhas contendo a coluna "Tipo" e a coluna "Valor / Expectativa" para os 5 anos históricos e 4 de projeção.

---

## **5. Requisitos Visuais da Nova Home (Cockpit Geral)**

Para integrar essas regras sem poluir o sistema, a interface do Radar Fundamentalista implementará um painel de introdução unificado que distribui o tráfego do usuário.

```text
+------------------------------------------------------------------------------------+
|                               RADAR FUNDAMENTALISTA B3                             |
+------------------------------------------------------------------------------------+
| [ 🏠 Home / Painel Geral ]       [ 📈 Renda Variável ]       [ 🪙 Renda Fixa ]     |
+------------------------------------------------------------------------------------+
|                                                                                    |
|  CUSTO DE OPORTUNIDADE (FOCUS)     TOP ATIVOS (RENDA VARIÁVEL)                     |
|  +---------------------------+     +--------------------------------------------+  |
|  | Selic: 14,00% (➘ Queda)   |     | 1. BRSR6  [Score: 9,04]  | DY: 10,95%      |  |
|  | IPCA:   5,30% (⚟ Estável) |     | 2. EVEN3  [Score: 8,44]  | DY: 15,99%      |  |
|  | Câmbio: R$ 5,20           |     | 3. RECV3  [Score: 8,42]  | DY: 13,35%      |  |
|  +---------------------------+     +--------------------------------------------+  |
|  [Ver Curva de Juros Completa]     [Navegar para Renda Variável →]              |
|                                                                                    |
|  OPORTUNIDADES EM DESTAQUE (TESOURO DIRETO)                                        |
|  +------------------------------------------------------------------------------+  |
|  | 1º Tesouro IPCA+ 2035   | Rate: IPCA + 6,45% | Score: 9,25/10  | 🟢 Premium  |  |
|  | 2º Tesouro Prefixado 2029| Rate: 13,10%       | Score: 8,50/10  | 🟢 Premium  |  |
|  +------------------------------------------------------------------------------+  |
|  [Navegar para Simulador de Renda Fixa →]                                           |
+------------------------------------------------------------------------------------+
```
