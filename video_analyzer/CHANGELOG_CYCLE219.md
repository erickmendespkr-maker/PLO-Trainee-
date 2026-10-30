# Cycle 219 — Offline OCR proposal review bridge

Scope: docs/VIDEO_ANALYZER_SCOPE.md. No live poker integration, no play simulator, no paid services, no GitHub Actions.

## New files

- video_analyzer/offline_ocr_review_bridge.py: accepts a normalized offline OCR/vision observation JSON stream and a previously human-declared reviewed clip plan. Validates plan/video SHA-256 claims, table identity, hand boundaries, per-frame PTS, normalized ROI, engine, field, card slot and raw OCR confidence. Produces a deterministic per-hand review worksheet and a blocked manual-annotation skeleton.
- video_analyzer/test_offline_ocr_review_bridge.py: synthetic tests for valid inputs, four tables, conflicts, duplicate cards, invalid ROI, bad timestamps, wrong table, nonfinite confidence, mismatched provenance, CLI safety, and the invariant that 100% OCR confidence never enables equity.

## CLI

python video_analyzer/offline_ocr_review_bridge.py plan.json ocr_proposals.json new_worksheet.json new_annotations.json

Input JSON schema: schema_version=1, status=offline_ocr_proposals_unverified, source_plan_sha256 (hash of plan.json), source_video_sha256_claim (must match plan), observations (list of objects).

Each observation has hand_id, table_id, field, slot, value, pts_seconds, confidence, roi, engine. Fields: hero_card, board_card, pot, stack, action, variant. Only card fields take numeric slot. Engines: synthetic, tesseract, vision. ROI object: x, y, w, h normalized to [0,1]. PTS must be within the declared hand boundaries. Raw OCR confidence is not calibrated.

The review worksheet preserves all OCR suggestions and flags conflicting slots, duplicated cards, low raw confidence, and unrecognized card text. The generated annotation skeleton is compatible with the existing math-queue schema but has card_review_status=ocr_unverified and NO cards, per-card human evidence, opponent range, or simulation parameters. It cannot start Monte Carlo or assert actions. Reviewers must inspect original frames and independently create human-confirmed annotations, including card-by-card timestamps and hypothetical opponent ranges.

## Verification

Local command: python -m unittest discover -p 'test_offline_*.py'

Result: 179 tests passed, including 20 new tests, using the source/test snapshot from Cycle 218 and the two new files. Git hashes of prior queue and portable bundle matched their GitHub branch blobs before testing.

Tests are synthetic. No OCR engine was invoked, no actual cards or actions were recognized from video, and no Windows or 40–60 minute real-session test was performed.

## Blockers and limitations

An authorized, human-annotated 3–5 minute PLO5/PLO6 sample video is needed for recognition accuracy measurement. This is a proposal-to-review adapter, not an OCR detector or a calibrated vision model. The source-video hash is a declared claim, not independently validated video content. The manual annotation skeleton is not a completed review. The full remote repository test suite was not executed.
