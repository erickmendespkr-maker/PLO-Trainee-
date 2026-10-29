# Cycle 190 — conditional offline equity + local MP4 explanation

Scope: docs/VIDEO_ANALYZER_SCOPE.md. Branch: feature/plo5-plo6-training.

## Implemented

- offline_reviewed_equity_clip_report.py: bridges previously generated selected-action/ROI/MP4 binding to manually entered PLO5/PLO6 cards and existing Monte Carlo engine. Checks SHA-256 of binding and MP4, hand/table/variant/proposal identity, manual review assertion, ranges and seed. Rejects raw OCR as a card source, mismatched evidence, extra fields, missing confirmation and output overwrite.
- offline_equity_clip_explanation.py: renders standalone offline HTML next to clip.mp4, with playback, conditional equity, sampling-only 95% interval, range type, seed, iteration count, optional hypothetical call EV, and uncertainty warnings. Escapes OCR text; no external resources.
- 26 bridge tests + 11 HTML tests + 20 existing Monte Carlo tests = 57 targeted local tests.

## Reproduction

From video_analyzer/:

    python offline_reviewed_equity_clip_report.py BINDING.json clip.mp4 MANUAL_REVIEW.json NEW_REPORT.json
    python offline_equity_clip_explanation.py NEW_REPORT.json clip.mp4 NEW_EXPLANATION.html
    python -m unittest -q test_offline_plo_equity_monte_carlo test_offline_reviewed_equity_clip_report test_offline_equity_clip_explanation

HTML output must be adjacent to the media file named clip.mp4.

## Synthetic demonstration

Used the existing synthetic cycle 188 MP4 (4 seconds, checked with FFprobe) and selected ROI binding. Manual card confirmation was SIMULATED: the cards were not transcribed from the video. The demonstration equity of 100% is a contrived royal-flush case, unrelated to the selected OCR action. This validates data plumbing and hashes, not visual accuracy or strategic quality.

## Limitations and safety

- The bridge does NOT rerun source-video/frame/ROI replay. It checks previous binding claims and hashes, not reviewer identity or cryptographic authenticity.
- The selected OCR action is NOT attributed to the hero or graded. Cards are manually entered assertions, not automatically proven correct.
- Opponent ranges are assumptions. The confidence interval measures Monte Carlo sampling error only.
- Optional terminal call EV is a heads-up no-rake/no-future-betting hypothetical, not EV of the observed action.
- No live poker interaction, playable table, simulated opponents, production, credentials, Actions or spending.
- No authorized annotated 3–5 minute real recording. Windows and 40–60 minute real sessions unverified.
- Local targeted 57 tests passed; headless Chromium check timed out and is NOT counted as a successful UI test.
