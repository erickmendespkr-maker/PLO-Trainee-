# Macro10 — Offline PLO5 review integration
Base d9b15a91e1d7e2cfadc0abe4ef3fa5d56c602e55. Branch feature/plo5-plo6-training only, no main modification. Recovered Linux subset /mnt/data/plo5_05b, not complete checkout. Prior DNS issue not retested.

## Delivered
- bbbdf8ce0a6562dcd3a69f5a66f5c32c6baf57ee: review adapter for declared postflop decision prefix, legal actor/actions, modeled holding, gross immediate pot odds, exact discrete-policy lookup, EV of chosen action and difference vs best modeled action, model metadata and cache provenance. Optional native index/rank service. Uses existing multiway solver and strategy cache. No interpolation of unmodeled bet sizes, no invented EV on missing policy/reach. Preflop history classification and policy extraction; preflop-to-flop bridge with joint posterior and approximation audit. Preflop training prior provenance remains unverified. No independent preflop EV guarantee. Declared replay and settlement reconciliation separated from strategic EV. Candidate visual manifests produce evidence-only reports.
- 2d7fc44965b37f6e0b413adb5e707cedc95dc467: Portuguese standalone HTML with summary, expandable diagnostics, action table and optional embedded PNGs; escaped text, no remote assets/scripts, SHA256 integrity check against frame manifest, bounded files, no overwrite. Image hash matching is not proof of video origin or correctness. Gross pot odds do not account for side pots, rake or future payments.
- 641e1ae4c418ecf550587f25a455f912394accd2: six integration tests.
- 5c47e2fdf525c798ae01fd3cb87dd6a635cc9530: CLI, modes visual/postflop/preflop/bridge/settlement. Native executable paths explicit CLI options, not input JSON. Only visual and postflop CLI paths separately smoke tested; other service methods tested.

All four remote blobs equal local executed files:
78969bb656c107bd8948a652b337fc1cc72faf7b plo5_review.py
1a0d757a889358787304a16b6886d6c1fb33819b plo5_review_html.py
aaf9152da1afb6b4758345b1fd1fb2ec270dda44 test_plo5_review.py
acd1fd7b20dc37c3dc2effb6f007e9a681617b1a plo5_review_cli.py

## Local execution
Existing six dependency blobs checked against GitHub HEAD: strategy_cache, post_gto_multiway, pre_policy_bridge, rank_service, reconstruction_candidates, action_recovery. Run from recovered video_analyzer:
    PYTHONPATH=.. PLO5_CFR_EXE=../native/cli PLO5_MULTISTREET_EXE=../native/multistreet PLO5_MULTIWAY_EXE=../native/multiway PLO5_INDEX_EXE=../native/index_batch PLO5_RANK_EXE=../native/rank_batch PLO5_RANK_CATALOG=../rank_macro07/rank_catalog.json python -W error::ResourceWarning -m unittest discover -q
    Ran 124 tests in 23.835s
    OK
Six new tests passed individually in 1.857s. Local subset includes two additional existing action_recovery tests not authored here; do not report eight new tests. compileall succeeded, then new CLI py_compile and two smoke commands succeeded.

CLI:
    python video_analyzer/plo5_review_cli.py visual MANIFEST.json NEW_REPORT.html --screens 2
    python video_analyzer/plo5_review_cli.py postflop MODEL.json NEW_REPORT.html --cache cache.sqlite --native PATH_TO_MULTIWAY_BINARY --index PATH_TO_INDEX_BINARY --rank PATH_TO_RANK_BINARY
Model JSON keys context, history (public prefix only), holding, action (name, incremental chips), rake_on_fold; optional iterations, pot_bps, joint. Bridge mode requires context, policy, flop, history, holding, action; optional iterations, pot_bps, approximate_joint. No native paths supplied in JSON.

## Real recordings
Reused exactly 20 existing source-PTS sampled PNGs per recording from Macro09. Rehashed both original MP4s and all 40 PNGs; hashes matched prior manifests. Reexecuted MixedReader/Tesseract on each frame and asserted equality of platform/field/value against earlier observations. This is a repeatability check, not independent accuracy. No new frame extraction and no training on Parte06.
- Parte01: 80 slots, 9 unresolved display changes; 2.336884s recognition + evidence collection (excludes original decode). HTML with two PNGs, 2886736 bytes.
- Parte06: 80 slots, 4 unresolved display changes; 1.272030s recognition + evidence collection (excludes original decode). HTML with two PNGs, 2450352 bytes.
Private media/report files not committed. No reconstructed verified real hands, no real-video EV emitted.
Synthetic polar river fixture, native 5000 iterations, 2 private deals, BTN call 2 BB into 4 BB, gross pot odds 1/3, model EV +0.007263639960555172 BB, fold EV 0, gap 0 to best modeled action, NashConv 0.005482399819266348 BB. Rank 7460, canonical index 3110965515717, native computed. Full review including optional rank 0.245661s first, 0.251130s cached, so cache does not accelerate this tiny case; rank subprocess initialization likely dominates, not separately profiled. One measurement each. Example HTML generated locally, not actual video hand.

## Pending
Macro10 partial: automatic evidence-to-verified-decision bridge, all-seat actions and stack histories, positions and showdown/rebuy confirmation, real calibrated card banks, full preflop equilibrium/provenance, broader solver quality and sizing coverage, robust batch review, DriveHUD history integration, UI integration, Windows and full repository regression. No false strategic labels for incomplete real hands. Macro11 prioritize profiling persistent native rank service, batching, cache lookup, video OCR/recognition bottlenecks, realistic session timings/RSS on target hardware; retain all prior backlog. Target 5–10 min per 1h video not demonstrated.
