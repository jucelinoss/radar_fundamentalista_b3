# **Regras de Análise Fundamentalista e Alocação Macro**

**Radar Fundamentalista B3**  
**Versão Consolidada:** 2.6.1 (Full Spec)  
**Última Atualização:** 2026-07-12  
**Autor/Mantenedor:** Jucelino Santos Silva  
**Escopo do Sistema:** 91 ações, 120 FIIs, 36 FIAGROs, Tesouro Direto  

---

## **1. Arquitetura Geral do Sistema (Cockpit e Navegação)**

O sistema opera como um Dashboard Executivo estruturado em uma aplicação Single Page Application (SPA) para garantir máxima fluidez de UX sem recarregamentos parciais de tela.

### **1.1 Estrutura de Telas**
1.  **Home (Painel Geral):** Atua como o centro de comando do usuário. Divide-se em um grid responsivo que exibe os Cards de Custo de Oportunidade (Focus), os três blocos de rankings de Renda Variável (**Top Ações**, **Top FIIs**, **Top FIAGROs**) e o bloco de **Oportunidades em Destaque do Tesouro Direto**. Cada sumário contém links de redirecionamento para suas respectivas tabelas analíticas.
2.  **Painel de Renda Variável:** Contém a barra de ferramentas com filtros unificados (Dropdown de Faixas Estilizadas, Índices, Setores e Busca de Ativos) e a tabela profunda com as abas de Ações, FIIs, FIAGROs e Análise Setorial.
3.  **Painel de Renda Fixa & Macro:** Apresenta o gráfico de linha estrutural da Curva de Juros (ETTJ) e a tabela analítica completa de títulos do Tesouro Direto ordenados por Score Contínuo.

### **1.2 Regra Visual do Filtro por Faixas (Dropdown Estilizado)**
Para acomodar notas decimais contínuas (0,00 a 10,00) sem poluição visual na interface mobile e desktop, os botões numéricos circulares foram substituídos por um componente Select integrado à barra de ferramentas:
*   **🟢 Premium (Score 8,0 a 10,0):** Ativos com ampla margem de segurança, alta eficiência operacional ou assimetria cíclica rara de juros reais ("Aprovados no Vestibular de Medicina").
*   **🟡 Bom (Score 6,0 a 7,9):** Ativos sólidos que cumprem os critérios de segurança regulamentares, mas sem prêmios exuberantes.
*   **🟠 Alerta / Regular (Score 4,0 a 5,9):** Ativos com falhas em múltiplos múltiplos plurianuais ou expostos a estresse severo de custos.
*   **🔴 Alto Risco (Score abaixo de 4,0):** Ativos reprovados na maioria das regras de sobrevivência, com risco de colapso de crédito, inadimplência estrutural ou *distress*.

---

## **2. Pipeline de Ingestão e Estado Macro (`macro_fetcher.py`)**

O motor de cálculo depende do dicionário global de estado `CURRENT_MACRO_STATE`, atualizado diariamente via chamadas de API do Banco Central do Brasil (SGS e Expectativas Focus):
*   `CURRENT_SELIC`: Taxa Selic Over/Meta diária (Série SGS 11).
*   `FOCUS_SELIC_NEXT_YEAR`: Mediana do consenso de mercado para o encerramento do ano subsequente.
*   `FOCUS_IPCA_TREND`: Indicador vetorial de curtíssimo prazo da inflação baseada nas últimas 4 semanas de relatório.
*   `ETTJ_CURVE_VERTICES`: Vetor de taxas dos contratos de DI Futuro (1Y, 3Y, 5Y, 10Y).

---

## **3. Regras e Fórmulas de Renda Variável (`analyzer.py`)**

### **3.1 Lógica Matemática dos 5 Critérios de Ações (Até 2,0 pontos cada)**

#### **A. Dividend Yield Médio de 3 Anos (Meta Cíclica)**
*   **Piso de Segurança:** Se `dy_medio_3y < DY_STOCK_TARGET` $\rightarrow$ `0.0` pontos.
*   **Fórmula Contínua:** Se passou do piso, a nota avança linearmente até o teto estipulado de 15% de DY real médio.
*   **Ajuste Dinâmico Selic:** $\text{DY\_STOCK\_TARGET} = \max(0.06, \text{CURRENT\_SELIC} \times 0.6)$.

#### **B. P/L Médio de 5 Anos (Estabilidade Fundamentalistia)**
*   **Piso de Segurança:** Se `pe_medio_5y <= 0` ou `pe_medio_5y > PE_MAX` $\rightarrow$ `0.0` pontos.
*   **Fórmula Contínua:** $\text{Score} = 1.0 + \left( \frac{\text{PE\_MAX} - \text{pe\_medio\_5y}}{\text{PE\_MAX}} \right) \times 1.0$.
*   **Ajuste Dinâmico Selic:** $\text{PE\_MAX} = \min\left(15.0, \frac{1.2}{\text{CURRENT\_SELIC}}\right)$.

#### **C. P/VP Blindado Assimétrico**
*   **Filtro de Ruína:** Se `pb_ratio < 0.50` ou `pb_ratio > 1.50` $\rightarrow$ `0.0` pontos automáticos.
*   **Fórmula Assimétrica (Premiação por Desconto):**  
    $$\text{Score} = 2.0 \times (1.50 - \text{pb\_ratio})$$
    *Premiar com pontuação decimal máxima o ativo que entregar maior margem de desconto patrimonial, sem criar curvas simétricas prejudiciais às pechinchas.*

#### **D. ROE Corrente (Validador Patrimonial)**
*   **Piso de Segurança:** Se `roe_corrente < 0.10` $\rightarrow$ `0.0` pontos.
*   **Fórmula Contínua:** Pontuação decimal incremental proporcional a o quanto a empresa entrega acima do patamar de 10%.

#### **E. Margem de Segurança Graham/PEG**
*   **Fórmula Contínua:** Se `price >= graham_price` $\rightarrow$ `0.0` pontos. Se `price < graham_price` $\rightarrow$ `1.0 + (graham_price - price) / price`, com teto limitado a `2.0` pontos cheios (atingido em 50% de desconto real sobre o Valor Justo).

### **3.2 Lógica Contínua de FIIs e FIAGROs**
*   **P/VP Ajustado:** Piso elevado para `0.70` e teto ideal em `1.05` para blindar contra fundos imobiliários em *distress* ou com vacância estrutural severa. Zonas limítrofes pontuam de forma reduzida.
*   **Travas de Risco Elásticas (CDI/Selic Alto):** Para impedir que a pontuação máxima seja destruída quando os rendimentos sobem de forma legítima acompanhando os juros do país, os tetos *High Yield* de risco tornam-se variáveis:
    *   $\text{DY\_FII\_MAX\_LIMIT} = \text{CURRENT\_SELIC} + 0.04$
    *   $\text{DY\_FIAGRO\_MAX\_LIMIT} = \text{CURRENT\_SELIC} + 0.06$
    *   Se ultrapassar o teto indexado, o critério de proventos zera devido ao risco predatório de crédito.

### **3.3 Gatilhos de Moderação Macro (Sem impacto nos múltiplos puros)**
Os novos critérios de sobrevivência a juros de dois dígitos rodam na saída do motor, modificando o score final:
1.  **Fator de Sobrevivência (Liquidez Corrente):** Se `current_ratio < 1.0` $\rightarrow$ Aplica penalidade rígida de **-1,5 pontos** no Score Final.
2.  **Índice de Cobertura de Juros (ICJ):** Se $EBIT / \text{Despesa Financeira} < 1.0x$ $\rightarrow$ Reduz o Score Final em **-1,0 ponto automático**.
3.  **Spread Equity Risk Premium (ERP):** Se `dy_normalizado > CURRENT_SELIC` $\rightarrow$ Adiciona bônus de atratividade de **+0,5 pontos** no Score Final.

---

## **4. Módulo de Renda Fixa — Scorecard do Tesouro Direto (0 a 10)**

Mede a assimetria cíclica macroeconômica baseada no risco soberano. Composto por 5 critérios de até 2,0 pontos:

1.  **Prêmio Real Esperado:** Nos Tesouro IPCA+, utiliza a taxa real contratada. Nos Prefixados, estima a taxa real pela fórmula de Fisher, descontando da taxa nominal a projeção IPCA Focus mais próxima do horizonte disponível. Taxas reais $\ge 6,0\%$ garantem nota base `1.0`, progredindo linearmente até o teto de $7,5\%$ a.a. (`2.0` pontos).
2.  **Captura de Marcação a Mercado:** Se o Focus sinalizar tendência de queda estrutural de juros nos anos seguintes ($\Delta\text{Selic} < 0$), títulos **Prefixados** e **IPCA+ Longos** recebem bônus linear de até `2.0` pontos pelo potencial de ganho de capital.
3.  **Risco de Duration / Volatilidade:** Se a tendência de 4 semanas do Focus para o IPCA for de aceleração, a nota de papéis longos é drenada e convertida para títulos pós-fixados (**Tesouro Selic**), blindando o patrimônio contra oscilações na curva.
4.  **Elasticidade Cambial:** Projeções de câmbio estressado no Focus bonificam títulos indexados à inflação (IPCA+) como proteção contra repasse cambial e inflação importada.
5.  **Eficiência Tributária:** Títulos com prazo de vencimento inferior a 360 dias sofrem penalidade na nota decimal devido às alíquotas elevadas de IR (22,5% e 20%). Vencimentos superiores a 720 dias (alíquota mínima de 15%) levam nota cheia.
