# Cycle 153 — Conditional stack and side-pot audit (2026-10-27)

Scope: [VIDEO_ANALYZER_SCOPE.md](../docs/VIDEO_ANALYZER_SCOPE.md). **Offline/asynchronous video analysis only**. No live poker integration, playable tables, AI opponents, production, credentials, paid services or GitHub Actions.

## Added

- offline_four_table_stack_sidepot_audit.py consumes a cycle-152 conditional pot report, emits an **unconfirmed** seat-review template, then validates a separately completed manual seat manifest.
- Binds the report and manual manifest by SHA-256, preserves recording hash, hand identity and table identity, and optionally rechecks the recording file.
- Checks decimal-only chip amounts, per-seat contributions against starting stacks, optional pre-award balances, all-in stack exhaustion, unique actors and declared seat counts.
- Computes **conditional** side-pot layers from net per-seat contributions. Folded players' chips remain in the pot but folded players are not listed as eligible. Unknown player states remain explicitly uncertain.
- Flags one-contributor top layers requiring uncalled-bet review, layers with no eligible contenders, unverified balances, unknown eligibility, mismatch with upstream pot accounting and all upstream blockers.
- Rejects duplicate JSON keys, NaN, malformed amounts, invalid manifests, changed hashes, symlink inputs and overwrites.
- Never promotes complete_hand_reconstructed, side_pot_eligibility_verified, ready_for_equity_or_ev or automatic_clip_selection_authorized to true.
- test_offline_four_table_stack_sidepot_audit.py: 42 new synthetic tests; fixtures/cycle153_pot_gap_report_input.json: four-table synthetic fixture.

## Reproduce

Run from video_analyzer/:

    python -m unittest -v test_offline_four_table_stack_sidepot_audit.py
    python offline_four_table_stack_sidepot_audit.py template fixtures/cycle153_pot_gap_report_input.json NEW_TEMPLATE.json

Fill a copy of the template with **explicitly hypothetical** seat data, attest reviewer_confirmed_offline, then:

    python offline_four_table_stack_sidepot_audit.py audit fixtures/cycle153_pot_gap_report_input.json COMPLETED_MANIFEST.json NEW_REPORT.json

## Locally verified

- 42 new synthetic tests passed; 67 selected regressions from the preceding betting-review/pot-gap modules passed (109 total in a combined run).
- python -m py_compile passed for all three modules and tests in the local selected suite.
- Four-table synthetic demonstration generated 2 conditional tiers for table 1 and 1 tier for each other table. All four remained blocked for equity/EV and automatic clip selection.
- Code and tests were compared to the published GitHub blobs using Git blob SHA.

## Not verified

- No authorized annotated poker video or genuine human seat review; source fixture is entirely synthetic.
- No complete all-in action history, side-pot award distribution, rake attribution, OCR accuracy, Monte Carlo/EV validation or 40–60 minute four-table performance claim.
- The full repository test suite was not executed. GitHub Actions were not used.

## Next

Introduce an explicit coverage/evidence manifest linking per-seat contributions and all-in states to reviewed action timestamps and OCR frames; keep unknown intervals and incomplete ranges fail-closed. Separately prepare parameterized Monte Carlo checks with exact Omaha two-hole/three-board rule, deterministic seeds and confidence intervals.
