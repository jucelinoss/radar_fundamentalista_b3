# Radar Fundamentalista B3

[![Pipeline Status](https://github.com/jucelinoss/radar_fundamentalista_b3/actions/workflows/daily-pipeline.yml/badge.svg?branch=main)](https://github.com/jucelinoss/radar_fundamentalista_b3/actions/workflows/daily-pipeline.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://python.org)
[![Code size](https://img.shields.io/github/languages/code-size/jucelinoss/radar_fundamentalista_b3)]()

Sistema automatizado de análise fundamentalista para **ações, FIIs e FIAGROs** da B3. Gera um dashboard web estático com scorecards quantitativos (Graham, Bazin), gráficos interativos e suporte PWA — tudo atualizado diariamente via GitHub Actions.

📊 **Dashboard:** [`https://jucelinoss.github.io/radar_fundamentalista_b3/`](https://jucelinoss.github.io/radar_fundamentalista_b3/)

---

## Funcionalidades

- **249 ativos monitorados:** 91 ações, 120 FIIs, 38 FIAGROs
- **Scorecards 0-5:** Graham (valor justo), Bazin (preço teto), P/L, P/VP, ROE, margem de segurança
- **Gráficos interativos:** Preço, P/L, P/VP, Dividend Yield (1A a 10A) com Chart.js
- **Filtros por índice:** IBOV, IDIV, SMLL — badges e seletor dinâmico
- **Análise setorial:** Médias ponderadas por setor com drill-down
- **Tema claro/escuro:** Persistente com `prefers-color-scheme`
- **PWA:** Instalável como aplicativo, funciona offline (caching do service worker)
- **Export:** CSV por categoria + JSON completo + Top Picks (formato otimizado para IA)
- **Deploy automático:** GitHub Actions diário, deploy condicional (só se dados mudaram)

---

## Estrutura do Projeto

```
radar_fundamentalista_b3/
├── .github/workflows/
│   └── daily-pipeline.yml     # CI/CD: testes → ingestão → deploy
├── config/
│   ├── tickers.json           # Lista mestra de tickers + config pipeline
│   └── indices.json           # Mapeamento ticker → índice B3
├── data/
│   ├── investments.db         # SQLite (stocks, fiis, fiagros, pipeline_log)
│   ├── ticker_mappings.json   # Renomeações/delistings de tickers
│   ├── export_stocks.csv      # Export ações
│   ├── export_fiis.csv        # Export FIIs
│   ├── export_fiagros.csv     # Export FIAGROs
│   ├── export_ativos.json     # Export completo JSON
│   ├── export_top_picks.json  # Top picks formato IA
│   ├── status.json            # Status em tempo real (para web UI)
│   └── failed_tickers.log     # Log de falhas de ingestão
├── docs/
│   ├── ARCHITECTURE.md        # Documentação da arquitetura
│   └── architecture.html      # Diagrama visual interativo
├── icons/
│   └── icon.svg               # Ícone PWA
├── scripts/
│   ├── analyze_top_picks.py   # CLI: analisar top picks
│   └── query_top_assets.py    # CLI: consultar ativos
├── src/
│   ├── __init__.py            # Marcador de pacote
│   ├── analyzer.py            # Motor de análise (Graham, Bazin, score)
│   ├── database.py            # Persistência SQLite
│   ├── exporter.py            # Export CSV/JSON/Top Picks
│   ├── generator.py           # Geração do dashboard HTML
│   ├── ingestion.py           # Ingestão paralela de dados
│   ├── pipeline.py            # Orquestrador CLI
│   ├── server.py              # Servidor HTTP local
│   ├── sources.py             # Fontes de dados (brapi.dev + yfinance)
│   ├── templates/
│   │   ├── dashboard_template.html  # Template Jinja2 (1.953 linhas)
│   │   └── pwa/manifest.json        # Manifest PWA
│   └── tests/
│       ├── conftest.py         # Fixtures compartilhadas
│       ├── test_analyzer.py    # 36 testes: analyzer
│       ├── test_sources.py     # 27 testes: sources (mockados)
│       ├── test_pipeline_integration.py  # 42 testes: pipeline
│       ├── test_integration_sources.py   # 6 testes: brapi.dev live
│       └── utils.py            # Helpers de mock
├── dashboard.html             # Dashboard gerado (~7.900 linhas)
├── manifest.json              # Manifest PWA (raiz)
├── service-worker.js          # Service Worker PWA
├── pyproject.toml             # Config do pacote Python (v2.1.0)
├── requirements.txt           # Dependências
├── PRD.md                     # Documento de requisitos
├── CHANGELOG.md               # Histórico de versões
├── CONTRIBUTING.md            # Guia de contribuição
└── .env.example               # Template de variáveis de ambiente
```

---

## Stack Tecnológica

| Componente | Tecnologia |
|-----------|-----------|
| **Linguagem** | Python 3.12 |
| **Fontes de dados** | brapi.dev API (primário) + yfinance (fallback) |
| **Banco de dados** | SQLite |
| **Template** | Jinja2 |
| **Gráficos** | Chart.js (CDN) |
| **Export** | CSV, JSON |
| **Testes** | pytest + pytest-mock (121 testes) |
| **CI/CD** | GitHub Actions |
| **Hospedagem** | GitHub Pages |
| **PWA** | Service Worker + Manifest |

---

## Como Executar Localmente

```bash
# 1. Clone
git clone https://github.com/jucelinoss/radar_fundamentalista_b3.git
cd radar_fundamentalista_b3

# 2. Ambiente virtual
python -m venv .venv
source .venv/bin/activate      # Linux/macOS
.venv\Scripts\Activate.ps1     # Windows

# 3. Dependências
pip install -r requirements.txt

# 4. Ingestão de dados
python src/ingestion.py        # ou: python src/pipeline.py

# 5. Gerar dashboard
python src/generator.py        # ou: python src/pipeline.py --generate-only

# 6. Servidor local (opcional)
python src/server.py           # http://localhost:8585

# Opção: pipeline completo
python src/pipeline.py
```

---

## Critérios de Pontuação (Scorecard 0-5)

### Ações
1. **Dividend Yield ≥ 6%** (critério Bazin)
2. **P/L ≤ 15** (Graham)
3. **P/VP ≤ 1.5** (Graham)
4. **ROE ≥ 10%**
5. **Margem de segurança de Graham** (preço atual < √(22.5 × LPA × VPA))

### FIIs e FIAGROs
1. **P/VP ideal** (0.85 ≤ P/VP ≤ 1.05)
2. **Preço limite** (P/VP ≤ 1.15)
3. **DY anual ≥ 8%**
4. **DY anual ≥ 10%** (alta performance)
5. **Distribuição ativa** (dividendo anual estimado > R$ 0)

---

## Arquitetura

Para uma visão detalhada da arquitetura, fluxo de dados e CI/CD:

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — Documentação textual
- [`docs/architecture.html`](docs/architecture.html) — Diagrama interativo com Mermaid
- [`PRD.md`](PRD.md) — Documento de requisitos do produto

---

## Testes

```bash
# Todos os testes (exceto rede)
python -m pytest src/tests/ -v

# Com testes de rede (brapi.dev, yfinance)
python -m pytest src/tests/ -v --run-network

# Apenas um arquivo
python -m pytest src/tests/test_analyzer.py -v

# Cobertura
python -m pytest src/tests/ --cov=src
```

**86 testes unitários** passam sem dependência de rede. **35 testes de integração** exigem `--run-network`.

---

## Licença

MIT
