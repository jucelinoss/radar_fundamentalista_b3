# Persistência do Histórico no GitHub Pages

## Goal
Publicar dados gerados sem versioná-los e restaurar cinco anos de histórico do Tesouro a partir da implantação anterior.

## Tasks
- [x] Limitar o histórico do Tesouro a cinco anos corridos. → Verificar: pontos mais antigos são removidos.
- [x] Restaurar o histórico publicado antes do pipeline e incluí-lo no artefato do Pages. → Verificar: primeira execução funciona sem arquivo prévio.
- [x] Reconstruir a série a partir do `data.json` publicado na primeira migração. → Verificar: implantação anterior sem arquivo de histórico não perde os pontos existentes.
- [x] Ignorar os estados gerados no Git sem apagar a cópia de trabalho. → Verificar: Git não lista os JSONs como rastreados.
- [x] Validar testes e sintaxe. → Verificar: suíte afetada passa.

## Done When
- [x] O Pages publica `data/tesouro_history.json` e a execução seguinte o reutiliza.
- [x] Nenhum JSON de estado gerado permanece versionado.
