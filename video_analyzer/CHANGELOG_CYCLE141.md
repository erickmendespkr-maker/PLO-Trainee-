# Cycle 141 — offline decoded-frame reference review (2026-10-27)

## Scope and safety
- Added `offline_reviewed_pts_contact_sheet.py`: re-audits the source MP4/WebM and all pipeline hashes, extracts exact *decoded-frame indices* (nearest and adjacent frames) using a single bounded FFmpeg pass, and creates a local HTML contact sheet plus an explicitly **unapproved** JSON correction template.
- Default selects only out-of-tolerance timestamps; `--include-decisions` additionally includes one decision reference per exported hand. Blocked hands never become approved or acquire inferred cards/actions. All files are create-only, under the same local parent as pipeline results. Outputs are capped and hashed. No network, live poker integration, gameplay, or automatic clip approval.
- Changed `offline_reviewed_source_pts_audit._scan_pts` to an O(F+T) two-pointer nearest-frame algorithm (F decoded frames, T timestamps), replacing the O(F×T) nested scan. Exact ties still select the earlier frame. Strict monotonicity is required; even micro backward PTS movement is rejected instead of silently assigning a possibly incorrect nearest frame.

## Reproduction
From `video_analyzer` with FFmpeg and FFprobe available:

```sh
python -m unittest -v test_offline_reviewed_pts_contact_sheet.py test_offline_reviewed_source_pts_audit.py test_offline_reviewed_decision_timeline.py
python offline_reviewed_pts_contact_sheet.py /path/source.mp4 /path/results/new_references /path/results/hand1 /path/results/hand2 --include-decisions
```

- 75 selected tests passed locally (including 7 timeline-page regressions), including 23 new tests (20 contact-sheet tests and 3 nearest-frame regression tests). Tests cover missing FFmpeg, tampered source/clips, symlinks, path traversal, collisions, HTML escaping, source mutation during extraction, duplicate frames, blocked hands, output limits and exact-frame extraction.
- An existing synthetic 5-second source and two PLO5/PLO6 pipeline result folders from the prior cycle yielded 2 decision review points and 3 unique JPEG frames, with zero timestamps outside the 0.15-second tolerance. This demonstrates the review export, **not** actual poker recognition.
- Additional 60-second 640×360 synthetic four-quadrant recording at 10 FPS: 600 frames and 120 queried timestamps; local FFprobe PTS scan measured 0.428 seconds wall time. This is not a 40–60-minute four-table performance validation.

## Limitations and next steps
- No authorized annotated real session was supplied. OCR, automatic hand boundaries, visible cards/actions, opponent ranges and actual strategic decisions remain unverified.
- Review JSON is a template, not a validated or directly importable clip annotation. Human correction and re-approval are required.
- FFprobe decoded-frame ordering and FFmpeg select-index correspondence were checked on synthetic sources, not across all codecs, variable-frame-rate videos, or real multi-table sessions.
- Next: a schema-validated human correction importer that re-audits timestamps and never automatically approves changes; realistic longer-duration benchmarks and then an annotated recording.
