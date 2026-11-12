# Conditional call EV — synthetic acceptance vectors (cycle 303)

Scope: offline PLO5/PLO6 video review only. This document specifies independent, auditable arithmetic fixtures, not a GTO solution or evidence about a recorded hand.

## Simplified heads-up model

Assumptions: one opponent, no rake, no side pots, no future betting, pot P measured before the hero calls, incremental call cost C. Equity q includes tie share. EV(call) = q(P+C)-C. Break-even q = C/(P+C). EV(fold) = 0 measured from the current decision. These equations are **not** valid as a general multiway/raise/side-pot solver.

| Range hypothesis | P (bb) | C (bb) | q | Conditional q interval | EV (bb) | Conditional EV interval (bb) |
|---|---:|---:|---:|---|---:|---|
| wide | 150 | 50 | 0.30 | [0.29,0.31] | +10 | [+8,+12] |
| tight | 150 | 50 | 0.20 | [0.19,0.21] | -10 | [-12,-8] |
| boundary | 150 | 50 | 0.25 | [0.24,0.26] | 0 | [-2,+2] |

Expected break-even: 0.25. Wide versus tight is **range_sensitive**, never an automatic error/acerto verdict. The interval between scenario outcomes is a sensitivity envelope, not a statistical confidence interval for the unknown opponent range. Monte Carlo confidence intervals, when available, must identify iterations and seed and remain conditional on the chosen range.

## Acceptance requirements

1. Reject NaN, Infinity, boolean-as-number, duplicated range IDs, reversed intervals and equity estimates outside their intervals.
2. Preserve source video SHA-256, hand/table IDs, timestamps and manual-review provenance before binding to any footage.
3. Never promote hypothetical ranges to observed evidence, GTO solutions, confirmed mistakes or automatic clip selection.
4. Mark missing video evidence as INSUFFICIENT_DATA.
5. Do not use PLO Mastermind data, scraping, proprietary solver output or any live poker connection.

Implementation and 12 passing local synthetic unit tests were prepared separately for this cycle; this document does not claim those local files are committed or that repository CI has executed them.
