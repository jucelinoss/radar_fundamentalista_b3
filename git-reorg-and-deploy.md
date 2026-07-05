# Plano: Reorganizar Git e Subir para GitHub

## Situação Atual

```
Commits em master (3 commits, todos locais):
  [1º] 2d7ed54  "v2.0 - Screener B3"       ← TEM A CHAVE DA API ⚠️
  [2º] 6a440e7  "security: move brapi token" ← Remove a chave
  [3º] 8f6c4d4  "feat: GitHub Pages deploy"  ← Workflow atualizado
```

## Problema
O primeiro commit contém a chave da API brapi.dev em `config/tickers.json`.
Antes de subir pro GitHub, precisamos reescrever o histórico sem a chave.

## Objetivo Final

```
master ── (branch vazia / protegida)

dev ── [commit 1] "v1 - Screener Fundamentalista B3"  ← SEM a chave
       [commit 2] "security: token no .env"            ← Corrige
       [commit 3] "feat: GitHub Pages + env var"       + tag v1
```

## Passos

### Fase 1: Reorganizar Branches

- [ ] 1. `git branch dev` — salva os 3 commits atuais na branch dev
- [ ] 2. `git checkout master` + limpar — reseta master para estado vazio (sem commits)
- [ ] 3. `git checkout dev` + `git reset --soft HEAD~3` — desfaz commits, mantém arquivos

### Fase 2: Commits Limpos

- [ ] 4. Remover a chave de `config/tickers.json` (trocar por `"token": ""`)
- [ ] 5. `git add -A` + commit — "v1 - Screener Fundamentalista B3"
- [ ] 6. Ajustes de segurança + commit — "security: token no .env"
- [ ] 7. Workflow Pages + commit — "feat: GitHub Pages deploy"
- [ ] 8. `git tag v1`

### Fase 3: Verificação e Deploy

- [ ] 9. `git log -p --all | grep "3cHb8"` — não deve retornar NADA
- [ ] 10. Criar repositório no GitHub (público)
- [ ] 11. Configurar GitHub Secrets → BRAPI_TOKEN
- [ ] 12. `git remote add origin <url>` + `git push -u origin master dev --tags`
- [ ] 13. Ativar GitHub Pages (Settings → Pages → GitHub Actions)

## Verificação de Sucesso

- [ ] `git log` em master mostra apenas 1 commit vazio
- [ ] `git log` em dev mostra 3 commits limpos
- [ ] Nenhuma ocorrência do token em nenhum commit (`git log -p --all | grep 3cHb8`)
- [ ] GitHub Pages servindo o dashboard em `https://<user>.github.io/investor/`
- [ ] Workflow Actions roda manualmente sem erros
