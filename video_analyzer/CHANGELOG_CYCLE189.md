# Ciclo 189 — Monte Carlo PLO5/PLO6 offline, com entrada revisada manualmente

Escopo conforme `docs/VIDEO_ANALYZER_SCOPE.md`: somente análise assíncrona de gravações. Este módulo matemático **não** se conecta a plataformas de pôquer, não identifica jogadores e não aceita automaticamente OCR como fato.

## Entregas
- `offline_plo_equity_monte_carlo.py`: avaliador de mãos Omaha PLO5/PLO6 usando **exatamente 2 cartas privadas e 3 do board**, inclusive wheel, straight flush, quads, full house e desempates.
- Estimativa Monte Carlo heads-up no flop/turn/river, com semente fixa, número de iterações, vitória/empate/derrota e equity (empate vale metade).
- Modelo adversário explícito `uniform` ou `weighted_combos` (combinações de 5 ou 6 cartas com pesos); remoção de combinações bloqueadas por cartas visíveis. Não há inferência de range por OCR.
- Intervalo aproximado de 95% baseado na variância amostral dos resultados 0/0,5/1, **apenas erro de amostragem**, não incerteza sobre ranges, OCR ou identificação do jogador.
- EV incremental **somente de call no showdown heads-up** quando `pot_now` e `call_cost` são fornecidos: `equity * (pot_now + call_cost) - call_cost`. Supõe pote atual incluindo a aposta adversária, sem rake, side pots ou futuras apostas. Fold incremental = 0; raise EV não implementado.
- Validação estrita de cartas, duplicatas, pesos, semente, parâmetros, JSON e proibição de sobrescrever o arquivo de saída. Requer afirmação explícita `manual_review_confirmed: true`, sem alegar que essa revisão foi comprovada.

## Como reproduzir (offline)

```bash
cd video_analyzer
python offline_plo_equity_monte_carlo.py examples/offline_plo6_manual_synthetic.json novo_resultado.json
python -m unittest -v test_offline_plo_equity_monte_carlo
```

O exemplo é **inteiramente sintético**: PLO6, 2.000 iterações, semente 42, flop 2s/3s/4s e range adversário uniforme. No ambiente Python 3.13 testado: equity `0.847`, IC aproximado `[0.8312189064302524, 0.8627810935697475]` e EV de call `80.875` fichas sob as hipóteses do modelo. Esses números **não** são recomendações de jogada real.

## Testes executados localmente
- 20 testes novos aprovados, incluindo regra 2+3, ranking de mãos, cenários sintéticos de vitória/derrota/empate certos, PLO6, bloqueadores de range, EV de call, reprodutibilidade, JSON malformado e rejeição de sobrescrita.
- 215 testes aprovados na seleção disponível no pacote local do Ciclo 188, incluindo os 20 novos, após restaurar as fixtures sintéticas do pacote. **Não é a suíte integral do repositório remoto.**
- CLI sintético com 2.000 simulações executado localmente, produzindo JSON de saída e o resultado acima.
- Nenhum teste foi executado por GitHub Actions.

## Não verificado e bloqueios
- Não há ligação automática entre evidência OCR/ROI, mão reconstruída e entrada matemática. `manual_review_confirmed` é uma afirmação de entrada, não uma verificação independente.
- Ainda faltam vídeo real autorizado e anotado de 3–5 minutos, validação no Windows, sessão real de 40–60 minutos e avaliação de ranges adversários reais.
- Não há cálculo multiway, pré-flop, EV de raise/fold equity, efeitos de futuras apostas, rake ou side pots; a fórmula de call é um modelo terminal simplificado.
- A CI normal pode ter cobertura inadequada para amostras pequenas ou equity próxima de 0/1; não deve ser interpretada como intervalo de incerteza estratégica.

## Próximo ciclo
Vincular uma mão revisada a dados matemáticos sem promover automaticamente OCR incerto; executar teste de integração positivo com um único conjunto sintético coerente do vídeo até o clipe e o relatório; expandir validação de equity com referências independentes.
