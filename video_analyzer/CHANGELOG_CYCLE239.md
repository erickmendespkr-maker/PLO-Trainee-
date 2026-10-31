# Cycle 239 — manual per-table MP4 crop export

## Scope
Offline-only PLO5/PLO6 video analysis. No playable tables, live poker integrations, betting or AI opponents. The first authorized, annotated 3–5 minute recording remains unavailable.

## New modules
- `offline_ev_table_crop.py`: accepts the original recording, an existing conditional-EV batch output directory, a manually specified JSON table layout, and a **new empty** output directory.
- `test_offline_ev_table_crop.py`: synthetic preflight, FFmpeg export, integrity, collision, failure/rollback cases.
- `test_offline_ev_table_crop_pixels.py`: checks the actual RGB pixels of four different quadrants after FFmpeg cropping, not just video metadata.

## Example layout

```json
{
  "schema_version": 1,
  "status": "manual_offline_table_regions_unverified",
  "source_video_sha256": "REPLACE_WITH_SHA256_OF_ORIGINAL_VIDEO",
  "regions": [
    {"table_id": "T1", "x": 0, "y": 0, "width": 320, "height": 180},
    {"table_id": "T2", "x": 320, "y": 0, "width": 320, "height": 180},
    {"table_id": "T3", "x": 0, "y": 180, "width": 320, "height": 180},
    {"table_id": "T4", "x": 320, "y": 180, "width": 320, "height": 180}
  ]
}
```

## CLI

```bash
mkdir -p cropped
python video_analyzer/offline_ev_table_crop.py original.mp4 batch_output layout.json cropped
python -m unittest -v video_analyzer/test_offline_ev_table_crop.py video_analyzer/test_offline_ev_table_crop_pixels.py
```

The original source must match the SHA-256 in the batch report and layout. Each cropped MP4 is re-encoded from the original at the audited start/end timestamps, so the explanation overlay is added **after** cropping. Audio is intentionally omitted from these cropped demonstration clips. The original full-frame batch output is not modified. Crop metadata and a consolidated crop ledger retain provenance and hashes.

## Safety checks
- No automatic table detection or OCR-to-math promotion; geometry is a manual unverified claim.
- At most four distinct table regions and twenty rendered clips; regions must fit the original frame and have even dimensions.
- Strict JSON keys, unique table IDs and clip IDs, SHA-256 consistency for video, batch and per-clip reports, and timestamp consistency.
- Symlink and pre-existing output rejection; fail-closed output rollback if rendering or input integrity checks fail.
- No changes to existing batch/overview modules, production, credentials, GitHub Actions or main.

## Verification
Local selected tests: **17/17 passed** on Linux with installed FFmpeg/FFprobe, including a real four-output synthetic render and pixel-level crop verification. Test fixtures use an artificial four-quadrant colored video; they do not validate poker recognition, ranges, EV or real session processing. This is not a full-repository test run.

## Limitations and next cycle
- Manual geometry only; no automatic table detection or tracking over moving layouts.
- Crop output has its own ledger; it is not yet linked into the existing `session_overview.html`.
- Video authenticity, OCR accuracy, Windows compatibility, 40–60 minute throughput and end-to-end session reconstruction are unverified.
- Next: add read-only offline crop overview, then table region tracking and calibration against an authorized annotated recording.

## Additional integration — read-only crop overview
- `offline_ev_table_crop_overview.py` validates the crop batch ledger, each MP4 digest, per-clip metadata, source-video/layout provenance and the no-automatic-OCR flag before writing `crop_overview.html` with local MP4 playback links.
- `test_offline_ev_table_crop_overview.py` adds five synthetic tests for four video links, output collisions, tampered clips/metadata and OCR authorization tampering.
- Run: `python video_analyzer/offline_ev_table_crop_overview.py cropped` after the crop exporter.
- Updated local verification: **22/22 selected tests passed** (17 crop/pixel tests + 5 HTML tests); not the full repository suite.
