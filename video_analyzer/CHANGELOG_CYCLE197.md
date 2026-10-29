# Cycle 197 — offline conditional EV sensitivity

## Scope
Adds `offline_conditional_ev_sensitivity.py`, a JSON-only, offline sensitivity analysis for the hypothetical terminal heads-up PLO5/PLO6 fold/call/raise EV model from cycle 196. It does not infer opponent behavior or evaluate a recorded decision.

## Interface

```sh
python video_analyzer/offline_conditional_ev_sensitivity.py input.json new_output.json
```

Input must contain `hypotheses` (1–5 objects, each with a unique `label` and a complete cycle-196 `ev_input`) and `fold_probabilities` (2–21 strictly increasing finite values in [0,1]). Every hypothesis must describe the same variant, hero cards, board, pot, call cost and raise size. Opponent ranges, seeds and simulation counts may differ.

Each hypothesis is Monte Carlo sampled **once per call/raise-called scenario** by the existing EV engine. For each assumed fold probability `p`, the model computes `raise_EV = p * pot_now + (1-p) * called_raise_EV`, holding its conditional range fixed. Call EV is constant along the probability grid. Outputs include marginal Monte Carlo sampling bounds and their conservative combination for EV differences; these are **not** joint 95% confidence intervals and do **not** quantify range/fold-probability uncertainty.

## Local verification

- 13 new `unittest` methods pass, covering PLO5/PLO6, endpoint arithmetic, synthetic royal flush, independent range hypotheses, determinism, bad inputs, mismatched hand/pot, CLI and no-overwrite.
- 211 selected local tests passed with the cycle-196 ZIP dependencies (not the repository's full test suite).
- A two-hypothesis PLO6 synthetic CLI run produced a JSON report with six assumed fold probabilities. This is not an evaluation of a recorded hand.
- GitHub Actions not used. No production, secrets or main-branch changes.

## Limitations / blockers

- No authorized, human-annotated 3–5 minute PLO5/PLO6 video for real OCR/hand-reconstruction accuracy measurements.
- No link from the new sensitivity JSON to the acknowledged frame gallery or MP4 HTML explanation yet.
- No Windows validation, long-session benchmark, rake, multiway, side pots, all-in or future-betting model.
- `manual_review_confirmed` is a human assertion, not independent proof that cards are visible.

## Next

Integrate the sensitivity JSON into an offline explanation/report with explicit provenance and no action-grade claim. Subsequently connect it to reviewed video evidence only when the source hand and all relevant inputs can be cross-checked, without upgrading OCR proposals into facts.
