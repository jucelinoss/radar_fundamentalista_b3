# Radar Fundamentalista B3 - Ações, FIIs e FIAGROs

Um sistema completo e automatizado de análise, triagem (*screening*) e visualização fundamentalista de ativos negociados na bolsa brasileira (B3). O projeto utiliza dados históricos e correntes para avaliar a saúde financeira, precificação e qualidade dos ativos com base em teorias consagradas de investimentos (Graham e Bazin) e scorecards quantitativos.

---

## 🖥️ Demonstração Visual e Funcionalidades

O sistema compila todas as análises em um **Dashboard Web Premium** (com suporte a temas claro/escuro persistente e responsividade móvel completa) que oferece:

1. **Triagem de Ações por Índices (IBOV, IDIV, SMLL)**:
   * Badges de índice sob cada ticker indicando filiação.
   * Seletor de índice dinâmico (visível apenas na aba "Ações") que atua em cruzamento com a barra de pesquisas de texto.

2. **Pontuação Fundamentalista Customizada (Score de 0 a 5)**:
   * **Ações**: Baseado em dividend yield (Bazin >= 6%), P/L Graham, P/VP Graham, ROE de qualidade e margem de segurança do Valor Justo de Graham.
   * **FIIs & FIAGROs**: Baseado em múltiplos P/VP na zona ideal, faixa limite de preço, dividend yields anuais mínimos/excelentes e recorrência de distribuição de rendimentos.

3. **Gráficos de Histórico Interativos (1 a 10 Anos)**:
   * Clique em qualquer ativo da tabela para abrir o modal de histórico e visualizar gráficos interativos de **Preço**, **P/L** (apenas ações), **P/VP** e **Dividend Yield** no período selecionado (1A, 2A, 3A, 5A ou 10A).
   * Os gráficos e textos se adaptam automaticamente à mudança de tema do dashboard.

4. **Análise Setorial Dinâmica (Drill-down)**:
   * Uma aba exclusiva para análise setorial mostrando médias ponderadas de Score, DY e P/L.
   * Clique em qualquer setor para abrir um modal contendo as empresas correspondentes ordenadas por Score (qualidade) e Dividend Yield (filtro de boa opção). Clicar na empresa a partir deste modal redireciona instantaneamente para o seu modal de histórico individual.

---

## 🛠️ Arquitetura do Sistema

O projeto adota uma arquitetura enxuta dividida em quatro componentes principais:

```
├── data/
│   └── investments.db        # Banco SQLite contendo dados de ativos e JSON de históricos
├── src/
│   ├── database.py           # Gerenciamento de conexão, esquemas e inserções SQLite
│   ├── analyzer.py           # Regras analíticas fundamentalistas (Graham, Bazin e Scorecards)
│   ├── ingestion.py          # Script de coleta paralela/lote usando yfinance e tratamento de dados
│   ├── generator.py          # Script Python que processa o banco e renderiza o HTML usando Jinja2
│   └── templates/
│       └── dashboard_template.html  # Template estático HTML + CSS + JS (Chart.js)
├── dashboard.html            # Interface web compilada gerada pelo generator.py
└── requirements.txt          # Dependências do projeto
```

---

## 📊 Critérios de Pontuação (Scorecard 0-5)

### Ações (Base Graham & Bazin)
1. **Dividend Yield >= 6%** (Critério de Décio Bazin para renda passiva).
2. **P/L (Preço/Lucro) <= 15** (Critério de Benjamin Graham para liquidez e valuation).
3. **P/VP (Preço/Valor Patrimonial) <= 1.5** (Critério de Benjamin Graham para ativos descontados).
4. **ROE (Return on Equity) >= 10%** (Filtro de eficiência e rentabilidade corporativa).
5. **Margem de Segurança de Graham** (Preço Atual < Valor Justo de Graham: $V_i = \sqrt{22.5 \times LPA \times VPA}$).

### FIIs e FIAGROs
1. **P/VP Ideal** ($0.85 \le \text{P/VP} \le 1.05$) - Evita distorções de fundos em apuros e ágios abusivos.
2. **Preço Limite** ($\text{P/VP} \le 1.15$) - Margem de segurança de valuation de tijolo/crédito.
3. **Dividend Yield Anual >= 8%** (Retorno de rendimentos mínimo recomendado).
4. **Dividend Yield Anual >= 10%** (Indicador de alta performance de distribuição).
5. **Distribuição Ativa** (Rendimento anual estimado > R$ 0.00).

---

## 🚀 Como Executar o Projeto

### Pré-requisitos
* Python 3.10 ou superior.

### Passo 1: Instalar as Dependências
Crie um ambiente virtual e instale os pacotes necessários especificados no `requirements.txt`:
```powershell
# Criação do ambiente virtual
python -m venv .venv

# Ativação (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# Instalação de dependências
pip install -r requirements.txt
```

### Passo 2: Executar a Ingestão de Dados (Ingestion)
O script de ingestão irá inicializar o banco de dados SQLite e carregar as cotações, múltiplos e histórico de 10 anos via Yahoo Finance para os 143 ativos monitorados (97 ações, 32 FIIs e 14 FIAGROs):
```powershell
python src/ingestion.py
```
*Nota: A ingestão leva em torno de 2.5 a 3 minutos para respeitar a limitação de requisições do yfinance (`time.sleep(1)` entre ativos).*

### Passo 3: Gerar o Dashboard
Compile os dados salvos no banco SQLite no arquivo estático de visualização:
```powershell
python src/generator.py
```

### Passo 4: Visualizar no Navegador
Abra o arquivo `dashboard.html` gerado na raiz do projeto diretamente no seu navegador de preferência ou suba um servidor HTTP local para melhor visualização dos gráficos dinâmicos:
```powershell
# Iniciar servidor local
python -m http.server 8000
```
Acesse no seu navegador: `http://localhost:8000/dashboard.html`
