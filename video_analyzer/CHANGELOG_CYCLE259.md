# Cycle 259 — independent VFR-aware ingest PTS/crop audit

## Scope
Consulted `docs/VIDEO_ANALYZER_SCOPE.md` on `feature/plo5-plo6-training`. Offline/asynchronous recorded-video analysis only. No playable tables, live platform integration, credentials, spending, or changes to `main`.

## Added
- `offline_ingest_pts_audit.py`: independent post-ingest audit for `offline_video_ingest_probe.py`-style `manifest.json` and sampled JPEG ROIs. Validates source SHA-256/size before and after, table geometry (1–4 tables), unique bounded sample names, JPEG hashes/dimensions, and the manifest's **actual decoded PTS** against a separate FFprobe enumeration of source-frame PTS. Produces a new JSON report, never overwrites an existing one, and explicitly keeps OCR/hand/equity/EV authorization false.
- `test_offline_ingest_pts_audit.py`: FFmpeg-generated variable-frame-rate synthetic 320×240 source with four colored table quadrants, two crop images per table, and 13 tests (including tampered source/crop, wrong PTS, missing table, traversal/symlink/duplicate input, wrong geometry, non-overwrite, and PTS tick-quantization heuristic).

## Locally verified
- `python -m unittest -v test_offline_ingest_pts_audit`: **13/13 passed**, Linux Python 3.13.5, FFmpeg 7.1.5. Actual FFmpeg/FFprobe binaries were invoked for synthetic video generation, frame extraction, and timestamp audit.
- Synthetic VFR fixture: four regions, eight verified JPEG crops, source-frame PTS independently enumerated; VFR observed, no equity/EV authorized.
- Git blob SHA-1 of tested files matched the blobs published to the target branch.

## Reproduce
```bash
cd video_analyzer
python -m unittest -v test_offline_ingest_pts_audit
python offline_video_ingest_probe.py recording.mp4 regions.json new_ingest_dir
python offline_ingest_pts_audit.py recording.mp4 new_ingest_dir new_audit.json
```

## Limitations / not verified
- The **exact existing ingest module was inspected, but its build() was not executed together with the new auditor** in this cycle. The tests synthesize a schema-compatible manifest, not a full ingest run.
- The audit proves that manifest PTS values match independently enumerated source-frame timestamps and that the JPEG bytes match manifest hashes/dimensions. It **does not** independently establish that JPEG visual contents correspond to the claimed source frame/ROI, nor measure OCR accuracy.
- VFR detection is a heuristic that ignores minor timestamp tick quantization; it is not an authoritative codec/container classification.
- Full-frame FFprobe enumeration is bounded to 250,000 frames, 16 MiB output and 180 seconds. Large/high-FPS real recordings may exceed those limits; no 40–60 minute real video or Windows test was performed.
- The only video fixture was 320×240, approximately 1.4 seconds and four artificial color regions. No hand reconstruction, OCR, equity, EV or MP4 clip export was run.
- A user-authorized, annotated 3–5 minute PLO5/PLO6 sample is still missing for actual recognition accuracy.

## Next
Run the exact existing `offline_video_ingest_probe.build()` against a synthetic VFR four-table fixture and feed its real output to the auditor; reconcile any PTS/seek edge cases. Then test non-zero-start PTS and timestamp drift. Continue visual accuracy calibration only when an authorized annotated sample is available.
