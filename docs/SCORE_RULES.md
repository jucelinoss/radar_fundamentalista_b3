# Documento substituído — Regras de Análise Fundamentalista

> A especificação vigente foi consolidada em [ANALYSIS_RULES_SPECIFICATION.md](ANALYSIS_RULES_SPECIFICATION.md), que inclui ações, FIIs, FIAGROs, Tesouro Direto, análise macroeconômica, fontes e regras de qualidade de dados.
>
> Este arquivo é mantido temporariamente somente para preservar links existentes. Não o use como fonte para novas implementações: ele contém critérios e decisões de UI de versões anteriores.

---

# Histórico — Regras de Análise Fundamentalista — Scorecard 0-10

**Radar Fundamentalista B3**  
**Versão do documento:** 2.5  
**Última atualização:** 2026-07-08  
**Cobertura:** 91 ações, 120 FIIs, 36 FIAGROs  

---

## **1. Estrutura do Scorecard Contínuo (0 a 10) — v2.6 Gaussiano / Sigmoide**

Para solucionar tanto a baixa granularidade quanto o **"Efeito Penhasco" (*cliff edges*)** de cortes rígidos, o modelo adota um **sistema de pontuação contínua baseado em Distribuições Gaussianas Assimétricas (*Split Normal*) e Curvas Sigmoides Logísticas**.

O sistema mantém os **5 critérios fundamentais**, pontuando de **0,00 a 2,00 pontos** de forma contínua e suave, totalizando de **0,00 a 10,00**.

### **A Lógica Matemática do Modelo (`analyzer.py`)**
1. **Curvas em Sino (Gaussianas com Sweet Spot):** Utilizadas em P/VP, P/L e Dividend Yield. Evitam distorções tanto nos extremos inferiores (ex: riscos de insolvência ou lucros atípicos) quanto nos superiores (sobreavaliação ou *Dividend Traps*).
2. **Curvas Sigmoides (Logísticas em S):** Utilizadas em ROE e Margem de Segurança. Garantem transições suaves no ponto de inflexão e saturação assintótica para empresas de altíssima rentabilidade.

---

## **2. Ações (B3) — 5 Critérios Oficiais (Até 2,0 pontos cada)**

**Fonte dos dados brutos:** Yahoo Finance (yfinance)  
**Função no código:** `calculate_stock_score_continuous()` em `src/analyzer.py`

### **2.1 Dividend Yield Médio (3 anos) — Gaussiana Assimétrica**
- **Centro ($\mu$):** `max(9,5%, meta_selic + 1,5%)` | $\sigma_{\text{esq}} = 3,5\%$, $\sigma_{\text{dir}} = 5,5\%$.
- **Comportamento & Literatura:** Décio Bazin / Luiz Barsi. Pontuação a partir de 6,0%, pico no *Sweet Spot* (9,5% a 12,0%) e decaimento suave após 16% contra *Dividend Traps*.

### **2.2 P/L Médio (5 anos) — Gaussiana**
- **Centro ($\mu$):** `min(6,5x, teto_selic * 0,8)` | $\sigma_{\text{esq}} = 2,0$, $\sigma_{\text{dir}} = 4,0$.
- **Comportamento & Literatura:** Alexandre Póvoa / Benjamin Graham. Centro de valor em 6,5x (múltiplo histórico B3). Penaliza múltiplos caros (> 15x) e lucros cíclicos atípicos (< 3,5x).

### **2.3 P/VP — Gaussiana Assimétrica (Pico Deep Value Barsi/Graham)**
- **Centro ($\mu$):** `0,80` | $\sigma_{\text{esq}} = 0,25$, $\sigma_{\text{dir}} = 0,45$.
- **Comportamento & Literatura:** Benjamin Graham / Luiz Barsi. P/VP entre 0,65 e 0,95 pontua como zona de excelência (1,85 a 2,00 pts). P/VP = 0,80 atinge nota cheia (2,00 pts). Transição suave evita penalizar barganhas seguras.

### **2.4 ROE Corrente — Sigmoide Logística**
- **Ponto de Inflexão ($x_0$):** `12,0%` (custo de capital no Brasil) | $k = 22,0$.
- **Comportamento & Literatura:** Aswath Damodaran / José Roberto Securato. Recompensa criação de valor sobre o capital próprio ($K_e$), saturando em 2,0 pts para ROEs $\ge 20\%$.

### **2.5 Margem de Segurança Clássica (Graham / PEG) — Sigmoide**
- **Inflexão ($x_0$):** `0,0` (preço justo = 1,0 pt) | $k = 4,0$.
- **Comportamento:** Margens amplas de desconto (+50% a +100%) convergem suavemente para 1,80–2,00 pts. Para Tecnologia/Comunicação, avalia $1 - \text{PEG}$.

### **[Indicador de Suporte Visual] Saúde Financeira (Sem peso no Score)**
- **Métrica no Modal:** `Dívida Líquida / EBITDA` (Alvo visual: `≤ 3,0x`). Exibido de forma informativa.

---

## **3. FIIs e FIAGROs — Scorecard Contínuo v2.6 (Até 10,0 pontos)**

**Funções no código:** `calculate_fii_score_continuous()` e `calculate_fiagro_score_continuous()` em `src/analyzer.py`

1. **P/VP (3,5 pts) — Gaussiana Assimétrica:**
   - Centro em `0,95` (*Sweet Spot* de valor justo), $\sigma_{\text{esq}} = 0,18$, $\sigma_{\text{dir}} = 0,14$.
   - Fim dos cortes secos em 0,60 e 0,70: transição suave protegendo contra fundos *zumbis* ou em ágio excessivo.
2. **Dividend Yield (4,0 pts) — Gaussiana com Trava Suave de Yield Trap:**
   - **FIIs:** Centro em `11,5%` (0,115), $\sigma_{\text{esq}} = 2,5\%$, $\sigma_{\text{dir}} = 3,5\%$.
   - **FIAGROs:** Centro em `13,5%` (0,135), $\sigma_{\text{esq}} = 3,0\%$, $\sigma_{\text{dir}} = 4,0\%$ (prêmio agro).
   - Elimina o zeramento brusco no cap de 14,5%/16,5%: decai suavemente na cauda direita.
3. **Consistência de Proventos (2,5 pts) — Sigmoide Logística:**
   - Inflexão em `85,0%` de retenção semestral ($k = 15,0$).
   - Fundos estáveis ($\ge 95\%$) recebem nota quase cheia (2,26 a 2,50 pts); sem histórico: neutro 1,5 pts.

---

## **3.1 Tesouro Direto — Scorecard Contínuo v2.6 (Até 10,0 pontos)**

**Função no código:** `score_bond()` em `src/tesouro_analyzer.py`

1. **Taxa Real / Entrada (5,0 pts; 6,0 Selic):** Curva Sigmoide Logística com $k=110,0$ centrada em 5,5% a.a. (juro real de equilíbrio neutro). Reflete a força da taxa contratada atualizada pelo VNA.
2. **Taxa vs. Histórico (3,0 pts):** Percentil Empírico Contínuo (CDF) sobre a base oficial do Tesouro Transparente (STN).
3. **Potencial de Marcação a Mercado MTM (1,0 pt):** Convexidade por Duration Efetiva e projeção Focus de corte da Selic.
4. **Taxa vs. Pares do Grupo (0,5 pt):** Percentil em cluster homogêneo (mesmo indexador e fluxo de cupom).
5. **Eficiência Fiscal IR (0,5 pt):** Tabela regressiva de imposto de renda no vencimento.

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
