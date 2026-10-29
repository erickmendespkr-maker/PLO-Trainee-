# Cycle 201 — Offline blocker-aware range preflight (synthetic)

## Scope
Only `feature/plo5-plo6-training`. No live poker, simulator, betting, production, credentials or paid infrastructure.

## Changes
- New `offline_range_blocker_audit.py` checks human-declared hero/board cards against each hypothetical call and raise-called weighted opponent range, for PLO5 and PLO6.
- Rejects invalid combos, duplicates (including reordered cards), wrong variant, invalid weights, hero/board overlap and ranges with no eligible combos. Individual opponent combos blocked by known cards are excluded and counted.
- Records supplied/eligible/blocked combo counts, blocked *weight fraction*, model SHA-256 fingerprint and whether legal conditional ranges overlap. Weighted ranges are renormalized after blockers; this is **not** an empirically inferred opponent range.
- Uniform ranges remain marked hypothetical. Disjoint call/raise-called ranges are permitted as distinct conditional assumptions but explicitly disclosed.
- The acknowledged sensitivity bundle includes `range_blocker_audit` in JSON and a bounded, HTML-escaped-by-construction numeric summary in the offline HTML. No raw combo/card text is inserted into the HTML audit section.
- 12 new standalone tests and 2 integration tests; selected regression suite: 110/110 passed locally. Synthetic PLO6 bundle generated with 75% of supplied call-range weight blocked, and HTML disclosed this fraction.

## Reproducibility
From `video_analyzer`:

```sh
python -m unittest -q test_offline_range_blocker_audit.py test_offline_acknowledged_sensitivity_bundle.py test_offline_plo_equity_monte_carlo.py test_offline_conditional_action_ev.py test_offline_conditional_ev_sensitivity.py test_offline_acknowledged_ev_sensitivity_html.py test_offline_ev_assumptions_form.py
```

## Not verified / blocked
- The full selected offline discovery suite was attempted but exceeded the local execution time limit; **do not** count it as passed.
- No real annotated PLO5/PLO6 video was available. OCR accuracy, action reconstruction, player identification, real-hand EV calibration, Windows file:// behavior and 40–60 minute four-table performance are not verified.
- Human acknowledgement remains a declaration, not automated visual proof. Sampling intervals do not cover uncertainty in opponent ranges or fold probabilities.
- No GitHub Actions used. Main, production and secrets untouched.

## Next
Synthetic four-table video/timestamp segmentation benchmark, then real annotated 3–5 minute video evaluation when supplied. Consider an explicit preflight page in the offline form, but never infer ranges from OCR as fact.
