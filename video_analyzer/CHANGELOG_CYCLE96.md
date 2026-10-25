# Ciclo 96 — matemática hipotética PLO5/PLO6 com entrada humana explícita

## Escopo

`hand_math_scenario_run.py` recebe (1) um JSON original de `hand_math_intake.py`, (2) uma **cópia preenchida manualmente**, e (3) um caminho novo para o relatório JSON. É um executor **offline, assíncrono e de hipóteses**, sem leitura de poker ao vivo, integração com sites, apostas ou seleção automática de cortes.

```bash
cd video_analyzer
python hand_math_scenario_run.py intake_original.json intake_preenchido.json resultado_hipotetico.json
```

## Entrada e proteção

- Os campos protegidos do intake (IDs, mesas, timestamps, flags de bloqueio, hashes, referências e contagens) devem permanecer **idênticos** ao original. Somente `manual_scenario_draft` pode ser preenchido; o arquivo original deve continuar imutável.
- Exigir `human_confirmed: true` no cenário e em **cada** um dos cinco campos, com `source: "independent_manual_video_review"`, timestamp no intervalo e confiança numérica de 0 a 1. Isso registra **declaração humana**, não autentica o vídeo nem prova a observação.
- Informar `hero_cards` (5 ou 6 cartas), `board` (0 a 5), `observed_action` (`call` ou `raise`), `pot_before_action`, `call_amount`, `call_range` (lista de `{ "cards": [..], "weight": 1.0 }`), `monte_carlo_trials` (1 a 5000), `monte_carlo_seed` (inteiro), `model_notes` e `observation_confidence`.
- Informar `model_assumptions` com `heads_up`, `all_in_no_future_betting`, `no_rake`, `no_side_pots` e `no_icm` todos `true`, e `hero_extra_chips` / `villain_extra_chips_if_called` ambos `null` para `call`. Para `raise`, informar os dois valores e `fold_probability` (0 a 1).
- Máximo de 8 cenários executados por lote e 128 combinações de mãos no range de cada cenário. Mãos adversárias incompatíveis, cartas duplicadas, pesos inválidos e alterações nos campos protegidos são rejeitados. Cenários incompletos são bloqueados e reportados, sem interromper os demais.
- Leitura de arquivos limitada a 16 MiB; entrada por symlink rejeitada; chaves JSON duplicadas e constantes NaN/Infinity rejeitadas; saída existente nunca sobrescrita.

## Resultado e limites

Calcula equity de showdown PLO5/PLO6 com **exatamente duas cartas privadas e três comunitárias**, usando `estimate_weighted_range_equity`. Para `call`, EV simplificado vs fold=0 usa `simplified_call_ev`. Para `raise`, usa `heads_up_all_in_raise_ev` com probabilidade de fold manual. Inclui semente, trials, vitórias/empates/derrotas, range, estimativa e intervalo de amostragem de 95% de equity e EV.

**Todos os resultados são hipóteses, não reconstruções verificadas**: o intervalo de confiança quantifica apenas erro de amostragem Monte Carlo, não incerteza de OCR, limites do vídeo, ranges ou modelo. O cálculo não prova erro estratégico. `ready_for_equity_or_ev`, `hand_reconstruction_verified`, `strategic_error_established` e `automatic_clip_selection_authorized` permanecem `false` na saída, mesmo quando há uma simulação hipotética.

## Testes locais deste ciclo

`python -m unittest -v test_hand_math_scenario_run test_hand_math_intake test_equity test_range_ev test_equity_confidence test_range_sensitivity`

Testes sintéticos cobrem PLO5/PLO6, call/raise, resultados determinísticos, board incompleto, semente fixa, quatro mesas, adulteração de metadados, confiança/timestamps, ranges inválidos, hipóteses de modelo, integridade de arquivos e ausência de autorização estratégica. Não representam validação com vídeos reais. Suíte completa, CI remoto, OCR e sessões longas ainda não verificados.

## Bloqueio

Falta uma gravação PLO5/PLO6 autorizada de 3–5 minutos e anotações humanas independentes para medir reconstrução e OCR. Nenhum gasto, credencial ou infraestrutura adicional é necessário para os testes sintéticos.
