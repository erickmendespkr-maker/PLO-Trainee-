# Cycle 221 — human-declared table geometry -> OCR samples

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. Offline recorded-video analysis only; no live integrations, no AI opponents, no playable tables.

## Added

- `offline_table_roi_sampler.py` composes **human-declared** table rectangles and field rectangles (normalized 0..1) into FFmpeg/Tesseract sample ROIs per reviewed hand.
- Configurable strictly ordered fractions of each hand interval (0.01..0.99), up to five, with deterministic ordering and a 6,000-sample cap inherited from the extractor.
- Generates a geometry-only PNG overlay on one video frame. It is for **manual alignment review**, not proof of accurate OCR, hand recognition, or card identity.
- Checks exact table coverage (max four), non-overlap of table rectangles, unique field slots, valid pixel crops, reviewed hand/video duration, source SHA-256 and no-overwrite output paths.
- Produces the exact `human_declared_offline_roi_samples` schema accepted by `offline_ffmpeg_tesseract_proposals.py`. No OCR values are confirmed and no Monte Carlo is enabled.

## CLI

```
python video_analyzer/offline_table_roi_sampler.py VIDEO.mp4 PLAN.json TEMPLATE.json NEW_SAMPLES.json NEW_PREVIEW.png
python video_analyzer/offline_ffmpeg_tesseract_proposals.py VIDEO.mp4 PLAN.json NEW_SAMPLES.json NEW_PROPOSALS.json
```

Template schema: `{"schema_version":1,"status":"human_declared_table_geometry_unverified","fractions":[0.5],"tables":[{"table_id":"T1","roi":{"x":0,"y":0,"w":0.5,"h":0.5},"fields":[{"field":"hero_card","slot":0,"roi":{"x":0.25,"y":0.25,"w":0.25,"h":0.25}}]}]}`. Each `field.roi` is **relative to its parent table**; table ROI is relative to the full video. Template must include every table in the reviewed clip plan.

## Tests / evidence

- New synthetic tests: ROI composition, FFmpeg/Tesseract four-card fixture, explicit Monte Carlo block, deterministic multi-fraction sampling, preview PNG, path and SHA guards, overlapping/missing tables, invalid slots, tiny crops, timestamp and sample limits.
- Selected regression: `python -m unittest -q test_offline_reviewed_hand_math_queue test_offline_ocr_review_bridge test_offline_ffmpeg_tesseract_proposals test_offline_table_roi_sampler` (95 tests; test imports duplicate some test classes).
- An attempted full `test_offline_*.py` discovery exceeded the local execution timeout; **full suite not verified**.
- Demo contains four artificial tables and one card glyph per table; real poker video accuracy remains unknown.

## Limitations

This is a *semiautomatic geometry mapper*, **not automatic table detection**. It requires user-provided table/field coordinates and hand boundaries, and a video of known dimensions. The overlay frame is taken near the first reviewed hand start and cannot verify temporal correctness for all hands. Current reviewed-plan validator caps one plan at 100 hands; batch aggregation for longer sessions is a separate component. The OCR confidence remains raw and uncalibrated. Real video and Windows tests are pending.
