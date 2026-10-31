# Cycle 241 — offline reviewable table-region proposals

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. Recorded PLO5/PLO6 video only; no playable tables, live capture, client integration or automatic promotion of OCR into mathematical facts.

## Added
- `offline_table_region_proposals.py` proposes one, two or four rectangular regions from three FFmpeg grayscale samples and central neighbor-contrast seams. Evidence is a deterministic, **uncalibrated heuristic**; not proof that a table was detected.
- Writes `proposals.json` with video SHA-256, source dimensions, timestamps, seam scores, regions and explicit `human_confirmation=false` / `automatic_ocr_math_authorization=false`.
- Writes `preview.png` showing the candidate rectangles; original video is not changed. The preview and proposal are hash-linked.
- Explicit human-reviewed confirmation command converts to the existing `manual_offline_table_regions_unverified` schema accepted by the crop exporter. The command rejects altered source video, preview, sampled evidence, geometry, output collisions and symlinks. It is never invoked automatically.
- `test_offline_table_region_proposals.py`: 19 synthetic FFmpeg regression tests for four/two/one-region cases, deterministic results, output protection, confirmation gate and tampering.

## Usage
```bash
mkdir -p review
python video_analyzer/offline_table_region_proposals.py propose session.mp4 review
# Inspect review/preview.png AND the original recording, adjust geometry manually if needed.
# Only after genuine human review of these exact proposed regions:
python video_analyzer/offline_table_region_proposals.py confirm session.mp4 review/proposals.json review/manual_layout.json --confirm-reviewed
```

## Verified locally
- 19/19 new synthetic tests passed on Linux with FFmpeg/FFprobe. No real poker video was used.
- Four-color-quadrant synthetic example yielded four rectangles; vertical/horizontal split examples yielded two; uniform video yielded one.
- Confirmed layout matches the pre-existing crop export schema (shape only; no end-to-end crop in this cycle).

## Limitations
- A contrast seam can be a HUD, text, window border or another object. Table detection accuracy, multi-table tracking, OCR, Windows execution and 40–60 minute performance are unverified.
- The heuristic samples only three frames and does not track moving/resized windows.
- The confirmation flag represents an explicit user action, not proof that the user actually reviewed the image.
- Authorized annotated 3–5 minute PLO5/PLO6 video still missing for calibration and accuracy evaluation.

Next: compare proposals to annotated real recordings, allow manually corrected region coordinates with audit trail, then consider tracking across time.
