# **Regras de Ingestão e Análise Macroeconômica — Scorecard & Alocação**

**Radar Fundamentalista B3**  
**Versão do documento:** 3.0  
**Última atualização:** 2026-07-13  
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

## **3. Scorecard Contínuo de Renda Fixa — Tesouro Direto (0 a 10)**

Diferente da renda variável, o Tesouro Direto não possui risco de crédito (risco soberano). Portanto, os **5 critérios (valendo até 2,0 pontos cada)** medem a **Assimetria Cíclica de Oportunidade e Alocação** (implementados em `src/tesouro_analyzer.py`).

### **3.1 Prêmio Real Esperado (Peso: 2,0)**
*   **Métrica:** Taxa real contratada nos títulos Tesouro IPCA+ ou taxa real esperada nos Prefixados.
*   **Prefixados:** A taxa real esperada desconta da taxa nominal a projeção IPCA Focus mais próxima do horizonte disponível: $r_{real} = (1+r_{prefixado})/(1+IPCA_{Focus})-1$.
*   **Regra de Pontuação:**
    *   $\text{Taxa} < 6,0\%$ a.a. $\rightarrow$ **0.0 pontos**
    *   $\text{Taxa} = 6,0\%$ a.a. $\rightarrow$ **1.0 ponto** (nota base)
    *   $\text{Taxa} \ge 7,5\%$ a.a. $\rightarrow$ **2.0 pontos** (nota máxima)
    *   *Comportamento:* Interpolação linear entre $6.0\%$ e $7.5\%$ a.a. Tesouro Selic recebe nota **0.0** neste critério; Prefixados só recebem zero quando não há projeção Focus válida ou quando a taxa real esperada fica abaixo da faixa mínima.

### **3.2 Captura de Marcação a Mercado via Focus (Peso: 2,0)**
*   **Métrica:** Expectativa de queda da taxa de juros básica da economia (Selic).
*   **Apenas Elegíveis:** Títulos de longo prazo (Prefixados e IPCA+ com prazo $\ge 1826$ dias ou 5 anos).
*   **Regra de Pontuação:**
    *   Calcula-se a variação esperada da taxa Selic: $\Delta\text{Selic} = \text{Selic\_Focus\_Ano\_Seguinte} - \text{CURRENT\_SELIC}$
    *   $\Delta\text{Selic} \ge 0.0\%$ (estável ou alta de juros) $\rightarrow$ **0.0 pontos**
    *   $\Delta\text{Selic} \le -3.0\%$ (queda máxima de referência) $\rightarrow$ **2.0 pontos**
    *   *Comportamento:* Interpolação linear para quedas entre $0.0\%$ e $-3.0\%$. Títulos pós-fixados (Tesouro Selic) recebem nota **0.0** automática neste critério.

### **3.3 Risco de Duration / Volatilidade (Peso: 2,0)**
*   **Métrica:** Prazo de vencimento e sensibilidade à tendência inflacionária (IPCA Focus).
*   **Regra de Pontuação:**
    *   Títulos pós-fixados (**Tesouro Selic**) possuem proteção integral contra inflação $\rightarrow$ **2.0 pontos** independente do cenário.
    *   Cenário de queda inflacionária ($\text{IPCA\_trend} = \text{"baixa"}$) $\rightarrow$ todos os vencimentos recebem **2.0 pontos**.
    *   Cenário de aceleração inflacionária ($\text{IPCA\_trend} = \text{"alta"}$):
        *   Curto Prazo ($\le 365$ dias): **1.5 pontos**
        *   Médio Prazo ($365$ a $1826$ dias): **0.5 pontos**
        *   Longo Prazo ($\ge 1826$ dias): **0.0 pontos**
    *   Cenário de estabilidade inflacionária ($\text{IPCA\_trend} = \text{"estável"}$):
        *   Curto Prazo ($\le 365$ dias): **2.0 pontos**
        *   Médio Prazo ($365$ a $1826$ dias): **1.5 pontos**
        *   Longo Prazo ($\ge 1826$ dias): **1.0 ponto**

### **3.4 Filtro de Elasticidade Cambial / Hedge (Peso: 2,0)**
*   **Métrica:** Câmbio projetado Focus vs. limite de estresse de R$ 5,50/USD.
*   **Regra de Pontuação:**
    *   Cenário de estresse cambial ($\text{Câmbio\_Focus\_Ano\_Seguinte} > \text{R\$ 5,50}$):
        *   Títulos indexados à inflação (IPCA+, IGP-M+) $\rightarrow$ **2.0 pontos** (proteção máxima).
        *   Tesouro Selic $\rightarrow$ **1.5 pontos** (BC tende a subir juros com câmbio estressado).
        *   Prefixados $\rightarrow$ **0.0 pontos** (câmbio corrói taxa real pré-fixada).
    *   Cenário de câmbio normal ($\text{Câmbio\_Focus\_Ano\_Seguinte} \le \text{R\$ 5,50}$):
        *   Títulos indexados à inflação $\rightarrow$ **1.0 ponto**.
        *   Tesouro Selic $\rightarrow$ **1.5 pontos**.
        *   Prefixados $\rightarrow$ **1.0 ponto**.

### **3.5 Eficiência Tributária (Peso: 2,0)**
*   **Métrica:** Prazo de dias até o vencimento baseado na tabela regressiva de alíquotas de IR.
*   **Regra de Pontuação:**
    *   Vencimento $\le 180$ dias (22,5% de IR sobre rendimento) $\rightarrow$ **0.5 pontos**
    *   Vencimento entre $181$ e $360$ dias (20.0% de IR sobre rendimento) $\rightarrow$ **1.0 ponto**
    *   Vencimento entre $361$ e $720$ dias (17.5% de IR sobre rendimento) $\rightarrow$ **1.5 pontos**
    *   Vencimento $> 720$ dias (15.0% de IR sobre rendimento - alíquota mínima) $\rightarrow$ **2.0 pontos**

---

## **4. Arquitetura Gráfica e Apresentação Visual (v3.0)**

### **4.1 Painel do Tesouro Direto (`#td-detail-modal`)**
*   **Dimensões do Modal:** Configurado com `max-width: 650px` para compatibilidade com múltiplos dispositivos e ausência de barra de rolagem lateral.
*   **Seletor Dropdown de Gráficos:** Substitui múltiplos gráficos lado a lado por um seletor dinâmico (`#td-chart-type`), alternando entre **Taxa Histórica**, **PU Histórico** e **Score Histórico**.
*   **Plugin `valueLabels`:** Rótulos numéricos dinâmicos desenhados diretamente na linha do gráfico nos extremos e nos picos/vales locais. O indicador de score é formatado com precisão de 1 casa decimal (ex: `7.5`), enquanto o Y-axis para taxas e PUs possui `grace: '20%'` para evitar corte visual.

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
