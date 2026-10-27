# Cycle 133 — conditional reviewed call EV (offline only)

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. This cycle does not read poker clients, capture live tables, play hands, recognize cards, compute equity, or authorize automatic clips.

## New component

`offline_reviewed_call_ev.py` accepts a **separately declared** synthetic or human-annotated PLO5/PLO6 hand and an **externally supplied** Monte Carlo equity estimate with a claimed confidence interval. It validates card syntax/count/uniqueness, declared opponent-range assumptions, the claimed simulation seed and trial count, and pot/call/rake units. It computes a **conditional** chip-EV comparison of a call versus folding only for a single heads-up pot with no future betting or side pots. Fold EV is zero relative to the decision, treating earlier chips as sunk.

The equation is `EV(call) = equity_share * (pot_before_call + call_cost) - call_cost - expected_rake`. The pot includes opponent bets already made and excludes the hero's pending call. The equity share includes ties; rake is a fixed unconditional expected chip cost, not a full rake model. The interval is a mechanical propagation of supplied equity bounds, **not a newly computed statistical confidence interval**. Break-even equity is `(call_cost + expected_rake) / (pot_before_call + call_cost)`.

The tool blocks EV output when equity is absent, annotations are unresolved, action is not call, more than one opponent is declared, future betting/side pots are present, or the call is zero/unaffordable. It rejects invalid cards, malformed numbers, contradictory intervals, duplicate JSON keys, existing output files and symlink input paths. The tool does not treat a human-annotation label as independent verification of the source recording.

## Usage

`python video_analyzer/offline_reviewed_call_ev.py reviewed_hand.json new_conditional_ev_report.json`

The output file must not already exist. See `test_offline_reviewed_call_ev.py` for a complete synthetic input fixture and the exact schema. Example fixture: pot=100, call=40, equity=0.40 with claimed bounds [0.38, 0.42], expected rake=0. EV(call)=16 chips, propagated range [13.2, 18.8] chips, break-even equity approximately 0.2857. This is a mathematical demonstration, not a recommendation or a verified poker decision.

## Integration boundary and limitations

The earlier `offline_hand_evidence_review_queue.py` marks all hands as requiring manual review and does not authorize equity/EV. This module **does not bypass that gate**: a separate explicit annotation file is needed, and it remains unverified. Linking queue entries to reviewed annotations and validating actual Monte Carlo engine outputs are future work. A range label/assumptions are recorded but not evaluated; the external equity estimate might not correspond to that range. No side pots, raises, fold equity, future streets of betting, real-video OCR, or clip export are analyzed here.

## Verification

25 synthetic `unittest` tests passed locally. Source and test Git blob hashes can be compared to published branch blobs. Full repository regression and CI are not claimed.
