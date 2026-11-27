# Macro01 follow-up / Macro02 foundations — 2026-11-27
Base a275783613f24e606d098aeb44338e6f0169ec02. Branch feature/plo5-plo6-training, main untouched. Offline PLO5 only.

## Macro01
Local recovered source blobs match previous confirmed repository versions. git ls-remote still fails DNS, exit 128; full checkout/regression unavailable. Python 3.13.5, GCC 14.2.0, Linux. Original 12 Python methods passed again. Extended tests: random.Random(27112026), deck rank order 23456789TJQKA and suit order cdhs excluding BOARD fixture from test_plo5_post_gto_river, shuffle deck, split at 23. For each pool sample n unique five-card combinations from list(itertools.combinations(pool,5)); assign weights i+1. context(a,b) default pot/stacks 2, BB 1, pot_bps=(), 100 iterations, 9 nodes. Pools disjoint deliberately to exercise full pair budget, not representative of real ranges. Separate process per measurement, wall time of solve only; resource.ru_maxrss includes setup and process history; parent peak not concurrent total.

| n per seat | legal pairs | Python seconds | native seconds | Python parent peak KiB | native parent peak KiB | gap BB |
|---:|---:|---:|---:|---:|---:|---:|
|32|1024|0.666826757|0.076257364|100244|100108|0.029519640705540695|
|64|4096|2.397657775|0.162081693|100328|100644|0.023246995281492655|

Compared all 128/256 policy rows, frequencies, EVs, reach masses; max absolute difference 0.0 in both cases. Values identical: 1.247304791539699 / 1.3213382333667876 BB respectively. These are finite-iteration approximations; gap not zero. RSS includes fixture generation, not isolated native allocation. No target Windows measurement.

## Macro02 delivered
- 5848b2bda1df96ee1138c8e93aa9cec434a79385: SQLite sparse cache with full public history, action lookup, versions and source/executable SHA-256; budgets, checksum and invalidation. Physical context, not canonical suit equivalence; cache local trusted data (checksum detects accidental damage, not malicious alteration). Supports Python/native zero-rake river.
- 9594ee2136b4602547cb1fa68048b1ffdba956fb: joint range posterior on exact action path, disjoint physical holdings, known holdings at observation time only, exact decimal-rational model frequencies, missing/zero status; exact bounded integer conversion of marginal input, never silently approximate. Not a multiway or cross-street inference engine.
- dc770624ab1cbb9b785cd7a4de5fd4222c8f3ce5: exact HU terminal rake ledger; contested pot after returning uncalled excess, optional fold rake, cap and integer-chip floor; fractional split (odd-chip allocation pending); zero cap explicitly zero rake. Room-specific rules not verified. This is NOT a rake-aware CFR implementation; zero-rake solver remains unchanged.
- 1270cfaac45977fe9c0c1c4ec1fc69a1db5b4c74: 10 new test methods, including native cache separation, corruption, history, budget, blockers, two-action conditioning and exact ledger. Initial test leaked a SQLite connection (ResourceWarning); fixed test with closing context manager. Final command in recovered video_analyzer directory:
    PLO5_CFR_EXE=../native/cli python -W error::ResourceWarning -m unittest -q test_plo5_post_gto_macro02 test_plo5_post_gto_river test_plo5_post_gto_river_native
    Ran 22 tests in 0.857s
    OK
Compileall on recovered subset succeeded. All four newly published file blob hashes verified against local executed files:
    b93b2c9d7200863dfd75642dd1b6891d9fa570ff plo5_post_gto_store.py
    f758f3be4ad70793d6f2bfb90ddba967c22d1a03 plo5_post_gto_joint_ranges.py
    edd9ecdf018f8a3e5c70f55e61d1c008ac5f5c4c plo5_post_gto_rake.py
    ff222e1d0b68a09f40e0e1ca488adc9757e630c3 test_plo5_post_gto_macro02.py

## Remaining
Macro01 full checkout/regression and Windows still pending. Macro02 next: implement independent two-player utility updates for rake-variable-sum game, unilateral best responses/NashConv (no generic Nash guarantee), oracle and zero-rake regression; then expand cache/lookup, canonical model keys, review integration, resource and concurrency tests; ensure no future card leakage. Keep video and preflop backlogs. Do not promote this to complete river solver or MVP.
