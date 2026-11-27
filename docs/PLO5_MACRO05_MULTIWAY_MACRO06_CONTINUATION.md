# Macro05 multiway / Macro06 continuation foundation — 2026-11-27
Base cce4219637227dce93b012b028794b601aed7018. Branch feature/plo5-plo6-training, offline PLO5 only, main untouched. Direct git ls-remote failed DNS (Could not resolve host github.com); recovered source subset in /mnt/data/plo5_05b. Prior ledger/turn solver blobs matched official repository.

## Deliverables
- 67255e81a180cfb45781d5ad3ffa22873164a885: C++ 2–6 seat vector utility CFR+, shared infosets and per-player reach.
- b15db3e168e436c7977da52853fbf6f40a42a9b8: bounded native forest adapter.
- 9e04da471096046b452dafd1d7568022f6c4cdc4: exact chance postflop multiway solver, discrete pot-limit actions, independent payoff/BR per player, correlated priors, cached ranks and settlements, rake and side pots through existing exact ledger.
- 4eab2a627e08f26054ecc33533c475c3cf100f22: six tests including 2–6 players, weighted/disjoint range constraints, pure-response enumeration of small three-seat river, turn chance and six native parity comparisons.
- ce95dfb2899f727ca3145ae8611fccf0c4583d87: modeled-game identity and singleton support diagnostics. Identity is game identity, not iteration/backend-specific cache key.
- 41d42b878b73423b9cca253a605b430180048f56, ecafe767e6932f0246822c8f01acd286bc56a120: exact decimal-rational posterior of joint distributions through modeled actions and public draws; folded holdings retained as blockers. Three reach tests, including full conservation over next card branches after fold.
- 0b89c156dca06a3ee15366c04c374a98faf980aa, 803a6192a35ba51ed8335beecd98f6e09bd2dc80: optional conditional EV rows for each full private distribution at fixed public root/prior/average policy, weighted EV reconstructs overall EV. Two tests, including 3-seat flop and asymmetric stacks. This is groundwork, not preflop continuation certification. Do not insert a fixed table into an unrelated range/reach context.

## Final source verification
All 7 final code/test blobs matched exact files executed locally:
 d524d89a95b06974ae7d1df2b97ee1d66861f45d native/plo5_multiway_cfr.cpp
 6282ea49901636c213ad7fbc59046bde249e1a6c plo5_multiway_native.py
 32d4463d95f9b7e4de1e04370c95a24a52362788 plo5_post_gto_multiway.py
 9e01bb38d57c5bed4bc87d2e9bd2db15beeadcb3 test_plo5_post_gto_multiway.py
 b98ba6df1ea82a0167da5c4da144367a40b00413 plo5_post_gto_multiway_reach.py
 b9cb4403eae4e1b6951eb90cb3de9e8959978750 test_plo5_multiway_reach.py
 4d5bcd4f8105a4b98d2bae343e00da147dabfc9b test_plo5_multiway_continuation.py

## Actual commands
    g++ -O3 -std=c++17 -Wall -Wextra -Werror native/plo5_multiway_cfr.cpp -o native/multiway
    cd video_analyzer
    PLO5_CFR_EXE=../native/cli PLO5_MULTISTREET_EXE=../native/multistreet PLO5_MULTIWAY_EXE=../native/multiway python -W error::ResourceWarning -m unittest discover -q
    Ran 64 tests in 17.110s
    OK
    python -m compileall -q .
Both final commands exit 0. 53 historical methods plus 11 new methods, all native env vars supplied. Six parity fixtures: river 2/3 seats with two holdings per seat, river 4/5/6 seats single holding, turn 3 seats single holding, 10 iterations, synthetic 50% fee cap 2 with fold rake. Compare all frequencies, action EVs, root EV and BR within 1e-8. Independent oracle enumerates pure plans for each of three players on a fixed-deal river, using production tree for public topology but unit-chip cash flow and uncached rank evaluator, not production settlement/BR recursion. Not an independent evaluator certification or broad-range BR oracle.

## Measurements
River fixture(6,2), 1 BB stack per seat, pot 2 BB, 64 joint distributions, 385 nodes, 100 iterations, 500 bps cap 2 with fold rake. At these tiny integer chip pots the fee rounds to zero; rake effects are tested separately with synthetic high rates, not realistic room rates.
Python 6.029220386 s, native 0.278786495 s, ~21.63x, sequential wall time includes tree/evaluation/diagnostics. Python NashConv 0.024054042054858046 BB vs C++ 0.024054042054858293 BB. EV Python [-0.0072096151804317155, 0.043237001757266816, -0.0001440426328942549, 0.8870532210062017, -0.00010334200309480839, 1.0771667770529527]. Single-run benchmark, no claim on Windows/session time.
Three-seat flop fixture(3,1,3), 1 iteration, native: 28,925 public nodes, 1,122 ordered runouts, 1.8754 s, NashConv 2.188997 BB. Three-seat river asymmetric stacks 1/2/3 BB, pot 3, 34 nodes, single deal. This only verifies basic execution/conservation. 6-seat full flop, deep stacks and broad ranges not tested.

## Limitations / next
Root assumes positive stacks, equal eligibility in root pot, no prior side pots and no players folded before root. In-street and later folds retain blockers. Ledger uses proportional fractional rake allocation, cap zero means zero rake, no room-specific odd-chip rule. Product-weight prior conditioned on disjunction or explicitly weighted joint prior; limited support may reveal opponents' holdings via own cards; diagnostics flag singleton holdings but do not correct inference or guarantee coverage. Maximum 4096 joint deals, 1M Cartesian candidates, 155648 outcomes, 100000 public nodes, 1M node-deal visits per iteration and 100M work; defaults lower. Not all maximum combinations fit simultaneously. Native input assumes trusted local adapter; no general convergence guarantee in multiplayer. No actual full game GTO or profit claim.
Macro05 remains partial: broaden asymmetric/deep-stack and multi-sizing tests, six-player flop budgets, weighted independent BR oracle, prior pot layers and folded pre-root blockers, cache and model provenance, native protocol audits and RAM, full checkout, Windows, actual video integration. Macro06 initial conditional EV export only; next recover preflop exact modules and connect public flop transition, joint reaches and utility baseline, validate integrated restricted game independently. Preserve all previous backlogs including rake launcher and room rules. 
