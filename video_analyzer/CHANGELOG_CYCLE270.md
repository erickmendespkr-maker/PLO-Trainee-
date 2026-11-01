# Cycle 270 — original offline sampler/OCR chain orchestration

## Scope
Follow `docs/VIDEO_ANALYZER_SCOPE.md`: user-uploaded recorded PLO5/PLO6 only; no live capture, betting, AI opponents, playable tables or real-time assistance.

## Implemented
- Added `run_original_chain(...)` to `offline_joint_pixel_ocr_audit.py`. The function stages the original `offline_four_table_sample_review.build`, binds user-supplied ROI tasks to the newly created region manifest SHA-256, invokes `offline_four_table_ocr_proposals.scan`, and runs the existing independent pixel/OCR joint audit.
- Checks input file identities and hashes, strictly parses JSON, rejects duplicate ROI tasks, validates sample times, rejects unsafe status promotion, and only publishes a new directory after all stages succeed.
- Outputs `region_bundle/`, `roi_tasks_bound.json`, `original_ocr.json`, `joint_audit/` and `pipeline_report.json`. No labels are authenticated, no hands are reconstructed, and equity/EV/automatic clip selection stay disabled.
- Existing joint audit CLI remains unchanged; the orchestration is exposed as a Python function.

## Local verification — 2026-11-01
- 21/21 tests in `test_offline_joint_pixel_ocr_audit.py` passed: 16 existing + 5 new orchestration tests. Tests use real FFmpeg decoding and the real joint pixel/OCR auditor on a synthetic four-table MP4.
- **Important:** the upstream sampler and Tesseract scanner are substituted with fixture-producing functions in these new orchestration tests. The actual original `build` and `scan` implementations were not run together. Do not describe this as an end-to-end original-tool validation.
- Five new cases: successful four-table staging with real joint audit; scanner failure without publication; duplicate ROI rejection; unsafe OCR promotion rejection; create-only output.
- The Git blob SHA values for the two updated Python files were compared to locally tested versions.

## Limitations and next work
- Run original `build` and `scan` without test doubles against a generated MP4; include FFmpeg, Tesseract, and pixel audit in the same run.
- Test variable-frame-rate and nonzero-origin PTS, corrupt/ambiguous OCR, and report retention on failure.
- A 3–5-minute authorized annotated poker video is still missing; no real OCR accuracy, hand boundary detection, 40–60-minute performance, equity/EV integration or MP4 clip export is established.
- Output-directory publication uses a new-path check followed by rename in a trusted local workspace; cross-process filesystem races are not fully prevented.

## Example Python usage
```python
from offline_joint_pixel_ocr_audit import run_original_chain
run_original_chain('recording.mp4', 'layout.json', 'roi_tasks.json',
                   'labels.json', 'new_output_directory', [0.0, 1.0])
```

The ROI template uses `{"schema_version":1,"tasks":[{"table_id":1,"sample_index":0,"field":"pot","roi":{"x":0,"y":0,"width":80,"height":40}}]}`. These ROIs are manually specified; labels are supplied for diagnostics, not authenticated.
