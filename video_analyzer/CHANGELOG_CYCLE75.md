# Ciclo 75 — pré-auditoria de entradas matemáticas (somente revisão)

## Escopo e implementação

Novo módulo `activity_math_readiness_triage.py` recebe `activity_hand_review_packet` e **exatamente** o `activity_reviewed_hand_timeline` de origem. Ele valida SHA-256 canônico, identidade da gravação, mãos, observações e sinais de inconsistência. Gera tarefas por observação humana de `fold`, `check`, `call`, `bet` ou `raise` com checklist de campos presentes **no timestamp da decisão**, sem preencher valores a partir de frames anteriores ou posteriores.

Para cada tarefa, distingue campo ausente, rótulo humano sem referência OCR, referência OCR no mesmo PTS ainda não verificada e referência em PTS divergente. Sinaliza conflito entre PLO5/PLO6 e quantidade de cartas privadas, divergências de consistência, candidatos OCR conflitantes e truncamento de orçamento. Lista explicitamente hipóteses ausentes (ranges, número de oponentes, stacks efetivos, rake, apostas futuras, identidade do herói e semântica de apostas). `raise` e `bet` exigem adicionalmente modelo de fold equity/respostas.

**Nenhum valor é promovido para entrada matemática.** A saída mantém `ready_for_equity_or_ev=false`, `automatic_clip_selection_authorized=false` e `strategic_error_established=false`, mesmo quando todos os campos da observação humana estão preenchidos. A presença de rótulos e hashes não autentica o conteúdo do vídeo.

## Uso local

```bash
python video_analyzer/activity_math_readiness_triage.py \
  hand_review_packet.json reviewed_timeline.json math_triage.json \
  --max-tasks 1000
```

Opcionalmente use `--expected-packet-sha256` e `--expected-timeline-sha256` para vincular entradas específicas. O destino precisa ser novo, não pode substituir entradas nem apontar para symlink. Os arquivos JSON de entrada precisam ser arquivos regulares.

## Testes e limitações

- `python -m pytest -q test_activity_math_readiness_triage.py` verifica quatro mesas sintéticas, bloqueio de uso de cartas futuras, proveniência no mesmo PTS, divergências, variante PLO6, orçamentos, imutabilidade, CLI, SHA e proteção contra sobrescrita.
- `python -m pytest -q test_activity_math_readiness_triage.py test_activity_hand_review_packet.py test_activity_consistency_frame_review.py test_activity_timeline_consistency_audit.py test_activity_reviewed_hand_timeline.py test_activity_ocr_timeline_review.py test_activity_hypothetical_math.py test_activity_scenario_worksheet.py test_equity.py test_range_ev.py` é a regressão direcionada.
- **Não** há validação de OCR em vídeos reais nem reconstrução autônoma de mãos. Vídeo autorizado de 3–5 minutos ainda necessário para aferir reconhecimento. Não foram adicionados gastos, serviços de produção ou integração em tempo real.
- As saídas deste módulo são checklists de revisão; o motor hipotético de equity/EV já existente exige uma via separada de atestação e hipóteses explícitas.
