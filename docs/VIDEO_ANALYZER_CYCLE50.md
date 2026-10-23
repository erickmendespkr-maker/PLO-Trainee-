# Ciclo 50 — editor offline publicado e equity/EV hipotético

Escopo: `docs/VIDEO_ANALYZER_SCOPE.md`. Apenas `feature/plo5-plo6-training`.

## Entregas

- Publicação do `video_analyzer/activity_review_editor.py` e `test_activity_review_editor.py` (antes disponíveis somente no pacote local). Editor HTML sem rede, exporta JSON e exige validação Python antes de qualquer uso posterior. Um clique em “confirmado” **não** autentica o vídeo nem autoriza EV.
- Novo `video_analyzer/activity_hypothetical_math.py` com testes: a partir de um worksheet revisado e de um pedido explícito, executa equity Monte Carlo versus range ponderado informado pelo usuário e EV simplificado de *call* heads-up all-in. Inclui seed, número de simulações, intervalo de amostragem e SHA-256 de worksheet/pedido.
- Falha se faltarem campos revisados, se o modelo simplificado não for reconhecido explicitamente, se houver range inválido, duplicação, valores inválidos, ou se o pedido não estiver vinculado ao worksheet.
- O relatório **sempre** informa `ready_for_equity_or_ev: false` e `authorized_for_clips: false`: é uma simulação *what-if*, não uma avaliação autenticada de jogadas gravadas.

## Uso local

A partir de `video_analyzer/`:

```bash
python activity_review_editor.py render fila_decisoes.json editor.html
python activity_review_editor.py validate fila_decisoes.json rascunho.json rascunho_validado.json
python activity_review_handoff.py fila_decisoes.json rascunho_validado.json handoff.json
python activity_scenario_worksheet.py handoff.json worksheet.json
python activity_hypothetical_math.py worksheet.json pedido_hipotetico.json relatorio_hipotetico.json
python -m unittest discover -p 'test_*.py' -q
```

`pedido_hipotetico.json` exige `schema_version: 1`, `worksheet_sha256` (SHA-256 canônico produzido por `activity_hypothetical_math.digest`) e `scenarios` com identidade exata da decisão, `model_acknowledgement: "hypothetical_heads_up_all_in_no_rake_no_future_betting"`, `opponent_range` com mãos e pesos, `trials` e `seed`.

## Limites e próximos passos

- Não valida OCR, cartas escondidas, ranges adversários ou decisões reais. O IC de 95% cobre apenas a amostragem Monte Carlo; **não** cobre incerteza dos ranges.
- Não calcula EV de raise/fold nem situações multiway, rake, apostas futuras ou side pots.
- A etapa para resultados reais continua exigindo auditoria independente dos quadros e PTS, revisão das ações e validação do modelo de ranges.
- Falta vídeo autorizado de 3–5 minutos para validar reconhecimento e reconstrução de mãos reais.
- Testes locais: 634 testes, incluindo 10 novos testes de matemática hipotética; smoke de Chromium: quatro mesas, zero erros JS, JSON validado. CI remoto não verificado.
