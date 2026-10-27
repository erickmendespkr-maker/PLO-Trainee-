# Cycle 134 — reviewed range Monte Carlo to conditional call EV (offline)

Scope: docs/VIDEO_ANALYZER_SCOPE.md. No live poker integration, playable tables, autonomous opponents, or real-time decisions.

## New bridge

video_analyzer/offline_reviewed_range_equity_bridge.py connects the cycle-133 reviewed-hand schema to the existing range_ev.estimate_weighted_range_equity engine. The input has exactly five keys:

- schema_version: 1
- reviewed_hand: cycle-133 schema with equity_estimate set to null
- review_gate: status is synthetic_fixture or human_confirmed_claim, plus reviewer_label
- weighted_range: 1 to 1000 explicit card combinations and nonnegative weights, at least one positive
- monte_carlo: trials 100 to 50000, seed 0 to 2^64-1

Usage: python video_analyzer/offline_reviewed_range_equity_bridge.py input.json new_output.json

For a heads-up single-pot call with no future betting or side pots, the bridge recomputes equity against the declared weighted combos. The existing engine enforces Omaha's exactly-two-private/three-board rule. The bridge propagates the engine's 95% Hoeffding sampling interval to EV(call) = equity * (pot_before_call + call_cost) - call_cost - expected_rake. Fold EV is zero relative to the decision. Rake is a fixed unconditional analyst estimate, not a rake schedule.

**The opponent range is a hypothesis, not inferred from video. The review gate is a claim, not independent verification.** The Hoeffding interval covers Monte Carlo sampling uncertainty, not range plausibility, OCR, or annotation uncertainty.

Unresolved annotations, non-call actions, multiway pots, unaffordable or zero calls, future betting, side pots, and mismatched gate/annotation type block Monte Carlo and EV. Supplied external equity is rejected to avoid representing it as recomputed. The report preserves the claimed source hash, range hash, seed, trials, wins/ties/losses, sampling interval, EV interval, and explicit flags indicating that video/range/strategic correctness are not verified. Automatic clip selection is not authorized.

## Verification and limitations

24 new synthetic unit tests and 25 cycle-133 regression tests passed locally (49 total). They cover PLO5/PLO6, deterministic samples, flop sampling, weighted combos, blocking conditions, malformed inputs, and safe JSON export. The two new published Python files have Git blob hashes matching the locally tested versions.

The local test harness used behaviorally equivalent minimal copies of the existing range_ev.py, equity.py, and hand_history.validate_cards because direct Git cloning was unavailable. **The full checked-out repository, full regression suite, CI and real-video integration were not tested.** These results do not validate OCR, source video, opponent ranges, long sessions, or the complete application.

## Blocker

No authorized annotated 3–5 minute sample video is available. Continue with independent components and synthetic tests until supplied.
