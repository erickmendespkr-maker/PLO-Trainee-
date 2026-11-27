# Macro09 — Offline hand reconstruction foundations
Base 33a39926ff31abc7729b60f90e5bb4099b492781. PLO5 exclusively, feature/plo5-plo6-training. Main not modified by this cycle. No live assistance or private media published.
Recovered Linux subset in /mnt/data/plo5_05b; not a full checkout. Prior DNS blocker not re-tested.

## Delivered
- 143df932fc516dc95408b9ee4b29be57e846310e, e827463f4fe61c6de40843e720e8871158007279: plo5_reconstruct_ledger.py and five tests. Full declared incremental-payment history replay through existing preflop and postflop legal trees; standard blinds; preserve contributions across streets, folds and side pots; validate public/private card conflicts and complete showdown; use existing exact-two/exact-three evaluator and multiway settlement; compare independent declared awards, refunds, rake, stacks before and after separately declared rebuy. Reconciliation does not certify evidence. Fractional chips and proportional rake allocation remain model assumptions. Unsupported room rules, short posted blinds, antes/straddles, odd-chip rounding, cash-out or external transfers require additional modeling. Initial test exposed HU postflop actor order; fixed to BB then SB and reran all five.
- 10e7b9e5a2987ed0fdc6111ed633c38ebbcad1fb, fb60922668cc11ddfdcd9a343634a7bd8e0c5b32: plo5_reconstruction_candidates.py and four tests. Adapter for existing mixed-review manifest; preserve full fixed four-slot roster, exact decimal values, chronological continuity and optional card candidates; split on source gaps, layout/profile changes, card resets and uncertainty. Display deltas are explicitly unresolved, no inferred payout/rebuy/net. CLI: python video_analyzer/plo5_reconstruction_candidates.py MANIFEST.json NEW_OUTPUT.json. Source and manifest hashes included; input is a local candidate report, not authenticated proof of pixels. CLI executed on both real-window manifests produced this cycle.
- 5e852fd8fecd0a7f9c415185612f7878ee77d50f, 48b21a70eb7d876ce78a193ce12dc69c01f36c5a: plo5_action_reconstruct.py and four tests. Bounded same-street search through legal integer action payments, using complete declared stack roster and matching pot; optional actor and active roster constraints. Distinguish ambiguous, budget exhausted, no path within step limit and unique within step limit. Does not enumerate across chance, settlement, rebuy or other external changes; not integrated into automatic video action extraction; unique within limit is not proof of actual actions. Defaults 4 actions and 2000 states, caps 8/100000.

All six remote blobs confirmed equal to executed local files:
 11b94b46278d2d3942dfa4d10c21a0eeb3550e97 plo5_reconstruct_ledger.py
 e084a8177d635a914703e0eaf9e74979b7a49454 test_plo5_reconstruct_ledger.py
 ed657b932d6526ffb4d62dbd41aadc3f584ab65f plo5_reconstruction_candidates.py
 0596aacf558c41bba95f6a3d6134902647a1b627 test_plo5_reconstruction_candidates.py
 2d2fc709ea9ccc492e5d8624e5e084b69e09b657 plo5_action_reconstruct.py
 6c30a6c64edc122b3851f32573393b6ed9e55bef test_plo5_action_reconstruct.py

## Actual local execution
From /mnt/data/plo5_05b/video_analyzer:
    PYTHONPATH=.. PLO5_CFR_EXE=../native/cli PLO5_MULTISTREET_EXE=../native/multistreet PLO5_MULTIWAY_EXE=../native/multiway PLO5_INDEX_EXE=../native/index_batch PLO5_RANK_EXE=../native/rank_batch PLO5_RANK_CATALOG=../rank_macro07/rank_catalog.json python -W error::ResourceWarning -m unittest discover -q
    Ran 116 tests in 22.332s
    OK
    python -m compileall -q .
    exit 0
13 new test methods in this cycle (5+4+4). Discovered local subset differs from previously reported 98-method subset; do not imply 18 newly authored methods or full repository regression.

## Real recordings
Private Poker_Parte_01.mp4 (167993622 bytes, SHA256 c9aad5102a54941b8cb5f4bbc20eca45fc757ff96fd95de173c0ac0d95ac19eb) and Poker_Parte_06.mp4 (93777358 bytes, SHA256 fef7af4d59388f254f3c72efbf0a9127acacc42e9115c4d198a7277b18ae46a2), both 1504x696. Part 06 fetched from designated Drive folder in this cycle for evaluation only, no template training.
Used FFmpeg select first source frame per second, copyts and showinfo; each selected integer PTS independently matched ffprobe timestamp list and expected sampled-second roster. No independent pixel re-extraction, no full video processing. Original detect compared against MixedReader for all 160 fixed table slots, exact parity. Existing Tesseract used for pot/hero-stack reading, no manual codebook.

| recording/window | frames | active slots | non-null money candidates | display changes | extraction s | recognition s |
|---|---:|---:|---:|---:|---:|---:|
| 01 1510–1530 s |20|80|154|9|1.339227|2.388218|
| 06 600–620 s |20|57|114|4|1.121833|1.279639|

No missing sampled seconds. Layout cache hits/misses: 48/32 and 66/14. Money cache hits/misses: 117/43 and 98/16. All 13 changes concerned displayed pots, zero stack rises/drops detected in these two windows. This is not evidence of no actual stack movements. No card banks or all-seat action/stack evidence in these real tests; no complete hands reconstructed, no confirmed positions, no inferred legal sequences from these recordings, zero verified financial results. Part 06 remains independent of training; comparison to previous detector is not independent human ground truth or recognition accuracy. Single timings, not whole-session performance.

## Pending / next
Macro09 partial. Need recover complete recognition pipeline and calibrated card banks, board highlight treatment, all-seat stacks/bets/action labels and dealer, exact starting/ending snapshots, independent reference labels, finer temporal sampling, per-hand action-evidence binding and automated reconciliation; preserve unknowns and distinguish award/return/rebuy. Do not promote legal synthetic replay to video-hand verification. No full-session 5–10 min/hour claim. Continue Macro10 strategic review integration only for explicitly declared or independently validated histories, retaining solver limitations, provenance and no automatic EV for ambiguous events. Preserve all earlier database/solver/video/Windows/full checkout backlogs.
