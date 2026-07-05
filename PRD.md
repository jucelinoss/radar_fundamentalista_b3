# PRD — Product Requirements Document

## Screener Fundamentalista B3

**Versão:** 2.0  
**Data:** 2026-07-04  
**Status:** Aprovado

---

## 1. Resumo Executivo

Sistema automatizado de análise, triagem (screening) e visualização fundamentalista de ativos negociados na bolsa brasileira (B3). O projeto avalia a saúde financeira, precificação e qualidade de **97 ações**, **32 FIIs** e **14 FIAGROs** com base nas teorias de Benjamin Graham (value investing) e Décio Bazin (dividendos), exibindo os resultados em um dashboard web estático.

---

## 2. Objetivos do Produto

### 2.1 Missão
Democratizar o acesso à análise fundamentalista de qualidade para investidores brasileiros, eliminando a necessidade de planilhas manuais ou assinaturas caras de plataformas de dados.

### 2.2 Metas de Negócio
| Métrica | Meta |
|---|---|
| Cobertura de ativos B3 | ≥ 140 ativos (ações + FIIs + FIAGROs) |
| Frescor dos dados | ≤ 24h desde última atualização |
| Tempo de ingestão total | ≤ 60 segundos (paralelismo habilitado) |
| Disponibilidade do dashboard | 99% (servido como arquivo estático) |
| Testes unitários (analyzer) | 100% das fórmulas cobertas |

---

## 3. Personas

| Persona | Descrição | Necessidades |
|---|---|---|
| **Investidor Pessoa Física** | Investidor individual que busca alocar em ações e FIIs | Visão rápida dos melhores ativos por score, setor e índice. |
| **Analista Amador** | Entusiasta de finanças que quer aprofundar | Gráficos históricos, múltiplos, e margem de segurança. |
| **Gestor de Pequeno Porte** | Profissional que assessora carteiras de clientes | Relatório setorial, top picks, dados exportáveis. |

---

## 4. Funcionalidades

### 4.1 MVP Atual (v2.0)

| Funcionalidade | Prioridade | Status |
|---|---|---|
| **Ingestão automática** via Yahoo Finance (yfinance) | P0 | ✅ |
| **Scorecard quantitativo** (0-5) para ações (Graham/Bazin) | P0 | ✅ |
| **Scorecard quantitativo** (0-5) para FIIs e FIAGROs | P0 | ✅ |
| **Dashboard web estático** com tabelas, filtros e gráficos | P0 | ✅ |
| **Gráficos interativos** de histórico (preço, P/L, P/VP, DY) | P1 | ✅ |
| **Análise setorial** com drill-down | P1 | ✅ |
| **Índices de mercado** (IBOV, IDIV, SMLL) por ticker | P1 | ✅ |
| **Pipeline paralelo** com retry e logging | P0 | ✅ (v2.0) |
| **Refresh via API** (POST /api/refresh) | P1 | ✅ |
| **Tema claro/escuro** persistente | P2 | ✅ |
| **Responsividade mobile** | P2 | ✅ |

### 4.2 Futuro (Roadmap)

| Funcionalidade | Prioridade | Previsão |
|---|---|---|
| Comparação lado a lado de ativos | P2 | Q3 2026 |
| Exportar para CSV/Excel | P2 | Q3 2026 |
| Alertas de preço (e-mail/telegram) | P2 | Q4 2026 |
| Backtesting de scorecard | P3 | Q4 2026 |
| Dados fundamentalistas via BRAPI (fallback) | P3 | 2027 |

---

## 5. Arquitetura do Sistema

```
┌────────────────────────────────────────────────────────────┐
│                    DATA LAYER                              │
│  Yahoo Finance API  ──▶  ingestion.py  ──▶  analyzer.py   │
│                        (paralelo, retry)  (Graham, Bazin) │
│                                │                           │
│                                ▼                           │
│                        database.py                         │
│                     (SQLite via context manager)            │
│                     data/investments.db                    │
└────────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────────┐
│                   GENERATION LAYER                         │
│  generator.py  ──▶  Jinja2 Template  ──▶  dashboard.html  │
│  (sectores, top picks,   (dashboard_template.html)  (574KB)│
│   indices resolution)                                       │
└────────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────────┐
│                   DELIVERY LAYER                            │
│  ┌──────────────┐    ┌──────────────────┐                  │
│  │ server.py    │    │ GitHub Actions   │                  │
│  │ (dev server) │    │ (cloud schedule) │                  │
│  │ Port 8000    │    │ Daily 08:00 BRT  │                  │
│  └──────────────┘    └──────────────────┘                  │
│         │                                                    │
│         ▼                                                    │
│  Browser / GitHub Pages / Static Host                        │
└────────────────────────────────────────────────────────────┘
```

### 5.1 Stack Tecnológica

| Componente | Tecnologia | Justificativa |
|---|---|---|
| **Linguagem** | Python 3.10+ | Maturidade, ecossistema financeiro (yfinance, pandas) |
| **Web Framework** | Nenhum (static site) | Zero runtime backend, deploy simplificado |
| **Database** | SQLite | Simplicidade, sem servidor, portabilidade |
| **Templates** | Jinja2 | Template engine padrão do Python |
| **Charts** | Chart.js (CDN) | Leve, interativo, gratuito |
| **Ingestão** | yfinance + concurrent.futures | Dados gratuitos, paralelismo nativo |
| **CI/CD** | GitHub Actions | Schedule diário, commit automático |
| **Testes** | Pytest | Padrão da indústria Python |

---

## 6. Critérios de Scorecard

### 6.1 Ações (0-5)

| Critério | Fórmula | Peso |
|---|---|---|
| Dividend Yield ≥ 6% (Bazin) | `dy >= 0.06` | 1 |
| P/L ≤ 15 (Graham) | `0 < pe <= 15` | 1 |
| P/VP ≤ 1.5 (Graham) | `0 < pb <= 1.5` | 1 |
| ROE ≥ 10% | `roe >= 0.10` | 1 |
| Margem de Segurança | `price < graham_price` | 1 |

### 6.2 FIIs / FIAGROs (0-5)

| Critério | Fórmula | Peso |
|---|---|---|
| P/VP entre 0.85 e 1.05 | `0.85 <= pb <= 1.05` | 1 |
| P/VP ≤ 1.15 | `pb <= 1.15` | 1 |
| DY ≥ 8% | `dy >= 0.08` | 1 |
| DY ≥ 10% | `dy >= 0.10` | 1 |
| Distribuição Ativa | `dividend_rate > 0` | 1 |

---

## 7. Requisitos Não Funcionais

| Requisito | Especificação |
|---|---|
| **Performance** | Ingestão completa ≤ 60s (paralelo, 5 workers) |
| **Frescor dos dados** | Máximo 24h desde última atualização |
| **Tamanho do dashboard** | ≤ 1MB (atual: ~574KB) |
| **Tolerância a falhas** | Retry 3x com backoff exponencial em falhas de rede |
| **Logging** | Estruturado, com rotação diária em `logs/` |
| **Testabilidade** | 100% das fórmulas do analyzer cobertas por testes |
| **Segurança** | Zero credenciais no repositório (`.env` no `.gitignore`) |

---

## 8. Pipeline de Dados

### 8.1 Gatilhos de Execução

| Gatilho | Descrição |
|---|---|
| **Manual** | `python src/pipeline.py` |
| **Schedule Local (Windows)** | Task Scheduler diário 08:00 |
| **Schedule Local (Linux/Mac)** | Cron diário 08:00 |
| **Cloud (GitHub Actions)** | Workflow diário 08:00 BRT |
| **Via Dashboard** | Clique no botão "Atualizar Dados" |
| **API** | `POST /api/refresh` |

### 8.2 Etapas do Pipeline

1. **Load Config** — Carregar listas de tickers de `config/tickers.json`
2. **Init DB** — Garantir schema do SQLite
3. **Ingest Stocks** (paralelo) — Fetch → Analyze → Save
4. **Ingest FIIs** (paralelo) — Fetch → Analyze → Save
5. **Ingest FIAGROs** (paralelo) — Fetch → Analyze → Save
6. **Generate Dashboard** — Ler DB → Agregar → Renderizar HTML
7. **Log** — Registrar resultado no banco (`pipeline_log`)

---

## 9. Métricas de Sucesso

| Indicador | Como Medir | Alvo |
|---|---|---|
| **Tempo de ingestão** | Log do pipeline | < 60s |
| **Taxa de sucesso por ticker** | `ok / total` no log | > 90% |
| **Falhas consecutivas** | Log do pipeline | < 3 seguidas |
| **Freshness do dashboard** | `updated_at` no DB | ≤ 24h |
| **Cobertura de testes** | `pytest --cov` | > 80% |

---

## 10. Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Yahoo Finance muda API | Baixa | Alto | Fallback para brapi.dev / HG Brasil (MVPs existentes) |
| Rate limiting do yfinance | Média | Médio | Delay configurável, paralelismo controlado |
| Ticker é cancelado/renomeado | Média | Baixo | `ticker_mappings.json` para resolver mudanças |
| Banco SQLite corrompido | Baixa | Alto | Backup automático no pipeline; `pipeline_log` tabela separada |
| CDN do Chart.js offline | Baixa | Baixo | Gráficos não renderizam, dados da tabela ainda visíveis |

---

## 11. Versionamento

| Versão | Data | Mudanças |
|---|---|---|
| 1.0 | 2025-Q4 | MVP inicial: ingestão sequencial, dashboard estático |
| 1.1 | 2026-Q1 | Scorecards FII/FIAGRO, análise setorial, tema escuro |
| 2.0 | 2026-Q3 | Pipeline paralelo, retry, logging, config externa, testes, CI/CD |

---

*Documento mantido em `PRD.md` na raiz do repositório.*
