# Cycle 243 — sampled temporal table-region proposals (offline only)

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`; recorded PLO5/PLO6 sessions, at most four candidate regions. No playable poker tables, live capture, platform integration, AI opponents or betting automation.

## Added
- `offline_table_temporal_regions.py`: FFmpeg/FFprobe grayscale sampling over time; per-frame unverified 1/2/4-region geometry, contrast evidence and sample timestamps.
- Candidate seam displacement events with **time windows**, not invented exact move times; changes in topology, large jumps and missing visual support require human review. Table identities are not guaranteed across changes.
- Explicit fail-closed metadata: `human_confirmation=false`, `crop_authorized=false`, `automatic_ocr_math_authorization=false`. This module cannot feed OCR/equity/EV without a separate review step.
- Source SHA-256 integrity checks, bounded sample budget, existing output directory, collision/symlink protection and atomic JSON publication.
- `test_offline_table_temporal_regions.py`: 11 synthetic tests (moving/static/featureless video, timing, ambiguous transitions, geometry validation and output safety).

## Usage
```bash
mkdir -p temporal_review
python video_analyzer/offline_table_temporal_regions.py recording.mp4 temporal_review --interval 10 --max-samples 360
# Inspect temporal_review/temporal_regions.json and original recording.
# No automatic approval/crop/strategy verdict is produced.
```

## Verified locally (Linux)
- 11/11 new tests passed with FFmpeg/FFprobe.
- 30/30 selected tests passed (11 new + 19 prior region proposal tests).
- A separate synthetic 6-second, 4-quadrant MP4 produced six observations (0.5–5.5s) and one candidate shift first seen at 3.5s, bounded by [2.5s, 3.5s], with displacement x=24px, y=12px. No confirmation was claimed.
- GitHub published blob hashes for the new module and tests matched the tested local files.

## Not verified / blockers
- No authorized annotated 3–5 minute PLO5/PLO6 video is available to measure detection accuracy. The heuristic detects color/contrast seams, **not poker tables**.
- No temporal human-reviewed layout approval/export adapter yet. No OCR/hand/street tracking, Windows verification, 40–60 minute throughput benchmark, or complete repository suite in this cycle.
- Sampling is interval-based and may miss changes between frames; no guarantee of table identity after movement.
