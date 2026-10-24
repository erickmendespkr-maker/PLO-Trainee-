# Cycle 81 — temporal review hints from audited table OCR

Scope: **offline/async recorded PLO5/PLO6 videos only**. No playable tables, opponents, live integration, or betting automation.

## Implemented
- Added `activity_crop_ocr_temporal_review.py`, consuming one or more Cycle 80 `math_review_crop_ocr.json` reports from the **same recording and manual ROI profile**.
- Groups observations by table, OCR field and exact ROI geometry; compares only explicitly PTS-verified, parsable, above-threshold OCR candidates in a bounded time window.
- Emits `possible_visual_value_change` hints for different OCR values, not confirmed poker actions or hand boundaries. Duplicate decoded PTS, low confidence, unparsed OCR, unverified PTS, nonmonotonic PTS and long gaps interrupt comparisons and produce review hints.
- Re-parses raw OCR strings to detect mismatched candidate values. Preserves input SHA-256 and crop/ROI SHA-256 references. Refuses symlink inputs, output overwrite, incompatible recordings/profiles, invalid confidence/timestamps, excessive candidate budgets, and reports claiming automatic mathematical authority.
- Explicitly blocks equity, EV, strategic-error conclusions, verified hand boundaries and automatic clip selection.

## CLI

```sh
python video_analyzer/activity_crop_ocr_temporal_review.py \
  session_sample1/math_review_crop_ocr.json \
  session_sample2/math_review_crop_ocr.json \
  --output temporal_review.json --max-gap-seconds 30
```

Input reports must use the Cycle 80 schema. The result is a **review queue**, not a validated reconstruction. Confidence is Tesseract engine output, **not** a calibrated probability. Even verified decoded PTS only proves reproduction of the upstream PNG under that audit's method, not the underlying card/amount recognition.

## Tests (synthetic only)
- 16 new tests passed, including four-table separation, OCR change hints, board candidate changes, duplicate/nonmonotonic PTS, unverified timestamps, confidence gating, long gaps, forged candidate values/status, budget checks, input hashes, symlinks, CLI and overwrite protection.
- 45 focused integration/regression tests passed, including existing FFmpeg/Tesseract crop OCR, PTS, table crops and temporal consensus.
- A full-suite attempt did **not** complete within the execution limit; no full-suite pass is claimed.
- No authorized real PLO5/PLO6 video supplied; precision/recall and real hand reconstruction remain unverified.

## Next
Validate on authorized 3–5 minute video and hand-labeled ground truth; quantify per-field precision/recall, identify actual hand boundaries conservatively, and only then connect reviewed decisions to Monte Carlo equity, conditional EV and MP4 explanation clips.
