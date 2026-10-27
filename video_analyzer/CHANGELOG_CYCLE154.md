# Cycle 154 — Cross-stage evidence and temporal coverage (2026-10-27)

Scope: [VIDEO_ANALYZER_SCOPE.md](../docs/VIDEO_ANALYZER_SCOPE.md). Offline/asynchronous PLO5/PLO6 **recorded-video** analysis only. No live poker connection, playable tables, AI opponents, production changes, paid services or GitHub Actions.

## Added

- `offline_four_table_evidence_coverage.py`: joins four already-produced artifacts: human-reviewed action report (cycle 151), conditional pot audit (152), manual seat manifest and conditional stack/side-pot audit (153).
- Verifies the SHA-256 provenance chain between those four inputs and the shared recording identity. Optional `--recording` rehashes the actual video. Without it, the output clearly states that the video hash was **not** rechecked.
- Revalidates upstream reviewed-action and pot schemas, fail-closed status, hand/table/game identity, seat balances, per-seat totals and side-pot tier arithmetic. Rejects duplicate JSON keys, malformed inputs, symlinks, invalid numeric values, changed source hashes and output overwrites.
- Preserves reviewed action observation indices and PTS, actor/street assignments and their **human-assigned** contribution values. No hidden cards or inferred actions are generated.
- Compares reviewed contributions by actor to the net seat ledger; reports signed unexplained differences, unobserved all-in labels, contradictory all-in states, manual adjustments without PTS anchors and optional long time gaps. A long gap is **not proof** that an action occurred.
- All hands remain explicitly `complete_hand_reconstructed=false`, `action_history_complete=false`, `ready_for_equity_or_ev=false` and `automatic_clip_selection_authorized=false`, regardless of apparent accounting consistency.
- 40 new synthetic tests and three source fixtures; 109 selected prior tests reused.

## Reproduce locally

From `video_analyzer/`:

```sh
python -m unittest -v test_offline_four_table_betting_review test_offline_four_table_pot_gap_audit test_offline_four_table_stack_sidepot_audit test_offline_four_table_evidence_coverage
python -m py_compile offline_four_table_evidence_coverage.py test_offline_four_table_evidence_coverage.py
python offline_four_table_evidence_coverage.py REVIEWED.json POT.json SEATS.json STACK.json NEW_REPORT.json --gap-seconds 10
```

Inputs must originate from the **same** processing chain. To verify the original recording's bytes, also provide `--recording VIDEO.mp4`. The report is never a substitute for a human ground-truth annotation.

## Verified in local synthetic tests

- 40 new tests + 109 selected regressions = 149 passing tests before publication.
- Four-table synthetic provenance chain and signed per-seat discrepancies, timestamps, unobserved all-in and manual pot adjustments.
- The test fixture recording SHA-256 is synthetic; no actual poker video was used.

## Not verified

- Full repository test suite, real-video OCR accuracy, genuine hand/action reconstruction, independent human review, full 40–60 minute video processing, Monte Carlo equity/EV integration or automatic MP4 clip selection.
- SHA-256 proves byte identity **only**, not that an annotation is true. The original recording is not rehashed unless supplied explicitly.

## Next

Introduce evidence anchors for manual blinds, refunds and unobserved contributions (with PTS and reviewed image hashes), followed by a separate mathematically reproducible PLO5/PLO6 Monte Carlo test harness. Do not enable EV or clip selection without verified inputs and explicit ranges.
