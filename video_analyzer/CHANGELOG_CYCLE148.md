# Cycle 148 — offline OCR human-review gate (2026-10-27)

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`; only offline recordings and synthetic tests. No live poker integration, opponent AI, playable tables, credentials, paid services, or main branch changes.

## Delivered

- `offline_four_table_ocr_human_review.py`: import human decisions (`confirm`, `correct`, `reject`) for every OCR candidate; validate source recording, region-sample manifest, source crop hashes, source PTS, OCR report hash and review manifest hash.
- Reject unreviewed/duplicate/misaligned candidates, tampered crops, unsupported fields, malformed cards/amounts/actions, symlinks and existing output files. Atomic create-only JSON output.
- Preserve candidate lineage and record explicit `visual_evidence_checked`, while retaining `ready_for_equity_or_ev=false` and `complete_hand_reconstructed=false`.
- `test_offline_four_table_ocr_human_review.py`: 22 self-contained synthetic tests generating a short 4-region H.264 video with FFmpeg, region crops, Tesseract OCR and review decisions.

## Verified locally

- 22 new tests pass; 104 selected tests pass with prior region extraction, OCR, change detector, layout and segment tests.
- Separate 60-second synthetic four-table benchmark: 16 OCR proposals reviewed in a JSON example; no hand is reconstructed or passed to equity/EV.
- Git blob hashes of published Python module and test match local tested files.

## Not verified / blockers

- No real annotated PLO5/PLO6 video (ideally 3–5 minutes); recognition precision cannot be measured.
- No full repository test suite or GitHub Actions run.
- Human review is an explicit manifest, not authenticated reviewer identity or a graphical editing interface.
- PLO5/PLO6 game type, pot and action history, ranges, confidence calibration, and full hand reconstruction require separate validation before mathematical analysis.

## Example

`python video_analyzer/offline_four_table_ocr_human_review.py samples/ ocr_proposals.json review_manifest.json reviewed_fields.json --recording recording.mp4`

The review manifest must have exactly `schema_version`, `source_ocr_sha256`, `decisions`. Each decision has `candidate_index`, `decision`, `reviewed_text`, `visual_evidence_checked`, `note`. All candidates require a decision; `confirm` requires the raw OCR text to match exactly; `correct` permits a reviewed replacement; `reject` requires `reviewed_text: null`. This tool never authorizes equity, EV, or automatic clip selection.
