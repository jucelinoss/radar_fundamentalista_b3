# Contratos de Funcionalidades

Estes arquivos são a camada operacional curta para IA e desenvolvimento. Leia o contrato da funcionalidade solicitada **antes** de editar código. Os contratos complementam, sem substituir, as especificações em `docs/`.

## Roteamento

| Pedido | Contrato obrigatório |
|---|---|
| Dados, score, fontes, pipeline ou `data.json` | [data-and-analysis.md](data-and-analysis.md) |
| Navegação, Home, tabelas, Top Picks, modais ou gráficos | [ui-and-navigation.md](ui-and-navigation.md) |
| Focus, Selic esperada, curva ou hipóteses futuras | [macro-radar.md](macro-radar.md) |
| Qualquer alteração | [quality-gates.md](quality-gates.md) |

## Formato obrigatório de uma entrega

1. Declare o contrato lido e o escopo exato.
2. Altere somente o dono da funcionalidade.
3. Atualize o contrato quando o comportamento público mudar.
4. Crie ou ajuste ao menos um teste unitário.
5. Informe validações, resultado e impactos conhecidos.

Se houver conflito, a prioridade é: `docs/ANALYSIS_RULES_SPECIFICATION.md` → `docs/UI_UX_SPECIFICATION.md` → este contrato → implementação existente.
