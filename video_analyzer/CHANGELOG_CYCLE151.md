# Cycle 151 — Offline manual betting-action review (2026-10-27)

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. This is an asynchronous, user-supplied recording workflow only. No live poker integrations, table simulator, AI opponents, credentials, production changes or paid services.

## Added

- `offline_four_table_betting_review.py`: creates a deliberately unconfirmed JSON review template from a cycle-150 action/street audit; separately accepts a human-completed manifest and produces a new immutable JSON report.
- Rejects unexpected keys, duplicate JSON keys, symlinked inputs, changed source hashes, invalid action indices, inconsistent hand/table identity, missing manual confirmations, invalid actors, impossible street reversals, board-street conflicts, and invalid chip contributions.
- Retains source timestamps and observed action labels, differentiates human-assigned actor/street/contribution from observed OCR/vision facts, and preserves review flags.
- Does **not** claim pot reconciliation, complete action history, known opponent ranges, equity, EV or automatic clip selection. A review manifest is not independently authenticated.
- `test_offline_four_table_betting_review.py`: 32 synthetic tests, including tampering and fail-closed cases.

## Reproduction

```sh
cd video_analyzer
python -m unittest -v test_offline_four_table_action_timeline_audit.py test_offline_four_table_betting_review.py
python offline_four_table_betting_review.py template INPUT_ACTION_AUDIT.json NEW_TEMPLATE.json
# Manually review and edit a copy of the template, including its attestations.
python offline_four_table_betting_review.py review INPUT_ACTION_AUDIT.json COMPLETED_MANIFEST.json NEW_REPORT.json
```

## Local verification

- 32 new tests + 33 earlier action-audit tests = **65 selected tests passed**, rerun after publishing the two Python files; no GitHub Actions used.
- Git blob hashes of both published Python files match the tested local files.
- Synthetic cycle-150 audit (four tables, seven observed action labels) produced an unconfirmed template and a synthetic completed-manifest report; all four hands remain blocked for mathematical analysis.
- Full repository suite not executed. No authorized real poker recording supplied, so OCR accuracy, full session performance and correct hand reconstruction are not validated.

## Next

Design an evidence-first, non-automatic hand action coverage review: blinds/antes, player seats, missing actions, side pots and chip-accounting consistency. Require explicit range and uncertainty modeling before enabling equity/EV; do not promote unverified hands.
