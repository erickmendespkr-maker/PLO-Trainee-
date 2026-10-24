# Ciclo 76 — entrega conservadora para revisão matemática offline

## Escopo
Somente análise assíncrona de gravações PLO5/PLO6. Nenhuma mesa jogável, IA adversária, integração com poker real ou operação ao vivo.

## Adicionado
- `activity_math_review_handoff.py`: vincula o checklist matemático do ciclo 75 ao pacote de evidências e ao histórico humano originais. Recalcula o checklist integralmente, rejeitando alterações de identidade, timestamps, blockers, permissões ou truncamento.
- Exporta uma tarefa por decisão anotada com identidade da mesa/mão, SHA-256 do evento, status de campos no PTS da decisão, impedimentos e formulário **vazio** para auditoria humana, ranges, stacks, rake e hipóteses.
- Janela de navegação temporal limitada aos **timestamps observados** da mão; não é limite real da mão nem autorização para gerar clipes.
- `test_activity_math_review_handoff.py`: testes sintéticos para quatro mesas, orçamento, identidade, alteração maliciosa, limites temporais, CLI e proteção contra sobrescrita.

## Execução local
Na pasta `video_analyzer`:

```bash
python activity_math_review_handoff.py math_triage.json hand_review_packet.json reviewed_timeline.json math_review_handoff.json
python -m unittest -v test_activity_math_review_handoff.py test_activity_math_readiness_triage.py
```

Parâmetros opcionais: `--expected-triage-sha256`, `--expected-packet-sha256`, `--expected-timeline-sha256`, `--seconds-before`, `--seconds-after`.

## Limites e bloqueios
- Todos os campos novos de revisão humana são `null` e todos os sinais de autorização matemática, seleção automática de clipes e erro estratégico são `false`.
- O módulo **não** calcula equity/EV, não autentica OCR, não escolhe nem exporta MP4, não reconhece cartas ocultas e não aprova mãos.
- É necessário vídeo autorizado e anotação humana para validar reconhecimento real e limites de mão. Sem isso, somente testes sintéticos.
- A prova de conceito com vídeo real de 3–5 minutos, benchmark OCR e processamento integral de 40–60 minutos continuam pendentes.
