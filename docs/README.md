# Documentação do Radar Fundamentalista B3

## Especificações vigentes

| Documento | Use quando precisar... | Não use para... |
|---|---|---|
| [ANALYSIS_RULES_SPECIFICATION.md](ANALYSIS_RULES_SPECIFICATION.md) | alterar fontes, normalização, métricas, fórmulas, limites, score ou análise macro | decidir posição de elementos, layout ou comportamento de modal |
| [UI_UX_SPECIFICATION.md](UI_UX_SPECIFICATION.md) | alterar telas, navegação, cards, tabelas, filtros, modais, gráficos, tema ou responsividade | alterar critérios de análise, fontes ou cálculos |
| [TEST_SPECIFICATION.md](TEST_SPECIFICATION.md) | criar ou revisar testes, qualidade financeira, consistência de dados e aceite de features | substituir regras de negócio ou contratos de UI |
| [contracts/](contracts/README.md) | aplicar contratos curtos por funcionalidade antes de editar código | substituir as especificações completas |
| [ARCHITECTURE.md](ARCHITECTURE.md) | entender pipeline, camadas e fluxo técnico | substituir os contratos de negócio ou UI |

## Material histórico

* [SCORE_RULES.md](SCORE_RULES.md) é uma ponte para links antigos; sua regra não é vigente.
* `v3/` contém histórico de implementação e decisões passadas; não é fonte para novas alterações.

## Ordem de consulta para IA e desenvolvimento

1. Leia este índice e selecione o documento dono do pedido.
2. Leia o contrato da área alterada e seus critérios de aceite.
3. Consulte a implementação indicada no documento antes de modificar código.
4. Se a alteração alcançar negócio e UI, atualize os dois contratos e valide as regressões declaradas em cada um.
