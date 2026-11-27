# Macro04 full postflop / Macro05 ledger — 2026-11-27

Base 43798cd219bc3e6c5615708740d7f0a691c2298a, branch feature/plo5-plo6-training. Offline post-session PLO5 only. Direct git ls-remote again failed (DNS, exit 128). Recovered Linux sources in /mnt/data/plo5_05b matched remote starting blobs. Main not modified.

## Delivered
- d95d5a7fec9b349fc7fbf1b79080651cf1a59364: shared exact chance postflop solver (flop/turn/river); solve retains turn-only entry point, solve_flop and solve_multistreet added. Ordered runouts 1482/38/1 per physical compatible deal. Group chance transitions in one pass, memoize showdown share by deal and rank by holding/final unordered board, preserve distinct public histories. Budget 100000 public nodes, 1000000 node/deal visits per iteration, 155648 outcomes, 100000000 work units. Defaults lower. No sampled or abstract chance yet.
- 365eaac1cbd94c9d4b6264a3a8bb15055f2f7c3c: shared native adapter reads the correct next card from hidden ordered runout. Existing C++ executable reused (no kernel source change).
- 192306d93261a694225085e91aa0fa514de8b44f: condition joint ranges on history and correct street-dependent chance probabilities (1/39 then 1/38).
- 8f1bf151c65dea83678c0ad63fd184f5f0b5cf5c: independent rational uniform-policy root EV and both BR oracle across three streets (uses existing un-cached Omaha rank reference); public infosets, budgets, exact path mass, native flop parity and river-with-rake native comparison.
- e27a4d2973a7b6b3cc6924b57f59651c53c21f5b: Macro05 terminal financial ledger for 2–6 seats, layered pots, fold eligibility, returns, ties and capped rake.
- 8532e7dd60721c3100690259243e6ca6755e68fe: six ledger test methods, including 500 deterministic random all-live settlement cases. Initial fold fixture incorrectly expected fee 3 on contested 40 at 10%; corrected expected value to 4 and reran tests. The ledger assumes equal base pot eligibility, excludes prior side pots, rejects invalid folded-only layers, allocates rake proportionally across pots with fractional chips. No room-specific rule or strategic multiway certification.

Published blob SHA matches local executed:
  7ad2dbbe7459eb32dede10ae37530aacc90c73d3 plo5_post_gto_turn_solver.py
  0317bc60e0158a23ac11e75aaeb45f5256f41943 plo5_multistreet_native.py
  0a59cd2631053855621c9a8c002c3924f1124857 plo5_post_gto_turn_reach.py
  7a9be2ddf3f0fbf68f304c39cc6a8f32f6ff7dd5 test_plo5_full_postflop.py
  cadcf4b59d54f37a1d34807017b6fafcd7ca29d8 plo5_post_gto_multiway_ledger.py
  65c853be430c9ade18a10c5511910fb386fff0d9 test_plo5_multiway_ledger.py

## Tests
From recovered video_analyzer directory:
    PLO5_CFR_EXE=../native/cli PLO5_MULTISTREET_EXE=../native/multistreet python -W error::ResourceWarning -m unittest discover -q
    Ran 53 tests in 13.233s
    OK
    python -m compileall -q .
    exit 0
Prior regression 42/42, new full-postflop 5/5, multiway ledger 6/6. This is the recovered subset, not whole repository. Native parity on full flop at 3 iterations for no rake and synthetic 50% rate/cap 3/fold rake; compare all frequencies and action EVs plus root EV/BR with 1e-8 tolerance. Also compare native shared river vs existing Python rake river on two settings at 100 iterations.

## Fixture and performance
dict(polar(),board=BOARD[:3]), pot/stacks 2 BB, pot_bps=(), zero rake, 2 weighted compatible pairs. 2964 ordered outcomes, 16983 public nodes, 80028 node/deal visits per iteration, 2403 rank cache entries. Native sequential wall times:
| iterations | NashConv BB | seat0 EV BB | seconds |
|---:|---:|---:|---:|
|1|1.2916104363472154|0.6666666666667085|1.3161024|
|20|0.5439985078389189|0.8193545331486967|1.283955707|
|100|0.0847893643302009|0.9780158130111682|1.147230236|
|500|0.022702873827339154|0.9863422113618281|1.653961904|

Separate sequential comparison (warm rank cache possible), 20 iterations: Python 3.922292095 s, native 1.088097486 s, identical NashConv. No median benchmark or isolated peak RAM; parent process ru_maxrss max 208884 KiB across successive solves (not concurrent child or Windows RAM). At 500 iterations gap/pot = 1.1351%, above provisional 0.5% target. No full GTO or profit claim.

## Remaining
Macro04 partial: broader ranges/stacks/sizings, chance sampling/abstraction with held-out evaluation, budgets, stronger independent nonuniform BR oracle, postflop strategic cache and integration, Windows. Macro05 financial foundation started, still need joint correlated deals for 2–6 seats, folded-card blockers, per-player CFR+/BR/NashConv, prior pot layers and room-specific rake/odd chips. No multiplayer convergence guarantee. Preserve earlier full checkout/regression, video reconstruction and delivery backlogs. Main launcher rake integration pending; shared native river rake available as a separate solver entry point, not wired to existing rake GUI/cache. No future information in policy.
