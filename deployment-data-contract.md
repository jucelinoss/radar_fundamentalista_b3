# Contrato de Dados do Deploy

## Goal
Bloquear a publicação quando dados exigidos pelo site ou pelo próximo pipeline estiverem ausentes ou inválidos.

## Tasks
- [x] Validar o artefato do Pages. → Verificar: ausência de arquivo obrigatório falha.
- [x] Inserir a validação antes do upload no workflow. → Verificar: deploy depende da validação.
- [x] Cobrir a validação com testes. → Verificar: artefato completo passa.

## Done When
- [x] `data.json`, histórico do Tesouro e exportações são verificados antes do deploy.
