# Contribuindo — Radar Fundamentalista B3

Obrigado por considerar contribuir! Este documento guia como configurar o ambiente, rodar testes, e submeter mudanças.

## Ambiente de Desenvolvimento

### Pré-requisitos
- Python 3.10+
- Git

### Setup

```bash
# Clone o repositório
git clone https://github.com/jucelinoss/radar_fundamentalista_b3.git
cd radar_fundamentalista_b3

# Crie e ative o virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate

# Instale as dependências
pip install -r requirements.txt

# Instale dependências de desenvolvimento (opcional, para testes)
pip install pytest pytest-mock pytest-cov
```

### Token brapi.dev (opcional)
O sistema funciona sem token (usa yfinance como fallback), mas para dados mais rápidos:
1. Crie uma conta gratuita em [brapi.dev/dashboard](https://brapi.dev/dashboard)
2. Copie `.env.example` para `.env` e adicione seu token:
   ```
   BRAPI_TOKEN=seu_token_aqui
   ```

## Executando Testes

### Testes unitários (sem rede)
```bash
python -m pytest src/tests/ -v
```

### Testes completos (com conectividade de rede)
```bash
python -m pytest src/tests/ -v --run-network
```

### Com cobertura
```bash
python -m pytest src/tests/ --cov=src
```

## Executando o Pipeline

```bash
# Pipeline completo (ingestão + dashboard)
python src/pipeline.py

# Apenas ingestão
python src/ingestion.py

# Apenas geração do dashboard
python src/generator.py

# Exportar dados
python src/exporter.py

# Servidor local
python src/server.py
# Acesse: http://localhost:8585
```

## Estrutura do Projeto

```
.
├── config/                    # Configurações de tickers e índices
│   ├── tickers.json           # Lista mestra de ativos monitorados
│   └── indices.json           # Mapeamento ticker → índice B3
├── data/                      # Dados gerados (DB, exports, logs)
│   ├── investments.db         # SQLite com dados fundamentalistas
│   ├── ticker_mappings.json   # Renomeações/delistings de tickers
│   └── export_*.{csv,json}    # Arquivos exportados
├── docs/                      # Documentação da arquitetura
├── src/                       # Código fonte
│   ├── analyzer.py            # Motor de análise (Graham, Bazin)
│   ├── database.py            # Persistência SQLite
│   ├── exporter.py            # Export CSV/JSON
│   ├── generator.py           # Geração do dashboard HTML
│   ├── ingestion.py           # Ingestão paralela de dados
│   ├── pipeline.py            # Orquestrador CLI
│   ├── server.py              # Servidor HTTP local
│   ├── sources.py             # Fontes de dados (brapi.dev + yfinance)
│   └── tests/                 # Testes
└── dashboard.html             # Dashboard gerado
```

## Padrões de Código

### Estilo
- Type hints obrigatórios em todas as funções públicas
- `snake_case` para funções e variáveis
- `UPPER_CASE` para constantes
- Documentação em docstrings (inglês para código técnico)

### Commits
- Mensagens claras e concisas em português
- Prefixos sugeridos: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`

### Pull Requests
1. Crie um branch a partir de `main`
2. Faça mudanças pequenas e focadas
3. Garanta que todos os testes passem
4. Atualize o `CHANGELOG.md` se aplicável
5. Abra o PR com descrição clara do que mudou e por quê

## Reportando Problemas

Abra uma [issue no GitHub](https://github.com/jucelinoss/radar_fundamentalista_b3/issues) com:
- Descrição do problema
- Passos para reproduzir
- Comportamento esperado vs. observado
- Logs relevantes (se aplicável)

## Licença

MIT — veja o arquivo [LICENSE](LICENSE) para detalhes.
