# Cycle 118 — Source-bound human correction proposals

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. Offline, asynchronous review of uploaded recorded PLO5/PLO6 videos only. No playable tables, opponents, live capture, betting integration, credentials or paid services.

## Delivered

- `offline_hand_correction_overlay.py`: read a Cycle 107 manual hand-history draft and a human-authored JSON submission; produce an **immutable, pending-review correction overlay**, not a modified hand history.
- Bind proposals to `job_id`, SHA-256 of the canonical source draft, table/hand identity and SHA-256 of each original field. Reject stale drafts/fields, duplicates, unknown fields and unsafe data. Support proposed visible cards, board, actions, chip amounts, human-claimed timestamps, notes and subjective confidence.
- Preserve the original value for audit; never infer hidden cards or elevate human claims to verified OCR/PTS. Output explicitly disables equity/EV readiness and automatic clip selection.
- Write a new JSON output exclusively; never overwrite the source or an existing report. Reject symlink inputs, duplicate JSON keys and non-finite numbers.

## Reproduce locally

From `video_analyzer/`:

```bash
python -m unittest -v test_offline_hand_correction_overlay
python offline_hand_correction_overlay.py draft.json corrections.json new_overlay.json
```

The input `corrections.json` must have `schema_version`, `job_id`, `source_draft_sha256` (SHA-256 of canonical JSON object), `reviewer_label` and a nonempty `corrections` array. Each correction has `table_id`, `hand_label_human_assigned`, `field`, `expected_value_sha256` (canonical SHA-256 of the original field), `proposed_value`, `reason` and `confidence_subjective`. Use the `digest` helper in the module for canonical hashes.

Local result on 2026-10-26: **20 focused synthetic tests passed**. No complete repository suite or remote CI was run.

## Limitations and next steps

- A pending overlay is **not applied** to the draft and does not authorize equity, EV or clips. Independent human review, cross-field consistency and source-video verification are still required.
- No authorized annotated PLO5/PLO6 recording has been supplied, so OCR precision and reconstruction correctness remain unverified.
- The EOF timing shortfall seen in Cycle 117 is not addressed here; it remains a separate FFmpeg task.
- Only the feature branch was changed; no production/main, secrets or spending.
