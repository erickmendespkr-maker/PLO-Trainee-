# Cycle 84 — decoded-PTS audit for OCR boundary navigation images

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. Offline recorded-video analysis only. No playable tables, real-time poker integration, betting, or AI opponents.

## Implemented

- Added `activity_ocr_boundary_pts_audit.py`: verifies the Cycle 83 OCR boundary evidence manifest by **recomputing** the original Cycle 82 boundary triage and Cycle 83 frame plan from their unchanged input files. Infers the legacy 1–3 samples/window setting by exact plan comparison (the older manifest did not record it).
- Checks source recording SHA-256, temporal/boundary report hashes, optional manual ROI profile hash, all PNG hashes, filenames, table/frame IDs, frame counts, and absence of unexpected PNGs. Rejects forged verified-PTS flags, altered seeks, changed regions, symlinks, and pre-existing output destinations.
- Re-decodes each image with FFmpeg's original input seek and crop, adding `-copyts` and `showinfo` before crop. Accepts a decoded filtergraph PTS **only if** the re-decoded PNG is byte-identical to the original hash-verified navigation PNG. Nonidentical decodes remain unverified (not promoted to a timestamp).
- Emits an independent `boundary_pts_audit.json` in a new directory, preserving provenance and an explicit audit verdict for every PNG. It never changes the source evidence directory or its manifest.
- Never verifies hand boundaries, poker cards/actions, strategy, equity/EV inputs, or automatic clip selection.

## Usage

First generate Cycle 83 boundary evidence, then audit it with the **same original files**:

```sh
python video_analyzer/activity_ocr_boundary_visual_evidence.py session.mp4 temporal.json boundary.json ./navigation --regions-json regions.json --samples-per-window 3
python video_analyzer/activity_ocr_boundary_pts_audit.py session.mp4 temporal.json boundary.json ./navigation ./pts_audit --regions-json regions.json
```

Without a manual crop profile, omit `--regions-json` from **both** commands. The new output directory must not already exist or be inside the source navigation directory.

`decoded_pts_seconds` means FFmpeg filtergraph timestamp for the byte-identical frame, **not** the time of a poker action, verified hand transition, or wall-clock capture time. Seek offsets may differ from the decoded PTS, especially with variable-frame-rate or nonzero-start-timestamp videos.

## Local tests (2026-10-24)

- 12 new synthetic unit tests: passed, including four tables, full-frame and ROI crops, one/two/three sample settings, frame budgets, forged reports, altered PNGs, symlinks, overwrite refusal, and a simulated re-decode mismatch that leaves PTS unverified.
- 59 selected integration/regression tests: passed with FFmpeg 7.1.5.
- Full discovery suite was attempted but timed out after 230 seconds; **not** claimed to pass.
- No real authorized PLO5/PLO6 video, human-labeled ground truth, or remote CI run was used in these tests.

## Next

Provide an explicit human annotation/review schema for candidate hand boundaries, link audited frames to review tasks, and benchmark on a 3–5 minute authorized video. No OCR candidate or boundary is a verified poker fact without review.
