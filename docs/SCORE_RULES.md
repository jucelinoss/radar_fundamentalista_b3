# **Regras de Análise Fundamentalista — Scorecard 0-5**

**Radar Fundamentalista B3**  
**Versão do documento:** 2.3  
**Última atualização:** 2026-07-08  
**Cobertura:** 91 ações, 120 FIIs, 36 FIAGROs

## ---

**1\. Estrutura do Scorecard**

Cada ativo recebe uma **nota de 0 a 5** baseada em critérios objetivos binários (ganha 1 ponto ou 0).  
Não há pesos diferenciados — cada critério vale exatamente **1 ponto**.

| Pontos | Significado   |
| :---- | :---- |
| 5/5 | Excelente — atende todos os critérios fundamentalistas |
| 4/5 | Bom — apenas um critério não atende |
| 3/5 | Regular — metade dos critérios |
| 2/5 | Fraco — maioria dos critérios falha |
| 1/5 | Ruim — apenas um critério atende |
| 0/5 | Crítico — nenhum critério atende |

Os critérios seguem as filosofias de **Benjamin Graham** (value investing, margem de segurança) e **Décio Bazin** (dividendos sustentáveis), adaptados e calibrados para a realidade prática do mercado financeiro brasileiro.

## ---

**2\. Ações (B3) — 5 Critérios**

**Fonte dos dados brutos:** Yahoo Finance (yfinance)  
**Função no código:** calculate\_stock\_score() em analyzer.py  
**Abrangência:** 91 ações

### **2.1 Dividend Yield ≥ 6% (Bazin)**

* **Fórmula:** dy\_normalizado \>= 0.06  
* **Label no modal:** Dividend Yield \>= 6%  
* **Descrição:** O Dividend Yield dos últimos 12 meses deve ser igual ou superior a 6% ao ano. Baseado no método de Décio Bazin, que considera 6% a taxa mínima de retorno em proventos para justificar o investimento em renda variável.

### **2.2 P/L (Preço sobre Lucro) Corrente ≤ 15**

* **Fórmula:** 0 \< pe\_ratio \<= 15  
* **Label no modal:** P/L (Preço / Lucro) \<= 15  
* **Descrição:** O múltiplo Preço/Lucro (trailing P/E) deve ser positivo e menor ou igual a 15\. A trava superior evita ativos sobreprecificados, enquanto a checagem \> 0 garante lucros positivos recorrentes, mitigando distorções de empresas com prejuízos contábeis.

### **2.3 P/VP (Preço sobre Valor Patrimonial) ≤ 1,5 (Graham)**

* **Fórmula:** 0 \< pb\_ratio \<= 1.5  
* **Label no modal:** P/VP (Preço / V.P.) \<= 1.5  
* **Descrição:** O múltiplo Preço/Valor Patrimonial (Price-to-Book) deve ser positivo e menor ou igual a 1,5. Baseado no limite prudencial de Graham.

### **2.4 ROE ≥ 10%**

* **Fórmula:** roe \>= 0.10  
* **Label no modal:** ROE (Retorno s/ Patr.) \>= 10%  
* **Descrição:** O Retorno sobre o Patrimônio Líquido (Return on Equity) deve ser igual ou superior a 10% ao ano. A empresa deve demonstrar eficiência na geração de valor sobre o capital próprio investido.

### **2.5 Margem de Segurança (Graham / PEG Alternativo)**

* **Fórmula:** price \< graham\_price (para setores tradicionais) OR peg\_ratio \<= 1.0 (para tecnologia/serviços leves)  
* **Label no modal:** Margem de Segurança (Preço \< Justo / PEG)  
* **Descrição:** Garante margem de segurança na aquisição. Ativos industriais/financeiros usam o Preço Justo de Graham. Empresas de tecnologia ou de capital leve usam o PEG Ratio para não penalizar VPAs estruturalmente baixos.

## ---

**3\. FIIs (Fundos Imobiliários) — 5 Critérios**

**Fonte dos dados brutos:** Yahoo Finance (yfinance)  
**Função no código:** calculate\_fii\_score() em analyzer.py  
**Abrangência:** 120 Fundos de Investimento Imobiliário

### **3.1 P/VP Ajustado entre 0,70 e 1,05 (Desconto Saudável)**

* **Fórmula:** 0.70 \<= pb\_ratio \<= 1.05  
* **Label no modal:** Múltiplo P/VP entre 0.70 e 1.05 (Ideal)  
* **Descrição:** O P/VP deve estar entre 0,70 e 1,05. O piso elevado para 0,70 serve como blindagem matemática automática contra armadilhas de valor (*value traps*) e fundos em situação de estresse severo de crédito ou vacância estrutural (*distress*).

### **3.2 P/VP Limite e Não Excludente**

* **Fórmula:** (pb\_ratio \< 0.70) OR (1.05 \< pb\_ratio \<= 1.15)  
* **Label no modal:** Múltiplo P/VP em Região Limite ou Estresse  
* **Descrição:** Avalia as bordas de preço do mercado. Este critério pontua fundos fora da faixa ideal (0,70-1,05), mas que estão em zonas transitórias de ágio aceitável (até 1,15) ou desconto profundo de tijolos cíclicos, atuando como um contrapeso de risco.

### **3.3 Dividend Yield Anual ≥ 8%**

* **Fórmula:** dy\_normalizado \>= 0.08  
* **Label no modal:** Dividend Yield Anual \>= 8% (Mínimo)  
* **Descrição:** O retorno em proventos nos últimos 12 meses deve ser de no mínimo 8% ao ano, adequado à exigência legal de distribuição de 95% do lucro caixa dos FIIs.

### **3.4 Dividend Yield Anual ≥ 10% (Excelente)**

* **Fórmula:** dy\_normalizado \>= 0.10  
* **Label no modal:** Dividend Yield Anual \>= 10% (Excelente)  
* **Descrição:** Premia os fundos com excelente prêmio de distribuição de renda imobiliária.

### **3.5 Histórico Acumulado de Distribuição Ativa**

* **Fórmula:** sum(historical\_dividends\_365d) \> 0  
* **Label no modal:** Distribuição Real 12M \> R$ 0,00  
* **Descrição:** O fundo deve registrar pagamentos efetivos. Evita distorções de caixas estáticos ou fundos que interromperam totalmente seus rendimentos por inadimplência.

## ---

**4\. FIAGROs — 5 Critérios**

**Função no código:** calculate\_fiagro\_score() em analyzer.py  
**Abrangência:** 36 Fundos do Agronegócio  
*Nota de Calibração: Embora possuam dinâmica regulatória parecida, os FIAGROs não possuem a mesma obrigação imutável de 95% de distribuição dos FIIs pela Lei nº 14.130/2021. Devido ao maior risco de crédito envolvido na cadeia agropecuária (clima, variação de commodities), os limites de dividendos exigidos pelo score são elevados para compensar o prêmio de risco exigido pelo consenso de mercado.*

| Critério FIAGRO | Fórmula de Validação | Pontos   |
| :---- | :---- | :---- |
| **P/VP Ideal Agro** | 0.70 \<= pb\_ratio \<= 1.05 | 1 |
| **P/VP Limite Agro** | (pb\_ratio \< 0.70) OR (1.05 \< pb\_ratio \<= 1.15) | 1 |
| **Dividend Yield Mínimo Agro** | dy\_normalizado \<= 0.10 (10% a.a.) | 1 |
| **Dividend Yield Excelente Agro** | dy\_normalizado \<= 0.12 (12% a.a.) | 1 |
| **Distribuição Ativa 12M** | sum(historical\_dividends\_365d) \> 0 | 1 |

## ---

**5\. Métodos de Engenharia de Dados e Ajustes de API**

### **5.1 Processamento Antifalha de Dividendos via yfinance**

Para evitar as falhas ou congelamentos do campo estático dividendRate e blindar o sistema contra distribuições não recorrentes isoladas (como grandes amortizações), a extração de proventos deve seguir o fluxo lógico abaixo:  
\# Abordagem de Engenharia de Dados para o analyzer.py  
def get\_true\_yield(ticker):  
    history \= ticker.actions  
    if not history.empty and 'Dividends' in history.columns:  
        \# Filtra os proventos pagos estritamente nos últimos 365 dias  
        last\_12m\_dividends \= history\['Dividends'\].last('365D').sum()  
        return last\_12m\_dividends / current\_price  
    return ticker.info.get('dividendYield', 0.0)

### **5.2 Validação de Múltiplos Negativos**

Para barrar distorções em empresas com patrimônio líquido negativo ou passivos a descoberto (onde operadores lógicos de menor ou igual podem retornar falsos positivos), o código obrigatoriamente aplica uma trava maior que zero antes de testar os limites:  
if pb\_ratio and pb\_ratio \> 0:  
    \# Executa a validação do Scorecard  
else:  
    \# Ativo falha automaticamente no critério (0 pontos)

### **5.3 Normalização de Amostragem do Dividend Yield**

Ajuste unificado aplicado previamente em todas as checagens operacionais:  
se dy \> 1.0:  
    dy \= dy / 100  
senao:  
    dy \= dy

## ---

**6\. Apêndice: Mapa de Constantes Atualizadas (Versão 2.3)**

| Constante no Código | Valor Antigo (v2.2) | Valor Atualizado (v2.3) | Objetivo Técnico do Ajuste   |
| :---- | :---- | :---- | :---- |
| PB\_FII\_IDEAL\_LOW | 0.50 | **0.70** | Blindar o scorecard contra fundos imobiliários em *distress* ou colapso de crédito. |
| DY\_FIAGRO\_GOOD | 0.08 | **0.10** | Adequar o prêmio mínimo exigido pelo mercado para o risco de crédito agropecuário. |
| DY\_FIAGRO\_EXCELLENT | 0.10 | **0.12** | Premiar FIAGROs com excelente eficiência de distribuição histórica. |

