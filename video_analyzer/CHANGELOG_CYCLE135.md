# Ciclo 135 — handoff offline da revisão humana para Monte Carlo

Escopo: `docs/VIDEO_ANALYZER_SCOPE.md`. Apenas análise de gravações PLO5/PLO6; nenhum jogo ao vivo, adversário de IA ou integração com plataforma de pôquer.

## Entregue

- `offline_review_queue_math_handoff.py`: valida a identidade da mão na fila, a alegação de SHA-256 da gravação, a referência ao ledger, a variante e a mesa (1–4).
- Exige declaração explícita de revisão de cada evento, incluindo anotações de correções; bloqueia eventos, alertas de mão ou auditorias temporais não resolvidos.
- Exige concordância entre o revisor declarado, a origem das anotações e o `review_gate` do módulo de Monte Carlo.
- Bloqueia casos ainda não modelados: ação diferente de call, múltiplos adversários, apostas futuras e potes paralelos.
- Emite um relatório JSON rastreável e, **somente quando não houver bloqueios locais**, um candidato JSON separado para `offline_reviewed_range_equity_bridge.py`.
- Não executa Monte Carlo, não afirma que as cartas foram reconhecidas, não valida ranges e não autoriza seleção automática de clipes.
- `test_offline_review_queue_math_handoff.py`: 27 testes sintéticos com `unittest` (incluindo subcasos PLO5/PLO6, mesas 1–4, bloqueios e segurança de arquivos).

## Executar localmente

A partir de `video_analyzer/`:

```sh
python -m unittest -v test_offline_review_queue_math_handoff
python offline_review_queue_math_handoff.py input.json report-novo.json bridge-candidato-novo.json
```

O JSON de entrada possui exatamente: `schema_version`, `queue`, `hand_ref`, `manual_review`, `bridge_input`. A fila vem do módulo `offline_hand_evidence_review_queue.py`. A referência identifica `table_id`, `hand_label` e `ledger_canonical_sha256`. A revisão exige `source_kind`, `reviewer_label`, `event_resolutions` (um por evento, na ordem), `hand_flags_resolution`, `temporal_resolution`, `review_notes` e `annotations_attested`. O `bridge_input` usa o esquema já aceito por `offline_reviewed_range_equity_bridge.py`.

Um relatório com status `handoff_candidate_requires_bridge_validation` **não significa que o cálculo seja válido**: execute o bridge original para validar cartas, colisões, ranges e parâmetros. Um relatório `blocked_for_manual_review` não produz o arquivo candidato.

## Limitações e bloqueios

A verificação de hashes no handoff vincula **alegações entre relatórios**; não reabre a gravação original. Uma confirmação humana declarada não comprova a transcrição nem a correspondência das cartas com o vídeo. A verificação independente do `bridge_input` ainda é responsabilidade do módulo matemático. Não foi executado um teste ponta a ponta com vídeos reais. Falta gravação autorizada e anotada de 3–5 minutos.
