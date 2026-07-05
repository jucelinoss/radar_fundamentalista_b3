# Changelog — Radar Fundamentalista B3

## [2.1.1] — 2026-07-05

### Refatorado
- Fase 2 concluída: todas as funções > 70 linhas quebradas em helpers menores
  - `database.py:init_db`: 71 → 8 linhas (extraído `_create_stocks_table`, `_create_fiis_table`, `_create_pipeline_log_table`)
  - `exporter.py:export_top_picks`: 78 → 51 linhas (extraído `_build_top_picks_list`, reuso entre FIIs e FIAGROs)
  - `ingestion.py:ingest_single_asset`: 74 → 37 linhas (extraído `_fetch_with_retry`, `_persist_asset`)
  - `ingestion.py:run_full_ingestion`: 90 → 58 linhas (extraído `_prepare_ticker_lists`, `_log_pipeline_summary`, `_record_pipeline_run`)
- Logging duplicado entre módulos consolidado

### Documentação
- CHANGELOG.md adicionado
- CONTRIBUTING.md adicionado
- PRD.md sincronizado com status real de todas as fases (0-6 concluídas)

### Config
- Consistência validada entre `tickers.json`, `indices.json` e `ticker_mappings.json`
- MBRF3 adicionado ao `indices.json`

---

## [2.1.0] — 2026-Q3

### Adicionado
- Carga incremental: apenas tickers desatualizados são buscados
- PWA (instalável, offline, service worker)
- Export IA: JSON otimizado para análise com IA (`export_top_picks.json`)
- CSV/JSON exports completos

### Modificado
- Refatoração geral do código (type hints, constantes extraídas, logging centralizado)
- Limpeza de código morto

---

## [2.0.0] — 2026-Q3

### Adicionado
- Pipeline paralelo com ThreadPoolExecutor (5 workers)
- Retry com exponential backoff em falhas de rede
- Logging estruturado com rotação diária
- Config externa via `config/tickers.json`
- CI/CD com GitHub Actions (testes → pipeline → deploy)
- Testes unitários e de integração (pytest)
- Progress tracking thread-safe para web UI

---

## [1.1.0] — 2026-Q1

### Adicionado
- Scorecards para FIIs e FIAGROs (0-5)
- Análise setorial com drill-down
- Tema escuro persistente
- Gráficos interativos de histórico (Chart.js)

### Modificado
- Dashboard responsivo para mobile

---

## [1.0.0] — 2025-Q4

### Adicionado
- MVP inicial: ingestão sequencial via yfinance
- Scorecard quantitativo para ações (Graham/Bazin, 0-5)
- Dashboard web estático com tabelas e filtros
- Servidor HTTP local para desenvolvimento
