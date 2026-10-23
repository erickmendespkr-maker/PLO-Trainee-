# PLO Trainee — worksheet de hipóteses matemáticas (ciclo 49)

**Escopo:** gravações offline de PLO5/PLO6, até quatro mesas. Este módulo **não** analisa vídeo, não calcula equity/EV e não libera decisões para cálculos automaticamente.

## Fluxo local

1. Gere uma fila de decisões a partir de evidências com timestamps.
2. Revise o vídeo original e exporte um rascunho do editor HTML.
3. Valide o rascunho e produza um handoff com `activity_review_handoff.py`.
4. Execute:

```bash
python video_analyzer/activity_scenario_worksheet.py handoff.json worksheet.json
```

O JSON de saída contém as decisões e os campos confirmados manualmente, mas deixa `opponent_range`, `range_alternatives`, `fold_probability`, `future_betting_model`, `rake_model`, `trials` e `seed` como `null`. Cada cenário permanece com `ready_for_equity_or_ev=false` e mantém os bloqueios existentes. O SHA-256 do handoff é registrado para rastreabilidade.

**Importante:** mesmo com todos os campos preenchidos, a planilha de hipóteses não substitui auditoria independente das imagens e PTS nem validação de ranges. Não reutilize este JSON como manifesto autorizado de análise. Use a ponte de evidências auditadas e o gate de cenários apropriados antes de chamar o motor matemático.

## Testes

```bash
cd video_analyzer
python -m unittest test_activity_scenario_worksheet -v
python -m unittest discover -p 'test_*.py' -q
```

Demonstrações e testes usam dados sintéticos. Ainda falta vídeo real autorizado para medir OCR, limites de mãos e precisão de decisões.
