# Bloco 13 — equity heads-up contra ranges declarados

Novo plo5_range_equity.py: Monte Carlo de orçamento fixo, pré-flop/flop/turn/river, exclusivamente PLO5, uma mão adversária. Três formatos: uniform; rank_count (um rank com mínimo/máximo de ocorrências, pesos combinatórios exatos por contagem); weighted_holdings (mãos físicas distintas com pesos inteiros). Remove blockers e cartas mortas declaradas, renormaliza pesos, sorteia runouts sem reposição e aplica exatamente duas cartas privadas e três comunitárias. Semente explícita, 100 a 100.000 amostras, intervalo conservador de Hoeffding de 95% sobre a participação no pote. O intervalo cobre erro de amostragem sob o modelo, não incerteza do range, qualidade OCR ou desempenho real. Nenhum range é inferido por posição/ação; não é GTO nem EV de decisão. Sem serviço externo.

Teste Linux, mão Ks Js 8s 6c 5c, flop 7d Ac 3d, 10.000 simulações por cenário, seed 42, cache de ranking limpo:
| Street | Range | Equity | IC 95% | Tempo |
|---|---|---:|---|---:|
| Preflop | uniforme | 51,555% | 50,197–52,913% | 1,190 s |
| Preflop | pelo menos 2 ases | 45,080% | 43,722–46,438% | 1,102 s |
| Flop | uniforme | 33,220% | 31,862–34,578% | 1,056 s |
| Flop | pelo menos 2 ases | 18,805% | 17,447–20,163% | 1,052 s |

Cenários hipotéticos a partir de cartas de uma mão anteriormente anotada, não leitura de range efetivo ou recomendação. 25 testes selecionados aprovados em 5,591 s (7 novos, 18 regressões matemáticas), incluindo suporte combinatório, exclusão de blockers, amostragem ponderada e comparação com equity exata river em um cenário. Blobs locais/remotos idênticos: 4c8327c9ba8276f8f7a8bd434b5d393332360807 e 9fd589f0fc49432cff9100153863708674eac3a5. Main preservada. Não checkout integral.

Próximo: permitir cenários de ranges por posição explicitamente declarados, comparação de cenários e pot odds/EV condicional com ação e valores verificados; avaliar multiway e otimizações antes de ampliar. Recuperação CSV/SQLite, integração externa, validação Suprema, OCR, histórico e liquidação continuam pendentes. Não apresentar estimativa como estratégia GTO.
