# Cycle 234 — Offline conditional Monte Carlo showdown equity

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. No gameplay, live capture, poker-site integration, action EV, or automatic promotion of OCR/reviewer claims.

## New files
- `offline_mc_equity.py`: standalone CLI revalidates the independent manual scenario against the unverified visual summary via `offline_mc_input_contract.build` and hashes, then simulates showdown equity under explicit opponent ranges. Exactly **two private cards + three board cards** form every evaluated Omaha hand. PLO5 and PLO6 supported.
- `test_offline_mc_equity.py`: synthetic regression suite for hand ordering, two-hole Omaha rule, PLO5/PLO6, deterministic seeds, wins/losses, two- and three-way ties, conditional weighted opponent combos, runout sampling, provenance, refusal of OCR origin, and output non-overwrite.

## Model and limitations
- Opponent combos sampled jointly proportional to product of user-entered weights **conditioned on no collisions**. Enumerates feasible assignments; fails closed beyond 100,000 feasible joint assignments.
- Future community cards drawn uniformly without replacement after opponent hands are selected.
- Monte Carlo seed fixed and recorded; per-trial payoff is hero's share of the showdown pot (1 for sole winner, 1/k for a k-way tie, 0 for a loss).
- Approximate 95% CI uses sample variance of independent per-trial pot shares; it does **not** include model/range/OCR/visual uncertainty. A degenerate all-win or all-loss sample yields zero estimated sampling variance and is not proof of certainty.
- Maximum 50,000 trials per CLI run for bounded proof-of-concept execution, though the preceding contract permits up to 2,000,000; reject larger requests rather than silently reducing them.
- No EV for fold/call/raise, no bankroll/poker advice, no automatic assessment of player mistakes. No real-world precision or performance claims.
- The summary's video hash is a **claim**; input_origin is a manual **claim**, not independently authenticated. Input JSON may be manually fabricated; the model is explicitly hypothetical.
- Reads inputs without modifying them, refuses to overwrite any output, checks hashes before and after calculation. Output includes hashes and warnings.

## Usage
From `video_analyzer/`:

```bash
python offline_mc_equity.py unverified_summary.json independent_manual_scenario.json NEW_equity.json
python -m unittest -q test_offline_mc_input_contract.ContractTests test_offline_mc_equity.EquityTests
```

## Verification / blockers
Synthetic tests only. Requires a user-authorized and annotated 3–5 minute PLO5/PLO6 video to validate OCR, card recognition, timestamps and end-to-end clips. No 40–60 minute Windows or end-to-end video validation. No GitHub Actions or paid services.
