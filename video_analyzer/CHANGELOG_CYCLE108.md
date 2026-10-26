# Cycle 108 — PLO5/PLO6 offline hypothetical math from human hand drafts (2026-10-25)

## Branch and scope
Only `feature/plo5-plo6-training`. Offline, asynchronous review of user-supplied recordings. No live poker, playable tables, bots, production, credentials or paid services. See `docs/VIDEO_ANALYZER_SCOPE.md`.

## Verified integration gap
The branch's `video_analyzer/hand_math_scenario_run.py` imports `range_ev`, but `video_analyzer/range_ev.py` returned 404 when fetched from the branch. Restore the locally tested `range_ev.py` and its standalone tests so the mathematical runner has its missing dependency. This must be verified after publication.

## New module
`video_analyzer/offline_job_hand_math_review.py` bridges Cycle 107 **unverified** human hand-history drafts to a separate, empty, source-hash-bound worksheet, then accepts only independently re-entered hypothetical scenarios. It uses the same validated weighted-range Monte Carlo and heads-up all-in EV formulas as the existing scenario runner.

- `template <draft.json> <new_worksheet.json>`: no cards, actions, ranges or timestamps are auto-filled or considered facts.
- `calculate <draft.json> <worksheet.json> <filled_worksheet.json> <new_result.json>`: recomputes source SHA-256, refuses worksheet tampering, checks exact hand/table association, PLO5/PLO6 cards, board street, pot/call amount and matching hero decision timestamp.
- Requires explicit independent manual video-review claims for all five mathematical fields, confidence, range weights, seed, bounded trials and simplified model assumptions. This **cannot prove** that a human actually reviewed the video.
- Supports PLO5/PLO6 call and raise hypotheses. Maximum eight bounded scenarios per run. Reproducible seed and Hoeffding sampling confidence intervals. Unknown opponent ranges and future actions are not inferred.
- Output always marks `hand_reconstruction_verified=false`, `ready_for_equity_or_ev=false`, `strategic_error_established=false` and `automatic_clip_selection_authorized=false` even when hypothetical math is computed. Sampling CI is not a confidence interval for opponent ranges, OCR, or the model.
- Rejects duplicate JSON keys, symlinks, input/output overlap, changed inputs, oversize payloads, source changes and overwrites.

## Tests
- 31 new synthetic tests (PLO5/PLO6, call/raise, reproducibility, missing cards, cross-table isolation, invalid timestamps, conflicting cards/pot, protected metadata, integrity and exclusive file creation).
- 107 focused tests passed, plus 30 subtests, with the branch-identical `hand_math_scenario_run.py`, `offline_job_hand_history_draft.py`, `equity.py`, `hand_history.py`, `test_hand_math_scenario_run.py`, and the restored `range_ev.py`.
- Exact branch blob SHA verified for these existing files: `hand_math_scenario_run.py=2260a56a3a2340760cb38ad2868a66fb09d1aaa9`, `offline_job_hand_history_draft.py=2e9bbcfedc68f770892ecae79e08ea216ab72d17`, `equity.py=121f53ffb4fe462daa279f2e830949cab4374ef6`, `hand_history.py=b90e1a9ec7bdb580bd9d773d83cd42a07a38bf21`.
- Synthetic demonstration: one PLO5 and one PLO6 hypothetical calculation from fabricated JSON. No video or OCR tested this cycle.

## Limitations
Full repository suite, remote CI, exact source-video PTS, real OCR/hand reconstruction, 40–60-minute real sessions and automatic clip selection are **not verified**. No real-world strategic error can be concluded. Source PTS attestation is human-claimed only.

## Next
Re-audit source PTS with ffprobe/FFmpeg; independently compare reconstructed actions to an authorized annotated 3–5-minute sample; then join math results to human-selected MP4 explanations without upgrading hypothetical inputs to video-verified facts.
