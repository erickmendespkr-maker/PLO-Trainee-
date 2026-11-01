# Cycle 255 — reviewed-decision Monte Carlo bridge (offline)

## Scope
Implements `offline_math_mc_bridge.py` as a fail-closed adapter:
`offline_math_decision_snapshot` candidate -> existing
`offline_omaha_equity_mc.estimate` -> existing
`offline_call_ev_from_counts.build` -> new JSON report.

No playable tables, live integration, poker client, new credentials, production
deployment, or expense. No automatic OCR authorization or strategy verdict.

## Contract and limits
- Requires a timestamp-scoped, manually reviewed candidate and declared
  source hashes; the source hashes are **claims**, not a reinspection of
  the original video or human attestation.
- Uses only known board cards for the selected street; validates 5 or 6 hero
  cards, disjoint opponent combos and the exact Omaha 2-hole/3-board rule
  claimed by the existing engine.
- Requires uniform positive weights over **explicit** opponent combinations.
  Nonuniform weights are rejected, not silently flattened.
- Restricted to 100–10000 trials, 32-bit nonnegative seed, <=512 combinations.
- Heads-up, no rake, no side pots, all-in/terminal-showdown call/fold model.
  No raise EV, no future betting, no fold-equity inference.
- Reports Monte Carlo Hoeffding 95% bounds for sampling uncertainty only.
  Does not quantify OCR, range, model, or player-identity uncertainty.
- Refuses malformed input, duplicate JSON keys, future-street board,
  mismatched source-hash claims, overlapping cards, changed input during
  computation and overwriting an existing report.

## Local verification
The new adapter and tests were executed locally with a **test-only snapshot
of the existing engine interface and ranking/sampling algorithm**, plus the
actual locally available versions of the previous three adapters.
The selected suite ran 83 tests successfully (20 new, 63 regression).
The actual GitHub copy of `offline_omaha_equity_mc.py` was inspected via the
GitHub connector, but **not independently executed as the exact repository
file** in this run. This distinction must not be collapsed into an end-to-end
verification claim.

Two artificial candidate JSONs (PLO5/PLO6, 500 trials each) were processed
into JSON reports. Those numbers are examples, not measured poker performance.
No real session was used. The full repository suite and Windows execution
were not run.

## Reproduce in a checked-out authorized branch
```bash
cd video_analyzer
python -m unittest -v test_offline_math_mc_bridge test_offline_math_input_gate test_offline_math_decision_snapshot test_offline_call_ev_from_counts
python offline_math_mc_bridge.py reviewed_decision_candidate.json new_mc_ev_report.json
```

## Remaining blockers
- Authorized, annotated 3–5 minute PLO5/PLO6 recording for OCR/hand segmentation
  accuracy and end-to-end video-to-math validation.
- Re-run against the exact repository Monte Carlo engine and broader test suite.
- Benchmark longer recordings and four-table processing.
- Connect reviewed MC/EV reports to the existing MP4 evidence report without
  making uncertain actions or strategic labels appear definitive.
