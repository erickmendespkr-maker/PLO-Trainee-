# Macrobloco 01 — native river validation (2026-11-27)
PLO5 offline only. Source base 31f407be8040db8afc288740dac2738ac0be6c6e. Linux GCC 14.2.0, Python. No main changes.
Recovered exact original native CLI/kernel and Python adapter verified by git hash-object:
- CLI 75d60b469640cd0fc6a39ccc65c1d8cc936071f0
- kernel e6ffc0eea38f9ae8b39e72554a0270a1d65b817e
- adapter ba667d656da6ff29f8ff9802a1f734cafec414ff

Integration commit 9afdef32cfda11bcdd5297c06fa3e78dcb0866a1, solver blob e25dca88ce3c67b20b9171175a4e7457cfcb2f39 matches locally executed file. Optional keyword cfr_executable; default remains Python. Terminal utility is affine in showdown share q, fold utilities constant. Existing native protocol reused; no CONT1 needed. Same deals, infosets and public tree; common Python evaluation/BR/EV reporting. Native failures propagate rather than silently fall back. Backend identified in result.

Tests: 5986f4ed69cef80e33af1a9df1328b31799060db; per-action independent oracle added at 8a3f40bd8d43ed000303bebeb5ba3a6ec9dca6d4, final blob 85611ec7995427465c98afd867361bbd68e7be69 matches tested file.

Commands from recovered source directory:
    g++ -O3 -std=c++17 native/plo5_cfr_kernel.cpp -o native/kernel
    native/kernel
    g++ -O3 -std=c++17 native/plo5_cfr_cli.cpp -o native/cli
    cd video_analyzer
    PLO5_CFR_EXE=../native/cli python -m unittest -v test_plo5_post_gto_river test_plo5_post_gto_river_native
    python -m compileall -q .

Actual result: PASS 21 analytical HU fixtures. All 12 Python test methods passed in 0.781s, including 22 backend comparisons, 5 malformed protocol inputs, missing executable, and independent per-action cash-flow oracle on the nine-node game (6 runs). Comparisons use absolute 1e-8 tolerance for policy frequencies, EV, BR, value, reach, gap and 1e-9 for independent oracle. Compileall on recovered subset passed. Counts are test methods/analytical fixtures, not independent full game certifications.

Benchmarks: median of three solves per backend, wall clock includes evaluator, tree, subprocess, training and common diagnostics, warm process. Seed 27112026 for weighted ranges. No Windows or whole-session speed claim.

| Fixture | Nodes | Pairs | Iterations | Python ms | C++ ms | Speedup |
|---|---:|---:|---:|---:|---:|---:|
| Polar (pot 2, stacks 2, BB 1) | 9 | 2 | 5000 | 81.3819 | 5.1663 | 15.75x |
| Deep (pot 20 chips, stacks 200, BB 2) | 141 | 2 | 1000 | 237.7772 | 15.9762 | 14.88x |
| Weighted (12 holdings per seat, pot 12, stacks 20/22, BB 2) | 39 | 75 | 500 | 976.2915 | 34.3696 | 28.41x |

Gap BB Python/native: polar 0.005482399819266348 both; deep 0.04397127712245208 / 0.04397127712224602; weighted 0.027896275526287262 both.
Benchmark deep uses NUT/BLUFF weights 1/2 against CATCH weight 1; weighted uses random.Random(27112026), deck rank order 23456789TJQKA and suit order cdhs, exclude BOARD fixture; draw each holding via sample(deck,5) then randrange(1,30), 12 per seat. Both deep/weighted use 5000/10000 pot bps. Polar uses pot_bps=().

Status: core native integration and focal mathematical gate passed. Macroblock 01 not fully certified: full checkout/regression and RSS measurements remain outstanding, as do broad ranges, Windows target, complete preflop parity and actual video sessions. Continue these pending tasks and start independent 05C components as feasible. No rake/multiway or full-game GTO claim. No guaranteed profit.
