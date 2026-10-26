# Cycle 109 — Human-selected offline MP4 clip export (2026-10-25)

## Scope
Branch: `feature/plo5-plo6-training`. Offline user-supplied recorded PLO5/PLO6 sessions only. No real-time poker, automated decisions, bots, credentials, production, or paid APIs. Scope: `docs/VIDEO_ANALYZER_SCOPE.md`.

## Implementation
- `offline_manual_clip_export.py` accepts a recording, a **human-authored** source-hash-bound JSON selection, and a new `.mp4` path.
- Validates SHA-256 before and after export, the manually selected table (1–4), confidence, positive interval (max 180 seconds), FFprobe container duration, optional even-pixel crop within frame geometry, and explanation length.
- FFmpeg re-encodes an MP4 with a `mov_text` subtitle track containing the **human-written** explanation, not a claimed mathematical verdict. A new JSON sidecar preserves the source and output SHA-256, selection, warnings and limitations.
- Uses a temporary directory and exclusive hard-link publication; does not overwrite an existing MP4 or sidecar. Rejects symlink inputs, duplicate JSON keys, overlapping input/output paths, and oversized selection files.
- This does **not** authenticate hand start/end boundaries against decoded source frame PTS. FFprobe only checks the container timeline. It does **not** reconstruct hands, calculate equity/EV, link existing mathematical output, or automatically select clips.

## Local tests
- `python -m unittest -v test_offline_manual_clip_export`: **6 tests passed** on synthetic FFmpeg video, including subtitle stream, crop geometry, source-hash rejection, invalid selection, path safety and no-authorization flags.
- Python syntax compilation and sample MP4 export are separately verifiable.
- Remote CI, full repository suite and real PLO footage: **not verified**.

## Next
- Validate source frame PTS and variable-frame-rate behavior independently, with explicit error bounds and offsets.
- Bind human-selected clip timestamps to the review dossier and hypothetical math result using source hashes and hand IDs without silently promoting OCR or human claims to verified facts.
- Measure end-to-end accuracy against an authorized annotated 3–5-minute recorded session.
