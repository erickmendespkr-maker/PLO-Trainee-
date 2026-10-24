# Ciclo 69 — ligação conservadora entre fila visual e histórico revisado

Escopo: [`docs/VIDEO_ANALYZER_SCOPE.md`](../docs/VIDEO_ANALYZER_SCOPE.md). Sem mesas jogáveis, apostas, integração com poker ao vivo ou adversários de IA.

## Entrega

`activity_visual_timeline_crosswalk.py` lê a fila de mudanças de pixels em regiões manuais (`activity_region_review_queue.py`) e o histórico de mãos **humanamente atribuídas** (`activity_reviewed_hand_timeline.py`). Confere a identidade SHA-256 da gravação, estados conservadores, intervalos, mesas (1–4), índices de observação, contagens e hashes canônicos opcionais dos dois relatórios. Não lê ou interpreta novas cartas.

**Proteção essencial:** os pipelines podem utilizar origens diferentes de PTS. Sem uma declaração explícita de alinhamento de relógios, a saída **não associa nenhuma mudança visual a uma mão**. Uma declaração assinada apenas por texto humano continua sendo uma hipótese não calibrada, nunca prova de sincronização. Quando declarada, a ligação é somente por sobreposição de intervalos de observação na **mesma mesa**. Várias mãos sobrepostas são marcadas como ambíguas; a ferramenta não atribui automaticamente mão ou ação, não autoriza equity/EV, seleção de clipes ou afirmações de erro.

## Uso offline

```bash
python video_analyzer/activity_visual_timeline_crosswalk.py \
  fila_roi.json historico_revisado.json crosswalk.json
```

Opcionalmente, após verificar manualmente que os PTS representam o mesmo vídeo e sua origem temporal, criar `alinhamento.json` com os campos:

```json
{
  "schema_version": 1,
  "recording_sha256": "<sha256-do-video>",
  "queue_timestamp_semantics": "decoded_source_pts_seconds_not_exact_hand_boundary",
  "timeline_timestamp_semantics": "decoded_filtergraph_pts_not_capture_time",
  "reviewer_confirmed_same_recording_pts_origin": true,
  "queue_pts_minus_timeline_pts_seconds": 0,
  "reviewer_note": "Descrever como foi verificada a origem dos PTS; não presumir zero."
}
```

Executar com `--alignment-json alinhamento.json`; o deslocamento é definido como `PTS_fila = PTS_timeline + offset`. Os parâmetros opcionais `--expected-queue-sha256` e `--expected-timeline-sha256` fixam os relatórios de entrada. O destino precisa ser novo; não há sobrescrita.

## Testes e limites

`python -m unittest -q test_activity_visual_timeline_crosswalk` verifica dados sintéticos de quatro mesas, recusa de cruzamento entre gravações diferentes, comportamento seguro sem alinhamento, deslocamento manual, ambiguidade entre mãos, dados inválidos, hashes, CLI, proteção contra sobrescrita e determinismo. Testes sintéticos não medem precisão de OCR ou reconstrução em sessões reais.

**Bloqueio:** falta gravação autorizada de 3–5 minutos para aferir a origem dos PTS, calibrar OCR e medir a reconstrução. Não foi validado o fluxo completo em sessões de 40–60 minutos.
