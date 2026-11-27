# Macro10 continuation — Session reports and batched native rank
Base a9adb69ad2022138697a3f1890654d80ad534aec (existing Macro10 integration). Branch feature/plo5-plo6-training only. No main writes. Recovered Linux subset, not full checkout.
Existing local review, report, CLI and test blobs matched previously published hashes. New files committed and reread:
- 7a0c3bc99e32ab154e5e3105fc6a2093d1d92107 — plo5_review_session.py (1d4446fdd76bc0d065e1e64b125d781fc7c0dd2d). Visual report selects before/after evidence per display change, crops only the relevant fixed table slot, verifies source MP4 SHA-256 when supplied and referenced PNG hashes, caches crop encoding, includes expandable detail and explicit evidence-only status. Declared decision batch (max 64), existing model cache and native ranks grouped by street, positive/negative/near-zero/unavailable EV and gross pot odds, alternative model actions, NashConv and provenance. No new authorization of unverified video hands. All generated HTML standalone, no remote assets.
- f5b4e2490d0fc87e6a086877989366296348cc68 — test_plo5_review_session.py (58aa942ff409fab58714e8cbc6c9715e7404f701). Four tests: crop geometry/path and hashes; source hash tampering; model cache, duplicate IDs and escaped markup; rank grouping and parity.
New tests 4/4 in 0.372s. Final run from recovered video_analyzer:
    PYTHONPATH=.. PLO5_CFR_EXE=../native/cli PLO5_MULTISTREET_EXE=../native/multistreet PLO5_MULTIWAY_EXE=../native/multiway PLO5_INDEX_EXE=../native/index_batch PLO5_RANK_EXE=../native/rank_batch PLO5_RANK_CATALOG=../rank_macro07/rank_catalog.json python -W error::ResourceWarning -m unittest discover -q
    Ran 128 tests in 25.931s
    OK
    python -m compileall -q . exit 0

## Real evidence reports
Existing Macro09 manifests and private PNGs reused; rehashed both MP4 files and all referenced PNGs. No new extraction or independent OCR truth validation. Parte01: 9 unresolved display changes, 17 unique table crops, 5520074 bytes. Parte06: 4 unresolved changes, 8 unique crops, 2543204 bytes. Reports in local user workspace, not committed. No real-video EV or financial outcomes certified.
Synthetic model report: 2 declared decisions (call and fold), same river context, 5000 iterations, native multiway, index/rank backend; 1 cache hit. Output 3087 bytes. Not a real recorded hand.
CLI:
    python video_analyzer/plo5_review_session.py visual MANIFEST.json NEW.html --video ORIGINAL.mp4
    python video_analyzer/plo5_review_session.py models BATCH.json NEW.html --cache CACHE.sqlite --native PATH --index PATH --rank PATH
BATCH.json contains decisions list of objects with id, context, history, holding, action, rake_on_fold and optional iterations/pot_bps/joint. Declared inputs only.

## Batch performance
Eight repeated polar river decisions, 100 iterations, same warmed SQLite strategy cache, native index/rank and multiway binaries. Three alternating sequential trials, result dictionaries exactly equal for each pair.
Individual seconds: 1.681633141, 1.621114965, 1.567338821; median 1.621114965.
Batch seconds: 0.201640186, 0.199467652, 0.192853635; median 0.199467652.
8.127x on this repeated fixture. Reduces rank service initialization by grouping queries by street. This does not measure full video processing or wide range solving; model cache still loaded per decision. Full-session performance target not established.

## Remaining
Preserve all Macro09/10 backlogs: automatic hand reconstruction and independent card/position/action verification, complete all-seat snapshot and actual showdown/rebuy reconciliation, merge parallel action-recovery APIs, import DriveHUD history, complete strategic coverage/provenance, full regression, Windows. New visual report uses fixed 1504x696 slots only; size/batch budgets reject excessive input and need session splitting. Macro11 can proceed with persistent native service, indexed cache rows, profiler and end-to-end real video benchmarks. Prior DNS blocker not retested. No GTO/profit certification.