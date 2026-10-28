# Cycle 158 — Offline manually reviewed four-table MP4 clip batch

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. Only branch `feature/plo5-plo6-training`. No real-time poker, playable tables, AI opponents, credentials, production changes or paid services.

## Implementation

- Added `offline_reviewed_clip_batch.py` as a bounded wrapper around the existing `offline_reviewed_clip_export.py`.
- Accepts an existing local MP4/WebM and a strictly validated JSON manifest with explicit human approval for each selected clip.
- Supports 1–4 table IDs and up to 12 clips per batch, each 0.1–180 seconds, with aggregate duration capped at 900 seconds. Different table crops may overlap in time; overlapping clips on the same table are rejected.
- Validates source video SHA-256, schema, crop dimensions, time bounds, unique hand/table IDs, output path safety, and changes to inputs during processing.
- Exports cropped, silent H.264 MP4s with FFmpeg and JSON explanation sidecars; verifies generated clip hashes; writes a batch report with source, manifest, request and clip hashes.
- Uses a temporary sibling directory and renames the complete result into a new destination only after every clip succeeds. Failed batches do not publish partial outputs.
- Does **not** claim that the chosen timestamps are genuine hands or that OCR, equity, EV, or any decision is verified. No automatic clip selection.

## Example manifest

```json
{
  "schema_version": 1,
  "source_video_sha256": "<64-character SHA-256 of the recording>",
  "reviewer_confirmed_offline": true,
  "reviewer_note": "I manually reviewed these selections.",
  "clips": [
    {
      "schema_version": 1,
      "hand_id": "hand_001",
      "table_id": 1,
      "start_seconds": 12.0,
      "end_seconds": 30.0,
      "crop": {"x": 0, "y": 0, "width": 320, "height": 180},
      "explanation": "Manual review notes; no automatic EV claim.",
      "source_video_sha256": "<same SHA-256>",
      "reviewer_confirmed_offline": true
    }
  ]
}
```

Usage: `python video_analyzer/offline_reviewed_clip_batch.py recording.mp4 manifest.json new_output_directory`.

## Tests actually run in the local ChatGPT environment

- 42 new `unittest` tests: strict validation, path traversal, duplicate JSON keys, symlinks, approval, hash mismatches, overlaps, failure rollback, input mutation, real FFmpeg exports and four-table simultaneous crops.
- 88 existing selected tests from the single-clip exporter, EV and Monte Carlo modules.
- **130 selected tests passed** in the local Python environment after the GitHub publication. No GitHub Actions were used.
- Four synthetic 320×180 MP4 crops were generated from a 3-second 640×360 test video. Each generated clip has 1.0-second duration, with matching SHA-256 hashes and sidecar reports.
- GitHub blob SHAs for both new Python files matched the locally tested files.

## Not verified / blocked

- No authorized annotated PLO5/PLO6 video was available. No accuracy estimate for OCR or actual hand reconstruction.
- The four-table demonstration is synthetic; the four crops are not real poker hands.
- Full 40–60 minute sessions, end-to-end OCR→history→equity/EV→clip selection, batch throughput and the full repository test suite remain unverified.
- Current batch export is manually selected, limited to 12 clips and 900 aggregate seconds; a session may be longer than the exported segments.

## Next

Bind manual clip requests to verified hand candidate and audit IDs, while preserving explicit uncertainty and refusing unverified mathematical conclusions. Then validate an authorized annotated 3–5 minute recording and assess longer-session throughput.
