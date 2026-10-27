# Cycle 150 — offline action/street candidate audit (2026-10-27)

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`; offline PLO5/PLO6 recordings only. No live integration, playable tables, opponent AI, credentials, production, spending or GitHub Actions.

## Published
- `offline_four_table_action_timeline_audit.py`: validates the incomplete, human-reviewed hand-candidate JSON from Cycle 149 and produces an action/street *candidate* audit.
- Board snapshots of 3/4/5 cards can suggest flop/turn/river. Actions before a board, at a board transition, or after a board conflict remain street-unknown. No actor, action order beyond PTS, hidden cards, betting sequence or opponent ranges are inferred.
- Review flags: partial/shrinking/non-prefix board, hero-card changes, visible card collisions, pot decreases, missing actions/board.
- Source JSON is bound by SHA-256; optional `--recording` checks the video hash. The source JSON still requires independent upstream provenance verification against original crops.
- Create-only output; duplicate JSON keys, symlinks, invalid cards/actions/amounts, repeated observation IDs, cross-hand reuse and overlapping windows are rejected.
- `test_offline_four_table_action_timeline_audit.py`: 33 fast synthetic tests passed locally (0.029 seconds; this is not a video throughput benchmark).
- Demo: four synthetic tables, seven observed action labels, six board snapshots, and no math promotion.

## Verification
- `python -m unittest -v test_offline_four_table_action_timeline_audit`: 33 passed, zero skipped.
- `python -m py_compile` for the module and tests: passed.
- Git blob hashes after publication match the locally tested files.

## Limitations
- No real annotated PLO5/PLO6 video (3–5 minutes recommended), no validated OCR/hand reconstruction accuracy, no 40–60 minute four-table benchmark, no full repository test suite, and no GitHub Actions.
- The module does not reconstruct full action history, authenticate human reviewers, or run Monte Carlo/equity/EV. Both `ready_for_equity_or_ev` and `automatic_clip_selection_authorized` stay false.

## Usage
`python video_analyzer/offline_four_table_action_timeline_audit.py hand_candidates.json new_action_timeline.json --recording session.mp4`
