# Offline activity OCR → human review (PLO5/PLO6)

Scope: recorded sessions only; no live capture, poker-client integration, betting or automatic decision advice. The original scope is `docs/VIDEO_ANALYZER_SCOPE.md`.

## Inputs and trust boundary

1. `activity_evidence_export.py` extracts per-table PNG evidence with decoded PTS and SHA-256 manifest.
2. `activity_ocr_bridge.py` runs OCR on manually defined regions and writes **unverified candidates**.
3. `activity_review_chain.py` re-audits the evidence and checks every candidate against its original table, image hash, PTS ticks, timestamp and requested seeks.
4. A review template is created with every `human_confirmed` flag set to `false`. It includes the SHA-256 of the exact OCR report, recording and evidence manifest.
5. A human must review source frames, assign a hand ID, PLO5/PLO6 variant, action, reviewer confidence and explicitly approve each OCR field. Corrections require a reason.
6. The optional reviewed bridge rejects missing approvals, candidate swaps, source alterations, cross-table/cross-frame reassignment and altered OCR reports.

## Commands

Run from the `video_analyzer` directory:

```bash
python activity_review_chain.py /path/to/evidence /path/to/manual_rois.json /path/to/ocr_candidates.json /path/to/unapproved_review.json
python activity_review_chain.py /path/to/evidence /path/to/manual_rois.json /path/to/ocr_candidates.json /path/to/reviewed.json --human-review /path/to/approved_review.json
python -m unittest -v test_activity_review_chain
```

Outputs are created exclusively; existing output files are not overwritten.

## Limits

Human confirmation does **not** prove annotation accuracy. OCR engine confidence is uncalibrated. Decoded PTS is not authenticated capture time. The output explicitly marks `ready_for_equity_or_ev=false`. Hidden cards, opponents' ranges, actions and hand boundaries are never inferred from OCR. Benchmarking on authorized real recordings remains pending.

## Dependencies and verification

The new module uses `activity_evidence_export`, `activity_ocr_bridge`, `review_packet` and `reviewed_ocr_bridge`. The cycle-44 local test suite passed 553 tests (including 12 new tests) on synthetic material. Remote GitHub Actions/CI was not confirmed.
