# PLO Trainee — handoff de revisão offline (ciclo 48)

Escopo: somente análise assíncrona de gravações autorizadas PLO5/PLO6, sem jogo ao vivo.

## Entrada e saída

O módulo `video_analyzer/activity_review_handoff.py` recebe:
1. Fila JSON de decisões do `activity_snapshot_chain.py`.
2. Rascunho JSON exportado pelo editor offline e associado à fila.
3. Caminho de um arquivo JSON de saída **novo**.

Execute a partir de `video_analyzer/`:

```bash
python activity_review_handoff.py queue.json reviewed_draft.json handoff.json
python -m unittest -v test_activity_review_handoff
```

O relatório registra, para cada decisão, mesa, mão, timestamp, campos atestados manualmente, confiança mínima declarada, SHA-256 da fila e do rascunho, e bloqueios pendentes.

## Segurança e limites

- Campos **não confirmados** jamais são promovidos para `model_inputs`.
- Mesmo com cinco campos marcados como conferidos, `ready_for_equity_or_ev` permanece **false**.
- A integridade da fila e os tipos de campos são validados; timestamps futuros, cartas duplicadas e adulterações de identidade são rejeitados.
- Confirmação humana não autentica o conteúdo visual; o hash vincula apenas os bytes da estrutura JSON.
- Nenhum range adversário, fold equity ou hipótese de EV é inventado; ficam como `null`.
- Não há processamento de vídeo real nem validação de OCR neste ciclo.

## Próximo passo

Conectar o relatório à auditoria independente de bytes de quadros/PTS, à revisão explícita de ranges e aos cálculos condicionais de equity e EV, sem desbloqueio automático. A validação de precisão depende de vídeo autorizado anotado manualmente.
