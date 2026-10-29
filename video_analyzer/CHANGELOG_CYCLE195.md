# Cycle 195 — Render acknowledged equity in the offline MP4 explanation

## Scope
Offline/async review of recorded PLO5/PLO6 only; see `docs/VIDEO_ANALYZER_SCOPE.md`.
No playable tables, real-time integration, AI opponents, or automated action grading.

## Changes
- `offline_equity_clip_explanation.py` accepts both the original conditional-equity report and the newer `offline_conditional_equity_after_human_frame_acknowledgement` report.
- The acknowledged report requires explicit human-acknowledgement status, complete card/frame counts, SHA-256-shaped provenance fields and false machine-visibility/PTS/video-replay verification flags.
- The HTML explains that gallery confirmation is a human assertion and that the renderer **does not recheck** PNGs or confirmation files; it still verifies the MP4 hash before writing the HTML.
- Legacy reports remain supported, but cannot masquerade as gallery-acknowledged reports by adding the new fields.
- New `test_offline_acknowledged_equity_explanation.py` covers synthetic positive integration, CLI, XSS escaping and unsafe/inconsistent metadata rejection.

## Local verification
- `python -m unittest -q test_offline_equity_clip_explanation test_offline_acknowledged_equity_explanation`: 32/32 passed.
- `python -m unittest discover -p 'test_*.py' -q` on the extracted Cycle 194 bundle plus changes: 187/187 passed (selected bundle only, not full GitHub repository).
- Synthetic clip and report used; no real annotated video, Windows run, or 40–60 minute sessions.

## Usage
From `video_analyzer/`:

```bash
python offline_equity_clip_explanation.py ACKNOWLEDGED_REPORT.json clip.mp4 explanation.html
```

`clip.mp4` and new `explanation.html` must share a directory. The report must reference that clip by SHA-256. The report's human confirmation metadata is validated for internal consistency, **not** independently verified against the original frames or video in this rendering step.
