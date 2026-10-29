# Cycle 194 — Gate conditional equity on human frame acknowledgement

## Scope
Offline/async PLO5/PLO6 video analysis only. No playable tables, AI opponents,
real-time poker connection, or automatic strategy grading. Refer to
`docs/VIDEO_ANALYZER_SCOPE.md`.

## Added
- `offline_acknowledged_equity_clip_report.py`: consumes selected ROI/clip binding,
  MP4 clip, manually entered cards, FFmpeg snapshot directory and human gallery
  confirmation JSON. Verifies **all** 5/6 private cards and 3–5 community cards
  have acknowledged frame links before invoking the existing Monte Carlo engine.
- Reuses `offline_audited_card_gallery.verify` to reject incomplete or altered
  acknowledgements, wrong hashes, tampered PNGs, unsafe paths and mismatched
  identity; `offline_reviewed_equity_clip_report.build` still enforces Omaha
  inputs, manually entered ranges and optional terminal call EV assumptions.
- SHA-256 ties the output to the binding, clip, review, snapshot manifest and
  gallery confirmation. Sources and frame hashes are rechecked after analysis.
- `test_offline_acknowledged_equity_clip_report.py`: synthetic PLO5/PLO6,
  CLI, determinism and negative cases. No GitHub Actions required.

## CLI
From `video_analyzer/`:

```bash
python offline_acknowledged_equity_clip_report.py \
  BINDING.json CLIP.mp4 MANUAL_REVIEW.json SNAPSHOT_DIR \
  CONFIRMATION.json NEW_REPORT.json
```

The snapshot directory is produced by `offline_manual_frame_snapshot_audit.py`,
and the confirmation JSON by the HTML gallery from
`offline_audited_card_gallery.py` (or synthetic test fixtures).

## Important limits
- **No machine verification of card visibility.** Confirmation is a human
  assertion; a fabricated confirmation with internally consistent hashes cannot
  be distinguished from a genuine human review.
- Frames are extracted from the hash-matched clip, but exact decoded PTS and
  the upstream video-to-ROI replay are not rechecked here.
- OCR action text is not assigned to hero and not graded.
- Equity is conditional on manually declared cards and assumed opponent ranges;
  the 95% confidence interval covers Monte Carlo sampling error only.
- The current Monte Carlo engine models one opponent and only a simplified
  terminal call EV; it does not model raises, multiway pots or future betting.
- Real annotated footage and Windows/full-session testing remain blocked.

## Verification
Tests must be executed locally and logs retained. Do not claim the full
repository suite passed unless independently verified. No spend or production
changes permitted.
