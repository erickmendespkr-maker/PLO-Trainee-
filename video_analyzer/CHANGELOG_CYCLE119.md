# Cycle 119 — Independent offline review of hand corrections

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. Recorded PLO5/PLO6 videos only, offline/asynchronous. No live poker, playable tables, AI opponents, credentials, production or spending.

## Added

- `offline_hand_independent_review.py`: requires a different named reviewer to accept or reject **every** Cycle 118 correction proposal. The reviewer is a self-declared label, not an authenticated identity.
- Binds review to the canonical SHA-256 of the original draft, correction overlay and individual proposal. Rebuilds the overlay from the original draft to detect unexpected original values or fields; prevents duplicate/missing decisions.
- Cross-field consistency gates on the combined *accepted* proposals: no duplicated hero/board cards; ordered hand timestamps, actions and streets; actions within known hand boundaries; call amount not exceeding effective stack. Rejected proposals do not alter the candidate values.
- Writes a new immutable review report; refuses existing outputs, symlink inputs and invalid JSON. Never modifies original draft or pending overlay.
- **All verification/authorization flags remain false**: accepted human proposals are not video-verified, not equity/EV-ready and do not authorize clip selection.

## Reproduce locally

From `video_analyzer/`:

```bash
python -m unittest -v test_offline_hand_independent_review test_offline_hand_correction_overlay
python offline_hand_independent_review.py draft.json overlay.json decisions.json new_review.json
```

`decisions.json` contains `schema_version: 1`, `job_id`, `source_draft_sha256`, `overlay_sha256`, `reviewer_label` and a `decisions` array with one object per proposal: `correction_sha256`, `decision` (`accept` or `reject`), `reason`. Use `digest()` from the Cycle 118 module for canonical SHA-256 hashes.

## Test evidence and limitations

On 2026-10-26, **19 new synthetic tests** and **20 Cycle 118 regression tests** passed locally (39 selected total). This is not a complete repository test run or a remote CI result.

- Self-declared reviewer names are not cryptographically authenticated. SHA-256 binds content but does not prove the person who entered a decision.
- Cross-field checks are intentionally incomplete; they do not verify betting legality, source PTS, OCR or source video.
- No authorized annotated real PLO5/PLO6 recording is available. No real OCR accuracy or 40–60 minute throughput was tested.
- The known EOF cut-duration issue remains separate and unresolved.
- No automatic acceptance, application of edits, mathematical recomputation or automatic clip selection is enabled.
