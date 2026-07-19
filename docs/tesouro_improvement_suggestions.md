# Sugestões de Melhorias para Análise do Tesouro Direto

## 1. Análise do Critério "IR se mantido até o vencimento"

### Contexto Atual
O critério `IR se mantido até o vencimento` é um dos 4 componentes do score, com peso máximo de **2,0 pontos** (20% do total). Ele funciona da seguinte forma:
- ≤ 180 dias: 0,5 pts
- 181-360 dias: 1,0 pts
- 361-720 dias: 1,5 pts
- > 720 dias: 2,0 pts

### Pontos Positivos
- Simplicidade e objetividade (usa apenas `days_to_maturity`).
- Alinhamento com a tabela regressiva de IR do Tesouro Direto.
- Transparência para o usuário.

### Pontos a Considerar
- Assume que o investidor manterá o título até o vencimento (não é verdade para todos).
- Peso elevado (20%) para um critério que depende do comportamento individual do investidor.
- Não mede atratividade intrínseca do título (como taxa ou risco).
- Títulos longos ganham pontos automaticamente, independentemente de sua taxa.

### Sugestão
**Reduzir o peso do IR para 0,5-1,0 pts** e adicionar critérios mais diretamente ligados à atratividade do título.

---

## 2. Critérios Alternativos Propostos (Total: 10 pts)

| Critério | Peso Proposto | Objetivo |
|----------|---------------|----------|
| Taxa Real Contratada/Esperada | 4,0 | Medir retorno acima da inflação (fator principal) |
| Posição Histórica da Taxa | 2,5 | Identificar se o título está barato/caro em relação ao seu passado |
| Potencial de Marcação a Mercado (Duration + Histórico) | 2,0 | Medir potencial de ganho/perda com vendas antecipadas |
| Comparação com Pares por Bucket de Prazo | 1,0 | Comparar com títulos realmente semelhantes (mesmo prazo) |
| Eficiência Tributária (IR) | 0,5 | Premiar títulos longos, mas com peso reduzido |

---

## 3. Inflação Implícita (Breakeven Inflation)

### O que é?
É a taxa de inflação anual média que o mercado "espera" para o período até o vencimento do título, calculada comparando:
- A taxa nominal de um título Prefixado
- A taxa real de um título IPCA+ com o mesmo vencimento (ou prazo muito próximo)

Fórmula exata:
```
Inflação Implícita = [(1 + Taxa Nominal Prefixado) / (1 + Taxa Real IPCA+)] - 1
```

### Por que é útil?
- Compara expectativas de mercado com o Boletim Focus.
- Ajuda a escolher entre Prefixado e IPCA+.
- Identifica desalinhamentos na curva de juros.

### Sugestão de Implementação
**Usar apenas como contexto informativo (não como critério de pontuação)**:
- Calcular por bucket de prazo (0-1y, 1-3y, etc.).
- Adicionar como informação extra no detalhe do título.
- Comparar com as projeções do Focus, se disponíveis.
- Não alterar o score total (mantém a integridade da análise atual).

---

## 4. Código de Exemplo para Inflação Implícita

```python
def calculate_breakeven_inflation_by_bucket(bonds: list[dict[str, Any]]) -> dict[str, float | None]:
    """
    Calcula a inflação implícita (breakeven inflation) por bucket de prazo,
    comparando títulos Prefixados e IPCA+ com prazos próximos.
    
    Retorna um dicionário com buckets como chaves (ex: "1-3y") e a inflação implícita (decimal).
    """
    prefixados = [b for b in bonds if b.get("type") == "Prefixado" and b.get("days_to_maturity") and b.get("buy_yield")]
    ipca_plus = [b for b in bonds if b.get("type") == "IPCA+" and b.get("days_to_maturity") and b.get("buy_yield")]
    
    if not prefixados or not ipca_plus:
        return {}
    
    buckets = [
        ("0-1y", 0, 365),
        ("1-3y", 365, 1095),
        ("3-5y", 1095, 1825),
        ("5-10y", 1825, 3650),
        ("10+y", 3650, float("inf")),
    ]
    
    breakeven = {}
    
    for bucket_name, min_days, max_days in buckets:
        bucket_prefix = [b for b in prefixados if min_days <= b["days_to_maturity"] < max_days]
        bucket_ipca = [b for b in ipca_plus if min_days <= b["days_to_maturity"] < max_days]
        
        if not bucket_prefix or not bucket_ipca:
            breakeven[bucket_name] = None
            continue
        
        median_prefix = sorted(b["buy_yield"] for b in bucket_prefix)[len(bucket_prefix) // 2]
        median_ipca = sorted(b["buy_yield"] for b in bucket_ipca)[len(bucket_ipca) // 2]
        
        be = ((1 + median_prefix) / (1 + median_ipca)) - 1
        breakeven[bucket_name] = round(be, 6)
    
    return breakeven
```
