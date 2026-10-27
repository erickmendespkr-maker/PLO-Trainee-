# Cycle 147 — verified four-table crop to unverified OCR proposals

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`; recorded MP4/WebM only, offline/asynchronous. No live poker integration, hidden-card inference, action advice, playable tables, or automatic mathematical promotion.

## Implementation

- `offline_four_table_ocr_proposals.py` consumes a previously verified `offline_four_table_sample_review` bundle and a human-declared JSON manifest bound to the exact SHA-256 of `region_samples.json`.
- Up to 32 explicit `(table_id, sample_index, field, ROI)` tasks, with fields `hero_cards`, `board`, `pot`, `bet`, `stack`, `action`. ROIs are bounded to the crop and prevalidated before subprocesses run.
- FFmpeg crops each selected source PNG; Tesseract produces raw TSV text and **uncalibrated engine word confidence**. Source crop SHA-256 and decoded source PTS are preserved per result. No card/action parsing is performed and every candidate remains `needs_manual_review`.
- Source manifests and crops are reverified after OCR; output is JSON with create-only atomic publication. The report explicitly blocks equity/EV and automatic action or hand inference.
- No runtime cloud services, credentials, or network needed.

## Tested locally

- 24 new tests: real Tesseract on a synthetic video with `POT 120` visible, all six field types, PTS binding, source/crop hash checks, duplicate/invalid tasks, path and overwrite rejection, tampering during OCR, and missing tool failures.
- 58 existing selected regression tests for four-table sampling, visual changes, layouts and video segments.
- **82 selected tests passed** in the local environment. `python -m unittest -q test_offline_four_table_ocr_proposals.py test_offline_four_table_change_candidates.py test_offline_four_table_sample_review.py test_offline_four_table_layout_contract.py test_table_regions.py test_video_segments.py`.

## Limitations

- OCR engine confidence is not a calibrated probability of correct cards, stacks, actions, or hand reconstruction. This module deliberately does not parse OCR into confirmed poker facts or feed mathematical calculations.
- No authorized, annotated real PLO5/PLO6 recording available. Real-world OCR accuracy, segmentation precision, and full 40–60 minute four-table throughput remain unverified.
- The full repository test suite and GitHub Actions were not run.

## Next

- Build a human review handoff that explicitly approves/corrects field values and binds them to source crop/PTS hashes before structured hand history.
- Benchmark on longer synthetic videos and then on an authorized annotated 3–5 minute recording when available.
