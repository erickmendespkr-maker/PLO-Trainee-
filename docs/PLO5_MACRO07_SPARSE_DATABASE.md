# Macro07 — Sparse mathematical and strategic database
Base 3b946cbf3551e6a1d1af80469ce491c29e8dd281. Offline PLO5, branch feature/plo5-plo6-training. Main not modified by this cycle. Direct git ls-remote failed DNS exit 128. Local recovered subset /mnt/data/plo5_05b; not full checkout. Original canonical index header 8c7c193b7b32b956f6d2a69ea9f76c49b0d26fdd, generator 3668afd0158edcf7c6187427ff6cd505af000ba4 and root-level plo5_rank_lookup.py b7ddcd4c94b794641c0debefd7e18299be3555f0 recovered and git hash-object matched.

## Delivered
- a6912ff0de66e9fec9de7c9be37ca620c183e37f: C++ bounded rank/unrank batch protocol, size and round-trip audit.
- c9e6fafe009fbfe68774ed9f393b97ec374691f9, 9d2787af036bd24a158f4d385f4188f9dc9342db: Python integration, cards-to-index and index-to-canonical-cards, tests of 24 global suit permutations, unordered flop, ordered turn/river, boundaries and invalid inputs.
- 376e056366ed57cd646ea58a8b78c3e0476004b6, 77b6aea295a2d3dd0edd652261aceba6414dac46: sparse SQLite lossless zlib result store for multiway solver. Full physical game identity including ranges/joint prior, rake, sizings, engine version; key includes iterations, backend, executable and source hashes, Python version, optional deal values and resource budgets. Compressed BLOB, raw checksum, bounded decompression, reject malformed/truncated/oversized data. No silent calculation of unmodeled histories. Trusted local DB only, checksum not authentication. SQLite/Python orchestration, native C++ training optional. Cache hits decode whole compressed artifact; no direct indexed policy-row storage yet.
- 52a5949670eadaabadecb0863cd327899f3125ad, b07d305d3d41b8dc4a525295f57c6430ec268d49, a0525512b36cb61efc6cef760a49609eba3d6010: native rank batch reuses original RankTable; service resolves cards to canonical IDs, queries existing mmap shard reader, deduplicates same-batch misses and optionally computes exact rank natively. UNSTORED distinct from SHARD and NATIVE_COMPUTED. No implicit write-back; not equity or policy.

All eight new code blobs compared against actual local files:
223eb7e4949140b23e59cee43b25831d8b6ff7b4 native/plo5_index_batch.cpp
1343530f3c047e839c8e7d4cba83815cde68575f plo5_index_native.py
27e8d173cd9cb63349bf180b976101980513e38c test_plo5_index_native.py
fa83a4bb49b33a50ae858eb55a8421049b108c01 plo5_strategy_cache.py
59ff76414ec414f833b6e6e53e71e8ee377791b4 test_plo5_strategy_cache.py
ff20bb0d554447c7a05d6188da489b84b2506ba9 native/plo5_rank_batch.cpp
a13c27a07bcb15e01885300b5909ec392152ae8e plo5_rank_service.py
942ee9086793ea37fbeb69d8d0f79374d835ea67 test_plo5_rank_service.py

## Actual execution evidence
    g++ -O3 -std=c++17 -Wall -Wextra -Werror native/plo5_index_batch.cpp -o native/index_batch
    g++ -O3 -std=c++17 native/plo5_rank_shard.cpp -o native/rank_shard
    native/rank_shard test
    PASS: 2598960 five-card category census; 7462 rank levels; 30000 roundtrips and suit swaps; exact-two/exact-three check
    g++ -O3 -std=c++17 -Wall -Wextra -Werror native/plo5_rank_batch.cpp -o native/rank_batch
    for s in 0 3 4 5; do echo "$s audit 100000" | /usr/bin/time -f 'wall=%e RSS_KiB=%M' native/index_batch; done

| board cards | state count | sampled round trips | wall s | peak KiB |
|---:|---:|---:|---:|---:|
|0|134459|100000|0.04|2048|
|3|1800975787|100000|0.06|2560|
|4|78124329712|100000|0.07|3840|
|5|3337988096872|100000|0.10|8576|

400000 sampled operations, not exhaustive bijection proof. Count is implicit single-holding state space; no all-state table or strategy certification.
Generated three immutable real P5RANK01 shards (100000 ranks each, start=1000000) using native/rank_shard generate STREET 1000000 100000 rank_macro07/streetSTREET.bin. Each 200040 bytes. Generator internal timings 0.035705/0.0887625/0.1428165 s (excludes initialization), actual reported river 0.142816 s. Root reader build_catalog validated FNV, rank bounds, SHA-256; mmap LRU cap two in tests. Local fixtures not committed as binaries. 606 independent ordinal comparisons against existing Python _five (all 7462 signatures enumerated independently, Omaha exact-two/three), plus 609 rank-service comparisons with native direct calculation (606 shard hits, 3 misses). All passed.

From video_analyzer:
    PYTHONPATH=.. PLO5_CFR_EXE=../native/cli PLO5_MULTISTREET_EXE=../native/multistreet PLO5_MULTIWAY_EXE=../native/multiway PLO5_INDEX_EXE=../native/index_batch PLO5_RANK_EXE=../native/rank_batch PLO5_RANK_CATALOG=../rank_macro07/rank_catalog.json python -W error::ResourceWarning -m unittest discover -q
    Ran 87 tests in 23.321s
    OK
    python -m compileall -q .
    exit 0
77 previous + 10 new test methods, all relevant native env vars supplied. No full repository regression.

## Cache benchmark
Synthetic river fixture(6,2), 385 nodes, 64 legal private deals, 100 iterations, native multiway, include_deal_values=True, rake_on_fold=False. One cache miss 0.371819254 s incl solve/write; one hit 0.013571356 s incl read/hash/decode. Raw JSON 222728 bytes, zlib 15687 bytes, SQLite 28672 bytes. Exact round-trip and separate backend identity tested. Single sequential measurement, not general storage ratio or Windows performance.

## Remaining and next
Macro07 partial: generator resume/queue, automatic persistence of computed sparse misses, canonical joint/context suit remapping with proof, equity and runout caches, CSV provenance/license, migration and concurrent cache management, direct policy index/eviction, persistent native evaluator and solver hot-path integration, broader performance/RAM, full repo/Windows. Prior solver and review/video backlogs preserved. Do not conflate 3.42 trillion canonical addresses with stored ranks or solved strategies. Macro08 may begin independently (visual signatures and ROI cache) after reading existing pipeline; real-video development and holdout validation still needed. No new video work in this cycle.
