# Contrato — Dados, Análise e Publicação

## Donos

`src/sources.py`, `src/analyzer.py`, `src/tesouro_analyzer.py`, `src/macro_fetcher.py`, `src/generator.py` e `data.json`.

## Entrada e saída

| Entrada | Saída contratada |
|---|---|
| fontes autorizadas, SQLite e estado macro | registros normalizados no banco e `data.json` |
| ativo/título válido | identificador, dados normalizados, `fundamental_score`, `score_breakdown`, atualização e proveniência |

## Invariantes

1. `fundamental_score` é número finito entre 0 e 10 e é calculado apenas pelas regras do domínio.
2. O breakdown pertence ao mesmo domínio, possui critérios válidos e corresponde ao total publicado.
3. `0` é dado válido; ausência é `null`/ausência explícita. Nunca usar falsidade para converter zero em fallback.
4. Dados de ações, FIIs, FIAGROs e Tesouro não podem ser misturados.
5. Dados de fonte inválidos, infinitos ou fora dos limites de sanidade não podem chegar ao usuário como fatos financeiros válidos.
6. `data.json` deve refletir banco e score publicados, inclusive quando o score é `0.0`.

## Proibições

* Não calcular regra de negócio no frontend.
* Não usar Focus, expectativa, curva projetada ou sinal macro para alterar score, breakdown, P/L, P/VP, DY, ROE, Graham, Bazin ou preço justo.
* Não inventar cotação, expectativa ou histórico para preencher lacuna.
* Não trocar fonte, fórmula, unidade ou fallback sem atualizar a especificação de análise e seus testes.

## Aceite mínimo

- [ ] Fonte, data e condição do dado (atual/cache/demonstração) foram preservadas.
- [ ] Há teste unitário de valor válido, limite e dado ausente/inválido.
- [ ] Score, breakdown e JSON passam nos testes de consistência.
- [ ] Não houve alteração incidental de UI.
