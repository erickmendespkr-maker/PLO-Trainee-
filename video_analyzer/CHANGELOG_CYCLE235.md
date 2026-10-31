# Cycle 235 — conditional chip EV, offline PLO5/PLO6

## Scope

Implements `video_analyzer/offline_mc_action_ev.py`, an **offline** calculator
for conditional *decision-point chip EV* from an independently entered scenario.
It calls the cycle-233 validator and the cycle-234 Monte Carlo equity engine;
there is **no OCR-to-math authorization** and no live poker integration.

## Model and formulas

Let `P` be `pot_before_call` (all chips in the pot **before** hero acts,
including opponent's current bet), `C` be `to_call`, `e` the Monte Carlo
showdown equity (pot share, including split pots), and `R` the hero's total
raise contribution from this decision point.

- `EV(fold) = 0` (baseline: no further chips invested).
- `EV(call/check) = e * (P + C) - C` (no further contributions, no future betting).
- Heads-up optional raise model: opponent has already bet `C`, can match
  the raise, and contributes `R - C` **if called**. If `f` is assumed fold
  probability and `e_called` is an **independently supplied** conditional
  showdown equity for the opponent's calling range:

  `EV(raise) = f * P + (1 - f) * [e_called * (P + R + (R-C)) - R]`

  This deliberately does **not** reuse pre-raise equity as if it described
  a calling range. The engine does not infer fold probability or called equity.
  Raise EV is rejected for multiway pots (side-pot and response modeling absent).

## Important limitations

- Zero rake, no future betting, no side pots, no ICM, no tournament risk.
- The `pot_before_call` field must include all chips already committed.
- Opponent stack coverage is explicitly assumed, not measured from video.
- Raise fold probability and called equity are **manual assumptions**;
  there is no confidence interval for the raise estimate.
- The call/check EV interval is a linear transformation of the equity
  engine's approximate Monte Carlo 95% interval; it does not account for
  uncertain cards, ranges, OCR, future action, or model misspecification.
- A positive modeled EV is not a definitive strategy recommendation.
- No OCR or visual-review ledger becomes verified mathematical evidence.
- The source summary is explicitly *unverified*; source video hashes are claims.

## CLI

```bash
python video_analyzer/offline_mc_action_ev.py \
  SUMMARY.json SCENARIO.json ACTIONS.json NEW_RESULT.json
```

The action JSON has exactly these keys:

```json
{
  "schema_version": 1,
  "source_scenario_sha256": "<sha256 of scenario file>",
  "model": "single_decision_showdown_no_future_betting_zero_rake",
  "rake": 0,
  "assumptions": "No future betting, side pots, or rake; pot already includes opponents' bets.",
  "raise_model": null
}
```

To model a **heads-up** raise, replace `raise_model` with:

```json
{
  "raise_total": 75,
  "fold_probability": 0.2,
  "called_equity_fraction": 0.5,
  "opponent_can_match_raise": true,
  "assumptions": "Opponent can cover the raise; fold probability and called equity are independent assumptions."
}
```

The CLI revalidates the source summary and independently transcribed scenario,
recomputes Monte Carlo equity, verifies hashes again before writing, and
refuses to overwrite an existing result. No external API or live poker data.

## Verification

Synthetic unit tests cover chip accounting, wins, losses, splits, PLO5/PLO6,
fold/call/check/raise, heads-up restriction, invalid probabilities, invalid
rake, action-source hash mismatch, OCR-origin rejection, deterministic outputs,
and CLI overwrite/duplicate-key protections. A 3–5-minute authorized,
annotated recording is still needed to validate actual video recognition.
No Windows or 40–60-minute session validation is claimed.
