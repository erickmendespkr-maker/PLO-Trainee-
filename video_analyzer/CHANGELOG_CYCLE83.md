# Cycle 83 — OCR boundary visual evidence (offline review only)

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. No playable tables, AI opponents, live integration or betting automation.

## Implemented

- Added `activity_ocr_boundary_visual_evidence.py`: takes the Cycle 81 temporal OCR JSON, the Cycle 82 boundary-triage JSON, and the **local original MP4/WebM**. Recomputes boundary triage from temporal evidence; rejects mismatched or forged reports and video SHA-256 mismatches.
- Samples start/end and optionally midpoint of each **candidate** window (up to 120 bounded requests). Priority `review_first` is sampled first. Four tables remain separate. Insufficient budgets and windows beyond recording duration are explicitly reported.
- Optional manually supplied per-table pixel rectangles crop FFmpeg PNG navigation images; without them, full frames are exported and identified as such. Output manifest retains table/window associations, seek requests, PNG SHA-256, original source hashes and optional crop-profile hash.
- Refuses symlink inputs, pre-existing output directories, invalid rectangles, false authority flags and unbounded work. Uses a temporary staging directory and an exclusive destination-directory creation.
- **Crucial limit:** extracted PNGs are not decoded-PTS audited; requested seeks never become confirmed timestamps, hands, poker actions, equity/EV inputs, or automatically selected clips.

## CLI

```sh
python video_analyzer/activity_ocr_boundary_visual_evidence.py session.mp4 temporal_ocr.json boundary_triage.json ./boundary_navigation --regions-json table_regions.json --max-frames 60 --samples-per-window 3
```

Example manual `table_regions.json` for a 320×240 four-table test video:

```json
{"1":{"x":0,"y":0,"width":160,"height":120},"2":{"x":160,"y":0,"width":160,"height":120},"3":{"x":0,"y":120,"width":160,"height":120},"4":{"x":160,"y":120,"width":160,"height":120}}
```

The upstream boundary JSON must be created by `activity_ocr_boundary_triage.py` from the **same unchanged temporal JSON file** (including its recorded SHA-256). The original recording must match the temporal report's `recording_sha256`.

## Tests actually executed locally

- 8 new synthetic unit tests: passed.
- 52 selected integration/regression tests: passed in ~10 seconds (includes new tests and Cycle 82 triage, temporal OCR, math review frame and table stills tests).
- FFmpeg 7.1.5: four distinct table-region PNGs exported from a generated 4-second video; SHA-256 matched the manifest; no decoded PTS or poker facts asserted.
- Python compileall for the two new modules: passed.
- No full suite or remote CI result is claimed for this cycle.

## Remaining blockers

No authorized real PLO5/PLO6 sample or human-labeled ground truth. Recognition accuracy, hand reconstruction and 40–60 minute throughput are not verified. Next: decoded-PTS audit of OCR-boundary navigation frames and human review/annotation benchmark. No math or clip-selection authorization from OCR hypotheses alone.
