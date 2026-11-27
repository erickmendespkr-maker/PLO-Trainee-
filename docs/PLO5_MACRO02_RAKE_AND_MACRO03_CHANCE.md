# Macro02 rake / Macro03 chance — 2026-11-27
Base 553483049c2dfc2f45270b88ee0d86b51644957e. Offline PLO5 only. main unchanged.
Recovered prior source hashes match. Linux Python 3.13.5. Full git clone remains blocked by DNS (Could not resolve host github.com). No claim of complete repository regression or Windows verification.

## Delivered and blob-verified against locally tested files
- bc8136de5d97965c803fe2470693db8d6c8cb1bf — rake-aware HU river CFR+ heuristic, independent utility vector, per-seat BR, NashConv, explicit fold rule, expected rake and EVs (778fc8f040e08cec463d53a2fe87b1919e89ebac).
- 92a1687122e17e0c1a4e8bd71f3ef0f3fb572a4b — cache model identity includes fold rule, context rate/cap, backend, source hashes. No silent native fallback for rake (0d891a89a7d65a732e2c6e31c7353c81b37f80d2).
- 484c62875bf81461dc1635216c37cc9310515a7c — profiles by platform/club/stake, SQLite, exact percent-to-bps and BB-to-chip conversion (42202954c074e4ecc913faddf973ad0b88b89e11).
- f283d1a5c978a1dfe84f208fd32f90c06fc37231 — standalone Tkinter offline river study GUI, JSON context import, presets, background worker for local desktop computation, cached result (bb3491b7c81043ced9c6f20644254f3991b6c45d).
- 5d5a88df4a42e7562cb08a5dba112d721169515a — 5 test methods, including 8 independent oracle parameter combinations (9891b2168647425b1ea37cb580296dae9f776255).
- 9a9aa77595e96bd86da175eaa8eefc1eadb4fa78 — Macro03 exact physical turn-to-river public chance from root ranges, branch probabilities and conditional joint deals (3f920776a501e5aa92f75020cba68af73fac389d).
- f4c62c214a7e128845d96b17db63067f084a1978 — 3 chance tests (619eb332d0d61b8b6be3b92f71da9f4d1ecfeff1).

## Evidence
From recovered video_analyzer directory:
    PLO5_CFR_EXE=../native/cli python -W error::ResourceWarning -m unittest -q test_plo5_turn_chance test_plo5_rake_solver test_plo5_post_gto_macro02 test_plo5_post_gto_river test_plo5_post_gto_river_native
    Ran 30 tests in 0.983s
    OK
Earlier 27 tests in 1.109s before chance module. Compileall passed on recovered subset before chance module, which was imported and tested in final suite. Tkinter smoke via Xvfb created window 720x610 titled PLO Trainee — Rake / River offline, then closed. GUI service solve_file tested with real temporary context JSON and cache. No manual click-through or Windows test.
Independent pure-plan oracle 16 x 4 strategies of nine-node polar fixture at 500 iterations: rates 0, 5000, 10000 bps with varied caps and fold rules (8 combinations); EVs and both best responses agree within nine decimal places. At zero rake, compare old solver policy/EV within eight decimal places. At 1000 iterations polar zero-rake values [1.0000695829567539, 0.9999304170432464] BB; 50% rake cap 3, no fold rake, values [0.4999990009998327, 9.990006663018747e-07], expected rake 1.499999999999501 BB. Deliberately extreme synthetic fee to test effect, not a room fee. Test confirms frequency changes.
Turn chance: 38 cards for each compatible physical pair; exact conditional probabilities sum to one and reconstruct prior; excludes all 14 known cards. Limit 4096 pairs x 38 = 155648 outcomes, not benchmarked at maximum. Root prior only, no action-reach update or strategic turn infosets yet.

## Usage
    python video_analyzer/plo5_rake_gui.py
Input is a valid existing post-gto-context-v1 HU river context JSON. Set profile manually, cap zero means zero rake, fold checkbox. Rake cap must be exactly representable in chips, no silent rounding. Model rake floors to integer chip; fractional tied awards, odd-chip rule pending. Profiles/river cache stored under ~/.plo_trainee. No real room rates presumed.
The existing primary video launcher and video pipeline are not wired to this GUI yet. Rake-aware strategy runs in Python; existing C++ zero-rake backend preserved. Variable-sum CFR+ is heuristic; NashConv measured, not universal Nash convergence or profit guarantee.

## Pending
Macro02: C++ separate-utility kernel, broader rake oracle and performance, room rules, main launcher and review integration, cache concurrency, canonical context, cross-street reach. Macro03: joint turn/river game tree with per-deal chance and reach, infosets only observing public card when dealt, all-in exact terminal, independent BR and leakage tests. Prior full regression, Windows and video backlog remain.
