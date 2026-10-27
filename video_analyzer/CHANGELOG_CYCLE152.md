# Cycle 152 — Conditional pot-accounting gap audit (2026-10-27)

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. Offline/asynchronous PLO5/PLO6 video analysis only. No live integration, playable tables, AI opponents, credentials, production changes, paid services or GitHub Actions.

## Added

- `offline_four_table_pot_gap_audit.py`: creates an **unconfirmed** accounting manifest from cycle-151 human-reviewed action records, then checks a separate, explicitly confirmed manual manifest.
- Checks reviewed-action contributions against per-street totals, preserving original source hashes and table/hand identity.
- Accepts optional, explicitly **human-supplied hypotheses** for starting pot, blinds/antes/straddles, missing contributions, uncalled-bet returns, rake, final pot and side-pot presence.
- Rejects invalid amounts, missing attestations, duplicate forced entries, refund amounts exceeding the same player's contributions in the same street, invalid seat references, changed hashes, duplicate JSON keys, symlinks and unsafe output overwrites.
- Reports **conditional** arithmetic differences only when enough human-supplied values exist; arithmetic equality never marks a hand as complete or a pot as reconciled.
- Explicitly keeps `complete_hand_reconstructed`, `ready_for_equity_or_ev`, and `automatic_clip_selection_authorized` false for all outputs.
- `test_offline_four_table_pot_gap_audit.py`: 35 new synthetic tests; 32 existing cycle-151 regression tests.

## Reproduce

```sh
cd video_analyzer
python -m unittest -v test_offline_four_table_betting_review.py test_offline_four_table_pot_gap_audit.py
python offline_four_table_pot_gap_audit.py template REVIEWED_ACTIONS.json NEW_TEMPLATE.json
# Fill and attest a copy of the template. Never treat these entries as observed facts.
python offline_four_table_pot_gap_audit.py audit REVIEWED_ACTIONS.json COMPLETED_MANIFEST.json NEW_REPORT.json
```

## Verified locally

- 67 selected synthetic tests passed, including malformed inputs, provenance and fail-closed behavior.
- CLI demonstration processed four synthetic table records; conditional estimate was 67.50 chips vs human-supplied final 120 for hand1, reporting a -52.50 chip discrepancy. Other three hands had no supplied final-pot observation and no difference was claimed.
- All four hands remained blocked for equity/EV and automatic clip selection.

## Not verified

- No authorized PLO5/PLO6 recording, real OCR accuracy, genuine human review, full pot/side-pot accounting or end-to-end 40–60 minute four-table run.
- Full repository suite not executed. Conditional arithmetic does not validate the manual inputs or reconstruct unobserved actions.

## Next

Build a distinct evidence-based coverage layer for forced bets, per-seat balances, all-in side pots and missing action intervals. Keep mathematics blocked until independent verification and explicit range assumptions are available.
