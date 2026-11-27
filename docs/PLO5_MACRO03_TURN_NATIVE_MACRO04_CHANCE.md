# Macro03 turn-river / Macro04 chance — 2026-11-27
Base e49123d15f1a48b06664759009fcff703cb01634, branch feature/plo5-plo6-training, offline PLO5 only. main untouched.
Recovered sources in Linux workdir /mnt/data/plo5_05b; tree, context, rake solver, turn chance hashes matched current GitHub. Direct git ls-remote again exit 128, Could not resolve host github.com. No full checkout, Windows or video session verification.

## Delivered
- a79b10edae7228fa8b8c1be75fe5149438bb08e1: restricted HU turn-river exact-chance CFR+ with two utilities, explicit rake, shared information sets, all-in runouts and per-seat best responses. Predealt hidden river participates only in terminal payoff and public chance routing; turn policy keys are public history/node plus own holding, not future card.
- 3d21daeb991e2b6aa719689b0a14f1bda1460dc5: native two-utility CFR+ kernel, bounded flattened scenario forest with shared infosets. No change to older native zero-rake river kernel.
- 9b3e5ec6202abfa6085464dcedfe1b5e8e766c4d, 7e576453d6042c3991c60b14d21c0666cfaeb6b2: adapter and optional native turn backend. Python retains tree construction, ranks, EV/BR diagnostics and default fallback choice (native failures propagate).
- 9f4cf9a8a8871fd59d69a22a1002d0a03c068003, a4b8a4715439c8aabcb35c5729879d6825c2676b, c9ee45e39092ce1f279b98a9200520820fe2e9e1: test suite: 6 methods including independent all-in EV and independent uniform-policy two-player best response oracle, 9 native parity comparisons, 3 invalid native inputs, information set and convergence checks.
- b2577d4d3bd90fa9c31f8fbec83cbaf566a4c5c0, 9697134e64972f0c1a4ebe9f79076154de735511: exact rational conditional joint range and 3 tests for observed action + public chance path. Known holdings must be known at observation time; not a prediction of actual opponent cards.
- 41da4f1347b5122190b71576e1a7d69ee4f5e5d5, 5868ed173da835c4db689421a70355f4379db98b, f06edc1a682af8afdbab402dc6f3687ef1d82072: Macro04 streaming exact ordered flop runouts, blockers, probability conservation, turn consistency, budgets. Last commit aligns inconsequential semicolon with tested blob. Per compatible pair 39*38=1482 ordered paths. Not strategic flop solver yet.

## Evidence
Final local git hash-object / remote matched:
 b20f971674e59147cb9a2ea32e5160f317a1d12d plo5_post_gto_turn_solver.py
 906b82d7b38278cdfb9bbbda5fe9764a626d9be7 native/plo5_multistreet_cfr.cpp
 c26c841e6670b016be5b3c232d8bb93bf98dead5 plo5_multistreet_native.py
 71e3a5c289bcdac6a8c57acb2997c79bdec8456d test_plo5_turn_solver.py
 0eb0a1c11c801e99160713b9a396883e1e7cf69b plo5_post_gto_turn_reach.py
 0f1ae084b854a1cb8359655f60df946aa0e2cdd1 test_plo5_turn_reach.py
 cde22998cee7946e19201733a62a85df2ad25e16 plo5_post_gto_flop_chance.py
 d8d36912a02291c42f29a081a68577f4c80f5616 test_plo5_flop_chance.py

Build:
    g++ -O3 -std=c++17 -Wall -Wextra -Werror native/plo5_multistreet_cfr.cpp -o native/multistreet
Initial misleading-indentation warning corrected. Final build clean.
From video_analyzer directory:
    PLO5_CFR_EXE=../native/cli PLO5_MULTISTREET_EXE=../native/multistreet python -W error::ResourceWarning -m unittest -q test_plo5_flop_chance test_plo5_turn_reach test_plo5_turn_solver test_plo5_turn_chance test_plo5_rake_solver test_plo5_post_gto_macro02 test_plo5_post_gto_river test_plo5_post_gto_river_native
    Ran 42 tests in 2.939s
    OK
Prior invocation mistakenly named nonexistent test_plo5_river_native in addition to the correct module (43 discovered, one import error); corrected invocation above. python -m compileall -q . exit 0 on recovered subset.

Fixture dict(polar(),board=BOARD[:4]), pot and stacks 2 BB, pot_bps=(), rake zero, two compatible physical pairs, 76 hidden outcomes, 396 public nodes, work per iteration 1368:
| iterations | NashConv BB | value seat0 BB |
|---:|---:|---:|
|1|1.188596491228071|0.6666666666666646|
|20|0.2741657839618954|0.9453067487889457|
|100|0.08871598344166254|0.98297565744148|
|1000|0.017733207740734058|not recorded|

Wall-time single sequential solves (Python first, native second, warmed rank cache possible), not rigorous median or Windows benchmark:
| iterations | Python seconds | native seconds | gap both BB | max policy frequency diff |
|---:|---:|---:|---:|---:|
|100|0.232890415|0.02490828|0.08871598344166254|0|
|1000|1.5968048|0.04047677|0.017733207740734058|0|
Parity tests include zero rake, 50% synthetic stress-test rake cap 3 with and without fold charging, at 1/20/100 iterations, compare EV and BR within 1e-8. Uniform independent oracle computes optimal responses conditional on own holding and public chance, verifies both BR and root EV within 9 decimal places. Evaluator reference uses existing un-cached Omaha rank, not an independently sourced evaluator. Gap at 1000 is about 0.887% of starting pot, still above 0.5% target. No convergence guarantee for variable sum or broad ranges.

## Pending
Macro03 remains partial: broader multi-sizing/deeper-stack/weighted range tests, exact oracle beyond uniform strategy, convergence/quality and RSS benchmarks, cache provenance and persistence for turn, review integration; native max forest and work limits; validate no leaks on actual reconstructed hands. Macro04 started only chance streaming, no flop betting solver. Native separate-utility river backend integration (standalone river), main launcher rake, room rules, full regression, Windows and video remain open. Next build shared multi-street chance/infoset architecture with bounded sampling or exact on small fixtures, extend to flop while preserving these gates.
