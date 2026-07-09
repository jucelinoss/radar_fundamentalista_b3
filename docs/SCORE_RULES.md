# **Regras de Análise Fundamentalista — Scorecard 0-10**

**Radar Fundamentalista B3**  
**Versão do documento:** 2.5  
**Última atualização:** 2026-07-08  
**Cobertura:** 91 ações, 120 FIIs, 36 FIAGROs  

---

## **1. Estrutura do Scorecard Contínuo (0 a 10)**

Para solucionar o problema de baixa granularidade (múltiplos ativos empatados no topo), o modelo migra de uma lógica binária rígida para um **sistema de pontuação contínua com casas decimais (não arredondadas)**. 

O sistema mantém os **5 critérios fundamentais** por classe de ativo, mas cada indicador passa a pontuar proporcionalmente em uma escala de **0,0 a 2,0 pontos** com base na distância da meta. A soma dos 5 critérios gera a nota final no range de **0,0 a 10,0**.

### **A Lógica Matemática do Desempate (`analyzer.py`)**
1. **Filtro de Ruína (Piso):** Se o ativo falhar nos limites de segurança absoluta (ex: P/VP abaixo do piso), ele recebe **nota 0,0 automática** naquele critério.
2. **Aproveitamento Proporcional:** Se passar no piso, a nota decimal é calculada baseada em o quão acima da meta mínima o indicador está (premiando os ativos altamente eficientes com frações decimais extras).

---

## **2. Ações (B3) — 5 Critérios Oficiais (Até 2,0 pontos cada)**

**Fonte dos dados brutos:** Yahoo Finance (yfinance)[cite: 2]  
**Função no código:** `calculate_stock_score()` em `analyzer.py`[cite: 2]

### **2.1 Dividend Yield Médio (3 anos) — Meta: ≥ 6%**
- **Cálculo da Nota (Max 2,0):** 
  - Se `dy_medio_3y < 0.06` $\rightarrow$ `0.0` pontos.
  - Se `dy_medio_3y >= 0.06` $\rightarrow$ `1.0 + (dy_medio_3y - 0.06) * fator_proporcional`.
- **Descrição:** Média dos dividendos distribuídos nos últimos 3 anos dividida pelo preço atual[cite: 2]. Neutraliza o efeito distorção de empresas cíclicas no topo do ciclo[cite: 2].

### **2.2 P/L Médio (5 anos) — Meta: ≤ 15**
- **Cálculo da Nota (Max 2,0):** 
  - Se `pe_medio_5y <= 0` ou `pe_medio_5y > 15` $\rightarrow$ `0.0` pontos[cite: 1, 2].
  - Se `0 < pe_medio_5y <= 15` $\rightarrow$ `1.0 + ((15 - pe_medio_5y) / 15) * fator_proporcional`[cite: 1, 2].
- **Descrição:** Preço atual dividido pela média do Lucro por Ação (LPA) de 5 anos[cite: 2]. Evita classificar ações como baratas baseando-se em lucros não recorrentes temporários[cite: 2].

### **2.3 P/VP Blindado — Intervalo Seguro: 0,50 a 1,50**
- **Cálculo da Nota (Max 2,0):**
  - Se `pb_ratio < 0.50` ou `pb_ratio > 1.50` $\rightarrow$ `0.0` pontos (Filtro de Ruína / *MGLU Proteção*)[cite: 1, 2].
  - Se `0.50 <= pb_ratio <= 1.50` $\rightarrow$ Pontuação calculada com base na proximidade do valor justo ideal.

### **2.4 ROE Corrente — Meta: ≥ 10%**
- **Cálculo da Nota (Max 2,0):**
  - Se `roe_corrente < 0.10` $\rightarrow$ `0.0` pontos[cite: 1, 2].
  - Se `roe_corrente >= 0.10` $\rightarrow$ `1.0 + (roe_corrente - 0.10) * fator_proporcional`[cite: 1, 2].
- **Descrição:** Validador do P/VP[cite: 2]. Impede notas altas para empresas com desconto patrimonial aparente, mas que estão destruindo capital com prejuízos[cite: 2].

### **2.5 Margem de Segurança Clássica (Graham / PEG)**
- **Cálculo da Nota (Max 2,0):**
  - Se `price >= graham_price` $\rightarrow$ `0.0` pontos.
  - Se `price < graham_price` $\rightarrow$ Ponto base + fração da margem de desconto em relação ao preço justo.
- **Descrição:** O preço atual deve ser inferior ao Preço Justo de Graham ou apresentar PEG Ratio $\le 1,0$ em empresas de tecnologia/capital leve[cite: 2].

### **[Indicador de Suporte Visual] Saúde Financeira (Sem peso no Score)**
- **Métrica no Modal:** `Dívida Líquida / EBITDA` (Alvo: `≤ 3,0x`)[cite: 2]. Exibido de forma puramente informativa para monitorar o risco de juros altos[cite: 2].

---

## **3. FIIs e FIAGROs — Lógica de Pontuação Decimal**

Os 5 critérios abaixo somam até 10,0 pontos, aplicando os novos pisos e as travas superiores contra risco predatório de crédito (*High Yield* podre)[cite: 2].

1. **P/VP Ajustado (Piso 0,70 / Teto 1,05):** Ativos abaixo de 0,70 recebem `0.0` automático no critério para evitar fundos em *distress*[cite: 1, 2].
2. **P/VP Limite e Não Excludente:** Pontua de forma fracionada ativos em zonas de borda de preço (0,60 a 0,70 ou 1,05 a 1,15)[cite: 2].
3. **Dividend Yield Anual Mínimo:** Base decimal calculada a partir de 8% para FIIs e 10% para FIAGROs[cite: 2].
4. **Trava de Risco de Crédito (Yield Equilibrado):** Se o yield ultrapassar **14,5% em FIIs** ou **16,5% em FIAGROs**, o critério zera (`0.0`)[cite: 2]. Yields excessivos indicam risco severo de inadimplência mascarado[cite: 2].
5. **Consistência de Proventos:** Pontuação proporcional baseada na estabilidade da distribuição semestral (mínimo de 95% de retenção em relação ao período anterior)[cite: 2].

---

## **4. Requisitos de Interface e Regra Visual do Filtro (Opção 2)**

Para acomodar as notas fracionadas (ex: `3.8`, `7.65`, `9.42`) sem estourar o layout ou criar uma barra poluída com 11 botões horizontais no mobile, o sistema adota oficialmente a **Opção 2: Filtro por Faixas Estilizadas via Dropdown**.

### **4.1 Componente do Filtro na Barra de Ferramentas**
Substituir os botões circulares numéricos atuais por um componente Dropdown (*Select*) estilizado[cite: 1], posicionado simetricamente ao lado dos filtros de "Setores" e "Índices"[cite: 1].

```text
+--------------------------------------------------------+
| Todos os Índices | Todos os Setores | Todos os Scores ▾|
+--------------------------------------------------------+
                                       | Todos os Scores |
                                       | 🟢 Premium (≥ 8.0)
                                       | 🟡 Bom (6.0 a 7.9)
                                       | 🟠 Alerta (4.0 a 5.9)
                                       | 🔴 Risco (< 4.0)