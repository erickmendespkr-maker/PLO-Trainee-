# Cycle 140 — decoded-source PTS audit (2026-10-27)

## Scope
Adds `offline_reviewed_source_pts_audit.py`, a read-only offline cross-check
of human-entered start, decision and end timestamps against **decoded frame
PTS** in the actual source MP4/WebM. Re-audits every prior pipeline artifact,
verifies the SHA-256 of the supplied source recording, and produces a bounded
JSON report plus a static, escaped HTML review page beside the result folders.
Blocked hands remain visible with no approved timestamps. No automatic hand
recognition, OCR, poker gameplay, live assistance or clip selection.

## Reproducible local validation
- `python -m unittest -v test_offline_reviewed_decision_timeline.py test_offline_reviewed_decision_timeline_page.py test_offline_reviewed_source_pts_audit.py`
- Synthetic FFmpeg-generated 10 FPS and 24 FPS source recordings; tests include
  tampering, symlinks, output collisions, PTS gaps, invalid timestamps and
  FFprobe failure. Full repository suite and remote CI were not run.
- An additional integration demonstration uses the **existing cycle-138
  Monte Carlo pipeline output** for PLO5 and PLO6, together with its synthetic
  source MP4. The scan found 50 decoded frames and checked six human-entered
  timestamps; all six were within 0.15 seconds of a decoded frame PTS.
- This is *temporal proximity only*. It does not prove the correct poker hand,
  action, OCR, range, or EV is visible at those times.

## Remaining blocker
An authorized annotated 3–5 minute PLO5/PLO6 recording is still required to
measure real OCR and hand-boundary accuracy. Full 40–60 minute four-table
performance is unverified. Next: frame contact sheets for flagged timestamps,
manual correction loop, then bounded longer-duration benchmarks.
