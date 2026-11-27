# PLO5 solver acceptance gates

Scope: offline post-session study only. No claim of guaranteed real-world profit.

1. Rules and rank evaluator: independent exact oracle tests, exhaustive five-card ranks where feasible, exactly two hole cards and three board cards; card collisions, pot-limit bounds, short raises, side pots, uncalled returns and rake.
2. Chance: exact enumeration when feasible; otherwise reproducible sampling, independent holdout and uncertainty intervals. Distinguish sampling error from abstraction error.
3. Strategy: normalized policies, conditional EV with explicit baseline, independent best responses. In two-player zero/constant-sum restricted models report Nash gap divided by initial pot; provisional targets 1%, 0.5%, 0.1%. No full-game certificate from restricted-tree gap. Action-dependent rake may break constant-sum assumptions.
4. Multiway: report every unilateral deviation gain and NashConv on supplied support; no CFR convergence guarantee or universal profit claim. Check holdout chance support and range sensitivity.
5. Continuation: public-card chance transitions with physical blockers and action-conditioned reaches; no future board information in decision infosets. Independently validate cross-street EV.
6. Performance: record hardware, wall time, peak RSS, tree size, legal deals, iterations, cache hit rates. Compare identical workloads before/after optimization; no extrapolated benchmark claims.
7. Release: reproducible end-to-end tests against actual checkout and reviewed real hands; external comparisons when equivalent parameters are available. Keep unresolved states explicit. No promotion of experimental policies to certified full GTO.
