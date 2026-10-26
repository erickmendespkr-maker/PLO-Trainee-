# Cycle 126 — offline event-to-crop evidence linkage

Scope: `docs/VIDEO_ANALYZER_SCOPE.md` — analysis of uploaded recorded PLO5/PLO6 sessions only.

## Added

- `offline_action_evidence_link.py` links **already reconstructed** ledger events to supplied frame crop files with table/hand/digest agreement, event index, PTS distance (<=1.5 seconds), pixel bounding box and two separate confidence values.
- Checks SHA-256 of the crop bytes, rejects path traversal and symlinks, duplicate event IDs, unsafe JSON and overwrites. The source recording SHA-256 and duration are explicitly **unverified manifest claims**.
- Produces a JSON report with unmatched event IDs, timestamps and review-only evidence links. It does **not** perform OCR or verify crop origin against the video; all equity/EV and automatic clip gates remain false.
- `test_offline_action_evidence_link.py` contains 22 synthetic tests; CLI demonstration uses a synthetic PNG and the Cycle 125 synthetic ledger report.

## Test evidence

- 22 new tests passed locally.
- 170 selected tests passed locally including 148 prior tests from the Cycle 125 archive (not the complete repository suite).
- Python module compilation and synthetic CLI smoke test passed.
- No CI, real-video accuracy, full-session performance or actual recording hash check was performed.

## Next

- Validate recording SHA-256 from real uploaded file, and verify FFmpeg frame extraction PTS against the recording before assigning stronger evidence status.
- Preserve OCR uncertainty; do not enable mathematical judgement solely from linked crops.
- Revisit the end-of-recording MP4 clip duration issue with synthetic FFprobe checks.

## Blocker

An authorized, annotated 3–5 minute PLO5/PLO6 recording is still missing.
