# Macro11 — Persistent native rank and audited RGB stream
Base 24340bc477fcc5d2cf717b1a6635fd3abb52d63f. Offline post-session PLO5 only. Branch feature/plo5-plo6-training, no main writes. Local recovered subset /mnt/data/plo5_05b. Prior DNS blocker not retested.
## Delivered
- 0a239872046862e3e60439a556f679e70c7fc7f9: C++ rank worker, lazy one RankTable and per-street canonical index, up to 4096 states/request, exact cards-to-index and Omaha rank, response flush per request.
- 203b7a83a139956924ceddeeba7aa9f257f51685, 0c117fd7be17cfcb8ace8c4b30e7f9a24b2527e8: Python context-managed worker, bounded input/output, deduplicate identical batch rows, serialized pipe exchange, timeout/failure kills and closes worker; 4 tests including 265 row comparisons (five 53-row batches, boundaries/duplicates) to legacy native index/rank, dead process, malformed input, timeout and model report parity. Initial killed-worker regression showed unclosed stdout because stdin close raised BrokenPipe; corrected with finally and reran.
- 83d98b3aba9ba0835122d95daab3501485ddc8ab: opt-in --persistent-rank executable for review-session models mode, or RankWorker passed to review_batch across batches. Legacy shard/index/rank backend remains, mutually exclusive with persistent worker. CFR training is still separate subprocess, not persistent; worker currently computes rank rather than using shards.
- 20bdf2722c878a460cb70d87135e7860d3996989, 1bf267e15bfde42e52400dc80a706e46c8382ec1: bounded FFmpeg RGB direct scan (2–120s windows, fixed 1504x696 geometry, default 2 OCR workers, 1 decode thread, source hashes before/after, source PTS roster audited through ffprobe/showinfo). Reuse MixedReader and reconstruction candidate collector. No intermediate PNG; sample_*.rgb names are logical IDs, not files. No verified actions or EV. Two tests synthetic black MP4/PTS and invalid window. No CLI/launcher routing yet.
## Verification
Remote blobs matched tested local files:
 a3e130d9c942c06cba71a1193e9e804a36ceaf98 native/plo5_rank_worker.cpp
 8fb16d6b985875f9ffa9b5353a76959dae22deb0 plo5_rank_worker.py
 b272505eb647af1e4614547c71bb65b3a3b493cc test_plo5_rank_worker.py
 15d3debfe0ad50d1fd79c7c7eb8d67eab318c349 plo5_review_session.py
 4f44ec0212734e5c11ab20ed110b55ecde5a4d88 plo5_video_stream.py
 0768e77d64ab47c2853f22e0c2bb39bcab1a45ee test_plo5_video_stream.py
Build g++ -O3 -std=c++17 -Wall -Wextra -Werror native/plo5_rank_worker.cpp -o native/rank_worker passed.
From recovered video_analyzer:
 PYTHONPATH=.. PLO5_CFR_EXE=../native/cli PLO5_MULTISTREET_EXE=../native/multistreet PLO5_MULTIWAY_EXE=../native/multiway PLO5_INDEX_EXE=../native/index_batch PLO5_RANK_EXE=../native/rank_batch PLO5_RANK_CATALOG=../rank_macro07/rank_catalog.json PLO5_RANK_WORKER_EXE=../native/rank_worker python -W error::ResourceWarning -m unittest discover -q
 Ran 134 tests in 26.946s
 OK
 python -m compileall -q . exit 0
128 previous + 6 new test methods. No full repository or Windows test.
## Benchmarks
Nine single-state queries (flop/turn/river repeated 3x), same holding and board prefixes; three sequential trials comparing old two-subprocess service (1.878597,1.602578,1.605127 s), worker cold including launch (0.176018,0.191868,0.206302 s), then same warmed worker (0.000546,0.000519,0.000412 s). Exact equal results all trials. Medians 1.605127,0.191868,0.000518944 s respectively. 8.37x cold speedup; warm microbenchmark isolates rank/index IPC, not solver or session. Linux /proc VmHWM 27904 KiB; resident ~27252–27256 KiB after all three street indexes initialized. Not aggregate memory or Windows measurement.
Real videos Parte01 [1510,1530) and Parte06 [600,620): fresh FFmpeg extraction PNG baseline with source hashes, ffprobe roster, original extraction settings and same MixedReader 2 workers; independently direct RGB scan. 20 frames each. All 40 exact PTS, RGB SHA-256, and recognition observation dictionaries identical; PNG hashes matched previous Macro09 manifests. Evidence collector counts 9 and 4 unresolved display changes, no certified hand. Sequential single run each, no new labeled accuracy reference. Parte01 PNG pipeline 4.6245144 s, RGB 3.0786431 s, 21736210 PNG bytes avoided; Parte06 PNG 2.9996346 s, RGB 1.9316702 s, 19231227 bytes avoided. Baseline rechecks prior PNG hashes, stream computes RGB hashes; evidence artifact requirements differ. No new private media committed. Not a full-session benchmark.
## Remaining and Macro12
Priority: selective PTS-bound screenshot extraction from stream result and integration into existing report; CLI/window orchestration and per-session source hashing/cache reuse, complete visual card/seat/action calibration, all-seat snapshots and hand verification, DriveHUD import, consolidation of duplicate recovery APIs, persistent solver/cache hot-path, total memory/profile and 1h real-session benchmark on target Windows hardware. No actual real hand reconstruction verified. Main launcher and installer not validated. Macro12 can start packaging/build smoke and integration tests while preserving these blockers. No claim of full MVP, GTO certification or 5–10 minutes/hour target achieved.
